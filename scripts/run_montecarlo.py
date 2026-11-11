"""Monte Carlo of the NPV (SI Fig. S20): 3,000 triangular draws per region on the sourced cost ranges, fee held.

    python -X utf8 scripts/run_montecarlo.py [--N 3000] [--seed 261006] [--n-eval K]

The full run is 4 x 3,000 cost-model evaluations (about 3 min).  --n-eval K evaluates only the first K
draws of the same design (quick check).
"""
import argparse
import time

import _common as C
from ash_phswing import montecarlo as MC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--N', type=int, default=3000)
    ap.add_argument('--seed', type=int, default=261006)
    ap.add_argument('--n-eval', type=int, default=None)
    a = ap.parse_args()
    t0 = time.time()
    res = MC.run(N=a.N, seed=a.seed, n_eval=a.n_eval)
    ref = C.reference()['monte_carlo']
    rows = []
    for reg, r in res.items():
        rows.append([reg, r['N'], '%.1f' % r['p5'], '%.1f' % r['p50'], '%.1f' % r['p95'], '%.1f' % (100 * r['P_gt0']),
                     '%.1f / %.1f%%' % (ref[reg]['p50'], 100 * ref[reg]['P_gt0'])])
    print(C.table(rows, ['region', 'N', 'p5 M$', 'median M$', 'p95 M$', 'P(NPV>0) %', 'published median / P']))
    print('%.0f s' % (time.time() - t0))
    out = {reg: {k: v for k, v in r.items()} for reg, r in res.items()}
    print('written', C.rel(C.write_json('montecarlo.json', dict(N=a.N, seed=a.seed, n_eval=a.n_eval, regions=out))))


if __name__ == '__main__':
    main()
