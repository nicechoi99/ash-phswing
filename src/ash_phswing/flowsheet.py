"""Saved Aspen Plus results ('processData') in a portable JSON form.

The Aspen drivers (scripts/aspen) read every stream and block of a converged flowsheet with
ash_phswing.aspen.access_data and pickle the result.  `export_pickle` writes the same content to JSON
(DataFrames as columns / dtypes / rows, NaN as null in float columns); `load` rebuilds the dictionary
with pandas DataFrames, so the cost model reads identical numbers from either form.
"""
import copy
import json
import math
import pickle

import numpy as np
import pandas as pd

KEYS = ['Components', 'ComponentTypes', 'Units', 'Streams', 'StreamCompositions', 'Input', 'Output', 'FeedStreams',
        'ProductStreams', 'DesignSpecs']


def _jv(v):
    if isinstance(v, np.floating):
        v = float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, dict):
        return {str(k): _jv(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_jv(x) for x in list(v)]
    return v


def _df_to_json(df):
    cols = list(df.columns)
    dt = {c: ('float' if pd.api.types.is_float_dtype(df[c]) else 'object') for c in cols}
    return dict(columns=cols, dtypes=dt, rows=[[_jv(df.at[i, c]) for c in cols] for i in df.index])


def _df_from_json(d):
    df = pd.DataFrame(d['rows'], columns=d['columns'])
    for c, t in d['dtypes'].items():
        if t == 'float':
            df[c] = pd.to_numeric(df[c].astype(object).where(df[c].notna(), np.nan), errors='coerce').astype('float64')
        else:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def export_pickle(pkl_path, json_path, meta=None):
    """Convert an access_data pickle ({'processData': ...} or the bare dict) to JSON."""
    with open(pkl_path, 'rb') as f:
        p = pickle.load(f)
    pdd = p['processData'] if isinstance(p, dict) and 'processData' in p else p
    out = {k: (_df_to_json(pdd[k]) if isinstance(pdd.get(k), pd.DataFrame) else _jv(pdd.get(k))) for k in KEYS}
    out['_meta'] = meta or (p.get('meta') if isinstance(p, dict) else None)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=0)


_CACHE = {}


def _from_dict(d):
    pdd = {k: (_df_from_json(d[k]) if isinstance(d.get(k), dict) and 'rows' in d[k] else d.get(k)) for k in KEYS}
    pdd['_meta'] = d.get('_meta')
    return pdd


def iter_archive(zip_path):
    """Yield (name, processData, meta) for every solution in a zipped pool archive (data/pool/aspen_pool_*.zip)."""
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(z.namelist()):
            if n.endswith('.json'):
                pdd = _from_dict(json.loads(z.read(n).decode('utf-8')))
                yield n[:-5], pdd, pdd['_meta']


def load(path):
    """processData dictionary of a saved flowsheet (a fresh deep copy on every call)."""
    if path not in _CACHE:
        with open(path, encoding='utf-8') as f:
            _CACHE[path] = _from_dict(json.load(f))
    return copy.deepcopy(_CACHE[path])


# ---------------------------------------------------------------- stream accessors
def stream_value(pd_, name, col):
    df = pd_['Streams']
    m = df['NAME'] == name
    return df.loc[m, col].values[0] if m.any() else None


def mass_flows(pd_, name, sub='MIXED'):
    return pd_['StreamCompositions'].get(name, {}).get(sub, {}).get('mass_flow', {})


def component(pd_, name, species, subs=('MIXED', 'CISOLID')):
    c = pd_.get('StreamCompositions', {}).get(name, {})
    return sum((c.get(s, {}).get('mass_flow', {}).get(species, 0) or 0) for s in subs)


def non_water(pd_, name):
    S = pd_['Streams']
    r = S[S.NAME == name]
    sc = pd_['StreamCompositions'].get(name, {})
    w = sum(sc.get(k, {}).get('mass_flow', {}).get('WATER', 0) or 0 for k in sc)
    return float(r.MASSFLOW_TOTAL.values[0]) - w


def add_water(pd_, name, W):
    """Add W kg/h of water to the liquid of one stream (cake wash filtrate joining the brine)."""
    mix = pd_['StreamCompositions'][name]['MIXED']
    mix['mass_flow']['WATER'] += W
    if 'mole_flow' in mix:
        mix['mole_flow']['WATER'] = mix['mole_flow'].get('WATER', 0) + W / 18.01528
    S = pd_['Streams']
    m = S.NAME == name
    for col, add in (('MASSFLOW_MIXED', W), ('MASSFLOW_TOTAL', W), ('MOLEFLOW_MIXED', W / 18.01528),
                     ('MOLEFLOW_TOTAL', W / 18.01528), ('VOLFLOW', W / 60.0)):
        if col in S.columns:
            S.loc[m, col] = S.loc[m, col] + add
