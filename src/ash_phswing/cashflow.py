"""Total capital investment, cost of manufacture and the discounted cash flow (Seider factor method).

TBM   = sum of bare-module costs + miscellaneous item + Stage I cooler
TDC   = [TBM + site + service + allocated (5 % TBM + utility plant)] x (1 + contingency) + chlor-alkali plant ($/t Cl2 x
        installed Cl2 capacity), times the location factor
TCI   = TDC + land 2 % + start-up 10 % + working capital
COM   = feed (reagent make-up, electrolysis power + membranes, waste) + utilities + labor + maintenance + overhead
        + property tax and insurance + book depreciation;  C = COM + general expenses (% of sales)
OPEX  = C - book depreciation (cash cost);  annualized CAPEX = CRF x TCI with CRF over the operating years
NPV   = sum of (after-tax earnings + MACRS depreciation - capital - working capital) / (1 + r)^(year - 1); negative taxable
        income is credited at the tax rate (credited-tax convention).
"""
import numpy as np


def capital_and_cashflow(pd_, C, T, k):
    """k: case-dependent cost factors (site, location factor, chlor-alkali $/t, maintenance, labor, selling, ...)."""
    op_hr = C['op_hr']
    S_total = pd_.get('S_total', 0)
    CC = pd_['CapitalCost']
    C_EQP = sum(sum(v) for v in CC.values())
    C_comp = T['capital.misc_equipment_usd'] + k['extra_bm']
    C_TBM = C_EQP + C_comp
    C_CA_TDC = k['ca_per_t'] * pd_['ElectrolysisCAPEX']['Cl2_tpa']
    C_site = k['site'] * C_TBM
    C_serv = T['capital.service_frac'] * C_TBM

    # utility-plant allocation (Seider Table 22.32 rules on the steam, power and cooling-water demand)
    index_ratio = T['capital.cepci_now'] / T['capital.cepci_seider']
    OC = pd_.get('OperatingCost', {})
    S_steam = (sum(OC.get('STEAM', [0])) / (C['steam_mp'] * 1000 * 1993.38) / op_hr * 0.454) if sum(OC.get('STEAM', [0])) > 0 else 0
    S_elec = (sum(OC.get('ELECTRICITY', [0])) / C['electricity'] / op_hr * 0.001) if sum(OC.get('ELECTRICITY', [0])) > 0 else 0
    S_cw = (sum(OC.get('COOLING', [0])) / C['process_water'] / op_hr * 0.0044) if sum(OC.get('COOLING', [0])) > 0 else 0
    C_alloc_steam = index_ratio * T['capital.utility_alloc_steam_coef'] * (S_steam ** T['capital.utility_alloc_steam_exp']) if S_steam > 0 else 0
    C_alloc_elec = index_ratio * T['capital.utility_alloc_elec_coef'] * (S_elec ** T['capital.utility_alloc_elec_exp']) if S_elec > 0 else 0
    C_alloc_cw = index_ratio * T['capital.utility_alloc_cw_coef'] * (S_cw ** T['capital.utility_alloc_cw_exp']) if S_cw > 0 else 0
    sum_alloc = C_alloc_steam + C_alloc_elec + C_alloc_cw
    C_alloc = T['capital.allocation_frac'] * C_TBM + sum_alloc * 1.0
    C_DPI = C_TBM + 0.0 + C_site + C_serv + C_alloc
    C_cont = T['capital.contingency_frac'] * C_DPI
    C_TDC = C_DPI + C_cont + C_CA_TDC
    C_TDC = C_TDC * k['location_factor']
    C_land = T['capital.land_frac'] * C_TDC
    C_startup = T['capital.startup_frac'] * C_TDC
    C_TPI = C_TDC + C_land + 0 + C_startup

    # ---------------- cost of manufacture
    C_materials_makeup = pd_.get('C_materials_total', 0)
    C_electrolysis_opex = pd_.get('C_electrolysis', 0)
    C_materials_net = C_materials_makeup + C_electrolysis_opex
    C_waste = pd_.get('C_waste', {}).get('total', 0)
    C_feed = [C_materials_net, C_waste]
    u = pd_.get('C_utilities', {})
    C_util_list = [u.get('steam', 0), u.get('electricity', 0), u.get('cooling', 0) + k['extra_util']]

    workers = int(T['labor.operators_per_shift'])
    DWandB = k['wage'] * workers * int(T['labor.shifts']) * int(T['labor.hours_per_shift_yr'])
    C_O = [DWandB, T['labor.supervision_frac'] * DWandB, T['labor.supplies_frac'] * DWandB,
           T['labor.tech_assist_usd'] * workers, T['labor.control_lab_usd'] * workers]

    # maintenance on TDC: chlor-alkali block net of the initial membranes (replaced in OPEX), MVR share, rest
    el = pd_.get('Electrolysis', {}) or {}
    mem_direct = (el.get('membrane_annual_cost', 0) or 0) * C['electrolysis']['membrane_life']
    _CA = C_CA_TDC
    _MVR = sum(CC.get('evaporator', [])) * (C_TDC - _CA) / C_TBM
    _CAm = max(0.0, _CA - mem_direct)
    _REST = C_TDC - _CA - _MVR
    MWB = k['maint_rest'] * _REST + k['maint_mvr'] * _MVR + k['maint_ca'] * _CAm
    pd_['CapitalSplit'] = dict(CA_TDC_level=_CA, MVR_TDC_level=_MVR, REST=_REST)
    C_M = [MWB, 0.25 * MWB, 1.00 * MWB, 0.05 * MWB]

    MOSWB = C_O[0] + C_O[1] + C_M[0] + C_M[1]
    oh = T['overhead.frac']
    C_OH = [oh[0] * MOSWB, oh[1] * MOSWB, oh[2] * MOSWB, oh[3] * MOSWB]
    C_prop = T['property.tax_insurance_frac'] * C_TDC
    C_prop = C_prop * T['property.tax_insurance_frac'] / 0.02
    C_D = [T['depreciation.frac_tdc'] * (C_TDC - 1.18 * C_alloc), T['depreciation.frac_alloc'] * 1.18 * C_alloc, 0, 0]
    COM = sum(C_feed) + sum(C_util_list) + sum(C_O) + sum(C_M) + sum(C_OH) + C_prop + sum(C_D)
    GE = [k['selling'] * S_total, T['general.rd_frac'] * S_total, T['general.allocated_rd_frac'] * S_total,
          T['general.admin_frac'] * S_total, T['general.incentive_frac'] * S_total]

    # ---------------- cash flows
    n = int(T['financial.plant_life_yr'])
    irate = k['discount_rate']
    cp = int(T['financial.construction_yr'])
    MACRS = T['financial.macrs']
    tax = T['financial.tax_rate']
    Ctot = COM + sum(GE)
    wc_c, wc_a, wc_b = T['financial.working_capital_com_frac'], T['financial.working_capital_sales_frac_a'], T['financial.working_capital_sales_frac_b']
    C_WC = wc_c * COM + wc_a * S_total + wc_b * S_total - wc_c * sum(C_feed)
    C_TCI = C_TPI + C_WC
    n_op = n - cp
    A = (irate * (1 + irate) ** n_op) / ((1 + irate) ** n_op - 1)
    OPEX = Ctot - sum(C_D)

    pr = pd_.get('ProductRevenue', {})
    AP = (pr.get('CAOH2', {}).get('flow_kg_hr', 0) + pr.get('CACO3_from_CO2', {}).get('flow_kg_hr', 0)) * op_hr

    CF = np.zeros((n, 9))
    CF_C_TDC, CF_C_WC, CF_C_D, CF_C = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    CF_NE, CF_DCF, CF_PV, CF_NPV = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        if i < cp:
            CF_C_TDC[i] = -C_TDC / cp
            if i == cp - 1:
                CF_C_WC[i] = -C_WC - C_land - C_startup
        if i == cp - 1:
            macrs_end = min(cp + len(MACRS), n)
            CF_C_D[cp:macrs_end] = np.array(MACRS[:macrs_end - cp]) * C_TDC
        if i >= cp:
            CF_C[i] = Ctot - sum(C_D)
            CF_NE[i] = (S_total - CF_C[i] - CF_C_D[i]) * (1 - tax)
        if i == n - 1:
            CF_C_WC[i] = CF_C_WC[i] + C_WC + C_land
    for i in range(n):
        CF_DCF[i] = (CF_NE[i] + CF_C_D[i]) + CF_C_TDC[i] + CF_C_WC[i]
        CF_PV[i] = CF_DCF[i] / (1 + irate) ** i
        CF_NPV[i] = np.sum(CF_PV[:i + 1])
    CF = np.column_stack([CF_C_TDC, CF_C_WC, CF_C_D, CF_C, np.full(n, S_total), CF_NE, CF_DCF, CF_PV, CF_NPV])

    pd_['CASHFLOW'] = CF
    pd_['NPV'] = CF_NPV[-1]
    pd_['EconomicData'] = dict(
        C_EQP=C_EQP, C_comp=C_comp, C_TBM=C_TBM, C_CA_TDC=C_CA_TDC, C_site=C_site, C_serv=C_serv, C_alloc=C_alloc,
        C_DPI=C_DPI, C_cont=C_cont, C_TDC=C_TDC, C_land=C_land, C_royal=0, C_startup=C_startup, C_TPI=C_TPI,
        C_WC=C_WC, C_TCI=C_TCI, C_feed=C_feed, C_util=C_util_list, C_O=C_O, C_M=C_M, C_OH=C_OH, C_prop=C_prop,
        C_D=C_D, C_COM=COM, GE=GE, C=Ctot, S=[S_total], AP=AP, OPEX=OPEX, CRF=A, C_materials_makeup=C_materials_makeup,
        C_materials_net=C_materials_net, C_electrolysis=C_electrolysis_opex, C_waste=C_waste, workers_per_shift=workers,
        n=n, construction=cp, irate=irate, tax=tax, MACRS=list(MACRS))
    return pd_


def npv_standalone(pd_):
    """NPV without the credit on negative taxable income (losses carried forward)."""
    ed = pd_['EconomicData']
    r, cp, n, tax, M = ed['irate'], ed['construction'], ed['n'], ed['tax'], ed['MACRS']
    TDC, WC, land, su, Ssum = ed['C_TDC'], ed['C_WC'], ed['C_land'], ed['C_startup'], ed['S'][0]
    OPEX = ed['C'] - sum(ed['C_D'])
    D = [0.0] * n
    for k, m in enumerate(M):
        if cp + k < n:
            D[cp + k] += m * TDC * (1.0 - 0.0)
    npv, nolb = 0.0, 0.0
    for i in range(n):
        cf = 0.0
        if i < cp:
            cf -= TDC * (1.0 - 0.0) / cp
        if i == cp - 1:
            cf -= WC + land + su
        if i >= cp:
            ti = Ssum + 0.0 - OPEX - D[i]
            use = min(max(ti, 0.0), nolb)
            taxable = ti - use if ti > 0 else 0.0
            nolb = nolb - use + (-ti if ti < 0 else 0.0)
            tp = tax * max(taxable, 0.0)
            cf += Ssum + 0.0 + 0.0 - OPEX - tp
        if i == n - 1:
            cf += WC + land
        npv += cf / (1 + r) ** i
    return npv / 1e6
