"""Regional cases of the co-located plant (SI Table S27): EU, US Gulf Coast, Korea 2027 and Japan (the typical
off-site disposal fee of 50,000 JPY/t and the fee of 65,000 JPY/t agreed in Chiba Prefecture).  Same plant and host power; the fee, labor rate and location factor change.

    python -X utf8 scripts/run_regions.py
"""
import _common as C
from ash_phswing import tea, params


def main():
    ref = C.reference()['regions']
    rows, out = [], {}
    for reg in params.regions():
        case = tea.base_case(reg)
        q = tea.evaluate(case)
        rep = tea.report(q)
        be = tea.breakevens(case)
        out[reg] = dict(case=case.as_dict(), report={k: v for k, v in rep.items() if k != 'cashflow'}, breakeven=be)
        rows.append(dict(region=reg, label=case.label, fee_usd_t=case.fee_usd_t, wage_usd_h=case.wage_usd_h,
                         location_factor=case.location_factor, TCI_M=rep['CAPEX']['TCI'], OPEX_M=rep['OPEX']['total'],
                         annual_cost_M=rep['annual_cost'], revenue_M=rep['revenue']['total'], LC=rep['LC'], MSP=rep['MSP'],
                         NPV_M=rep['NPV'], NPV_published_M=ref[reg]['NPV'], breakeven_fee_usd_t=be['fee_usd_t'],
                         breakeven_fee_multiple=be['fee_multiple_of_case'], common_price_usd_t=be['uniform_product_price_usd_t']))
    print(C.table([[r['region'], '%.1f' % r['fee_usd_t'], '%.1f' % r['TCI_M'], '%.1f' % r['revenue_M'], '%.3f' % r['MSP'],
                    '%+.1f' % r['NPV_M'], '%+.1f' % r['NPV_published_M'], '%.0f' % r['breakeven_fee_usd_t'],
                    '%.2f' % r['breakeven_fee_multiple']] for r in rows],
                  ['region', 'fee $/t', 'TCI M$', 'revenue M$/yr', 'net LC $/kg', 'NPV M$', 'published', 'BE fee $/t', 'BE/fee']))
    print('\nwritten', C.rel(C.write_csv('regions.csv', rows)), C.rel(C.write_json('regions.json', out)))


if __name__ == '__main__':
    main()
