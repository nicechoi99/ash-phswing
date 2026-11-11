"""REQUIRES ASPEN PLUS V14 (Windows, pywin32).  Design-space campaign on the measured-CaCl2 composite feed
(the 350 runs behind data/pool/aspen_pool_261026n5.zip and data/pool/pool_261026n5.csv).

    python -X utf8 scripts/aspen/run_campaign.py --workers 7 --M 5 4 3 2 1 --template-dir <dir with b1M.bkp ... b5M.bkp>
    (or --template <one .bkp> for every molarity)

Sampling: per HCl molarity M = 1-5, 70 samples of an 11-D Latin hypercube (scipy.stats.qmc, seed 90), sample 0 = the base
recipe.  Variables: HCl wt (+-5 % of the nominal strength of M), composition multipliers on CaCO3 / Ca(OH)2 / SiO2 /
Mg(OH)2 (0.95-1.05; CaCl2 fixed in kg/h, CISOLID total fixed), Stage I acid dose relative to the chloride-corrected base
(0.65-0.85), pH2 10.5-11.5, pH3 12.5-13.0, T1 10.09-39.91 C, T2 / T3 10.09-39.91 C.
Solve: Stage I pinned at the dose; Stage II / III outside bisection, II then III per pass, >= 2 and <= 6 passes until both
are within 0.05 pH; a final confirming run at the three pins.  Converged = |pH3 - target| < 0.15 (pH2 reported).
Outputs (under --out): pkl/{M}M_{id:03d}.pkl ({'processData', 'meta'}), ckpt/mol{M}M.csv, logs/.  Price the pickles
with scripts/price_pool.py after converting them (ash_phswing.flowsheet.export_pickle).
"""
import argparse
import copy
import csv
import json
import multiprocessing as mp
import os
import pickle
import sys
import time

import numpy as np
from scipy.stats import qmc

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(ROOT, 'src'))

SEED, NPER = 90, 70
WT_TABLE = {1: 0.0358, 2: 0.0707, 3: 0.1046, 4: 0.1378, 5: 0.1683}
DRY = 30000.0
MW = {'CACO3': 100.087, 'CA(OH)2': 74.093, 'MG(OH)2': 58.32, 'AL(OH)3': 78.00, 'FE(OH)3': 106.87,
      'ZN(OH)2': 99.42, 'PB(OH)2': 241.2, 'CU(OH)2': 97.56, 'CR(OH)3': 103.02}
BEQ = {'CACO3': 2, 'CA(OH)2': 2, 'MG(OH)2': 2, 'AL(OH)3': 3, 'FE(OH)3': 3, 'ZN(OH)2': 2, 'PB(OH)2': 2, 'CU(OH)2': 2, 'CR(OH)3': 3}
MW_HCL = 36.461
VARORDER = ['HCl_wt', 'CACO3', 'CAOH2', 'SIO2', 'MGO', 'dose_rel', 'pH2', 'pH3', 'T1', 'T2', 'T3']
COMP2VAR = {'CACO3': 'CACO3', 'CA(OH)2': 'CAOH2', 'SIO2': 'SIO2', 'MG(OH)2': 'MGO'}
DOSE_LO, DOSE_HI = 0.65, 0.85
FIELDS = ['id', 'M', 'converged', 'status', 'ph1_ach', 'ph2_ach', 'ph3_ach', 'ph2_bisect', 'ph3_bisect', 'passes',
          'hcl_kg_hr', 'naoh1', 'naoh2', 'ca_in_3mix_kg_hr', 'naoh2_per_ca', 'naoh2_pure_kg_hr', 'naoh2_pure_per_ca',
          'ca_product_kg_hr', 'ca_filtrate_kg_hr', 'rec3_pct', 'uosstat', 'secs',
          'HCl_wt', 'CACO3', 'CAOH2', 'SIO2', 'MGO', 'dose_rel', 'pH2', 'pH3', 'T1', 'T2', 'T3',
          'base_eq_corr', 'base_eq_model', 'dose_mol_kg', 'dose_rel_model', 'acid_kg_hr', 'CaCl2_kg_hr', 'error']


def load_feed(path, name='COMP'):
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    return j['feeds'][name], j['meta']


def bounds(M):
    hb = WT_TABLE[M]
    return {'HCl_wt': [hb * 0.95, hb * 1.05], 'CACO3': [0.95, 1.05], 'CAOH2': [0.95, 1.05], 'SIO2': [0.95, 1.05],
            'MGO': [0.95, 1.05], 'dose_rel': [DOSE_LO, DOSE_HI], 'pH2': [10.5, 11.5], 'pH3': [12.5, 13.0],
            'T1': [283.24 - 273.15, 313.06 - 273.15], 'T2': [10.09, 39.91], 'T3': [10.09, 39.91]}


def samples_for(M, f_dose):
    b = bounds(M)
    U = qmc.LatinHypercube(d=len(VARORDER), seed=SEED).random(NPER)
    lo = np.array([b[v][0] for v in VARORDER]); hi = np.array([b[v][1] for v in VARORDER])
    X = qmc.scale(U, lo, hi)
    out = []
    for i in range(NPER):
        d = {VARORDER[j]: float(X[i, j]) for j in range(len(VARORDER))}
        d['id'] = i; d['M'] = M
        out.append(d)
    out[0] = dict(HCl_wt=WT_TABLE[M], CACO3=1.0, CAOH2=1.0, SIO2=1.0, MGO=1.0, dose_rel=f_dose, pH2=11.0, pH3=12.8,
                  T1=25.0, T2=25.0, T3=25.0, id=0, M=M)
    return out


def feed_for(s, cis0):
    """Composition multipliers on the acid-consuming phases; CaCl2 fixed in kg/h; CISOLID total fixed."""
    tot = sum(cis0.values())
    cacl2 = cis0['CACL2(S)']
    nf = {c: v * (s[COMP2VAR[c]] if c in COMP2VAR else 1.0) for c, v in cis0.items() if c != 'CACL2(S)'}
    k = (tot - cacl2) / sum(nf.values())
    nf = {c: v * k for c, v in nf.items()}
    nf['CACL2(S)'] = cacl2
    bc = sum(nf[c] / MW[c] * BEQ[c] for c in nf if c in BEQ)       # corrected base, kmol eq/h
    acid = s['dose_rel'] * bc * MW_HCL / s['HCl_wt']
    return nf, bc, acid


def naoh_kg(sc, name):
    tot = 0.0
    for sub, d in (sc.get(name) or {}).items():
        mf = d.get('mass_flow') or {}
        tot += (mf.get('NAOH') or 0) + (mf.get('NAOH(S)') or 0) + (mf.get('NA+') or 0) * 39.997 / 22.990
    return tot


def write_csv(path, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def worker(args):
    M, wid, samples, cfg = args
    from ash_phswing.aspen.session import Session, ca_kg_hr
    from ash_phswing.aspen.access_data import access_data
    feed, meta0 = load_feed(cfg['feeds'])
    mix0 = dict(feed['mix'])
    x_kmol = meta0['X_eq_kg'] * DRY / 1000.0
    log = open(os.path.join(cfg['out'], 'logs', 'w%d_%d.log' % (M, wid)), 'a', encoding='utf-8')

    def say(*a):
        print('[%dM w%d]' % (M, wid), *a, flush=True)
        print(time.strftime('%H:%M:%S'), *a, file=log, flush=True)
    s = Session(cfg['template'][M], os.path.join(cfg['out'], 'work', '_w%d_%dM.bkp' % (wid, M)), say)
    cur = {}

    def setup(smp, nf, acid):
        s.set_feed(nf, mix0, DRY, smp['HCl_wt'])
        s.set_targets(4.0, smp['pH2'], smp['pH3'], smp['T1'], smp['T2'], smp['T3'])
        s.pin(1, acid)

    def recover():
        s.close(); s.open(); setup(*cur['args'])

    partf = os.path.join(cfg['out'], 'ckpt', 'mol%dM.w%d.part.csv' % (M, wid))
    rows = []
    s.open()
    try:
        for smp in samples:
            t0 = time.time()
            nf, bc, acid = feed_for(smp, dict(feed['cis']))
            row = {k: smp[k] for k in VARORDER}
            row.update(id=smp['id'], M=M, converged=0, base_eq_corr=bc, base_eq_model=bc + x_kmol,
                       dose_mol_kg=smp['dose_rel'] * bc / DRY * 1000, dose_rel_model=smp['dose_rel'] * bc / (bc + x_kmol),
                       acid_kg_hr=acid, CaCl2_kg_hr=nf['CACL2(S)'])
            try:
                cur['args'] = (smp, nf, acid)
                setup(smp, nf, acid)
                p1 = (1, acid)
                s.pin(3, 47000.0)
                n1 = n2 = None
                for k in range(6):
                    ph2, n1, _, _ = s.bisect(2, smp['pH2'], 1000.0, 75000.0, pins=(p1, (3, n2 or 47000.0)), iters=20, recover=recover, clip_tol=None)
                    s.pin(2, n1)
                    ph3, n2, _, _ = s.bisect(3, smp['pH3'], 5000.0, 160000.0, pins=(p1, (2, n1)), iters=20, recover=recover, clip_tol=None)
                    s.pin(3, n2)
                    row['passes'] = k + 1
                    if k >= 1 and abs(ph2 - smp['pH2']) < 0.05 and abs(ph3 - smp['pH3']) < 0.05:
                        break
                pins = (p1, (2, n1), (3, n2))
                s.run(check=s.pins_ok(pins), recover=recover)                  # confirming evaluation
                v = {n: s.ds(n) for n in (1, 2, 3)}
                assert abs(v[1][0] - acid) < 0.0011 * acid, ('stage I dose not held', v[1][0], acid)
                stat = s.R(r'\Data\Results Summary\Run-Status\Output\UOSSTAT2')
                p = access_data({}, s.h)
                sc = p['StreamCompositions']
                ca3, prod, filt = ca_kg_hr(sc, '3MIX'), ca_kg_hr(sc, 'CAOH2'), ca_kg_hr(sc, '3OUT3')
                npure = naoh_kg(sc, 'NAOH2')
                row.update(ph1_ach=v[1][1], ph2_ach=v[2][1], ph3_ach=v[3][1], ph2_bisect=ph2, ph3_bisect=ph3,
                           hcl_kg_hr=v[1][0], naoh1=v[2][0], naoh2=v[3][0], uosstat=stat, ca_in_3mix_kg_hr=ca3,
                           naoh2_per_ca=v[3][0] / ca3 if ca3 > 0 else None, naoh2_pure_kg_hr=npure,
                           naoh2_pure_per_ca=npure / ca3 if ca3 > 0 else None, ca_product_kg_hr=prod, ca_filtrate_kg_hr=filt,
                           rec3_pct=100 * prod / (prod + filt) if prod + filt > 0 else None)
                ok = abs(v[3][1] - smp['pH3']) < 0.15
                row['converged'] = int(ok)
                row['status'] = 'ok' if ok else 'pH3 off target (%.3f vs %.3f)' % (v[3][1], smp['pH3'])
                meta = dict(smp)
                meta.update({k: row.get(k) for k in FIELDS if k not in smp})
                meta.update(r_star=meta0['F_DOSE'], base_eq=bc, naoh1=v[2][0], naoh2=v[3][0], uosstat=stat,
                            feed_cis_kg_h=nf, feed_mix_kg_h=mix0, campaign='261011 CaCl2 feed')
                with open(os.path.join(cfg['out'], 'pkl', '%dM_%03d.pkl' % (M, smp['id'])), 'wb') as fh:
                    pickle.dump({'processData': copy.deepcopy(p), 'meta': meta}, fh)
            except Exception as ex:
                row['status'] = 'ERR:%s' % type(ex).__name__
                row['error'] = str(ex)[:200]
                say('sample %d failed: %s' % (smp['id'], row['error']))
                s.close()
                try:
                    s.open()
                except Exception as ex2:
                    say('reopen failed: %s' % ex2)
            row['secs'] = round(time.time() - t0, 1)
            rows.append(row)
            say('id %d conv %s pH %s/%s/%s %.0fs' % (smp['id'], row['converged'], row.get('ph1_ach'), row.get('ph2_ach'),
                                                    row.get('ph3_ach'), row['secs']))
            write_csv(partf, rows)
    finally:
        s.close()
        try:
            os.remove(s.work)
        except OSError:
            pass
        log.close()
    return rows


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=7)
    ap.add_argument('--M', type=int, nargs='*', default=[5, 4, 3, 2, 1])
    ap.add_argument('--template', default=os.path.join(ROOT, 'data', 'aspen', 'model', '261026_AshpHSwing5M-NaOH5N_MVR-Converged.bkp'))
    ap.add_argument('--template-dir', default=None, help='directory holding b1M.bkp ... b5M.bkp (one template per molarity)')
    ap.add_argument('--feeds', default=os.path.join(ROOT, 'data', 'aspen', 'feeds.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'results', 'aspen', 'campaign'))
    a = ap.parse_args()
    for sub in ('pkl', 'ckpt', 'logs', 'work'):
        os.makedirs(os.path.join(a.out, sub), exist_ok=True)
    tmpl = {M: (os.path.join(a.template_dir, 'b%dM.bkp' % M) if a.template_dir else a.template) for M in range(1, 6)}
    cfg = dict(template=tmpl, feeds=a.feeds, out=a.out)
    f_dose = load_feed(a.feeds)[1]['F_DOSE']
    for M in a.M:
        merged = os.path.join(a.out, 'ckpt', 'mol%dM.csv' % M)
        old = read_rows(merged)
        for w in range(32):
            old += read_rows(os.path.join(a.out, 'ckpt', 'mol%dM.w%d.part.csv' % (M, w)))
        best = {}
        for r in old:
            i = int(float(r['id']))
            if i not in best or float(r.get('converged') or 0) > float(best[i].get('converged') or 0):
                best[i] = r
        keep = {i: r for i, r in best.items() if float(r.get('converged') or 0) == 1}
        prev_fail = {i: r for i, r in best.items() if i not in keep}
        todo = [s for s in samples_for(M, f_dose) if s['id'] not in keep]
        print('=== %d M: kept %d, to run %d' % (M, len(keep), len(todo)), flush=True)
        if not todo:
            continue
        chunks = [[] for _ in range(a.workers)]
        for i, s in enumerate(todo):
            chunks[i % a.workers].append(s)
        jobs = [(M, w, c, cfg) for w, c in enumerate(chunks) if c]
        with mp.Pool(len(jobs)) as pool:
            res = pool.map(worker, jobs)
        new = {int(r['id']): r for c in res for r in c}
        allr = dict(prev_fail); allr.update(keep); allr.update(new)
        write_csv(merged, [allr[i] for i in sorted(allr)])
        for w in range(32):
            try:
                os.remove(os.path.join(a.out, 'ckpt', 'mol%dM.w%d.part.csv' % (M, w)))
            except OSError:
                pass
        print('%d M: %d/%d converged' % (M, sum(1 for r in allr.values() if float(r.get('converged') or 0) == 1), len(allr)), flush=True)


if __name__ == '__main__':
    main()
