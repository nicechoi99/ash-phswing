"""Operating cost and revenue.

Reagent loop: the chlor-alkali duty is sized to the larger of the Stage I HCl and Stage II + III NaOH needs divided by
the HCl-synthesis efficiency; surplus HCl is sold as 30 wt% acid, surplus NaOH is not priced.  Utilities follow the
Aspen block duties; host steam is re-priced at the electricity the host loses.  The plant bills the treatment fee on
all ash received and landfills its own Stage I residue and Stage II cake at the residue rate.
"""
import numpy as np

HCL_CONC = 0.30           # purchased / sold HCl solution, wt fraction
NAOH_CONC = 0.50          # NaOH lye, wt fraction
MW_NA, MW_CL, MW_HCL, MW_NAOH, MW_OH, MW_H = 22.990, 35.453, 36.461, 39.997, 17.007, 1.008
RECYCLE_STREAMS = {'RE', 'RE-NAOH', 'S6'}


def _heating_cost(T_K, J, C):
    op = C['op_hr']
    if T_K <= 125 + 273.15:
        return C['steam_lp'] * J * 3600 * op
    elif T_K <= 175 + 273.15:
        return C['steam_mp'] * J * 3600 * op
    elif T_K <= 250 + 273.15:
        return C['steam_hp'] * J * 3600 * op
    return C['heat_oil'] * J * 3600 * op


def _cooling_cost(T_K, J, C):
    op = C['op_hr']
    if T_K <= 4.4444 + 273.15:
        return C['chilled'] * J * 3600 * op
    elif T_K <= 25 + 273.15:
        return C['cw'] * J * 3600 * op
    return C['cw'] / 10 * J * 3600 * op


def estimate(pd_, C, T, prep):
    """C: cost dictionary of the case (ash_phswing.tea.cost_dict)."""
    op_hr = C['op_hr']
    elec_price = C['electricity']
    units = pd_['Units']
    feed_info = pd_.get('Input', {})
    feed_streams = pd_.get('FeedStreams', [])
    comps = pd_.get('StreamCompositions', {})

    # ---------------- reagents consumed by the process (pure basis)
    hcl_pure_feed = 0
    for sname in feed_streams:
        if 'HCL' in sname.upper() or 'ACID' in sname.upper():
            mf = comps.get(sname, {}).get('MIXED', {}).get('mass_flow', {})
            h_mol = mf.get('H+', 0) / MW_H if mf.get('H+', 0) else 0
            cl_mol = mf.get('CL-', 0) / MW_CL if mf.get('CL-', 0) else 0
            hcl_pure_feed += mf.get('HCL', 0) + min(h_mol, cl_mol) * MW_HCL
    naoh_pure_feed = 0
    for sname in feed_streams:
        if 'NAOH' in sname.upper() or 'BASE' in sname.upper():
            mf = comps.get(sname, {}).get('MIXED', {}).get('mass_flow', {})
            na_mol = mf.get('NA+', 0) / MW_NA if mf.get('NA+', 0) else 0
            oh_mol = mf.get('OH-', 0) / MW_OH if mf.get('OH-', 0) else 0
            naoh_pure_feed += mf.get('NAOH', 0) + min(na_mol, oh_mol) * MW_NAOH

    el = C['electrolysis']
    eff_hcl = el['hcl_synthesis_efficiency']
    brine_na_kg = brine_cl_kg = 0
    for sname in pd_['Streams']['NAME'].values:
        if sname == '3OUT3' or 'BRINE' in sname.upper():
            cd = comps.get(sname, {})
            if 'MIXED' in cd:
                brine_na_kg += cd['MIXED']['mass_flow'].get('NA+', 0)
                brine_cl_kg += cd['MIXED']['mass_flow'].get('CL-', 0)
    nacl_mol = min(brine_na_kg / MW_NA, brine_cl_kg / MW_CL)

    if prep['regen'] == 'need':
        # chlor-alkali duty = need-based (larger of the HCl and NaOH needs) / HCl-synthesis efficiency
        _n = max(naoh_pure_feed / MW_NAOH, hcl_pure_feed / MW_HCL) / eff_hcl
        naoh_recovered_pure = _n * MW_NAOH
        hcl_recovered_pure = _n * eff_hcl * MW_HCL
    else:
        # full regeneration (salt deficit): the cells run on all electrolyzable NaCl of the brine
        naoh_recovered_pure = nacl_mol * MW_NAOH * el['current_efficiency']
        hcl_recovered_pure = nacl_mol * MW_HCL * el['current_efficiency'] * eff_hcl

    naoh_recovered_ton_yr = naoh_recovered_pure * op_hr / 1000
    elec_kwh_yr = naoh_recovered_ton_yr * el['energy_per_ton_NaOH']
    C_electrolysis_elec = elec_kwh_yr * elec_price
    membrane_area = el['membrane_area_per_ton_yr'] * naoh_recovered_ton_yr
    C_membrane_annual = membrane_area * el['membrane_cost_per_m2'] / el['membrane_life']
    C_electrolysis = C_electrolysis_elec + C_membrane_annual

    hcl_makeup_pure = max(0, hcl_pure_feed - hcl_recovered_pure)
    naoh_makeup_pure = max(0, naoh_pure_feed - naoh_recovered_pure)
    hcl_surplus = max(0, hcl_recovered_pure - hcl_pure_feed)
    naoh_surplus = max(0, naoh_recovered_pure - naoh_pure_feed)
    hcl_solution_makeup = hcl_makeup_pure / HCL_CONC
    naoh_solution_makeup = naoh_makeup_pure / NAOH_CONC

    ash_flow = 0
    for sname in feed_streams:
        if 'ASH' == sname.upper():
            tot = feed_info.get(sname, {}).get('Massflow_Total', 0) or 0
            wat = 0.0
            for sub in comps.get(sname, {}).values():
                wat += sub.get('mass_flow', {}).get('WATER', 0) or 0
            ash_flow += max(0.0, tot - wat)            # dry ash only
    material_costs = dict(ASH=0.0, HCL_makeup=hcl_solution_makeup * op_hr * C['HCL'],
                          NAOH_makeup=naoh_solution_makeup * op_hr * C['NAOH'])
    C_materials_total = sum(material_costs.values())

    hcl_total_feed = feed_info.get('HCL', {}).get('Massflow_Total', 0) or 0
    naoh_total_feed = sum((feed_info.get(s, {}).get('Massflow_Total', 0) or 0) for s in feed_streams if 'NAOH' in s.upper())
    electrolysis = dict(
        HCl_feed_total_kg_hr=hcl_total_feed, HCl_feed_pure_kg_hr=hcl_pure_feed, NaOH_feed_total_kg_hr=naoh_total_feed,
        NaOH_feed_pure_kg_hr=naoh_pure_feed, brine_Na_kg_hr=brine_na_kg, brine_Cl_kg_hr=brine_cl_kg,
        NaCl_electrolyzable_kmol_hr=nacl_mol, NaOH_recovered_pure_kg_hr=naoh_recovered_pure,
        HCl_recovered_pure_kg_hr=hcl_recovered_pure, HCl_makeup_pure_kg_hr=hcl_makeup_pure,
        NaOH_makeup_pure_kg_hr=naoh_makeup_pure, HCl_surplus_pure_kg_hr=hcl_surplus, NaOH_surplus_pure_kg_hr=naoh_surplus,
        HCl_solution_makeup_kg_hr=hcl_solution_makeup, NaOH_solution_makeup_kg_hr=naoh_solution_makeup,
        NaOH_recovered_ton_yr=naoh_recovered_ton_yr, electricity_kWh_yr=elec_kwh_yr,
        electricity_cost_yr=C_electrolysis_elec, membrane_area_m2=membrane_area, membrane_annual_cost=C_membrane_annual,
        total_electrolysis_opex=C_electrolysis)

    # ---------------- heat duties of the Aspen blocks
    steam, elec, cool = [], [], []
    for i in range(len(units)):
        if units.at[i, 'TYPE'] in ('Flash2', 'RGibbs', 'Heater'):
            hd = units.at[i, 'HEATDUTY']
            if hd is not None and isinstance(hd, (int, float)) and not np.isnan(hd):
                J = abs(hd) * 4.1868                     # cal/s -> W
                T_K = (units.at[i, 'TEMPERATURE'] or 25) + 273.15
                if hd > 0:
                    steam.append(_heating_cost(T_K, J, C))
                elif hd < 0:
                    cool.append(_cooling_cost(T_K, J, C))
    C_steam, C_elec_process, C_cooling = sum(steam), sum(elec), sum(cool)

    # ---------------- solids leaving to landfill (dry): Stage I residue and Stage II cake
    waste_solid_flow = 0
    for sname in pd_.get('ProductStreams', []):
        if 'UNREACT' in sname.upper() or sname == 'MGOH2':
            tw = pd_['Output'].get(sname, {}).get('Massflow_Total', 0) or 0
            ww = 0.0
            for sub in comps.get(sname, {}).values():
                ww += sub.get('mass_flow', {}).get('WATER', 0) or 0
            waste_solid_flow += max(0.0, tw - ww)

    # ---------------- products: Stage V carbonates the Ca(OH)2 with the CO2 released in Stages I-III
    MW_CO2, MW_CAOH2, MW_CACO3 = 44.01, 74.10, 100.09
    co2_total = 0.0
    for nm in ('1CO2', '2CO2', '3CO2'):
        c = comps.get(nm, {})
        for sub in ('MIXED', 'CISOLID'):
            if sub in c:
                co2_total += c[sub].get('mass_flow', {}).get('CO2', 0) or 0
    caoh2_pure = 0.0
    cc = comps.get('CAOH2', {})
    for sub in ('MIXED', 'CISOLID'):
        if sub in cc:
            caoh2_pure += cc[sub].get('mass_flow', {}).get('CA(OH)2', 0) or 0
    if T.get('design.stage5_cascade', 0):
        # three batch carbonators in rotation sized from the measured CO2 uptake (2026-10-29; five-tank cascade 2026-10-28): the cascade treats CO2 F,
        # takes ca_per_co2 * F of Ca(OH)2 and fixes capture * F as CaCO3; the unreacted Ca(OH)2 dissolves into the filtrate
        F_mol = min(co2_total / MW_CO2, caoh2_pure / MW_CAOH2 / T['design.stage5_ca_per_co2'])
        reacted_mol = T['design.stage5_capture'] * F_mol
        caoh2_consumed = T['design.stage5_ca_per_co2'] * F_mol * MW_CAOH2
        carb_cool = T['design.stage5_heat_mj_per_kmol'] * reacted_mol * 1e6 * op_hr * C['cw']
    else:
        reacted_mol = min(co2_total / MW_CO2, caoh2_pure / MW_CAOH2)
        caoh2_consumed = reacted_mol * MW_CAOH2
        carb_cool = 0.0
    caoh2_remaining = max(0.0, caoh2_pure - caoh2_consumed)
    caco3 = reacted_mol * MW_CACO3
    co2_reacted = reacted_mol * MW_CO2

    rev = {}
    for sname in pd_.get('ProductStreams', []):
        if sname in RECYCLE_STREAMS:
            continue
        if sname == 'CAOH2':
            rev['CAOH2'] = dict(flow_kg_hr=caoh2_remaining, caoh2_total_in_stream_kg_hr=caoh2_pure,
                                consumed_by_co2_kg_hr=caoh2_consumed,
                                annual_revenue=caoh2_remaining * op_hr * C['CAOH2'])
        elif sname == 'MGOH2':
            rev['MGOH2_waste'] = dict(flow_kg_hr=pd_['Output'].get(sname, {}).get('Massflow_Total', 0) or 0,
                                      annual_revenue=0.0)
    if caco3 > 0:
        rev['CACO3_from_CO2'] = dict(flow_kg_hr=caco3, co2_total_kg_hr=co2_total, co2_reacted_kg_hr=co2_reacted,
                                     co2_vented_kg_hr=max(0.0, co2_total - co2_reacted), caoh2_consumed_kg_hr=caoh2_consumed,
                                     annual_revenue=caco3 * op_hr * C['CACO3'])
    ash_consumed = max(0.0, ash_flow - waste_solid_flow)
    gate_rate = -C['ASH']
    if ash_consumed > 0 and gate_rate > 0:
        rev['ASH_gate_fee'] = dict(flow_kg_hr=ash_consumed, ash_in_kg_hr=ash_flow, waste_solid_out_kg_hr=waste_solid_flow,
                                   **{'rate_$_per_kg': gate_rate}, annual_revenue=ash_consumed * op_hr * gate_rate)
    if hcl_surplus > 0:
        s = hcl_surplus / HCL_CONC
        rev['HCL_surplus'] = dict(flow_kg_hr=s, pure_kg_hr=hcl_surplus, annual_revenue=s * op_hr * C['HCL'])
    if naoh_surplus > 0:
        s = naoh_surplus / NAOH_CONC
        rev['NAOH_surplus'] = dict(flow_kg_hr=s, pure_kg_hr=naoh_surplus, annual_revenue=s * op_hr * C['NAOH'])
    S_total = sum(p.get('annual_revenue', 0) for p in rev.values())

    pd_['OperatingCost'] = dict(STEAM=steam, ELECTRICITY=elec, COOLING=cool + ([carb_cool] if T.get('design.stage5_cascade', 0) else []))   # cascade heat also sizes the cooling-water allocation
    pd_['MaterialCost'] = material_costs
    pd_['C_materials_total'] = C_materials_total
    C_cooling += carb_cool                          # carbonation heat to cooling water (Stage V batch rotation)
    pd_['C_utilities'] = dict(steam=C_steam, electricity=C_elec_process, cooling=C_cooling,
                              total=C_steam + C_elec_process + C_cooling)
    pd_['Electrolysis'] = electrolysis
    pd_['C_electrolysis'] = C_electrolysis
    pd_['C_waste'] = {'solid': 0.0, 'brine': 0, 'total': 0.0}
    pd_['ProductRevenue'] = rev
    pd_['S_total'] = S_total

    # ---------------- power of the sized equipment, dryer heat
    kw = pd_.get('V2_power_kW', {})
    add_elec = sum(kw.values()) * op_hr * elec_price
    heat_MJ = pd_.get('V2_dryer_water_kg_hr', 0.0) * T['design.dryer_mj_per_kg_water'] * op_hr
    add_heat = heat_MJ * 1e6 * C['steam_lp']
    u = pd_['C_utilities']
    u['electricity'] += add_elec
    u['steam'] += add_heat
    u['total'] = u['steam'] + u['electricity'] + u['cooling']

    # ---------------- softening of the cell-feed brine: soda ash, sludge landfilled at the fee
    mfx = comps.get('3OUT3', {}).get('MIXED', {}).get('mass_flow', {})
    ca_kmol = (mfx.get('CA++', 0) or 0) / 40.078 * (1.0 - prep['purge_frac'])
    mg_kmol = (mfx.get('MG++', 0) or 0) / 24.305 * (1.0 - prep['purge_frac'])
    sa_kg = (ca_kmol + mg_kmol) * 105.988 * T['softening.soda_ash_excess']
    sludge_kg = ca_kmol * 100.087 + mg_kmol * 84.314
    c_sa = sa_kg * op_hr / 1000.0 * T['price.soda_ash_usd_t']
    c_sl = sludge_kg * op_hr * max(0.0, -C['ASH']) if T['softening.sludge_at_fee'] else 0.0
    pd_['C_waste']['total'] = pd_['C_waste'].get('total', 0) + c_sa + c_sl
    pd_['BrineSoftening'] = dict(Ca_kg_hr=ca_kmol * 40.078, Mg_kg_hr=mg_kmol * 24.305, soda_ash_kg_hr=sa_kg,
                                 soda_ash_kt_yr=sa_kg * op_hr / 1e6, sludge_kg_hr=sludge_kg, soda_ash_cost=c_sa, sludge_cost=c_sl)
    pd_['V2_added'] = dict(electricity_kWh_yr=sum(kw.values()) * op_hr, electricity_cost=add_elec,
                           dryer_heat_MJ_yr=heat_MJ, dryer_heat_cost=add_heat, by_kW=dict(kw))

    # ---------------- anolyte purge: deep-well disposal and its make-up water
    extra = {}
    if prep['purge_m3_h'] > 0:
        m3 = prep['purge_m3_h'] * op_hr
        extra['purge_disposal'] = m3 * T['regen.purge_disposal_usd_m3']
        mw = (prep['purge_water_kg_h'] / 1000.0 * op_hr) if prep['purge_water_kg_h'] else m3
        extra['purge_makeup_water'] = mw * T['regen.water_usd_m3']
    pd_['C_waste']['total'] = pd_['C_waste'].get('total', 0) + sum(extra.values())
    pd_['_added_opex'] = extra
    return pd_


def host_steam(pd_, C, p_lp, p_lt):
    """Re-price heat at the host's lost-electricity cost: Aspen duties at p_lt, dryer steam at p_lp ($/GJ)."""
    u = pd_['C_utilities']
    p0 = C['steam_lp']
    aspen_J = sum(pd_['OperatingCost']['STEAM']) / p0
    dryer_J = pd_['V2_added']['dryer_heat_MJ_yr'] * 1e6
    old = u['steam']
    assert abs(old - (aspen_J + dryer_J) * p0) < 1.0, (old, aspen_J, dryer_J)
    u['steam'] = aspen_J * p_lt * 1e-9 + dryer_J * p_lp * 1e-9
    u['total'] = u['steam'] + u['electricity'] + u['cooling']
    pd_['HostHeat'] = dict(aspen=aspen_J / 1e12, dryer=dryer_J / 1e12, old_steam_M=old / 1e6, steam_M=u['steam'] / 1e6)
    return pd_


def bill_all_ash(pd_, C, residue_rate_usd_kg):
    """Bill the fee on all ash received and landfill the residue + cake at residue_rate_usd_kg."""
    op = C['op_hr']
    g = pd_['ProductRevenue']['ASH_gate_fee']
    res = g['waste_solid_out_kg_hr'] * op
    add = res * g['rate_$_per_kg']
    g['annual_revenue'] = g['annual_revenue'] + add
    pd_['S_total'] = pd_['S_total'] + add
    pd_['C_waste']['total'] = pd_['C_waste']['total'] + res * residue_rate_usd_kg
    pd_['ResidueLandfill'] = dict(residue_kt=res / 1e6, rev_M=add / 1e6, landfill_M=res * residue_rate_usd_kg / 1e6)
    return pd_


def brine_acid(pd_, C):
    """Acidify the cell brine (2026-11-03).  The Stage III filtrate carries the free NaOH left after Ca(OH)2 precipitation
    back to the cells; membrane practice acidifies the inlet brine with HCl (Schmittinger et al., Ullmann's 2011, 7.2-7.3).
    One mol HCl per mol free OH- is taken from the cell HCl before the surplus is sold; a shortfall is bought as 30 wt% HCl.
    The NaCl formed returns to the cells, so the chloride cap is  cell HCl <= brine Cl- + acid Cl-."""
    el = pd_['Electrolysis']
    if float(el.get('NaOH_recovered_pure_kg_hr', 0.0)) <= 0.0:
        return pd_
    mf = pd_['StreamCompositions']['3OUT3']['MIXED']['mass_flow']
    cl_comp = float(mf.get('CL-', 0.0))
    scale = float(el.get('brine_Cl_kg_hr', cl_comp)) / cl_comp if cl_comp > 0 else 1.0
    oh_kmol = float(mf.get('OH-', 0.0)) / MW_OH * scale
    acid = oh_kmol * MW_HCL
    s = float(el.get('HCl_surplus_pure_kg_hr', 0.0))
    hs = pd_['ProductRevenue'].get('HCL_surplus')
    lost = 0.0
    if hs and hs.get('flow_kg_hr', 0.0) > 0:
        rate = hs['annual_revenue'] / hs['flow_kg_hr']
        keep = max(0.0, s - acid)
        new_sol = keep / HCL_CONC
        lost = hs['annual_revenue'] - new_sol * rate
        hs.update(flow_kg_hr=new_sol, pure_kg_hr=keep, annual_revenue=new_sol * rate)
        pd_['S_total'] -= lost
    short = max(0.0, acid - s)
    bought = 0.0
    if short > 0:
        bought = short / HCL_CONC * C['op_hr'] * C['HCL']
        mc = pd_['MaterialCost']
        mc['HCL_brine_acid'] = bought
        pd_['C_materials_total'] = sum(mc.values())
    el['HCl_brine_acid_pure_kg_hr'] = acid
    el['HCl_surplus_pure_kg_hr'] = max(0.0, s - acid)
    cell_hcl = float(el.get('NaOH_recovered_pure_kg_hr', 0.0)) / MW_NAOH * C['electrolysis'].get('hcl_synthesis_efficiency', 0.985)
    cl_sup = float(el.get('brine_Cl_kg_hr', 0.0)) / MW_CL + oh_kmol
    pd_['BrineAcid'] = dict(OH_kmol_h=oh_kmol, acid_t_h=acid / 1e3, acid_kt=acid * C['op_hr'] / 1e6, lost_rev_M=lost / 1e6,
                            bought_M=bought / 1e6, surplus_after_t_h=max(0.0, s - acid) / 1e3, cell_HCl_kmol_h=cell_hcl,
                            Cl_supply_kmol_h=cl_sup, Cl_cap_ok=bool(cell_hcl <= cl_sup + 1e-6))
    return pd_
