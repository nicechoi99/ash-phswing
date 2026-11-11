"""Attributional GWP100 of the co-located plant (ecoinvent 3.11 cut-off factors, IPCC 2021; factors in lca_factors.csv).

Two results (ISO 14044:2006/Amd 2:2020 - substitution only for co-products, never for the functional unit itself):
  footprint_per_kg   burdens only (power, heat, water, softening, purchased reagents) per kg of Ca(OH)2 + PCC
  net_per_t_ash      system expansion per t of dry ash received: footprint + landfill of the plant's residue + cake
                     - avoided hazardous landfill of the ash received - displaced hydrated lime and conventional PCC
Not counted: surplus HCl sold (cut-off, no displacement credit), the CO2 mineralized in Stage V (released from the ash
carbonate in Stage I), the brine purge to deep-well injection (no factor), capital goods, ash haul (co-located).
Host heat is burdened with the electricity the host does not export (Cv x heat x EF of the power case).
"""
from . import params


def inventory(q):
    """Annual inventory of one evaluated case (ash_phswing.tea.evaluate)."""
    C = q['_C']
    T = params.tea()
    HOURS = C['op_hr']
    el, rv, ut = q['Electrolysis'], q['ProductRevenue'], q['C_utilities']
    caoh2 = rv['CAOH2']['flow_kg_hr'] * HOURS
    pcc = rv['CACO3_from_CO2']['flow_kg_hr'] * HOURS
    gf = rv['ASH_gate_fee']
    price = C['electricity']
    cool_J = ut.get('cooling', 0.0) / C['cw']
    bs = q.get('BrineSoftening', {}) or {}
    ao = q.get('_added_opex', {})
    ht = q['HostHeat']
    dryer_MJ, aspen_MJ = ht['dryer'] * 1e6, ht['aspen'] * 1e6
    return dict(caoh2_kg=caoh2, pcc_kg=pcc, AP_kg=caoh2 + pcc, ash_in_kg=gf['ash_in_kg_hr'] * HOURS,
                solids_out_kg=gf['waste_solid_out_kg_hr'] * HOURS, kWh_cell=el.get('electricity_kWh_yr', 0.0),
                kWh_proc=(ut.get('electricity', 0.0) / price) if price else 0.0, kWh_th_cool=cool_J / 3.6e6,
                steam_MJ=dryer_MJ + aspen_MJ, dryer_MJ=dryer_MJ, aspen_MJ=aspen_MJ,
                di_kg=q['CarbonatorDesign']['di_water_kg_hr'] * HOURS,
                hcl_sol_kg=el.get('HCl_solution_makeup_kg_hr', 0) * HOURS, naoh_sol_kg=el.get('NaOH_solution_makeup_kg_hr', 0) * HOURS,
                soda_kg=bs.get('soda_ash_kg_hr', 0.0) * HOURS, sludge_kg=bs.get('sludge_kg_hr', 0.0) * HOURS,
                purge_water_kg=ao.get('purge_makeup_water', 0.0) / T['regen.water_usd_m3'] * 1000.0,
                CO2_mineralized_kg=rv['CACO3_from_CO2']['co2_reacted_kg_hr'] * HOURS,
                co2_vent_kg=rv['CACO3_from_CO2'].get('co2_vented_kg_hr', 0.0) * HOURS)


def ledger(inv, ef_power, ef_lost, heat_mode='lost', F=None):
    """GWP ledger (kg CO2-eq/yr) for a power emission factor ef_power; host heat burdened at ef_lost ('lost'),
    burden-free ('cutoff') or replaced by natural-gas steam ('gas')."""
    F = params.lca() if F is None else F
    AP = inv['AP_kg']
    ash_t = inv['ash_in_kg'] / 1e3
    kwh = inv['kWh_cell'] + inv['kWh_proc'] + inv['kWh_th_cool'] * F['COOL']
    if heat_mode == 'gas':
        steam = inv['steam_MJ'] * F['EF_STEAM_MJ']
    elif heat_mode == 'cutoff':
        steam = 0.0
    else:
        steam = (inv['dryer_MJ'] * F['CV_LP'] + inv['aspen_MJ'] * F['CV_LT']) / 3.6 * ef_lost
    led = dict(electricity=kwh * ef_power, steam=steam, NaOH_purchased=inv['naoh_sol_kg'] * F['EF_NAOH'],
               HCl_purchased=inv['hcl_sol_kg'] * F['EF_HCL'], water=inv['di_kg'] * F['EF_WATER'], soda_ash=inv['soda_kg'] * F['EF_SODA'],
               sludge=inv['sludge_kg'] * F['EF_SLUDGE'], purge_water=inv['purge_water_kg'] * F['EF_TAP'],
               plant_landfill=inv['solids_out_kg'] * F['CRED_LANDFILL'], avoided_ash_landfill=-inv['ash_in_kg'] * F['CRED_LANDFILL'],
               lime_credit=-inv['caoh2_kg'] * F['CRED_CAOH2'], pcc_credit=-inv['pcc_kg'] * F['CRED_PCC'],
               co2_vent=inv.get('co2_vent_kg', 0.0))     # ash-carbonate CO2 the carbonators do not fix
    burden = sum(led[k] for k in ('electricity', 'steam', 'NaOH_purchased', 'HCl_purchased', 'water', 'soda_ash', 'sludge', 'purge_water',
                                  'co2_vent'))
    net = sum(led.values())
    return dict(net_per_t_ash=net / ash_t, footprint_per_kg=burden / AP, kWh_per_t_ash=kwh / ash_t, kWh_per_kg=kwh / AP,
                ledger_per_t_ash={k: v / ash_t for k, v in led.items()},
                conventional_per_kg=(F['CRED_CAOH2'] * inv['caoh2_kg'] + F['CRED_PCC'] * inv['pcc_kg']) / AP)


def power_cases(F=None):
    F = params.lca() if F is None else F
    return [('Incinerator power (all host) - base', 0.0, 0.0),
            ('EU renewable PPA', F['EF_SOLAR'], F['EF_SOLAR']),
            ('France grid', F['EF_GRID_FR'], F['EF_GRID_FR']),
            ('Netherlands grid', F['EF_GRID_NL'], F['EF_GRID_NL']),
            ('Germany grid', F['EF_GRID_DE'], F['EF_GRID_DE']),
            ('Korean grid', F['EF_GRID_KR'], F['EF_GRID_KR'])]


def assess(q, F=None):
    """Power cases of SI Table S35 plus the break-even emission factors."""
    F = params.lca() if F is None else F
    inv = inventory(q)
    out = []
    for lab, ef, efl in power_cases(F):
        a, b, g = ledger(inv, ef, efl, 'lost', F), ledger(inv, ef, efl, 'cutoff', F), ledger(inv, ef, efl, 'gas', F)
        out.append(dict(label=lab, ef_power=ef, net_per_t_ash=a['net_per_t_ash'], footprint_per_kg=a['footprint_per_kg'],
                        net_per_t_ash_heat_cutoff=b['net_per_t_ash'], footprint_per_kg_heat_cutoff=b['footprint_per_kg'],
                        net_per_t_ash_gas_steam=g['net_per_t_ash'], footprint_per_kg_gas_steam=g['footprint_per_kg'],
                        ledger_per_t_ash=a['ledger_per_t_ash']))
    base = ledger(inv, 0.0, 0.0, 'lost', F)
    k = base['kWh_per_t_ash']
    z = ledger(inv, 0.0, F['EF_GRID_NL'], 'lost', F)       # heat burdened at the NL factor for the EF sweep
    return dict(inventory_per_yr=inv, cases=out,
                base=dict(net_per_t_ash=base['net_per_t_ash'], footprint_per_kg=base['footprint_per_kg'],
                          conventional_per_kg=base['conventional_per_kg'], kWh_per_kg=base['kWh_per_kg'], kWh_per_t_ash=k,
                          ledger_per_t_ash=base['ledger_per_t_ash'], neutral_ef_power=-z['net_per_t_ash'] / k,
                          parity_ef_power=(base['conventional_per_kg'] - z['footprint_per_kg']) / base['kWh_per_kg']))
