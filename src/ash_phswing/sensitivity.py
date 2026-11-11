"""One-at-a-time sensitivity of the NPV.

tornado_sourced(region)   both ends of each sourced range (data/parameters/sensitivity_ranges.csv); bars whose base value
                          sits at one end of its range are one-sided.  The AACE Class 4 band is uncertainty, not a lever.
tornado_uniform(region)   every input -20 % / +20 % of its base value (importance ranking, Main Fig. 5a).
"""
from . import params, tea

UNIFORM = 0.20


def _parse_over(s):
    out = {}
    for part in filter(None, (s or '').split(';')):
        k, v = part.split('=')
        out[k.strip()] = float(v)
    return out


def sourced_items(region):
    return [r for r in params.rows('sensitivity_ranges.csv') if r['region'] == region]


def _bar(base_case, base, key, label, lo, hi, extra=None):
    a = tea.evaluate(base_case.with_(**lo)) if lo else None
    b = tea.evaluate(base_case.with_(**hi)) if hi else None
    na, nb = (a['NPV'] if a else base['NPV']), (b['NPV'] if b else base['NPV'])
    ma, mb = (a['MSP'] if a else base['MSP']), (b['MSP'] if b else base['MSP'])
    d = dict(key=key, label=label, NPV_low_input=na, NPV_high_input=nb, MSP_low_input=ma, MSP_high_input=mb,
             dNPV_low_input=na - base['NPV'], dNPV_high_input=nb - base['NPV'], span=abs(nb - na))
    if extra:
        d.update(extra)
    return d


def tornado_sourced(region, case=None):
    case = tea.base_case(region) if case is None else case
    base = tea.evaluate(case)
    bars = []
    for r in sourced_items(region):
        lo, hi = _parse_over(r['low']), _parse_over(r['high'])
        b = _bar(case, base, r['key'], r['label'], lo, hi, dict(tier=r['tier'], values=r['values'], source=r['source']))
        b['one_sided'] = min(abs(b['dNPV_low_input']), abs(b['dNPV_high_input'])) < 0.5
        bars.append(b)
    bars.sort(key=lambda b: -b['span'])
    return dict(region=region, base_NPV=base['NPV'], base_MSP=base['MSP'], bars=bars)


def uniform_items(c):
    u = lambda x, s: x * (1 + s * UNIFORM)
    return [
        ('gate', 'Treatment fee', dict(fee_usd_t=u(c.fee_usd_t, -1), residue_fee_usd_t=u(c.fee_usd_t, -1)),
         dict(fee_usd_t=u(c.fee_usd_t, 1), residue_fee_usd_t=u(c.fee_usd_t, 1))),
        ('prices', 'Product prices', dict(price_caoh2_usd_t=u(c.price_caoh2_usd_t, -1), price_pcc_usd_t=u(c.price_pcc_usd_t, -1)),
         dict(price_caoh2_usd_t=u(c.price_caoh2_usd_t, 1), price_pcc_usd_t=u(c.price_pcc_usd_t, 1))),
        ('capex', 'Total capital', dict(location_factor=u(c.location_factor, -1)), dict(location_factor=u(c.location_factor, 1))),
        ('ca', 'Chlor-alkali capital', dict(ca_usd_per_t_cl2=u(c.ca_usd_per_t_cl2, -1)), dict(ca_usd_per_t_cl2=u(c.ca_usd_per_t_cl2, 1))),
        ('elec', 'Electricity price', dict(elec_usd_kwh=u(c.elec_usd_kwh, -1)), dict(elec_usd_kwh=u(c.elec_usd_kwh, 1))),
        ('energy', 'Electrolysis energy', dict(energy_kwh_per_t_naoh=u(c.energy_kwh_per_t_naoh, -1)),
         dict(energy_kwh_per_t_naoh=u(c.energy_kwh_per_t_naoh, 1))),
        ('maint', 'Maintenance rate', dict(maint_rest=u(c.maint_rest, -1), maint_mvr=u(c.maint_mvr, -1), maint_ca=u(c.maint_ca, -1)),
         dict(maint_rest=u(c.maint_rest, 1), maint_mvr=u(c.maint_mvr, 1), maint_ca=u(c.maint_ca, 1))),
        ('wage', 'Labour cost', dict(wage_usd_h=u(c.wage_usd_h, -1)), dict(wage_usd_h=u(c.wage_usd_h, 1))),
        ('hcl', 'Surplus HCl price', dict(hcl_price_usd_t=u(c.hcl_price_usd_t, -1)), dict(hcl_price_usd_t=u(c.hcl_price_usd_t, 1))),
        ('steam', 'Host steam price', dict(steam_lp_usd_gj=u(c.steam_lp_usd_gj, -1), steam_lt_usd_gj=u(c.steam_lt_usd_gj, -1)),
         dict(steam_lp_usd_gj=u(c.steam_lp_usd_gj, 1), steam_lt_usd_gj=u(c.steam_lt_usd_gj, 1))),
    ]


def tornado_uniform(region, case=None):
    case = tea.base_case(region) if case is None else case
    base = tea.evaluate(case)
    bars = [_bar(case, base, k, lab, lo, hi) for k, lab, lo, hi in uniform_items(case)]
    bars.sort(key=lambda b: -b['span'])
    return dict(region=region, change=UNIFORM, base_NPV=base['NPV'], base_MSP=base['MSP'], bars=bars)
