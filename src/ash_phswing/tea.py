"""Techno-economic model of the co-located plant: one call = one case.

    case = base_case('EU')                      # region defaults from data/parameters
    res = evaluate(case)                        # flowsheet -> sizing -> CAPEX -> OPEX -> DCF
    res['NPV'], res['MSP'], res['LC']           # M$, $/kg, $/kg
    rep = report(res)                           # CAPEX / OPEX / revenue breakdown (SI Tables S23-S25)

Definitions (main text Eqs. 3-4):
    LC   levelized cost         = (CRF x TCI + OPEX) / calcium products
    MSP  net levelized cost     = LC - (treatment fee + surplus HCl revenue) / calcium products   (engine key 'MSP')
    common product price at NPV = 0 (the 'MSP' of the main text) = breakevens(case)['uniform_product_price_usd_t']
"""
import copy
import math
from dataclasses import dataclass, field, replace

from . import params
from . import flowsheet as FS
from . import capex as CX
from . import opex as OX
from . import cashflow as CF
from . import equipment as EQ
from .paths import DESIGN_FLOWSHEET

MW = dict(NA=22.990, K=39.098, CL=35.453, H=1.008, OH=17.007, NAOH=39.997, HCL=36.461, CA=40.078,
          CAOH2=74.093, NACL=58.443, KCL=74.551)


@dataclass
class Case:
    region: str = 'EU'
    fee_usd_t: float = 0.0                    # treatment fee on every dry tonne received
    residue_fee_usd_t: float = None           # landfill rate of the plant's residue + cake (default: the fee)
    elec_usd_kwh: float = 0.05
    price_caoh2_usd_t: float = 218.0
    price_pcc_usd_t: float = 225.0
    hcl_price_usd_t: float = 150.0            # surplus HCl, 30 wt% solution
    steam_lp_usd_gj: float = 0.0
    steam_lt_usd_gj: float = 0.0
    wage_usd_h: float = 40.0
    location_factor: float = 1.0
    ca_usd_per_t_cl2: float = 1405.0          # chlor-alkali plant, $/(t Cl2/yr), TDC level, incl. Stinn rectifier
    energy_kwh_per_t_naoh: float = 0.0
    membrane_usd_m2: float = 1000.0
    membrane_life_yr: float = 4.0
    mvr_usd_per_tph: float = 305000.0
    maint_rest: float = 0.0                   # maintenance-wage fraction of the TDC; total maintenance = 2.3 x this
    maint_mvr: float = 0.0
    maint_ca: float = 0.0
    site_frac: float = 0.10
    selling_frac: float = 0.01
    discount_rate: float = 0.085
    flowsheet: str = DESIGN_FLOWSHEET
    label: str = ''

    def with_(self, **kw):
        return replace(self, **kw)

    def as_dict(self):
        """Inputs of the case with the flowsheet path relative to the repository."""
        import os
        from .paths import ROOT
        d = dict(self.__dict__)
        d['flowsheet'] = os.path.relpath(self.flowsheet, ROOT).replace(os.sep, '/')
        return d


def base_case(region='EU', **over):
    """Base case of a region: parameters from tea_parameters.csv and regions.csv."""
    T = params.tea()
    R = params.regions()[region]
    m = T['maintenance.frac_tdc'] / 2.3
    c = Case(region=region, fee_usd_t=R['fee_usd_t'], residue_fee_usd_t=R['fee_usd_t'], elec_usd_kwh=R['elec_usd_kwh'],
             price_caoh2_usd_t=T['price.caoh2_usd_t'], price_pcc_usd_t=T['price.pcc_usd_t'],
             hcl_price_usd_t=T['price.hcl_30pct_usd_t'], steam_lp_usd_gj=T['host_steam.lp_usd_gj'],
             steam_lt_usd_gj=T['host_steam.lt_usd_gj'], wage_usd_h=R['wage_usd_h'], location_factor=R['location_factor'],
             ca_usd_per_t_cl2=T['chloralkali.capital_usd_per_t_cl2'], energy_kwh_per_t_naoh=T['electrolysis.energy_kwh_per_t_naoh'],
             membrane_usd_m2=T['electrolysis.membrane_usd_m2'], membrane_life_yr=T['electrolysis.membrane_life_yr'],
             mvr_usd_per_tph=T['mvr.usd_per_tph'], maint_rest=m, maint_mvr=m, maint_ca=m, site_frac=T['capital.site_frac'],
             selling_frac=T['general.selling_frac'], discount_rate=T['financial.discount_rate'], label=R['label'])
    return replace(c, **over) if over else c


def cost_dict(case, T):
    """Prices and utility costs of one case in the units of the cost routines ($/kg, $/J, $/kWh)."""
    rate = max(case.fee_usd_t, 1e-6) / 1000.0
    return dict(
        op_hr=T['plant.operating_hours'], electricity=case.elec_usd_kwh,
        steam_lp=T['utility.steam_lp_usd_j'], steam_mp=T['utility.steam_mp_usd_j'], steam_hp=T['utility.steam_hp_usd_j'],
        heat_oil=T['utility.heat_oil_usd_j'], chilled=T['utility.chilled_water_usd_j'], cw=T['utility.cooling_water_usd_j'],
        process_water=T['utility.process_water_usd_kg'],
        CAOH2=case.price_caoh2_usd_t / 1e3, CACO3=case.price_pcc_usd_t / 1e3, HCL=case.hcl_price_usd_t / 1e3,
        NAOH=T['price.naoh_50pct_usd_t'] / 1e3, ASH=-rate,
        electrolysis=dict(current_efficiency=T['electrolysis.current_efficiency'], cell_voltage=T['electrolysis.cell_voltage'],
                          current_density=T['electrolysis.current_density'], element_area_m2=T['electrolysis.element_area_m2'],
                          hcl_synthesis_efficiency=T['electrolysis.hcl_synthesis_efficiency'],
                          energy_per_ton_NaOH=case.energy_kwh_per_t_naoh,
                          membrane_area_per_ton_yr=T['electrolysis.membrane_area_per_t_yr'],
                          membrane_cost_per_m2=case.membrane_usd_m2, membrane_life=case.membrane_life_yr))


def chlor_alkali_usd_per_t(case, T):
    """$/(t Cl2/yr) applied: the per-t value with its Stinn rectifier replaced by the BREF rectifier."""
    return case.ca_usd_per_t_cl2 - (T['chloralkali.rectifier_stinn_usd_kw'] - T['chloralkali.rectifier_bref_usd_kw']) \
        * T['chloralkali.dc_kw_per_t_cl2_yr']


def _feeds(pd_):
    h = FS.mass_flows(pd_, 'HCL')
    hcl = min(h.get('H+', 0) / MW['H'], h.get('CL-', 0) / MW['CL']) + (h.get('HCL', 0) or 0) / MW['HCL']
    naoh = 0.0
    for n in ('NAOH1', 'NAOH2'):
        m = FS.mass_flows(pd_, n)
        naoh += min(m.get('NA+', 0) / MW['NA'], m.get('OH-', 0) / MW['OH']) + (m.get('NAOH', 0) or 0) / MW['NAOH']
    return hcl, naoh


def prepare(pd_, T, regen='auto'):
    """Plant additions on top of the Aspen flowsheet: cake wash water into the brine, Stage I cooler, carbonator
    make-up water, and the brine-loop sizing.  regen 'need': cells sized to the reagent need, the cations beyond it
    leave with an anolyte purge; 'full': cells run on all NaCl of the brine, no purge; 'auto': 'need' unless the brine
    carries fewer cations than the need (salt deficit, no purge defined), then 'full'."""
    HOURS = T['plant.operating_hours']
    extra_bm = 0.0
    extra_util = 0.0
    moist, bv = T['design.wash_cake_moisture'], T['design.wash_bed_volumes']
    solids = sum(FS.non_water(pd_, n) for n in ('CAOH2', 'MGOH2', 'UNREACTE'))
    W = bv * moist / (1.0 - moist) * solids
    FS.add_water(pd_, '3OUT3', W)

    U = pd_['Units']
    hd1 = float(U.loc[U.NAME == 'B1', 'HEATDUTY'].values[0])
    T1 = float(U.loc[U.NAME == 'B1', 'TEMPERATURE'].values[0])
    hd4 = float(U.loc[U.NAME == 'B4', 'HEATDUTY'].values[0])
    cw, chw = T['utility.cooling_water_usd_gj'], T['utility.chilled_water_increment_usd_gj']
    Uhx = T['design.stage1_hx_U']
    d = abs(hd1) * 4.1868 if hd1 < 0 else 0.0
    chg = cw if T1 <= 25.0 + 1e-9 else T['utility.cooling_water_above25_usd_gj']          # cooling-water charge already in the Aspen duty costing
    if d > 1e4:                                            # Stage I leach cooler, medium by temperature
        if T1 >= 40.0:
            lm = ((T1 - 30) - (T1 - 40)) / math.log((T1 - 30) / (T1 - 40)); inc = cw - chg; med = 'cooling water'
        else:
            tr = min(15.0, T1 - 3.0)                       # chilled-water return, at least 3 K below the leach
            lm = ((T1 - 5) - (T1 - tr)) / math.log((T1 - 5) / (T1 - tr)); inc = chw - chg; med = 'chilled water'
        extra_bm += EQ.hx_bm_ti(d, lm, Uhx)
        extra_util += d * HOURS * 3600 / 1e9 * inc
    else:
        med = 'none (adiabatic)'
    d4 = abs(hd4) * 4.1868 if hd4 < 0 else 0.0
    if d4 > 1e4:
        lm4 = ((25 - 5) - (25 - 15)) / math.log(20 / 10)
        extra_bm += EQ.hx_bm_ti(d4, lm4, Uhx)
        extra_util += d4 * HOURS * 3600 / 1e9 * (chw - cw)
    extra_util += T['design.carbonation_makeup_water_t_h'] * HOURS * T['design.bfw_usd_m3']

    b3 = FS.mass_flows(pd_, '3OUT3')
    cat_b = b3.get('NA+', 0) / MW['NA'] + b3.get('K+', 0) / MW['K']
    hcl_n, naoh_n = _feeds(pd_)
    eff = T['electrolysis.hcl_synthesis_efficiency']
    N = max(naoh_n, hcl_n) / eff                           # cell duty, kmol/h NaOH
    purge_kmol = max(0.0, cat_b - eff * N)                 # cations beyond the cell duty leave with the anolyte purge
    if regen == 'auto':
        regen = 'need' if purge_kmol > 0 else 'full'
    if regen == 'need':
        c = T['regen.anolyte_g_l'] / 58.443
        purge_m3_h = purge_kmol / c
        purge_water = purge_m3_h * (T['regen.anolyte_density'] - T['regen.anolyte_g_l'] / 1000.0) * 1000.0
        naoh_kg = N * MW['NAOH']
    else:
        purge_kmol = purge_m3_h = purge_water = 0.0
        naoh_kg = None
    return dict(regen=regen, extra_bm=extra_bm, extra_util=extra_util, naoh_kg_h=naoh_kg, purge_frac=0.0,
                purge_m3_h=purge_m3_h, purge_water_kg_h=purge_water, cake_wash_t_h=W / 1e3, stage1_T_C=T1,
                stage1_duty_MW=d / 1e6, stage1_medium=med, HCl_need_kmol_h=hcl_n, NaOH_need_kmol_h=naoh_n, duty_kmol_h=N,
                binding='HCl' if hcl_n > naoh_n else 'NaOH')


def evaluate(case, T=None, pd_=None, regen='auto'):
    """Run the cost model for one case.  Returns the processData-like dictionary with the summary keys
    NPV, NPV_standalone (M$), LC, MSP ($/kg), TCI, TDC, cash_opex, capital_charge, annual, revenue (M$ or M$/yr)."""
    T = params.tea() if T is None else T
    q = FS.load(case.flowsheet) if pd_ is None else copy.deepcopy(pd_)
    prep = prepare(q, T, regen)
    C = cost_dict(case, T)
    CX.estimate(q, T, C['electrolysis'], prep, case.mvr_usd_per_tph)
    OX.estimate(q, C, T, prep)
    OX.brine_acid(q, C)                          # 2026-11-03: brine acidification HCl before the surplus is sold
    OX.host_steam(q, C, case.steam_lp_usd_gj, case.steam_lt_usd_gj)
    resid = case.fee_usd_t if case.residue_fee_usd_t is None else case.residue_fee_usd_t
    OX.bill_all_ash(q, C, resid / 1000.0)
    k = dict(extra_bm=prep['extra_bm'], extra_util=prep['extra_util'], ca_per_t=chlor_alkali_usd_per_t(case, T),
             site=case.site_frac, location_factor=case.location_factor, wage=case.wage_usd_h, maint_rest=case.maint_rest,
             maint_mvr=case.maint_mvr, maint_ca=case.maint_ca, selling=case.selling_frac, discount_rate=case.discount_rate)
    CF.capital_and_cashflow(q, C, T, k)
    q['_case'] = case
    q['_C'] = C
    q['_prep'] = prep
    q['_k'] = k
    q.update(summary(q))
    return q


def summary(q):
    ed = q['EconomicData']
    pr = q['ProductRevenue']
    A, AP, OPEX, TCI = ed['CRF'], ed['AP'], ed['OPEX'], ed['C_TCI']
    LC = (A * TCI + OPEX) / AP
    ca_rev = pr.get('CAOH2', {}).get('annual_revenue', 0) + pr.get('CACO3_from_CO2', {}).get('annual_revenue', 0)
    byp = q['S_total'] - ca_rev + 0.0
    el = q['Electrolysis']
    gf = pr['ASH_gate_fee']
    HOURS = q['_C']['op_hr']
    return dict(
        NPV=q['NPV'] / 1e6, NPV_standalone=CF.npv_standalone(q), LC=LC, MSP=LC - byp / AP, TCI=TCI / 1e6, TDC=ed['C_TDC'] / 1e6,
        cash_opex=OPEX / 1e6, capital_charge=A * TCI / 1e6, annual=(OPEX + A * TCI) / 1e6, revenue=q['S_total'] / 1e6,
        AP_kt=AP / 1e6, lime_kt=pr.get('CAOH2', {}).get('flow_kg_hr', 0) * HOURS / 1e6,
        pcc_kt=pr.get('CACO3_from_CO2', {}).get('flow_kg_hr', 0) * HOURS / 1e6,
        elec_GWh=(el['electricity_kWh_yr'] + q['V2_added']['electricity_kWh_yr']) / 1e6,
        Cl2_kt=q['ElectrolysisCAPEX']['Cl2_tpa'] / 1e3, ash_kt=float(gf['ash_in_kg_hr']) * HOURS / 1e6,
        gate_rev_M=gf['annual_revenue'] / 1e6,
        rev_by_stream_M={k: v.get('annual_revenue', 0) / 1e6 for k, v in pr.items() if v.get('annual_revenue', 0)})


def npv(case):
    return evaluate(case)['NPV']


# ---------------------------------------------------------------- report (SI Tables S21, S23-S25)
def report(q):
    """CAPEX, OPEX and revenue breakdown of one evaluated case (M$ and M$/yr)."""
    M = 1e6
    ed = q['EconomicData']
    sp = q['CapitalSplit']
    case = q['_case']
    tdc = ed['C_TDC'] / M
    ca_u = float(sp['CA_TDC_level']) / M
    ev_frac = float(sp['MVR_TDC_level']) / M / (tdc - ca_u)
    ca_s = ca_u * case.location_factor
    mvr_s = ev_frac * (tdc - ca_s)
    bc = q['BrineConcentration']
    capex = dict(TCI=ed['C_TCI'] / M, TDC=tdc, chlor_alkali_TDC=ca_s, MVR_TDC=mvr_s, rest_TDC=tdc - ca_s - mvr_s,
                 TBM=ed['C_TBM'] / M, location_factor=case.location_factor, startup=ed['C_startup'] / M,
                 land=ed['C_land'] / M, working_capital=ed['C_WC'] / M,
                 MVR_bare_module=(bc['evaporator_BM'] + bc['compressor_BM']) / M,
                 bare_module_by_section={k: sum(v) / M for k, v in q['CapitalCost'].items()},
                 chlor_alkali_usd_per_t_cl2_applied=q['_k']['ca_per_t'])
    el = q['Electrolysis']
    ut = q['C_utilities']
    rl = q['ResidueLandfill']
    cell = el['electricity_cost_yr'] / M
    mem = el['membrane_annual_cost'] / M
    resid = rl['landfill_M']
    c_waste = q['C_waste']['total'] / M
    items = dict(cell_electricity=cell, membranes=mem, electrolysis_other=ed['C_electrolysis'] / M - cell - mem,
                 NaOH_purchased=q['MaterialCost'].get('NAOH_makeup', 0.0) / M, HCl_purchased=q['MaterialCost'].get('HCL_makeup', 0.0) / M,
                 residue_and_cake_disposal=resid, other_waste=c_waste - resid,
                 process_electricity=ut['electricity'] / M, steam=ut['steam'] / M, cooling=ut['cooling'] / M,
                 other_utilities_softening_chilled=sum(ed['C_util']) / M - ut['total'] / M,
                 labour=sum(ed['C_O']) / M, maintenance=sum(ed['C_M'][:4]) / M, overhead=sum(ed['C_OH']) / M,
                 property_tax_insurance=ed['C_prop'] / M, general_expenses=sum(ed['GE']) / M)
    assert abs(sum(items.values()) - q['cash_opex']) < 1e-6
    rev = {k: v for k, v in q['rev_by_stream_M'].items()}
    hs = q['ProductRevenue'].get('HCL_surplus', {})
    HOURS = q['_C']['op_hr']
    return dict(
        region=case.region, label=case.label, NPV=q['NPV'], NPV_standalone=q['NPV_standalone'], LC=q['LC'], MSP=q['MSP'],
        CAPEX=capex, OPEX=dict(total=q['cash_opex'], items=items), capital_charge=q['capital_charge'], CRF=ed['CRF'],
        annual_cost=q['annual'], revenue=dict(total=q['revenue'], items=rev),
        products=dict(CaOH2_kt=q['lime_kt'], PCC_kt=q['pcc_kt'], total_kt=q['AP_kt']),
        ash=dict(received_kt=q['ash_kt'], residue_plus_cake_landfilled_kt=rl['residue_kt'], gate_fee_revenue_M=q['gate_rev_M'],
                 disposal_cost_M=resid),
        electricity_GWh=q['elec_GWh'], Cl2_kt=q['Cl2_kt'],
        reagents=dict(HCl_need_t_h=el['HCl_feed_pure_kg_hr'] / 1e3, HCl_made_t_h=el['HCl_recovered_pure_kg_hr'] / 1e3,
                      NaOH_need_t_h=el['NaOH_feed_pure_kg_hr'] / 1e3, NaOH_made_t_h=el['NaOH_recovered_pure_kg_hr'] / 1e3,
                      HCl_surplus_sold_kt_30pct=hs.get('flow_kg_hr', 0.0) * HOURS / 1e6),
        CO2_mineralized_t_yr=q['ProductRevenue']['CACO3_from_CO2']['co2_reacted_kg_hr'] * HOURS / 1e3,
        cashflow=cashflow_table(q))


def cashflow_table(q):
    ed = q['EconomicData']
    CFm = q['CASHFLOW']
    cp = ed['construction']
    rows = []
    for i in range(ed['n']):
        rows.append(dict(year=i + 1, phase='construction' if i < cp else 'operation', capital_M=float(CFm[i, 0]) / 1e6,
                         wc_land_startup_M=float(CFm[i, 1]) / 1e6, depreciation_M=float(CFm[i, 2]) / 1e6,
                         cash_opex_M=float(CFm[i, 3]) / 1e6, revenue_M=float(CFm[i, 4]) / 1e6 if i >= cp else 0.0,
                         net_earnings_M=float(CFm[i, 5]) / 1e6, cash_flow_M=float(CFm[i, 6]) / 1e6,
                         discounted_M=float(CFm[i, 7]) / 1e6, cum_discounted_M=float(CFm[i, 8]) / 1e6))
    return rows


# ---------------------------------------------------------------- break-even conditions
def _affine_root(f, a, b):
    ya, yb = f(a), f(b)
    s = (yb - ya) / (b - a)
    x = a - ya / s
    return x, s, f(x)


def breakevens(case):
    """NPV is affine in the fee and in the product prices, so two runs give the exact root (checked by a third)."""
    ratio = case.residue_fee_usd_t / case.fee_usd_t
    g, s, r1 = _affine_root(lambda x: npv(case.with_(fee_usd_t=x, residue_fee_usd_t=x * ratio)), 100.0, 600.0)
    u, _, r2 = _affine_root(lambda x: npv(case.with_(price_caoh2_usd_t=x, price_pcc_usd_t=x)), 300.0, 900.0)
    p, _, r3 = _affine_root(lambda x: npv(case.with_(price_pcc_usd_t=x)), 300.0, 900.0)
    for r in (r1, r2, r3):
        assert abs(r) < 1e-4, r
    return dict(fee_usd_t=g, fee_slope_M_per_usd_t=s, uniform_product_price_usd_t=u, PCC_needed_at_CaOH2_usd_t=p,
                fee_multiple_of_case=g / case.fee_usd_t)
