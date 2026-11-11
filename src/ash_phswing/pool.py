"""Analyses of the design-space campaign pool (data/pool/pool_261026n5.csv; 335 retained Aspen solutions, 1-5 M HCl,
priced with ash_phswing.tea on the base-case price set; EU = co-located base, US = $40/t fee).

surrogate      gradient-boosted trees (XGBoost) on the 12 inputs; quality gate = learning curve on a 25 % hold-out
               (mean absolute error in units of the hold-out standard deviation) and a GP-EI Bayesian-optimization check
elasticity     surrogate-based: mean over the pool of [f(x+) - f(x-)] / |f(x)| / ((x+ - x-) / x), with x+ = 1.1 x and
               x- = 0.9 x clipped to the pool box
shap           mean |SHAP| (TreeExplainer) of the surrogate on the levelized cost and on the EU NPV
nsga2          two objectives, max EU NPV and min net GWP per t ash (system expansion), on random-forest surrogates,
               NSGA-II pop 80, 60 generations, seed 1, bounds = pool box; GWP at any power factor is linear in the factor.
               The forests run single-threaded (n_jobs=1): a multithreaded forest sums its trees in a thread-dependent
               order, the last-digit differences change the NSGA-II trajectory and the front moves by up to ~2 M$.
"""
import numpy as np
import pandas as pd

from .paths import POOL_CSV

FEAT = ["HCl_wt_frac", "ASH_CACO3_mult", "ASH_CAOH2_mult", "ASH_SIO2_mult", "ASH_MGO_mult", "dose_rel", "pH_STG2", "pH_STG3",
        "T_B1", "T_B13", "T_B14", "naoh2_per_ca"]
NICE = {"HCl_wt_frac": "HCl concentration", "ASH_CACO3_mult": "Ash CaCO3", "ASH_CAOH2_mult": "Ash Ca(OH)2",
        "ASH_SIO2_mult": "Ash SiO2", "ASH_MGO_mult": "Ash MgO", "dose_rel": "Acid dose, Stage I", "pH_STG2": "pH, Stage II",
        "pH_STG3": "pH, Stage III", "T_B1": "T, Stage I", "T_B13": "T, Stage II", "T_B14": "T, Stage III",
        "naoh2_per_ca": "NaOH dose, Stage III"}
OPER = {'pH_STG2', 'pH_STG3', 'T_B1', 'T_B13', 'T_B14', 'HCl_wt_frac', 'dose_rel', 'naoh2_per_ca'}


def load(path=POOL_CSV):
    return pd.read_csv(path)


def surrogate():
    import xgboost as xgb
    return xgb.XGBRegressor(n_estimators=700, learning_rate=0.05, max_depth=3, subsample=0.8, colsample_bytree=0.8,
                            reg_lambda=2.0, random_state=0, n_jobs=-1)


def training(d):
    """Learning curve of the surrogate on the levelized cost and a 40-step GP expected-improvement search."""
    from sklearn.model_selection import train_test_split
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import Matern, ConstantKernel
    from scipy.stats import norm
    X, y = d[FEAT].values, d['LC'].values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0)
    sig = float(np.std(yte))
    sizes = np.linspace(0.15, 1.0, 8)
    tr, te = [], []
    for fr in sizes:
        n = max(20, int(len(Xtr) * fr))
        m = surrogate().fit(Xtr[:n], ytr[:n])
        tr.append(np.mean(np.abs(m.predict(Xtr[:n]) - ytr[:n])) / sig)
        te.append(np.mean(np.abs(m.predict(Xte) - yte)) / sig)
    rng = np.random.RandomState(0)
    lo, hi = X.min(0), X.max(0)
    Xn = (X - lo) / np.where(hi - lo == 0, 1, hi - lo)
    sel = list(rng.choice(len(Xn), 20, replace=False))
    best = [y[sel].min()]
    for _ in range(40):
        gp = GaussianProcessRegressor(ConstantKernel(1.0) * Matern(nu=2.5), normalize_y=True, alpha=1e-6, random_state=0).fit(Xn[sel], y[sel])
        mu, sd = gp.predict(Xn, return_std=True)
        imp = y[sel].min() - mu
        with np.errstate(divide='ignore', invalid='ignore'):
            z = np.where(sd > 0, imp / sd, 0.0)
            ei = np.where(sd > 0, imp * norm.cdf(z) + sd * norm.pdf(z), 0.0)
        ei[sel] = -np.inf
        sel.append(int(np.argmax(ei)))
        best.append(y[sel].min())
    return dict(train_sizes=(sizes * len(Xtr)).astype(int).tolist(), mae_train_sigma=[float(v) for v in tr],
                mae_holdout_sigma=[float(v) for v in te], surrogate_mae_sigma=[float(te[0]), float(te[-1])],
                bo_best=[float(v) for v in best], bo=[float(best[0]), float(best[-1]), float(y.min())],
                bo_iter_hit=int(next((i for i, b in enumerate(best) if abs(b - y.min()) < 1e-12), -1)))


def elasticity(d, target):
    X, y = d[FEAT].values, d[target].values
    m = surrogate().fit(X, y)
    y0 = m.predict(X)
    lo, hi = X.min(0), X.max(0)
    e = []
    for j in range(len(FEAT)):
        xp, xm = X.copy(), X.copy()
        xp[:, j] = np.minimum(X[:, j] * 1.10, hi[j])
        xm[:, j] = np.maximum(X[:, j] * 0.90, lo[j])
        dx = (xp[:, j] - xm[:, j]) / X[:, j]
        ok = dx > 1e-6
        e.append(float(np.mean(((m.predict(xp) - m.predict(xm)) / np.abs(y0))[ok] / dx[ok])))
    return {FEAT[i]: e[i] for i in np.argsort(-np.abs(e))}


def shap_importance(d, target):
    import shap
    X, y = d[FEAT].values, d[target].values
    m = surrogate().fit(X, y)
    imp = np.abs(shap.TreeExplainer(m).shap_values(X)).mean(0)
    share = 100 * sum(imp[i] for i, f in enumerate(FEAT) if f in OPER) / imp.sum()
    order = np.argsort(-imp)
    return dict(mean_abs_shap={FEAT[i]: float(imp[i]) for i in order}, operating_share_pct=float(share))


def gwp_at(d, ef, ef_ppa, ef_nl):
    """Net GWP per t ash of every run at power factor ef (linear in ef between the pool's PPA and NL columns)."""
    g_s, g_n = d['GWP_solar_t_ash'].values, d['GWP_grid_t_ash'].values
    return g_s + (ef - ef_ppa) * (g_n - g_s) / (ef_nl - ef_ppa)


def nsga2(d, ef, ef_ppa, ef_nl, base_gwp=None, base_npv=None):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold, cross_val_predict
    from pymoo.core.problem import Problem
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.optimize import minimize
    X, y_npv = d[FEAT].values, d['NPV_EU'].values
    y_g = gwp_at(d, ef, ef_ppa, ef_nl)
    lo, hi = X.min(0), X.max(0)
    kf = KFold(5, shuffle=True, random_state=0)
    mN = RandomForestRegressor(n_estimators=400, random_state=0, n_jobs=1).fit(X, y_npv)
    mG = RandomForestRegressor(n_estimators=400, random_state=0, n_jobs=1).fit(X, y_g)
    cvN = cross_val_predict(RandomForestRegressor(n_estimators=400, random_state=0, n_jobs=1), X, y_npv, cv=kf)
    cvG = cross_val_predict(RandomForestRegressor(n_estimators=400, random_state=0, n_jobs=1), X, y_g, cv=kf)

    class Prob(Problem):
        def __init__(self):
            super().__init__(n_var=len(FEAT), n_obj=2, xl=lo, xu=hi)

        def _evaluate(self, xx, out, *a, **k):
            out["F"] = np.column_stack([mG.predict(xx), -mN.predict(xx)])
    res = minimize(Prob(), NSGA2(pop_size=80), ('n_gen', 60), seed=1, verbose=False)
    fG, fN = res.F[:, 0], -res.F[:, 1]
    nd = np.array([i for i in range(len(y_g)) if not np.any((y_g <= y_g[i]) & (y_npv >= y_npv[i]) & ((y_g < y_g[i]) | (y_npv > y_npv[i])))])
    o2 = np.argsort(y_g[nd])
    jf, jg, ib = int(np.argmax(fN)), int(np.argmin(fG)), int(np.argmax(y_npv))
    return dict(ef=ef, base=dict(GWP=base_gwp, NPV=base_npv),
                cv_mae_npv_sigma=float(np.mean(np.abs(cvN - y_npv)) / y_npv.std()),
                cv_mae_gwp_sigma=float(np.mean(np.abs(cvG - y_g)) / y_g.std()),
                pool=dict(GWP_min=float(y_g.min()), GWP_max=float(y_g.max()), best_NPV=float(y_npv[ib]), GWP_at_best_NPV=float(y_g[ib])),
                non_dominated=[dict(id=int(d.id.iloc[i]), M=int(d.M.iloc[i]), NPV=float(y_npv[i]), GWP=float(y_g[i])) for i in nd[o2]],
                front=dict(GWP=[float(fG.min()), float(fG.max())], NPV=[float(fN.min()), float(fN.max())],
                           GWP_at_max_NPV=float(fG[jf]), NPV_at_min_GWP=float(fN[jg]),
                           HCl_wt_at_max_NPV=float(res.X[jf][FEAT.index('HCl_wt_frac')]),
                           HCl_wt_at_min_GWP=float(res.X[jg][FEAT.index('HCl_wt_frac')])),
                front_points=[dict(GWP=float(a), NPV=float(b)) for a, b in sorted(zip(fG, fN))])
