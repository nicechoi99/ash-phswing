"""Price the Aspen solutions of the design campaign with the base-case cost model -> one pool row per solution.

Each solution is priced on the EU and US base cases, and its GWP per t ash is evaluated for the EU renewable PPA and the
Netherlands grid (columns GWP_solar_t_ash / GWP_grid_t_ash; fp_* are the product footprints).  A solution whose brine
carries fewer cations than the reagent need is priced with full regeneration and no purge (regen_mode).  Pool filters:
economic guard 0.2 < LC < 5 $/kg, then the top 1 % levelized cost and the bottom 1 % EU NPV are trimmed.
"""
import pandas as pd

from . import tea, lca, params

COLUMNS = ['id', 'M', 'converged', 'ph1_ach', 'ph2_ach', 'ph3_ach', 'LC', 'MSP_EU', 'MSP_US', 'NPV_EU', 'NPV_US', 'TCI', 'annual',
           'cash_opex', 'revenue', 'AP_kt', 'PCC_kg_hr', 'CAOH2_kg_hr', 'HCl_made_kg_hr', 'NaOH_made_kg_hr', 'HCl_need_kg_hr',
           'NaOH_need_kg_hr', 'HCl_surplus_kg_hr', 'NaOH_surplus_kg_hr', 'elec_GWh_yr', 'evap_t_h', 'regen_mode', 'fp_solar',
           'fp_grid', 'GWP_solar_t_ash', 'GWP_grid_t_ash', 'HCl_wt_frac', 'dose_rel', 'r_star', 'pH_STG2', 'pH_STG3', 'T_B1',
           'T_B13', 'T_B14', 'ASH_CACO3_mult', 'ASH_CAOH2_mult', 'ASH_SIO2_mult', 'ASH_MGO_mult', 'sample_id', 'naoh2_per_ca',
           'naoh2_pure_per_ca', 'naoh2_kg_hr', 'ca_in_3mix_kg_hr', 'rec3_pct', 'dose_mol_kg']


def price(pd_, meta, eu=None, us=None):
    eu = tea.base_case('EU') if eu is None else eu
    us = tea.base_case('US') if us is None else us
    e = tea.evaluate(eu, pd_=pd_)
    u = tea.evaluate(us, pd_=pd_)
    F = params.lca()
    inv = lca.inventory(e)
    s = lca.ledger(inv, F['EF_SOLAR'], F['EF_SOLAR'], 'lost', F)
    g = lca.ledger(inv, F['EF_GRID_NL'], F['EF_GRID_NL'], 'lost', F)
    pr, el = e['ProductRevenue'], e['Electrolysis']
    mode = 'need-only + purge' if e['_prep']['regen'] == 'need' else 'full regeneration, no purge (salt deficit)'
    return dict(id=meta['id'], M=meta['M'], converged=1, ph1_ach=meta.get('ph1_ach'), ph2_ach=meta.get('ph2_ach'),
                ph3_ach=meta.get('ph3_ach'), LC=e['LC'], MSP_EU=e['MSP'], MSP_US=u['MSP'], NPV_EU=e['NPV'], NPV_US=u['NPV'],
                TCI=e['TCI'], annual=e['annual'], cash_opex=e['cash_opex'], revenue=e['revenue'], AP_kt=e['AP_kt'],
                PCC_kg_hr=pr.get('CACO3_from_CO2', {}).get('flow_kg_hr', 0.0), CAOH2_kg_hr=pr.get('CAOH2', {}).get('flow_kg_hr', 0.0),
                HCl_made_kg_hr=el.get('HCl_recovered_pure_kg_hr'), NaOH_made_kg_hr=el.get('NaOH_recovered_pure_kg_hr'),
                HCl_need_kg_hr=el.get('HCl_feed_pure_kg_hr'), NaOH_need_kg_hr=el.get('NaOH_feed_pure_kg_hr'),
                HCl_surplus_kg_hr=el.get('HCl_surplus_pure_kg_hr', 0.0), NaOH_surplus_kg_hr=el.get('NaOH_surplus_pure_kg_hr', 0.0),
                elec_GWh_yr=e['elec_GWh'], evap_t_h=e['BrineConcentration']['water_evaporated_kg_hr'] / 1e3, regen_mode=mode,
                fp_solar=s['footprint_per_kg'], fp_grid=g['footprint_per_kg'], GWP_solar_t_ash=s['net_per_t_ash'],
                GWP_grid_t_ash=g['net_per_t_ash'], HCl_wt_frac=meta['HCl_wt'], dose_rel=meta['dose_rel'], r_star=meta['r_star'],
                pH_STG2=meta['pH2'], pH_STG3=meta['pH3'], T_B1=meta['T1'], T_B13=meta['T2'], T_B14=meta['T3'],
                ASH_CACO3_mult=meta['CACO3'], ASH_CAOH2_mult=meta['CAOH2'], ASH_SIO2_mult=meta['SIO2'], ASH_MGO_mult=meta['MGO'],
                naoh2_per_ca=meta.get('naoh2_per_ca'), naoh2_pure_per_ca=meta.get('naoh2_pure_per_ca'), naoh2_kg_hr=meta.get('naoh2'),
                ca_in_3mix_kg_hr=meta.get('ca_in_3mix_kg_hr'), rec3_pct=meta.get('rec3_pct'), dose_mol_kg=meta.get('dose_mol_kg'))


def build_pool(rows):
    """Guard and trim the priced rows; returns (pool DataFrame, dropped-by-guard list)."""
    keep, guard = [], []
    for r in rows:
        if r['LC'] == r['LC'] and 0.2 < r['LC'] < 5.0:
            keep.append(r)
        else:
            guard.append((r['M'], r['id'], r['LC']))
    d = pd.DataFrame(keep)
    d = d[(d.LC < d.LC.quantile(0.99)) & (d.NPV_EU > d.NPV_EU.quantile(0.01))].reset_index(drop=True)
    d['sample_id'] = range(len(d))
    return d[COLUMNS], guard
