"""One-at-a-time NPV sensitivity: uniform +-20 % (Main Fig. 5a) and both ends of the sourced ranges (SI Fig. S19).

    python -X utf8 scripts/run_sensitivity.py [--regions EU US KR JPK]
"""
import argparse

import _common as C
from ash_phswing import sensitivity as SE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--regions', nargs='*', default=['EU', 'US', 'KR', 'JPK'])
    a = ap.parse_args()
    ref = C.reference()
    out = {'uniform': {}, 'sourced': {}}
    rows = []
    for reg in a.regions:
        tu = SE.tornado_uniform(reg)
        ts = SE.tornado_sourced(reg)
        out['uniform'][reg], out['sourced'][reg] = tu, ts
        for kind, t in (('uniform_20pct', tu), ('sourced_range', ts)):
            for b in t['bars']:
                rows.append(dict(region=reg, kind=kind, key=b['key'], label=b['label'], values=b.get('values', '-20 / +20 %'),
                                 NPV_base=t['base_NPV'], NPV_low_input=b['NPV_low_input'], NPV_high_input=b['NPV_high_input'],
                                 span=b['span'], source=b.get('source', '')))
    eu = out['uniform'].get('EU')
    if eu:
        r = {b['key']: b for b in ref['tornado_uniform_EU']['bars']}
        print('Uniform +-20 %%, EU NPV (base %.1f M$)' % eu['base_NPV'])
        print(C.table([[b['key'], '%.1f' % b['NPV_low_input'], '%.1f' % b['NPV_high_input'], '%.1f' % b['span'],
                        '%.1f / %.1f' % (r[b['key']]['NPV_low_input'], r[b['key']]['NPV_high_input'])] for b in eu['bars']],
                      ['input', 'NPV at -20 %', 'NPV at +20 %', 'span', 'published']))
    for reg in a.regions:
        t = out['sourced'][reg]
        r = {b['key']: b for b in ref['tornado_sourced'].get(reg, {}).get('bars', [])}
        print('\nSourced ranges, %s NPV (base %.1f M$)' % (reg, t['base_NPV']))
        print(C.table([[b['key'], b['values'], '%.1f' % b['NPV_low_input'], '%.1f' % b['NPV_high_input'], '%.1f' % b['span'],
                        ('%.1f / %.1f' % (r[b['key']]['NPV_low_input'], r[b['key']]['NPV_high_input'])) if b['key'] in r else '-']
                       for b in t['bars']], ['input', 'range', 'NPV low input', 'NPV high input', 'span', 'published']))
    print('\nwritten', C.rel(C.write_csv('sensitivity.csv', rows)), C.rel(C.write_json('sensitivity.json', out)))


if __name__ == '__main__':
    main()
