"""Campaign pool: surrogate quality gate, Bayesian-optimization check, elasticities and SHAP (Main Fig. 5b, SI Figs.
S28-S29), plus pool statistics.

    python -X utf8 scripts/run_surrogate_shap.py
"""
import numpy as np
from scipy.stats import spearmanr

import _common as C
from ash_phswing import pool


def main():
    d = pool.load()
    ref = C.reference()['pool']
    tr = pool.training(d)
    el_lc, el_npv = pool.elasticity(d, 'LC'), pool.elasticity(d, 'NPV_EU')
    sh_npv, sh_lc = pool.shap_importance(d, 'NPV_EU'), pool.shap_importance(d, 'LC')
    sp = lambda x, y: float(spearmanr(d[x], d[y])[0])
    stats = dict(n=int(len(d)), n_by_M={int(k): int(v) for k, v in d.groupby('M').size().items()},
                 n_NPV_EU_positive=int((d.NPV_EU > 0).sum()),
                 median_NPV_EU_by_M={int(k): float(v) for k, v in d.groupby('M').NPV_EU.median().items()},
                 median_TCI_by_M={int(k): float(v) for k, v in d.groupby('M').TCI.median().items()},
                 median_evap_t_h_by_M={int(k): float(v) for k, v in d.groupby('M').evap_t_h.median().items()},
                 stageII_pH_error_median=float((d.ph2_ach - d.pH_STG2).abs().median()),
                 stageII_within_0p1_pct=float(((d.ph2_ach - d.pH_STG2).abs() <= 0.1).mean() * 100),
                 stageIII_pH_error_median=float((d.ph3_ach - d.pH_STG3).abs().median()),
                 stageIII_within_0p1_pct=float(((d.ph3_ach - d.pH_STG3).abs() <= 0.1).mean() * 100),
                 rho_naoh_rec3_by_M={int(m): float(spearmanr(g.naoh2_per_ca, g.rec3_pct)[0]) for m, g in d.groupby('M')},
                 rho_T3_naoh=sp('T_B14', 'naoh2_per_ca'), rho_naoh_NPV=sp('naoh2_per_ca', 'NPV_EU'),
                 naoh_pure_per_ca_median=float(d.naoh2_pure_per_ca.median()))
    print('pool n = %d, positive EU NPV %d' % (stats['n'], stats['n_NPV_EU_positive']))
    print('hold-out MAE of the levelized-cost surrogate: %.3f -> %.3f sigma (published %.3f -> %.3f)'
          % (tr['surrogate_mae_sigma'][0], tr['surrogate_mae_sigma'][1], ref['surrogate_mae_sigma'][0], ref['surrogate_mae_sigma'][1]))
    print('Bayesian optimization: best %.4f after %d iterations, campaign minimum %.4f' % (tr['bo'][1], tr['bo_iter_hit'], tr['bo'][2]))
    print('\nMean |SHAP| on the EU NPV (M$); operating share %.1f %% (published %.1f %%)'
          % (sh_npv['operating_share_pct'], ref['shap_NPV_operating_share']))
    print(C.table([[pool.NICE[k], '%.2f' % v, '%.2f' % ref['shap_NPV_EU'][k]] for k, v in sh_npv['mean_abs_shap'].items()],
                  ['input', 'this code', 'published']))
    print('\nMean |SHAP| on the levelized cost: operating share %.1f %% (published %.1f %%)'
          % (sh_lc['operating_share_pct'], ref['shap_LC_operating_share']))
    print('\nElasticity (% per %)')
    print(C.table([[pool.NICE[k], '%.3f' % v, '%.3f' % el_npv[k]] for k, v in el_lc.items()], ['input', 'levelized cost', 'EU NPV']))
    out = dict(stats=stats, training=tr, elasticity_LC=el_lc, elasticity_NPV_EU=el_npv, shap_NPV_EU=sh_npv, shap_LC=sh_lc)
    print('\nwritten', C.rel(C.write_json('surrogate_shap.json', out)))


if __name__ == '__main__':
    main()
