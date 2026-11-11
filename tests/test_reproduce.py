"""Reproduction of the published values (basis 261026n5, Stage III NaOH2 at 5 N, Stage V as three batch carbonators in rotation from the measured CO2 uptake) from the saved data, without Aspen.

Two levels: (1) the key values at the precision printed in the paper; (2) the full-precision reference values of the
original analysis (data/reference/canon_261026n5_reference.json) to 1e-6.
"""
import json
import os

import pytest

from ash_phswing import tea, lca, sensitivity, montecarlo, pool, paths, flowsheet, pool_pricing

REF = json.load(open(os.path.join(paths.DATA, 'reference', 'canon_261026n5_reference.json'), encoding='utf-8'))


@pytest.fixture(scope='module')
def eu():
    case = tea.base_case('EU')
    q = tea.evaluate(case)
    return case, q, tea.report(q)


def test_eu_base_case_printed_precision(eu):
    case, q, rep = eu
    assert round(rep['NPV'], 1) == 9.1
    assert round(rep['CAPEX']['TCI'], 1) == 270.8
    assert round(rep['MSP'], 3) == 0.173                         # net levelized cost ($/kg)
    assert round(rep['LC'], 3) == 1.116                          # levelized cost ($/kg)
    assert round(rep['revenue']['total'], 1) == 120.2
    assert round(rep['annual_cost'], 1) == 115.2
    assert round(rep['revenue']['items']['ASH_gate_fee'], 1) == 86.0
    assert round(rep['products']['total_kt'], 1) == 103.2
    assert round(rep['products']['CaOH2_kt'], 1) == 57.8
    assert round(rep['products']['PCC_kt'], 1) == 45.4


def test_eu_breakevens(eu):
    case, q, rep = eu
    be = tea.breakevens(case)
    assert round(be['uniform_product_price_usd_t']) == 206      # common product price at NPV = 0 ($/t)
    assert round(be['fee_usd_t']) == 348                         # break-even treatment fee ($/t)


def test_eu_full_precision(eu):
    case, q, rep = eu
    r = REF['regions']['EU']
    for k, v in (('NPV', rep['NPV']), ('NPV_standalone', rep['NPV_standalone']), ('MSP', rep['MSP']), ('LC', rep['LC']),
                 ('TCI', rep['CAPEX']['TCI']), ('TDC', rep['CAPEX']['TDC']), ('annual_cost', rep['annual_cost']),
                 ('cash_opex', rep['OPEX']['total']), ('revenue', rep['revenue']['total'])):
        assert abs(v - r[k]) < 1e-6, (k, v, r[k])
    for k, v in r['opex_items'].items():
        assert abs(rep['OPEX']['items'].get(k, 0.0) - v) < 1e-6, k
    for k, v in r['revenue_items'].items():
        assert abs(rep['revenue']['items'][k] - v) < 1e-6, k
    be = tea.breakevens(case)
    for k in ('fee_usd_t', 'uniform_product_price_usd_t', 'PCC_needed_at_CaOH2_usd_t'):
        assert abs(be[k] - r['breakeven'][k]) < 1e-6, k


@pytest.mark.parametrize('region,printed', [('US', -253.3), ('KR', -150.2), ('JPK', -21.2), ('JPK65', 61.4)])
def test_regions(region, printed):
    q = tea.evaluate(tea.base_case(region))
    assert round(q['NPV'], 1) == printed
    r = REF['regions'][region]
    assert abs(q['NPV'] - r['NPV']) < 1e-6 and abs(q['MSP'] - r['MSP']) < 1e-9 and abs(q['TCI'] - r['TCI']) < 1e-6


def test_lca(eu):
    case, q, rep = eu
    L = lca.assess(q)
    cs = {c['label']: c for c in L['cases']}
    assert round(L['base']['net_per_t_ash']) == -446            # system expansion, incinerator power
    assert round(cs['EU renewable PPA']['net_per_t_ash']) == -390
    assert round(L['base']['footprint_per_kg'], 3) == 0.028      # product footprint, no credit
    assert round(cs['EU renewable PPA']['footprint_per_kg'], 3) == 0.159
    for c in REF['lca']['cases']:
        m = cs[c['label']]
        for k in ('net_per_t_ash', 'footprint_per_kg', 'net_per_t_ash_gas_steam', 'net_per_t_ash_heat_cutoff'):
            assert abs(m[k] - c[k]) < 1e-6, (c['label'], k)
    for k, v in REF['lca']['base'].items():
        assert abs(L['base'][k] - v) < 1e-9, k


def test_ph3_ladder_design_point():
    best = None
    for f in sorted(os.listdir(paths.LADDER_DIR)) + ['design']:
        fs = paths.DESIGN_FLOWSHEET if f == 'design' else os.path.join(paths.LADDER_DIR, f)
        ph = 13.0 if f == 'design' else int(f.split('_p')[-1][:3]) / 10.0
        npv = tea.evaluate(tea.base_case('EU', flowsheet=fs))['NPV']
        ref = [r for r in REF['ph3_ladder'] if r['pH3'] == ph][0]
        assert abs(npv - ref['NPV_EU']) < 1e-6, ph
        if 12.5 - 1e-9 <= ph <= 13.0 + 1e-9 and (best is None or npv > best[1]):
            best = (ph, npv)
    assert best[0] == REF['design_pH3'] == 13.0


def test_uniform_tornado_eu():
    t = sensitivity.tornado_uniform('EU')
    ref = {b['key']: b for b in REF['tornado_uniform_EU']['bars']}
    assert [b['key'] for b in t['bars']] == [b['key'] for b in REF['tornado_uniform_EU']['bars']]
    for b in t['bars']:
        assert abs(b['NPV_low_input'] - ref[b['key']]['NPV_low_input']) < 1e-6
        assert abs(b['NPV_high_input'] - ref[b['key']]['NPV_high_input']) < 1e-6


@pytest.mark.parametrize('region', ['EU', 'US', 'KR', 'JPK'])
def test_sourced_tornado(region):
    t = sensitivity.tornado_sourced(region)
    ref = {b['key']: b for b in REF['tornado_sourced'][region]['bars']}
    for b in t['bars']:
        assert abs(b['NPV_low_input'] - ref[b['key']]['NPV_low_input']) < 1e-6, b['key']
        assert abs(b['NPV_high_input'] - ref[b['key']]['NPV_high_input']) < 1e-6, b['key']
        assert b['one_sided'] == ref[b['key']]['one_sided']


def test_montecarlo_first_draws():
    """Same sampler and seed: the first 10 draws of each region reproduce the published draws exactly."""
    res = montecarlo.run(N=3000, seed=261006, n_eval=10)
    for reg, r in res.items():
        assert max(abs(a - b) for a, b in zip(r['NPV'], REF['monte_carlo'][reg]['NPV_first40'][:10])) < 1e-6, reg


def test_pool_repricing_sample():
    """Ten saved campaign solutions re-priced with this code give their pool rows."""
    import pandas as pd
    d = pd.read_csv(paths.POOL_CSV).set_index(['M', 'id'])
    n = 0
    for name, pdd, meta in flowsheet.iter_archive(os.path.join(paths.POOL, 'aspen_pool_261026n5.zip')):
        key = (int(meta['M']), int(meta['id']))
        if key not in d.index or key[1] % 7:
            continue
        r = pool_pricing.price(pdd, meta)
        for c in ('NPV_EU', 'NPV_US', 'LC', 'MSP_EU', 'TCI', 'GWP_solar_t_ash', 'GWP_grid_t_ash'):
            assert abs(r[c] - d.loc[key, c]) < 1e-6 * max(1.0, abs(d.loc[key, c])), (key, c)
        n += 1
        if n >= 10:
            break
    assert n == 10


def test_surrogate_shap():
    d = pool.load()
    assert len(d) == 335
    s = pool.shap_importance(d, 'NPV_EU')
    ref = REF['pool']['shap_NPV_EU']
    for k, v in s['mean_abs_shap'].items():
        assert abs(v - ref[k]) < 1e-3 * max(1.0, abs(ref[k])), k
    assert round(s['operating_share_pct']) == 97
    assert list(s['mean_abs_shap'])[:2] == ['naoh2_per_ca', 'HCl_wt_frac']


def test_pool_summary():
    """Retained runs per molarity and the per-molarity medians of data/pool/pool_261026n5_summary.json."""
    S = json.load(open(os.path.join(paths.POOL, 'pool_261026n5_summary.json'), encoding='utf-8'))
    d = pool.load()
    assert len(d) == S['n_retained'] == 335
    assert {str(k): int(v) for k, v in d.groupby('M').size().items()} == S['n_retained_by_M']
    for m, g in d.groupby('M'):
        for k, v in S['by_M'][str(m)].items():
            assert abs(round(float(g[k].median()), 4) - v) < 1e-9, (m, k)
    assert int((d.NPV_EU > 0).sum()) == S['NPV_pos']
    assert abs(d.NPV_EU.max() - S['NPV_EU_max']) < 1e-9 and abs(d.LC.min() - S['LC_min']) < 1e-12


def test_montecarlo_summary():
    """Full Monte Carlo (4 x 3,000 cost-model runs, about 3 min): percentiles and P(NPV > 0) of every region."""
    res = montecarlo.run(N=3000, seed=261006)
    for reg, r in res.items():
        ref = REF['monte_carlo'][reg]
        for k in ('p5', 'p50', 'p95', 'mean', 'min', 'max', 'MSP_p50'):
            assert abs(r[k] - ref[k]) < 1e-6, (reg, k, r[k], ref[k])
        assert r['P_gt0'] == ref['P_gt0'], reg
    assert round(res['EU']['p50'], 1) == -61.2 and round(100 * res['EU']['P_gt0'], 1) == 14.7


def test_nsga2_front():
    """NSGA-II on the single-threaded random-forest surrogates reproduces the published fronts exactly."""
    from ash_phswing import params
    F = params.lca()
    d = pool.load()
    pub = REF['pool']['nsga2_published']
    for key, ef in (('host', 0.0), ('NL', F['EF_GRID_NL'])):
        r = pool.nsga2(d, ef, F['EF_SOLAR'], F['EF_GRID_NL'])
        ref = pub['cases'][key]
        for k, v in ref['front'].items():
            if isinstance(v, list):
                assert max(abs(a - b) for a, b in zip(r['front'][k], v)) < 1e-6, (key, k)
            else:
                assert abs(r['front'][k] - v) < 1e-6, (key, k)
        assert len(r['non_dominated']) == ref['n_non_dominated']
        assert abs(r['cv_mae_gwp_sigma'] - ref['cv_mae_gwp_sigma']) < 1e-9
        if key == 'host':
            assert abs(r['cv_mae_npv_sigma'] - pub['cv_mae_npv_sigma']) < 1e-9
