"""Parameter tables (data/parameters/*.csv).

tea_parameters.csv  key,value,unit,source,note      one row per cost / design / price parameter
regions.csv         one row per regional case
lca_factors.csv     key,value,unit,source,note      emission factors of the LCA
sources.csv         key,citation,doi_or_url         bibliography for the 'source' columns
"""
import csv
import json
import os
from functools import lru_cache

from .paths import PARAMS


def _parse(v):
    s = v.strip()
    if s.lower() in ('true', 'false'):
        return s.lower() == 'true'
    if s.startswith('['):
        return json.loads(s)
    try:
        return float(s)
    except ValueError:
        return s


def _read(name):
    with open(os.path.join(PARAMS, name), encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=None)
def table(name):
    """{key: value} of a key/value parameter table."""
    return {r['key']: _parse(r['value']) for r in _read(name)}


def rows(name):
    return _read(name)


def tea():
    return dict(table('tea_parameters.csv'))


def lca():
    return dict(table('lca_factors.csv'))


@lru_cache(maxsize=None)
def regions():
    out = {}
    for r in _read('regions.csv'):
        d = dict(r)
        for k in ('fee_usd_t', 'wage_usd_h', 'location_factor', 'elec_usd_kwh', 'grid_usd_kwh'):
            d[k] = float(d[k])
        out[r['region']] = d
    return out


@lru_cache(maxsize=None)
def sources():
    return {r['key']: r for r in _read('sources.csv')}
