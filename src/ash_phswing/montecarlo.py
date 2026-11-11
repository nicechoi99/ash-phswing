"""Monte Carlo of the NPV: triangular draws on the sourced cost ranges (data/parameters/montecarlo_spec.csv), the fee
held at each region's value.  One generator (numpy default_rng(seed)) is shared across the regions in the order
US, EU, KR, JPK, and each variable is drawn for all N samples in turn (the order of the spec rows)."""
import numpy as np

from . import params, tea

REGIONS = ('US', 'EU', 'KR', 'JPK')


def spec(region):
    out = {}
    for r in params.rows('montecarlo_spec.csv'):
        if r['region'] == region:
            out[r['variable']] = (float(r['low']), float(r['mode']), float(r['high']))
    return out


def draw(N=3000, seed=261006, regions=REGIONS):
    rng = np.random.default_rng(seed)

    def tri(lo, mode, hi, n):
        lo, hi = min(lo, hi), max(lo, hi)
        mode = min(max(mode, lo), hi)
        if hi - lo < 1e-12:
            return np.full(n, mode)
        return rng.triangular(lo, mode, hi, n)
    return {reg: {k: tri(*v, N) for k, v in spec(reg).items()} for reg in regions}


def sample_case(base, smp, i):
    mt = smp['maint'][i] / 2.3
    return base.with_(location_factor=base.location_factor * float(smp['capf'][i]), ca_usd_per_t_cl2=float(smp['ca'][i]),
                      energy_kwh_per_t_naoh=float(smp['energy'][i]), maint_rest=mt, maint_mvr=mt, maint_ca=mt,
                      price_caoh2_usd_t=float(smp['pcaoh2'][i]), price_pcc_usd_t=float(smp['ppcc'][i]),
                      mvr_usd_per_tph=float(smp['mvr'][i]), elec_usd_kwh=float(smp['elec'][i]),
                      steam_lp_usd_gj=float(smp['plp'][i]), steam_lt_usd_gj=float(smp['plt'][i]),
                      hcl_price_usd_t=float(smp['hcl'][i]))


def run(N=3000, seed=261006, regions=REGIONS, n_eval=None):
    """n_eval < N evaluates only the first n_eval draws of the full design (for quick checks)."""
    smp_all = draw(N, seed)
    res = {}
    for reg in regions:
        base = tea.base_case(reg)
        smp = smp_all[reg]
        n = N if n_eval is None else n_eval
        Y = np.empty(n)
        Ym = np.empty(n)
        for i in range(n):
            q = tea.evaluate(sample_case(base, smp, i))
            Y[i], Ym[i] = q['NPV'], q['MSP']
        res[reg] = dict(N=int(n), p5=float(np.percentile(Y, 5)), p50=float(np.percentile(Y, 50)), p95=float(np.percentile(Y, 95)),
                        mean=float(Y.mean()), P_gt0=float((Y > 0).mean()), min=float(Y.min()), max=float(Y.max()),
                        MSP_p5=float(np.percentile(Ym, 5)), MSP_p50=float(np.percentile(Ym, 50)), MSP_p95=float(np.percentile(Ym, 95)),
                        NPV=Y.tolist())
    return res
