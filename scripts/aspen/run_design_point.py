"""REQUIRES ASPEN PLUS V14 (Windows, pywin32).  Solve the design point (and the Stage III pH ladder) on the measured-
CaCl2 composite feed and save the results for the cost model.

    python -X utf8 scripts/aspen/run_design_point.py --ph3 13.0
    python -X utf8 scripts/aspen/run_design_point.py --ph3 12.2 12.4 12.5 12.6 12.8 13.2 13.4 --template <5 M bkp>

Protocol (the one that produced data/aspen/design_COMP_p130.json):
  * ASH feed = feeds.json 'COMP' (CISOLID kg/h incl. CaCl2(S); MIXED: 30,000 kg/h water + K+ / Cl-), HCl 16.83 wt% (5 M);
  * Stage I: DS-STG1 pinned at the measured endpoint dose (feeds.json acid_kg_h), not a pH target;
  * Stage II pH 11.0 and Stage III pH3 by outside bisection on NaOH1 / NaOH2, Stage II then III per pass, repeated until
    both are within 0.05 pH (at least 2 passes, at most 6); 25 C in B1, B13, B14;
  * a final confirming run at the three pins; the saved state is that run.
Outputs (under --out): <name>.pkl (access_data format), <name>.json (ash_phswing.flowsheet), <name>.bkp, ckpt.json.
The shipped template is the design-point model (Stage IV blocks re-specified, see README); the published runs used the
5 M flowsheet template from which it was derived, which differs only in Stage IV and in the initial flows.
"""
import argparse
import json
import os
import pickle
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from ash_phswing.aspen.session import Session            # noqa: E402
from ash_phswing.aspen.access_data import access_data    # noqa: E402
from ash_phswing import flowsheet as FS                   # noqa: E402

PH2 = 11.0
REF_EQ = 494.6                     # kmol/h base equivalents of the reference feed (bisection bracket scale)


def solve(template, out, feed, feed_name, ph3, hcl_wt, log):
    name = '%s_p%s' % (feed_name, str(ph3).replace('.', ''))
    s = Session(template, os.path.join(out, 'work', '_%s.bkp' % name), log)
    acid = feed['acid_kg_h']
    sc = max(feed['base_eq_corrected_kmol_h'] / REF_EQ, 0.5)

    def setup():
        s.set_feed(feed['cis'], feed['mix'], 30000.0, hcl_wt)
        s.set_targets(4.0, PH2, ph3, 25.0, 25.0, 25.0)

    def recover():
        s.close(); s.open(); setup(); s.pin(1, acid)

    t0 = time.time()
    s.open()
    try:
        setup(); s.pin(1, acid)
        ph2 = n1 = ph3a = n2 = None
        passes = 0
        for k in range(6):
            passes = k + 1
            setup(); s.pin(1, acid)
            ph2, n1, _, _ = s.bisect(2, PH2, 1000.0, 75000.0 * sc, pins=((1, acid),), iters=24, recover=recover, clip_tol=0.0011)
            s.pin(2, n1)
            ph3a, n2, _, _ = s.bisect(3, ph3, 5000.0, 160000.0 * sc, pins=((1, acid), (2, n1)), iters=24, recover=recover, clip_tol=0.0011)
            s.pin(3, n2)
            log('%s pass %d: pH2 %.3f (NaOH1 %.1f) pH3 %.3f (NaOH2 %.1f)' % (name, k + 1, ph2, n1, ph3a, n2))
            if k >= 1 and abs(ph2 - PH2) < 0.05 and abs(ph3a - ph3) < 0.05:
                break
        pins = ((1, acid), (2, n1), (3, n2))
        s.run(check=s.pins_ok(pins), recover=recover)                 # confirming run
        v = {n: s.ds(n) for n in (1, 2, 3)}
        assert abs(v[1][0] - acid) < 0.0011 * acid, ('Stage I dose not held', v[1][0], acid)
        p = access_data({}, s.h)
        meta = dict(name=name, feed=feed_name, pH3_target=ph3, pH2_target=PH2, hcl_wt=hcl_wt, acid_kg_hr=acid,
                    ph1=v[1][1], ph2=v[2][1], ph3=v[3][1], ph2_bisect=ph2, ph3_bisect=ph3a, naoh1=v[2][0], naoh2=v[3][0],
                    passes=passes, secs=round(time.time() - t0, 1),
                    ok=int(abs(ph2 - PH2) < 0.05 and abs(ph3a - ph3) < 0.05))
        pk = os.path.join(out, name + '.pkl')
        with open(pk, 'wb') as f:
            pickle.dump({'processData': p, 'meta': meta}, f)
        FS.export_pickle(pk, os.path.join(out, name + '.json'), meta)
        s.save_as(os.path.join(out, name + '.bkp'))
        return meta
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--template', default=os.path.join(ROOT, 'data', 'aspen', 'model', '261026_AshpHSwing5M-NaOH5N_MVR-Converged.bkp'))
    ap.add_argument('--feeds', default=os.path.join(ROOT, 'data', 'aspen', 'feeds.json'))
    ap.add_argument('--feed', default='COMP')
    ap.add_argument('--ph3', type=float, nargs='+', default=[13.0])
    ap.add_argument('--hcl-wt', type=float, default=0.1683)
    ap.add_argument('--out', default=os.path.join(ROOT, 'results', 'aspen', 'design'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(a.feeds, encoding='utf-8') as f:
        feed = json.load(f)['feeds'][a.feed]
    ck = os.path.join(a.out, 'ckpt.json')
    done = json.load(open(ck)) if os.path.exists(ck) else {}
    for ph3 in a.ph3:
        name = '%s_p%s' % (a.feed, str(ph3).replace('.', ''))
        if name in done:
            continue
        done[name] = solve(a.template, a.out, feed, a.feed, ph3, a.hcl_wt, lambda *m: print(*m, flush=True))
        with open(ck, 'w') as f:
            json.dump(done, f, indent=1)
    for k, r in sorted(done.items()):
        print('%-12s pH %.3f / %.3f / %.3f  NaOH1 %.1f  NaOH2 %.1f  ok %d' % (k, r['ph1'], r['ph2'], r['ph3'], r['naoh1'], r['naoh2'], r['ok']))


if __name__ == '__main__':
    main()
