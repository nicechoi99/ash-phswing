"""Equipment sizing and bare-module capital at the design point.

Reactors, mixers, CO2 disengagement drums, centrifuges, pumps, the Stage V carbonator, CO2 blower, PCC centrifuge,
product dryers and storage are sized from the Aspen stream and block results and costed with the Seider correlations
(ash_phswing.equipment).  The MVR brine concentrator is costed with the USBR Report 149 benchmark (six-tenths rule);
the Seider evaporator / compressor correlations only split that total between the two items and give the compressor
power.  The chlor-alkali plant is NOT part of the bare-module sum: it enters the TDC as $/(t Cl2/yr) x installed Cl2
capacity (ash_phswing.cashflow).
"""
import math

from . import equipment as EQ
from .flowsheet import stream_value, component

MW_NA, MW_CL, MW_NAOH, MW_H2O = 22.990, 35.453, 39.997, 18.015
MW_CO2, MW_CAOH2, MW_CACO3 = 44.01, 74.093, 100.087
F_FARADAY = 96485.0

# Seider Table 16.26 material factors by service: Stage I acid (SS316 as the proxy for rubber-lined CS),
# Stages II-III alkaline chloride brine (SS316); every other vessel defaults to design.vessel_fm.
MAT_VESSEL = {'B2': 2.1, 'B1': 2.1, 'B4': 2.1, 'B3': 2.1, 'B13': 2.1, 'B7': 2.1, 'B17': 2.1, 'B14': 2.1, 'B11': 2.1}
VESSEL_FM_DEFAULT = 2.1
# blocks inside the chlor-alkali battery limit (priced with the chlor-alkali plant)
IN_CHLOR_ALKALI = {'B5', 'B9', 'B10', 'B15', 'B16', 'B18', 'B20', 'B22'}
# pumped streams and pump material factor (Hastelloy C 2.95 in acid service, SS 2.0 otherwise)
PUMPED = [('HCL', 2.95), ('1MIX', 2.95), ('1OUT2', 2.95), ('1OUT3', 2.95),
          ('NAOH1', 2.0), ('NAOH2', 2.0), ('2MIX', 2.0), ('2OUT2', 2.0), ('2OUT3', 2.0),
          ('3MIX', 2.0), ('S9', 2.0), ('3OUT3', 2.0)]


def _find(conn, port):
    for s, p in conn.items():
        if p == port:
            return s
    return None


def _p_sat_bar(T_C):
    """Antoine equation for water (bar)."""
    TK = T_C + 273.15
    return 10 ** (4.6543 - 1435.264 / (TK - 64.848))


def estimate(pd_, T, el, prep, mvr_usd_per_tph):
    """Adds CapitalCost, ElectrolysisCAPEX, BrineConcentration, CarbonatorDesign, V2_power_kW and
    V2_dryer_water_kg_hr to the processData dictionary pd_.

    T: tea parameter table; el: electrolysis parameters of the case; prep: brine-loop sizing (ash_phswing.tea)."""
    units = pd_['Units'].copy()
    if 'Size' not in units.columns:
        units['Size'] = 0.0
    op_hr = T['plant.operating_hours']
    rho = T['design.slurry_density']
    vmax = T['design.vessel_max_m3']
    CC = {k: [] for k in ('reactor', 'mixer', 'flash2', 'separation', 'evaporator',
                          'pumps', 'co2_blower', 'stage5', 'storage')}
    kw = {'agitators': 0.0, 'pumps': 0.0, 'mvr': 0.0, 'co2_blower': 0.0, 'centrifuges': 0.0}

    for i in range(len(units)):
        ut, nm = units.at[i, 'TYPE'], units.at[i, 'NAME']
        conn = units.at[i, 'CONNECTION'] if isinstance(units.at[i, 'CONNECTION'], dict) else {}
        if nm in IN_CHLOR_ALKALI:
            continue
        fm_v = MAT_VESSEL.get(nm, VESSEL_FM_DEFAULT)
        if ut in ('RGibbs', 'Mixer'):
            out = _find(conn, 'P(OUT)') or _find(conn, 'M(OUT)')
            flow = ((stream_value(pd_, out, 'MASSFLOW_MIXED') or 0)
                    + (stream_value(pd_, out, 'MASSFLOW_CISOLID') or 0)) if out else 0
            tau = T['design.tau_reactor_min'] if ut == 'RGibbs' else T['design.tau_mixer_min']
            hp = T['design.hp_per_kgal_suspension'] if ut == 'RGibbs' else T['design.hp_per_kgal_blend']
            vol = flow / 3600 * tau * 60 / rho
            cost, n, p = EQ.agitated_tank_bm(vol, hp, fm_v, vmax)
            kw['agitators'] += p
            units.at[i, 'Size'] = vol
            CC['reactor' if ut == 'RGibbs' else 'mixer'].append(cost)
        elif ut == 'Flash2':
            cost = 0.0
            st = _find(conn, 'L(OUT)')
            if st:                     # CO2 disengagement drum: 5 min liquid hold-up at half full
                LF = (stream_value(pd_, st, 'MASSFLOW_MIXED') or 0)
                LD = (stream_value(pd_, st, 'DENSITY') or 1) * 1000
                if LF > 1e-6:
                    vol = LF / LD * 5 / 60 * 2
                    cpv, _, _ = EQ.vessel_vertical(vol, 1.01)
                    cost = EQ.bare_module(cpv, EQ.FBM['vessel'], fm=fm_v)
                    units.at[i, 'Size'] = vol
            CC['flash2'].append(cost)
        elif ut == 'Filter':
            s_out = _find(conn, 'S(OUT)')
            f_in = _find(conn, 'F(IN)')
            solids = 0.0
            if s_out:
                solids = (stream_value(pd_, s_out, 'MASSFLOW_TOTAL') or 0) - component(pd_, s_out, 'WATER')
            cost, n = EQ.centrifuge_bm(solids)
            q_in = (stream_value(pd_, f_in, 'VOLFLOW') or 0) * 60 / 1000 if f_in else 0
            kw['centrifuges'] += q_in * T['design.centrifuge_kwh_per_m3']
            units.at[i, 'Size'] = 0.0
            CC['separation'].append(cost)

    # ---------------- chlor-alkali cells (sized to the NaOH need; capital in cashflow.capital)
    ce = el['current_efficiency']
    V_cell = el['cell_voltage']
    j_A_m2 = el['current_density']
    na = component(pd_, '3OUT3', 'NA+', ('MIXED',))
    cl = component(pd_, '3OUT3', 'CL-', ('MIXED',))
    nacl_kmol = min(na / MW_NA, cl / MW_CL)
    naoh_kg = prep['naoh_kg_h'] if prep['naoh_kg_h'] is not None else nacl_kmol * MW_NAOH * ce   # full regeneration
    I_A = naoh_kg * 1000 / MW_NAOH / 3600 * F_FARADAY / ce
    area_m2 = I_A / j_A_m2
    pd_['ElectrolysisCAPEX'] = dict(
        NaOH_kg_hr=naoh_kg, Cl2_tpa=naoh_kg * op_hr / 1000.0 / T['chloralkali.naoh_per_cl2'], P_kW=I_A * V_cell / 1000,
        I_kA=I_A / 1e3, cell_voltage=V_cell, current_density_A_m2=j_A_m2, active_area_m2=area_m2,
        elements=area_m2 / el['element_area_m2'])

    # ---------------- brine concentration (single-effect MVR)
    w_brine = component(pd_, '3OUT3', 'WATER', ('MIXED',)) * (1.0 - prep['purge_frac'])
    w_membrane = naoh_kg / MW_NAOH * T['regen.water_transport_mol_per_mol'] * MW_H2O
    W = max(0.0, w_brine - w_membrane - prep['purge_water_kg_h'])
    Tb = 100.0 + T['mvr.bpe_K']
    Tc = Tb + T['mvr.dT_K']
    lam = 2257.0 - 2.5 * (Tc - 100)
    Q_kW = W / 3600 * lam
    area = Q_kW * 1e3 / (T['mvr.U_w_m2k'] * T['mvr.dT_K'])
    r = _p_sat_bar(Tc) / 1.01325
    k = 1.33
    w_is = k / (k - 1) * 0.4615 * (Tb + 273.15) * (r ** ((k - 1) / k) - 1)
    mvr_kW = W / 3600 * w_is / T['mvr.eta_isentropic'] / T['mvr.eta_motor']
    ev_bm, ev_n = EQ.evaporator_bm(area, T['mvr.tube_material'])
    cm_bm = EQ.compressor_bm(mvr_kW, fm=T['mvr.compressor_fm'])
    ref = T['mvr.ref_tph']
    _t = mvr_usd_per_tph * ref * (W / 1000.0 / ref) ** T['mvr.scale_exp']     # USBR benchmark, installed
    ev_bm, cm_bm = _t * ev_bm / (ev_bm + cm_bm), _t * cm_bm / (ev_bm + cm_bm)
    CC['evaporator'].append(ev_bm + cm_bm)
    kw['mvr'] = mvr_kW
    pd_['BrineConcentration'] = dict(
        water_evaporated_kg_hr=W, brine_water_kg_hr=w_brine, membrane_water_kg_hr=w_membrane,
        brine_NaCl_g_L=nacl_kmol * 58.443 / max((stream_value(pd_, '3OUT3', 'VOLFLOW') or 1) * 60 / 1000, 1e-9),
        duty_kW=Q_kW, area_m2=area, units=ev_n, compression_ratio=r,
        kWh_per_t=w_is / T['mvr.eta_isentropic'] / T['mvr.eta_motor'] / 3.6,
        compressor_kW=mvr_kW, evaporator_BM=ev_bm, compressor_BM=cm_bm)

    # ---------------- pumps
    head = T['design.pump_head_m']
    p_bm = 0.0
    for s, fm_p in PUMPED:
        q = (stream_value(pd_, s, 'VOLFLOW') or 0) * 60 / 1000
        b, pk = EQ.pump_bm(q, head, fm=fm_p)
        p_bm += b
        kw['pumps'] += pk
    naoh_sol_m3 = naoh_kg / 0.32 / 1350.0                     # regenerated 32 wt% lye
    hcl_ret_m3 = (stream_value(pd_, 'HCL', 'VOLFLOW') or 0) * 60 / 1000
    for q, fm_p in ((naoh_sol_m3, 2.0), (hcl_ret_m3, 2.95)):
        b, pk = EQ.pump_bm(q, head, fm=fm_p)
        p_bm += b
        kw['pumps'] += pk

    # ---------------- Stage V: carbonator, CO2 blower, PCC centrifuge, product dryers
    co2 = sum(component(pd_, s, 'CO2') for s in ('1CO2', '2CO2', '3CO2'))
    caoh2 = component(pd_, 'CAOH2', 'CA(OH)2')
    if T.get('design.stage5_cascade', 0):             # three batch carbonators in rotation + one filling, volumes scale with the CO2 treated
        F_mol = min(co2 / MW_CO2, caoh2 / MW_CAOH2 / T['design.stage5_ca_per_co2'])
        caoh2_used = T['design.stage5_ca_per_co2'] * F_mol * MW_CAOH2
        pcc = T['design.stage5_capture'] * F_mol * MW_CACO3
        slurry = caoh2_used / T['design.carbonator_wt_solid']
        vols = [T['design.stage5_vol%d_m3_per_kmolh' % i] * F_mol for i in range(1, 6) if T['design.stage5_vol%d_m3_per_kmolh' % i] > 0]
        cb_bm = cb_kw = 0.0
        for v in vols:                                                                        # carbon steel
            b_, _, k_ = EQ.agitated_tank_bm(v, T['design.hp_per_kgal_gas'], 1.0, vmax)
            cb_bm += b_; cb_kw += k_
        vol_cb = sum(vols)
    else:
        mol = min(co2 / MW_CO2, caoh2 / MW_CAOH2)
        caoh2_used = mol * MW_CAOH2
        pcc = mol * MW_CACO3
        slurry = caoh2_used / T['design.carbonator_wt_solid']
        vol_cb = slurry / 3600 * T['design.carbonator_residence_min'] * 60 / T['design.carbonator_density']
        cb_bm, _, cb_kw = EQ.agitated_tank_bm(vol_cb, T['design.hp_per_kgal_gas'], 1.0, vmax)     # carbon steel
    kw['agitators'] += cb_kw
    b, pk = EQ.pump_bm(slurry / T['design.carbonator_density'], head)
    p_bm += b
    kw['pumps'] += pk
    kk = T['design.co2_k']
    w_co2 = kk / (kk - 1) * 0.1889 * T['design.co2_T_K'] * (T['design.co2_pressure_ratio'] ** ((kk - 1) / kk) - 1) / T['design.co2_eta']
    bl_kW = co2 / 3600 * w_co2 / 0.95
    bl_bm = EQ.blower_bm(bl_kW)
    kw['co2_blower'] = bl_kW
    pcc_cf, _ = EQ.centrifuge_bm(pcc)
    lime_sold = max(0.0, caoh2 - caoh2_used)
    mo = T['design.cake_moisture']
    w_dry = (lime_sold + pcc) * mo / (1 - mo)
    dr_lime, _, _ = EQ.rotary_dryer_bm(lime_sold * mo / (1 - mo), 'CS')
    dr_pcc, _, _ = EQ.rotary_dryer_bm(pcc * mo / (1 - mo), 'CS')
    CC['stage5'] += [cb_bm, pcc_cf, dr_lime, dr_pcc]
    CC['co2_blower'].append(bl_bm)
    CC['pumps'].append(p_bm)
    pd_['CarbonatorDesign'] = dict(caoh2_carbonated_kg_hr=caoh2_used, slurry_kg_hr=slurry,
                                   di_water_kg_hr=slurry - caoh2_used, volume_m3=vol_cb, capex=cb_bm)

    # ---------------- storage: product silos, HCl and NaOH day tanks
    silo_m3 = (lime_sold + pcc) / 1000 * 24 * T['design.silo_days'] / T['design.bulk_density_t_m3']
    acid_m3 = (stream_value(pd_, 'HCL', 'VOLFLOW') or 0) * 60 / 1000 * 24 * T['design.reagent_tank_days']
    base_m3 = ((stream_value(pd_, 'NAOH1', 'VOLFLOW') or 0)
               + (stream_value(pd_, 'NAOH2', 'VOLFLOW') or 0)) * 60 / 1000 * 24 * T['design.reagent_tank_days']
    CC['storage'] += [EQ.storage_bin_bm(silo_m3), EQ.cone_roof_tank_bm(acid_m3, fm=2.0), EQ.cone_roof_tank_bm(base_m3, fm=1.0)]

    pd_['Units'] = units
    pd_['CapitalCost'] = CC
    pd_['V2_power_kW'] = kw
    pd_['V2_dryer_water_kg_hr'] = w_dry
    return pd_
