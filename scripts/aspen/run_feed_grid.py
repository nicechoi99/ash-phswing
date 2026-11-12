"""REQUIRES ASPEN PLUS V14 (Windows, pywin32).  Feed-concentration grid of the dry-ash flowsheet (SI Fig. S24):
HCl wt% x Stage II NaOH1 wt%, Stage III NaOH2 at the cell strength (17 wt%), Stage III pH 13.0.

    python -X utf8 scripts/aspen/run_feed_grid.py [case ...] [--workers 5] [--redo-failed]

Protocol per case:
  1. Stage I adiabatic probe on a fresh copy (B1 DUTY = 0; Stage I is feed-forward), then B1 isothermal at
     T1 = min(T_adiabatic, 45 C).
  2. Stage I pinned at the calibrated dose (acid moles fixed, solution mass = moles x MW / wt); Stage II (pH 11.0)
     and Stage III (pH 13.0) by outside bisection, up to 6 passes, every pin read back and FINAL_VAL[1] checked
     against the pin (no clipping, Clip otherwise).
  3. Stage II buffer jump: when the bisection bracket on NaOH1 collapses (< 0.5 % of the flow) while pH2 is still more than
     0.10 off 11.0, the model has two steady states on either side of the titration jump.  The UPPER branch is taken: the
     smallest bisected NaOH1 flow whose pH2 was at or above 11.0 (x 1.0002), Stage III re-bisected on it, accepted when
     10.95 <= pH2 <= 11.40.  The jump spans < 1 kg/h of NaOH1, so the dose is the same on both branches.
  4. Final run at the three pins, repeated up to 4 times on the buffer plateau; ok = 1 (both pH within 0.05, or the upper
     branch), ok = 2 (within 0.10 on a resolved Stage II flow).
Outputs (under --out): <case>.pkl, <case>.json, <case>.bkp, ckpt.json.
"""
import argparse
import json
import multiprocessing as mp
import os
import pickle
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(ROOT, 'src'))

KCL_CARRIER = 3700.0               # ASH stream water of the dry-ash flowsheet (KCl carrier), kg/h
SLURRY_W = 30000.0
KP, CLM = 687.23, 623.17           # dissolved K+ / Cl- of the ASH stream, kg/h
MW_NAOH, MW_H2O = 39.997, 18.015
PH2_T, PH3_T, T1_MAX = 11.0, 13.0, 45.0
HCL_GRID = [('3.6', 0.0358), ('7', 0.07), ('10.5', 0.105), ('14', 0.14), ('16.8', 0.1683), ('20', 0.20), ('25', 0.25), ('30', 0.30)]
N1_GRID = [('10', 0.10), ('14', 0.14), ('17', 0.17), ('20', 0.20), ('24', 0.24)]
CASES = {}
for hl, h in HCL_GRID:
    for nl, n in N1_GRID:
        CASES['D_h%s_n%s' % (hl, nl)] = dict(ash_w=KCL_CARRIER, hcl=h, n1=n, n2_mol=0.17)
CASES['R_anchor_slurry'] = dict(ash_w=SLURRY_W, hcl=0.1683, n1=0.17, n2_mol=0.17)
CASES['R_exp_slurry'] = dict(ash_w=SLURRY_W, hcl=0.0358, n1=0.17, n2_mol=0.17)


def worker(job):
    name, cfg, opt = job
    t0 = time.time()
    rec = dict(name=name, cfg=cfg, ok=0, reason=None, hist={2: [], 3: []})
    try:
        return _worker(name, cfg, opt, rec, t0)
    except Exception as ex:
        rec['reason'] = 'exception: ' + str(ex)[:300]
        rec['trace'] = traceback.format_exc()[-1500:]
        rec['secs'] = round(time.time() - t0, 1)
        return rec


def _worker(name, cfg, opt, rec, t0):
    from ash_phswing.aspen.session import Session, Clip, path
    from ash_phswing.aspen.access_data import access_data
    from ash_phswing import flowsheet as FS
    with open(opt['feeds'], encoding='utf-8') as f:
        F = json.load(f)['feeds']['COMP']
    comp = dict(F['cis'])
    WT = cfg['hcl']
    acid = F['acid_kg_h'] * 0.1683 / WT                        # calibrated dose (feeds.json COMP), any acid strength
    s1 = 0.17 / cfg['n1']
    wt2 = cfg['n2_mol'] * MW_NAOH / (cfg['n2_mol'] * MW_NAOH + (1 - cfg['n2_mol']) * MW_H2O)
    s2 = 0.3131 / wt2
    s3 = max(1.0, 0.1683 / WT) ** 0.5                         # Stage III bracket widened for the dilute cases
    log = lambda *m: print('[%s]' % name, *m, flush=True)
    s = Session(opt['template'], os.path.join(opt['out'], 'work', '_%s.bkp' % name), log)
    st = dict(t1=25.0)
    BIN = lambda b, k: path('Data', 'Blocks', b, 'Input', k)
    BOUT = lambda b, k: path('Data', 'Blocks', b, 'Output', k)

    def setup():
        s.set_feed(comp, {'K+': KP, 'CL-': CLM}, cfg['ash_w'], WT)
        for strm, frac in (('NAOH1', cfg['n1']), ('NAOH2', cfg['n2_mol'])):
            N = path('Data', 'Streams', strm, 'Input', 'FLOW', 'MIXED') + '\\'
            s.W(N + 'NAOH', frac); s.W(N + 'WATER', 1.0 - frac)
        s.set_targets(4.0, PH2_T, PH3_T, st['t1'], 25.0, 25.0)
        assert abs(float(s.R(BIN('B1', 'TEMP'))) - st['t1']) < 1e-6

    def recover():
        s.close(); s.open(); setup()

    # ---------------- 1. adiabatic probe of Stage I
    s.open(); setup()
    s.pin(1, acid); s.pin(2, 16000.0 * s1); s.pin(3, 50000.0 * s2 * s3)

    def adia():
        s.W(BIN('B1', 'SPEC_OPT'), 'DUTY'); s.W(BIN('B1', 'TEMP'), ''); s.W(BIN('B1', 'DUTY'), 0.0)

    def adia_ok():
        q, tt = s.R(BOUT('B1', 'QCALC')), s.R(BOUT('B1', 'B_TEMP'))
        if q is None or tt is None:
            return 'B1 result missing'
        return None if abs(float(q)) < 10.0 else 'B1 QCALC %.0f cal/s (stale result)' % float(q)
    adia()
    try:
        s.run(check=adia_ok, recover=lambda: (recover(), s.pin(1, acid), adia()))
        t_ad = float(s.R(BOUT('B1', 'B_TEMP')))
    except Exception as ex:
        log('adiabatic probe failed: %s' % str(ex)[:80])
        t_ad = None
    s.close()
    if t_ad is None:
        raise RuntimeError('adiabatic probe failed; T1 undetermined')
    st['t1'] = T1_MAX if t_ad > T1_MAX else round(t_ad, 3)
    rec.update(T1_adiabatic_C=round(t_ad, 2), T1_C=st['t1'], acid_kg_hr=round(acid, 1))

    # ---------------- 2. Stage I pinned, Stage II / III bisected
    s.open(); setup(); s.pin(1, acid); s.pin(3, 50000.0 * s2 * s3)
    b2 = (4000.0 * s1, 80000.0 * s1)
    b3 = (15000.0 * s2, 140000.0 * s2 * s3)
    passes = 0
    for k in range(6):
        passes = k + 1
        setup(); s.pin(1, acid)
        ph2, n1, lo2, hi2 = s.bisect(2, PH2_T, b2[0], b2[1], pins=((1, acid),), recover=recover, hist=rec['hist'][2])
        s.pin(2, n1)
        ph3, n2, lo3, hi3 = s.bisect(3, PH3_T, b3[0], b3[1], pins=((1, acid), (2, n1)), recover=recover, hist=rec['hist'][3])
        s.pin(3, n2)
        log('pass %d pH2 %.3f | pH3 %.3f  n1 %.1f n2 %.1f' % (k + 1, ph2, ph3, n1, n2))
        if k >= 1 and abs(ph2 - PH2_T) < 0.05 and abs(ph3 - PH3_T) < 0.05:
            break
        if k >= 2 and abs(ph2 - PH2_T) >= 0.05 and abs(hi2 - lo2) < 1.0:
            break                                            # bracket collapsed on the discontinuity
    # ---------------- 3. Stage II buffer jump -> upper branch
    rec['upper_branch'] = False
    if abs(ph2 - PH2_T) >= 0.10 and abs(hi2 - lo2) < 0.005 * n1:
        up = sorted(p for p in rec['hist'][2] if p[1] >= PH2_T)
        n1 = (up[0][0] if up else hi2) * 1.0002
        rec['upper_branch'] = True
        log('Stage II jump: upper branch NaOH1 %.1f' % n1)
        for k2 in range(3):
            setup(); s.pin(1, acid); s.pin(2, n1)
            ph3, n2, lo3, hi3 = s.bisect(3, PH3_T, b3[0], b3[1], pins=((1, acid), (2, n1)), recover=recover, hist=rec['hist'][3])
            s.pin(3, n2)
            ph2 = s.ds(2)[1]
            if PH2_T - 0.05 <= ph2 <= 11.40 and abs(ph3 - PH3_T) < 0.05:
                break
            n1 *= 1.0005
    # ---------------- 4. final runs at the three pins
    pins = ((1, acid), (2, n1), (3, n2))
    finals = []

    def inside(ph2_, ph3_):
        return (abs(ph2_ - PH2_T) < 0.05 or (rec['upper_branch'] and PH2_T - 0.05 <= ph2_ <= 11.40)) and abs(ph3_ - PH3_T) < 0.05
    for rr in range(5):
        if rr:
            s.run(check=s.pins_ok(pins), recover=recover)
        ph1, ph2, ph3 = s.ds(1)[1], s.ds(2)[1], s.ds(3)[1]
        finals.append((round(ph2, 4), round(ph3, 4)))
        if inside(ph2, ph3):
            break
    if not rec['upper_branch'] and not inside(ph2, ph3):
        for rr in range(4):
            if abs(ph2 - PH2_T) < 0.10 and abs(ph3 - PH3_T) < 0.05:
                break
            s.run(check=s.pins_ok(pins), recover=recover)
            ph1, ph2, ph3 = s.ds(1)[1], s.ds(2)[1], s.ds(3)[1]
            finals.append((round(ph2, 4), round(ph3, 4)))
    for n, x in pins:
        if abs(s.ds(n)[0] - x) >= 0.002 * x:
            raise Clip('final run DS-STG%d clipped' % n)
    ok = int(inside(ph2, ph3))
    if not ok and abs(ph3 - PH3_T) < 0.05 and abs(ph2 - PH2_T) < 0.10 and abs(hi2 - lo2) < 0.005 * n1:
        ok = 2
    p = access_data({}, s.h)
    meta = dict(name=name, cfg=cfg, T1_C=st['t1'], acid_kg_hr=acid, ph1=ph1, ph2=ph2, ph3=ph3, naoh1=n1, naoh2=n2,
                upper_branch=rec['upper_branch'], ok=ok)
    pk = os.path.join(opt['out'], name + '.pkl')
    with open(pk, 'wb') as f:
        pickle.dump({'processData': p, 'meta': meta}, f)
    FS.export_pickle(pk, os.path.join(opt['out'], name + '.json'), meta)
    s.save_as(os.path.join(opt['out'], name + '.bkp'))
    s.close()
    rec.update(ph1=round(ph1, 3), ph2=round(ph2, 3), ph3=round(ph3, 3), naoh1=round(n1, 1), naoh2=round(n2, 1), passes=passes,
               final_runs=finals, stageII_bracket_kg_h=round(abs(hi2 - lo2), 2), secs=round(time.time() - t0, 1), ok=ok, pkl=pk)
    log('done %.0fs pH %.3f/%.3f/%.3f ok %d' % (rec['secs'], ph1, ph2, ph3, ok))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cases', nargs='*')
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--redo-failed', action='store_true')
    ap.add_argument('--template', default=os.path.join(ROOT, 'data', 'aspen', 'model', '261026_AshpHSwing5M-NaOH5N_MVR-Converged.bkp'))
    ap.add_argument('--feeds', default=os.path.join(ROOT, 'data', 'aspen', 'feeds.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'results', 'aspen', 'feed_grid'))
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'work'), exist_ok=True)
    opt = dict(template=a.template, feeds=a.feeds, out=a.out)
    ck = os.path.join(a.out, 'ckpt.json')
    want = a.cases or [c for c in CASES if c.startswith('D_')]
    done = json.load(open(ck)) if os.path.exists(ck) else {}
    todo = [(n, CASES[n], opt) for n in want if n not in done or (a.redo_failed and not done[n].get('ok'))]
    todo.sort(key=lambda j: j[1]['hcl'])                     # longest (dilute) cases first
    if todo:
        with mp.Pool(min(len(todo), a.workers), maxtasksperchild=2) as pool:
            for rec in pool.imap_unordered(worker, todo):
                done[rec['name']] = rec
                with open(ck, 'w') as f:
                    json.dump(done, f, indent=1)
    print('ok', sum(1 for n in want if done.get(n, {}).get('ok')), '/', len(want))


if __name__ == '__main__':
    main()
