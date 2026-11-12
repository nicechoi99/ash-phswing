"""Stage III pH ladder (Section 2.4, SI Figs. S23 and S25a): price the saved Aspen solutions at pH3 12.2-14.0 and pick the
design pH3 = the highest EU NPV inside the experimental window 12.5-13.0 (pH3 12.0 is infeasible: the brine carries too
little sodium to regenerate the Stage I acid and no solution is saved).

    python -X utf8 scripts/run_ph3_ladder.py
"""
import os

import _common as C
from ash_phswing import tea, paths

WINDOW = (12.5, 13.0)


def main():
    files = sorted(os.listdir(paths.LADDER_DIR)) + [os.path.basename(paths.DESIGN_FLOWSHEET)]
    ref = {r['pH3']: r for r in C.reference()['ph3_ladder']}
    rows = []
    for f in files:
        ph = int(f.split('_p')[-1][:3]) / 10.0
        fs = paths.DESIGN_FLOWSHEET if f.startswith('design') else os.path.join(paths.LADDER_DIR, f)
        e = tea.evaluate(tea.base_case('EU', flowsheet=fs))
        u = tea.evaluate(tea.base_case('US', flowsheet=fs))
        rows.append(dict(pH3=ph, in_window=WINDOW[0] - 1e-9 <= ph <= WINDOW[1] + 1e-9, NPV_EU=e['NPV'], MSP_EU=e['MSP'], LC=e['LC'],
                         NPV_US=u['NPV'], TCI=e['TCI'], AP_kt=e['AP_kt'], CaOH2_kt=e['lime_kt'], PCC_kt=e['pcc_kt'],
                         elec_GWh=e['elec_GWh'], NPV_EU_published=ref[ph]['NPV_EU']))
    rows.sort(key=lambda r: r['pH3'])
    best = max((r for r in rows if r['in_window']), key=lambda r: r['NPV_EU'])
    print(C.table([['%.1f' % r['pH3'], 'yes' if r['in_window'] else '', '%+.1f' % r['NPV_EU'], '%+.1f' % r['NPV_EU_published'],
                    '%.3f' % r['MSP_EU'], '%.1f' % r['TCI'], '%.1f' % r['AP_kt']] for r in rows],
                  ['pH3', 'window', 'NPV EU M$', 'published', 'net LC $/kg', 'TCI M$', 'products kt/yr']))
    print('design pH3 = %.1f (EU NPV %+.1f M$)' % (best['pH3'], best['NPV_EU']))
    print('written', C.rel(C.write_csv('ph3_ladder.csv', rows)))


if __name__ == '__main__':
    main()
