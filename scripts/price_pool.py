"""Re-price the 350-run design campaign from its saved Aspen solutions (data/pool/aspen_pool_261026n5.zip) and rebuild
the pool table; compares every column with data/pool/pool_261026n5.csv.

    python -X utf8 scripts/price_pool.py
"""
import csv
import io
import os
import time
import zipfile

import numpy as np
import pandas as pd

import _common as C
from ash_phswing import flowsheet as FS, pool_pricing as PP, paths

ARCHIVE = os.path.join(paths.POOL, 'aspen_pool_261026n5.zip')


def main():
    t0 = time.time()
    with zipfile.ZipFile(ARCHIVE) as z:
        runs = list(csv.DictReader(io.StringIO(z.read('campaign_runs.csv').decode('utf-8'))))
    conv = {(int(float(r['M'])), int(float(r['id']))): int(float(r['converged'] or 0)) for r in runs}
    rows = []
    for name, pdd, meta in FS.iter_archive(ARCHIVE):
        if conv.get((int(meta['M']), int(meta['id'])), 0) != 1:
            continue
        rows.append(PP.price(pdd, meta))
    d, guard = PP.build_pool(rows)
    ref = pd.read_csv(paths.POOL_CSV)
    m = d.merge(ref, on=['M', 'id'], suffixes=('', '_ref'))
    worst = 0.0
    for c in PP.COLUMNS:
        if c in ('M', 'id', 'regen_mode'):
            continue
        a, b = m[c].astype(float), m[c + '_ref'].astype(float)
        worst = max(worst, float(np.nanmax(np.abs(a - b) / np.maximum(1.0, np.abs(b)))))
    print('runs %d, converged and priced %d, dropped by the 0.2 < LC < 5 guard %d, retained %d (published %d)'
          % (len(runs), len(rows), len(guard), len(d), len(ref)))
    print('rows matched %d, largest relative difference over all columns %.2e, regen modes equal %s'
          % (len(m), worst, bool((m.regen_mode == m.regen_mode_ref).all())))
    p = os.path.join(paths.results_dir(), 'pool_repriced.csv')
    d.to_csv(p, index=False)
    print('%.0f s, written %s' % (time.time() - t0, C.rel(p)))


if __name__ == '__main__':
    main()
