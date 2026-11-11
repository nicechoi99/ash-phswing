"""NSGA-II on random-forest surrogates of the campaign pool: max EU NPV vs min net GWP per t ash (Main Fig. 6d, SI Fig. S30),
on incinerator power (EF 0, the TEA power case) and on the Netherlands grid.

    python -X utf8 scripts/run_nsga2.py
"""
import _common as C
from ash_phswing import pool, params, tea, lca


def main():
    d = pool.load()
    F = params.lca()
    base = tea.evaluate(tea.base_case('EU'))
    L = lca.assess(base)
    cs = {c['label']: c for c in L['cases']}
    ref = C.reference()['pool']['nsga2_published']
    out = {}
    for key, ef, G0 in (('host', 0.0, L['base']['net_per_t_ash']), ('NL', F['EF_GRID_NL'], cs['Netherlands grid']['net_per_t_ash'])):
        r = pool.nsga2(d, ef, F['EF_SOLAR'], F['EF_GRID_NL'], base_gwp=G0, base_npv=base['NPV'])
        out[key] = r
        fr, pf = r['front'], ref['cases'][key]['front']
        print('%s: NSGA-II front NPV %.1f..%.1f M$ (published %.1f..%.1f), GWP %.1f..%.1f kg/t ash (published %.1f..%.1f); '
              'non-dominated pool runs %d (published %d); CV MAE GWP %.3f sigma'
              % (key, fr['NPV'][0], fr['NPV'][1], pf['NPV'][0], pf['NPV'][1], fr['GWP'][0], fr['GWP'][1], pf['GWP'][0], pf['GWP'][1],
                 len(r['non_dominated']), ref['cases'][key]['n_non_dominated'], r['cv_mae_gwp_sigma']))
    print('CV MAE of the NPV forest %.4f sigma (published %.4f)' % (out['host']['cv_mae_npv_sigma'], ref['cv_mae_npv_sigma']))
    print('written', C.rel(C.write_json('nsga2.json', out)))


if __name__ == '__main__':
    main()
