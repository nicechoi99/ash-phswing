"""Shared helpers of the run_* scripts (puts src/ on the path, JSON / CSV writers, the reference values)."""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, os.path.join(ROOT, 'src'))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from ash_phswing import paths  # noqa: E402

REFERENCE = os.path.join(paths.DATA, 'reference', 'canon_261026n5_reference.json')


def reference():
    with open(REFERENCE, encoding='utf-8') as f:
        return json.load(f)


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    return str(o)


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, '/')


def write_json(name, obj):
    p = os.path.join(paths.results_dir(), name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, default=_default)
    return p


def write_csv(name, rows, fields=None):
    p = os.path.join(paths.results_dir(), name)
    fields = fields or list(rows[0].keys())
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def table(rows, header):
    """Plain-text table: rows of strings."""
    w = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    line = '  '.join(str(h).ljust(w[i]) for i, h in enumerate(header))
    out = [line, '-' * len(line)]
    for r in rows:
        out.append('  '.join(str(c).ljust(w[i]) for i, c in enumerate(r)))
    return '\n'.join(out)
