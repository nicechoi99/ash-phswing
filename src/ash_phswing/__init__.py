"""Techno-economic and life-cycle model of circular pH-swing calcium recovery from incineration fly ash with
chlor-alkali regeneration of the HCl and NaOH (basis 261026n5: EU co-located base, 240 kt/yr dry ash, 5 M HCl,
Stage III pH 13.0, Stage III NaOH at 5 N (17 wt%), measured CaCl2 feed).

Modules: flowsheet (saved Aspen results), equipment / capex (sizing, bare-module cost), opex (reagents, utilities,
revenue), cashflow (TCI, COM, DCF), tea (one case end to end), lca (GWP), sensitivity, montecarlo, pool / pool_pricing
(design campaign, surrogate, SHAP, NSGA-II), aspen (COM drivers, require Aspen Plus V14).
"""
__version__ = '1.0.0'
