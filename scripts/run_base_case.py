"""EU co-located base case from the saved design-point Aspen results (no Aspen needed).

    python -X utf8 scripts/run_base_case.py [--region EU]

Prints the key results next to the published values and writes results/base_case_<region>.json
(report: CAPEX / OPEX / revenue items, cash-flow table, break-even conditions, LCA cases).
"""
import argparse

import _common as C
from ash_phswing import tea, lca


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', default='EU')
    a = ap.parse_args()
    case = tea.base_case(a.region)
    q = tea.evaluate(case)
    rep = tea.report(q)
    be = tea.breakevens(case)
    L = lca.assess(q)
    ref = C.reference()['regions'][a.region]
    lref = C.reference()['lca']
    cs = {c['label']: c for c in L['cases']}
    rows = [
        ('NPV, 20 yr (M$)', '%.1f' % rep['NPV'], '%.1f' % ref['NPV']),
        ('NPV without the tax credit (M$)', '%.1f' % rep['NPV_standalone'], '%.1f' % ref['NPV_standalone']),
        ('TCI (M$)', '%.1f' % rep['CAPEX']['TCI'], '%.1f' % ref['TCI']),
        ('TDC (M$)', '%.1f' % rep['CAPEX']['TDC'], '%.1f' % ref['TDC']),
        ('OPEX (M$/yr)', '%.1f' % rep['OPEX']['total'], '%.1f' % ref['cash_opex']),
        ('Annualized CAPEX (M$/yr)', '%.1f' % rep['capital_charge'], '%.1f' % ref['capital_charge']),
        ('Annual cost (M$/yr)', '%.1f' % rep['annual_cost'], '%.1f' % ref['annual_cost']),
        ('Revenue (M$/yr)', '%.1f' % rep['revenue']['total'], '%.1f' % ref['revenue']),
        ('  treatment fee (M$/yr)', '%.1f' % rep['revenue']['items']['ASH_gate_fee'], '%.1f' % ref['revenue_items']['ASH_gate_fee']),
        ('  surplus HCl (M$/yr)', '%.1f' % rep['revenue']['items']['HCL_surplus'], '%.1f' % ref['revenue_items']['HCL_surplus']),
        ('  Ca(OH)2 (M$/yr)', '%.1f' % rep['revenue']['items']['CAOH2'], '%.1f' % ref['revenue_items']['CAOH2']),
        ('  PCC (M$/yr)', '%.1f' % rep['revenue']['items']['CACO3_from_CO2'], '%.1f' % ref['revenue_items']['CACO3_from_CO2']),
        ('Products Ca(OH)2 / PCC / total (kt/yr)', '%.1f / %.1f / %.1f' % (rep['products']['CaOH2_kt'], rep['products']['PCC_kt'], rep['products']['total_kt']),
         '%.1f / %.1f / %.1f' % (ref['products']['CaOH2_kt'], ref['products']['PCC_kt'], ref['products']['total_kt'])),
        ('Levelized cost ($/kg)', '%.3f' % rep['LC'], '%.3f' % ref['LC']),
        ('Net levelized cost ($/kg) [engine key MSP]', '%.3f' % rep['MSP'], '%.3f' % ref['MSP']),
        ('Common product price at NPV = 0 ($/t)', '%.0f' % be['uniform_product_price_usd_t'], '%.0f' % ref['breakeven']['uniform_product_price_usd_t']),
        ('Break-even treatment fee ($/t)', '%.0f' % be['fee_usd_t'], '%.0f' % ref['breakeven']['fee_usd_t']),
        ('Electricity (GWh/yr) / Cl2 (kt/yr)', '%.0f / %.1f' % (rep['electricity_GWh'], rep['Cl2_kt']), '%.0f / %.1f' % (ref['electricity_GWh'], ref['Cl2_kt'])),
    ]
    if a.region == 'EU':
        ppa = cs['EU renewable PPA']
        lp = {c['label']: c for c in lref['cases']}['EU renewable PPA']
        rows += [('Net GWP, incinerator power (kg CO2-eq/t ash)', '%.0f' % L['base']['net_per_t_ash'], '%.0f' % lref['base']['net_per_t_ash']),
                 ('Net GWP, EU PPA (kg CO2-eq/t ash)', '%.0f' % ppa['net_per_t_ash'], '%.0f' % lp['net_per_t_ash']),
                 ('Footprint, incinerator power (kg CO2-eq/kg)', '%.3f' % L['base']['footprint_per_kg'], '%.3f' % lref['base']['footprint_per_kg']),
                 ('Footprint, EU PPA (kg CO2-eq/kg)', '%.3f' % ppa['footprint_per_kg'], '%.3f' % lp['footprint_per_kg'])]
    print('Base case %s (%s): fee $%.1f/t, host power $%.3f/kWh' % (a.region, case.label, case.fee_usd_t, case.elec_usd_kwh))
    print(C.table([list(r) for r in rows], ['quantity', 'this code', 'published']))
    out = dict(case=case.as_dict(), report=rep, breakeven=be, lca=L, comparison=[dict(quantity=r[0], model=r[1], published=r[2]) for r in rows])
    p = C.write_json('base_case_%s.json' % a.region, out)
    print('\nwritten', C.rel(p))


if __name__ == '__main__':
    main()
