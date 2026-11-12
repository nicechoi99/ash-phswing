# Design campaign, surrogate optimization and sensitivity

## 1. Aspen solve protocol (`scripts/aspen/`, `src/ash_phswing/aspen/session.py`; requires Aspen Plus V14)

* Three design specifications: DS-STG1 (HCl feed -> Stage I pH), DS-STG2 (NaOH1 -> Stage II pH), DS-STG3 (NaOH2 -> Stage III pH).
* Stage I is specified by the acid **dose**, not by a pH target: DS-STG1 is pinned (bounds x 0.999 / 1.001, read back) at the
  calibrated dose of the composite feed, 0.740 of its chloride-corrected base (10.42 mol HCl per kg dry ash;
  `data/aspen/feeds.json`, feed `COMP`, `acid_kg_h`). Because the pin holds the dose and not the pH, DS-STG1 reports block
  status 2 in the saved design solution; the Stage I pH (5.62) is an outcome.
* Stages II and III are solved by an **outside bisection** on the pinned NaOH flow (Aspen's inside secant diverges on the
  Ca(OH)2 buffer): Stage II then Stage III in each pass, repeated until both achieved pH values are within 0.05 of their
  targets (at least 2 passes, at most 6). A final confirming run at the three pins is the saved state; every run is checked
  to carry the pinned flows (stale results are rejected), with rerun -> Reinit -> reopen escalation.
* Design point (`run_design_point.py`): composite feed, 5 M HCl, pH2 11.0, pH3 13.0, 25 C, NAOH2 at 5 N (17 wt%, set in
  the template); the Stage III ladder pH3 12.0-14.0
  uses the same protocol (pH3 12.0 is infeasible: the brine carries too little sodium to regenerate the Stage I acid).
* **Stage II buffer jump, upper-branch rule** (`run_feed_grid.py`, feed-concentration grid of SI Fig. S24): Stage II titrates
  across a jump near pH 11 where the RGibbs model has two steady states. When the bisection bracket on NaOH1 collapses
  (< 0.5 % of the flow) while pH2 is still more than 0.10 off 11.0, the upper branch is taken: the smallest bisected NaOH1 flow
  whose pH2 was at or above 11.0 (x 1.0002); Stage III is re-bisected on it and the state is accepted when 10.95 <= pH2 <= 11.40.
  The jump spans less than 1 kg/h of NaOH1, so the dose is the same on both branches. The final run is repeated up to four
  times on the buffer plateau; ok = 2 marks a state within 0.10 on a resolved Stage II flow. Stage I is first probed
  adiabatically on a fresh copy and then run isothermally at min(T_adiabatic, 45 C).

## 2. Campaign sampling (`scripts/aspen/run_campaign.py`)

* Per HCl molarity M = 1-5: 70 samples of an 11-dimensional Latin hypercube (`scipy.stats.qmc.LatinHypercube(d=11, seed=90)`),
  sample 0 = the base recipe (dose 0.7396, pH2 11.0, pH3 12.8, 25 C, nominal wt%).
* Variables and ranges: HCl wt fraction +-5 % of the nominal strength (0.0358 / 0.0707 / 0.1046 / 0.1378 / 0.1683 for 1-5 M);
  multipliers 0.95-1.05 on CaCO3, Ca(OH)2, SiO2 and Mg(OH)2 of the feed (CaCl2 held at 4,421.9 kg/h, CISOLID total held);
  Stage I dose 0.65-0.85 of the chloride-corrected base of the sample; pH2 10.5-11.5; pH3 12.5-13.0; T1 10.09-39.91 C;
  T2 and T3 10.09-39.91 C.
* Campaign re-solved with NAOH2 at 5 N (17 wt%), same Latin-hypercube samples. Converged = |pH3 - target| < 0.15
  (pH2 reported, not gated): 347 of 350 runs. Aspen solutions are saved for 348 runs; run 41 at 1 M ends at
  pH3 12.71 against its target of 12.56 and is not priced.
* Pricing (`scripts/price_pool.py`, `pool_pricing.py`): each converged solution priced on the EU and US base cases; salt-deficit
  runs priced with full regeneration; economic guard 0.2 < LC < 5 $/kg (7 of the 347 runs dropped); trim of the top 1 % levelized cost and
  the bottom 1 % EU NPV -> **335 retained** (`data/pool/pool_261026n5.csv`). Re-pricing the shipped Aspen solutions
  (`data/pool/aspen_pool_261026n5.zip`) reproduces every column of the pool table to 1.6e-13 (relative).

## 3. Surrogates and importance (`src/ash_phswing/pool.py`, `scripts/run_surrogate_shap.py`)

* Inputs (12): HCl wt fraction, the four composition multipliers, Stage I dose, pH2, pH3, T1, T2, T3 and the Stage III NaOH
  dose per kg of Ca entering Stage III (`naoh2_per_ca`, so T3 and pH3 are not credited with the NaOH-dose effect).
* Surrogate: XGBoost regressor (700 trees, learning rate 0.05, depth 3, subsample 0.8, colsample 0.8, lambda 2, seed 0).
* Quality gate: 25 % hold-out (seed 0); learning curve at 8 training sizes; mean absolute error in units of the hold-out
  standard deviation falls from 0.434 to 0.069 sigma (levelized cost).
* Bayesian-optimization check: GP (constant x Matern 5/2, normalized y) with expected improvement over the pool, 20 random
  starts (seed 0) + 40 iterations; reaches the campaign minimum levelized cost (0.9677 $/kg) after 13 iterations.
* SHAP: mean |SHAP| (TreeExplainer) of the surrogate over the 335 runs. EU NPV: NaOH dose Stage III 42.8 M$, HCl concentration
  37.9, T Stage III 14.4, acid dose 5.1, pH3 4.1; operating variables 96.9 % of the importance (levelized cost: 97.7 %).
* Elasticity: for each input, every run is perturbed to 1.1x and 0.9x (clipped to the pool box), elasticity =
  mean[(f(x+) - f(x-)) / |f(x)| / ((x+ - x-) / x)] on the surrogate. Levelized cost: acid dose -0.94, pH3 -0.88, NaOH dose -0.39.

## 4. NSGA-II (`pool.nsga2`, `scripts/run_nsga2.py`)

* Objectives: maximize EU NPV, minimize net GWP per t ash (system expansion), on random-forest surrogates (400 trees, seed 0;
  a forest prediction is a mean of evaluated designs, so the search cannot extrapolate); 5-fold CV MAE 0.108 sigma (NPV),
  0.059 sigma (GWP, incinerator power) and 0.141 sigma (GWP, Netherlands grid).
* pymoo NSGA-II, population 80, 60 generations, seed 1, bounds = the pool box; two power cases: incinerator power (EF 0) and
  Netherlands grid. Non-dominated pool runs: 8 and 12.
* Reproducibility: the forests run with `n_jobs=1` (a multithreaded forest sums its trees in a thread-dependent order and
  moves the front by up to about 2 M$). The published front was computed the same way, and this code reproduces it
  exactly: NPV -150.2..26.7 M$ / GWP -511.2..-506.7 kg/t ash (incinerator power) and NPV -10.5..27.5 / GWP 169.0..215.0
  (Netherlands grid).

## 5. One-at-a-time sensitivity (`src/ash_phswing/sensitivity.py`, `scripts/run_sensitivity.py`)

* **Uniform +-20 %** (Main Fig. 5a): treatment fee (with the residue landfill rate), product prices, total capital (location
  factor), chlor-alkali $/t, power price, electrolysis energy, maintenance rate, labor rate, surplus HCl price, host steam price,
  each at 0.8x and 1.2x of its base value, one at a time.
* **Sourced ranges** (SI Fig. S19): both ends of each documented range, per region; a bar whose base sits at one end of its range
  is one-sided. The AACE Class 4 band (-20 / +30 % on the TDC) is reported as uncertainty, not as a lever; the discount rate is
  not varied.

| region | key | range (low / high) | case fields at the low end | case fields at the high end | tier | source |
|---|---|---|---|---|---|---|
| EU | gate | EUR 47 / 587 per t | fee_usd_t=53.04571186227696;residue_fee_usd_t=53.04571186227696 | fee_usd_t=663.9859795174667;residue_fee_usd_t=663.9859795174667 | A | `bref_wi2019`, `eurostat_hicp` |
| EU | wage | $40 / $53.5 per h | (base) | wage_usd_h=53.47738 | A | `eurostat_lc` |
| EU | lf | 1.00 / 1.20 | (base) | location_factor=1.2 | A | `seider2016` |
| EU | elec | 2 / 10.75 c/kWh | elec_usd_kwh=0.02 | elec_usd_kwh=0.10752006000000001 | A/C | `baidoo2026`, `eurostat_nrg` |
| EU | hcl | $96 / $150 per t | hcl_price_usd_t=96.4 | (base) | B/C | `intratec2025`, `comtrade_hcl` |
| EU | steam | 2.37/0.00 / 6.55/4.21 $/GJ | steam_lp_usd_gj=2.3698430679809532;steam_lt_usd_gj=0.0 | steam_lp_usd_gj=6.546120567975441;steam_lt_usd_gj=4.207716333333333 | A/assumption | `dea_cv` |
| EU | prices | 200/205 / 235/245 $/t | price_caoh2_usd_t=200.0;price_pcc_usd_t=205.0 | price_caoh2_usd_t=235.0;price_pcc_usd_t=245.0 | A | `usgs_lime`, `comtrade` |
| EU | aace | -20 / +30 % | location_factor=0.8 | location_factor=1.3 | A | `aace18r97` |
| EU | ca | 1,184 / 1,925 $/t | ca_usd_per_t_cl2=1184.0 | ca_usd_per_t_cl2=1925.0 | A/B | `hanwha2021`, `schmittinger2011`, `bref_cak2014` |
| EU | energy | 2.27 / 2.94 MWh/t Cl2 | energy_kwh_per_t_naoh=2047.5889929078014 | energy_kwh_per_t_naoh=2641.4769929078016 | B | `eurochlor_is12` |
| EU | membrane | $1,000 / $1,925 per m2 | (base) | membrane_usd_m2=1925.0;membrane_life_yr=4.0 | A | `bref_cak2014` |
| EU | mvr | 305 / 328 k$ per t/h | (base) | mvr_usd_per_tph=328000.0 | A | `usbr149` |
| EU | maint | 3 / 5 % | (base) | maint_rest=0.02173913043478261;maint_mvr=0.02173913043478261;maint_ca=0.02173913043478261 | A | `towler2021` |
| EU | site | 10 / 20 % | (base) | site_frac=0.2 | A | `seider2016` |
| EU | ge | 9.55 / 11.55 % | (base) | selling_frac=0.03 | A | `seider2016` |
| US | gate | $29.76 / $68.65 per t | fee_usd_t=29.76;residue_fee_usd_t=29.76 | fee_usd_t=68.65;residue_fee_usd_t=68.65 | A/B | `fairfax2016`, `eref2024` |
| US | wage | $40 / $68.7 per h | (base) | wage_usd_h=68.7 | A | `seider2016`, `bls` |
| US | elec | 2 / 6.10 c/kWh | elec_usd_kwh=0.02 | elec_usd_kwh=0.061 | A/C | `baidoo2026`, `eia_epm` |
| US | hcl | $96 / $150 per t | hcl_price_usd_t=96.4 | (base) | B/C | `intratec2025`, `comtrade_hcl` |
| US | steam | 2.37/0.00 / 6.55/4.21 $/GJ | steam_lp_usd_gj=2.3698430679809532;steam_lt_usd_gj=0.0 | steam_lp_usd_gj=6.546120567975441;steam_lt_usd_gj=4.207716333333333 | A/assumption | `dea_cv` |
| US | prices | 200/205 / 235/245 $/t | price_caoh2_usd_t=200.0;price_pcc_usd_t=205.0 | price_caoh2_usd_t=235.0;price_pcc_usd_t=245.0 | A | `usgs_lime`, `comtrade` |
| US | aace | -20 / +30 % | location_factor=0.8 | location_factor=1.3 | A | `aace18r97` |
| US | ca | 1,184 / 1,925 $/t | ca_usd_per_t_cl2=1184.0 | ca_usd_per_t_cl2=1925.0 | A/B | `hanwha2021`, `schmittinger2011`, `bref_cak2014` |
| US | energy | 2.27 / 2.94 MWh/t Cl2 | energy_kwh_per_t_naoh=2047.5889929078014 | energy_kwh_per_t_naoh=2641.4769929078016 | B | `eurochlor_is12` |
| US | membrane | $1,000 / $1,925 per m2 | (base) | membrane_usd_m2=1925.0;membrane_life_yr=4.0 | A | `bref_cak2014` |
| US | mvr | 305 / 328 k$ per t/h | (base) | mvr_usd_per_tph=328000.0 | A | `usbr149` |
| US | maint | 3 / 5 % | (base) | maint_rest=0.02173913043478261;maint_mvr=0.02173913043478261;maint_ca=0.02173913043478261 | A | `towler2021` |
| US | site | 10 / 20 % | (base) | site_frac=0.2 | A | `seider2016` |
| US | ge | 9.55 / 11.55 % | (base) | selling_frac=0.03 | A | `seider2016` |
| KR | elec | 2 / 12.80 c/kWh | elec_usd_kwh=0.02 | elec_usd_kwh=0.1279724215562122 | A/C | `baidoo2026`, `kpx2025` |
| KR | hcl | $96 / $150 per t | hcl_price_usd_t=96.4 | (base) | B/C | `intratec2025`, `comtrade_hcl` |
| KR | steam | 2.37/0.00 / 6.55/4.21 $/GJ | steam_lp_usd_gj=2.3698430679809532;steam_lt_usd_gj=0.0 | steam_lp_usd_gj=6.546120567975441;steam_lt_usd_gj=4.207716333333333 | A/assumption | `dea_cv` |
| KR | prices | 200/205 / 235/245 $/t | price_caoh2_usd_t=200.0;price_pcc_usd_t=205.0 | price_caoh2_usd_t=235.0;price_pcc_usd_t=245.0 | A | `usgs_lime`, `comtrade` |
| KR | aace | -20 / +30 % | location_factor=0.8 | location_factor=1.3 | A | `aace18r97` |
| KR | ca | 1,184 / 1,925 $/t | ca_usd_per_t_cl2=1184.0 | ca_usd_per_t_cl2=1925.0 | A/B | `hanwha2021`, `schmittinger2011`, `bref_cak2014` |
| KR | energy | 2.27 / 2.94 MWh/t Cl2 | energy_kwh_per_t_naoh=2047.5889929078014 | energy_kwh_per_t_naoh=2641.4769929078016 | B | `eurochlor_is12` |
| KR | membrane | $1,000 / $1,925 per m2 | (base) | membrane_usd_m2=1925.0;membrane_life_yr=4.0 | A | `bref_cak2014` |
| KR | mvr | 305 / 328 k$ per t/h | (base) | mvr_usd_per_tph=328000.0 | A | `usbr149` |
| KR | maint | 3 / 5 % | (base) | maint_rest=0.02173913043478261;maint_mvr=0.02173913043478261;maint_ca=0.02173913043478261 | A | `towler2021` |
| KR | site | 10 / 20 % | (base) | site_frac=0.2 | A | `seider2016` |
| KR | ge | 9.55 / 11.55 % | (base) | selling_frac=0.03 | A | `seider2016` |
| JPK | gate | $334.29 / $434.58 per t | fee_usd_t=334.29163602326673;residue_fee_usd_t=334.29163602326673 | fee_usd_t=434.5791268302467;residue_fee_usd_t=434.5791268302467 | A/B | `moe_jp_ertdf` |
| JPK | elec | 2 / 9.13 c/kWh | elec_usd_kwh=0.02 | elec_usd_kwh=0.09131510329611553 | A/C | `baidoo2026`, `jepx2024` |
| JPK | hcl | $96 / $150 per t | hcl_price_usd_t=96.4 | (base) | B/C | `intratec2025`, `comtrade_hcl` |
| JPK | steam | 2.37/0.00 / 6.55/4.21 $/GJ | steam_lp_usd_gj=2.3698430679809532;steam_lt_usd_gj=0.0 | steam_lp_usd_gj=6.546120567975441;steam_lt_usd_gj=4.207716333333333 | A/assumption | `dea_cv` |
| JPK | prices | 200/205 / 235/245 $/t | price_caoh2_usd_t=200.0;price_pcc_usd_t=205.0 | price_caoh2_usd_t=235.0;price_pcc_usd_t=245.0 | A | `usgs_lime`, `comtrade` |
| JPK | aace | -20 / +30 % | location_factor=0.9199999999999999 | location_factor=1.4949999999999999 | A | `aace18r97` |
| JPK | ca | 1,184 / 1,925 $/t | ca_usd_per_t_cl2=1184.0 | ca_usd_per_t_cl2=1925.0 | A/B | `hanwha2021`, `schmittinger2011`, `bref_cak2014` |
| JPK | energy | 2.27 / 2.94 MWh/t Cl2 | energy_kwh_per_t_naoh=2047.5889929078014 | energy_kwh_per_t_naoh=2641.4769929078016 | B | `eurochlor_is12` |
| JPK | membrane | $1,000 / $1,925 per m2 | (base) | membrane_usd_m2=1925.0;membrane_life_yr=4.0 | A | `bref_cak2014` |
| JPK | mvr | 305 / 328 k$ per t/h | (base) | mvr_usd_per_tph=328000.0 | A | `usbr149` |
| JPK | maint | 3 / 5 % | (base) | maint_rest=0.02173913043478261;maint_mvr=0.02173913043478261;maint_ca=0.02173913043478261 | A | `towler2021` |
| JPK | site | 10 / 20 % | (base) | site_frac=0.2 | A | `seider2016` |
| JPK | ge | 9.55 / 11.55 % | (base) | selling_frac=0.03 | A | `seider2016` |

## 6. Monte Carlo (`src/ash_phswing/montecarlo.py`, `scripts/run_montecarlo.py`)

3,000 draws per region from triangular distributions (low, mode, high) on the sourced cost ranges, with the fee held at each
region's value; one `numpy.random.default_rng(261006)` stream shared in the order US, EU, KR, JPK, each variable drawn for all
3,000 samples in the order below. `maint` is the total maintenance fraction of TDC (divided by 2.3 per part); `capf` multiplies
the regional location factor; `plp` / `plt` are the host steam prices ($/GJ); `hcl` the surplus HCl price ($/t, 30 wt%).

| region | variable | low | mode | high |
|---|---|---|---|---|
| US | elec | 0.02 | 0.05 | 0.061 |
| US | capf | 0.8 | 1 | 1.3 |
| US | ca | 1184 | 1405 | 1925 |
| US | energy | 2047.59 | 2162.82 | 2641.48 |
| US | maint | 0.03 | 0.03 | 0.05 |
| US | pcaoh2 | 200 | 218 | 235 |
| US | ppcc | 205 | 225 | 245 |
| US | mvr | 305000 | 305000 | 328000 |
| US | plp | 2.36984 | 2.80613 | 6.54612 |
| US | plt | 0 | 2.08333 | 4.20772 |
| US | hcl | 96.4 | 150 | 150 |
| EU | elec | 0.02 | 0.05 | 0.10752 |
| EU | capf | 0.8 | 1 | 1.3 |
| EU | ca | 1184 | 1405 | 1925 |
| EU | energy | 2047.59 | 2162.82 | 2641.48 |
| EU | maint | 0.03 | 0.03 | 0.05 |
| EU | pcaoh2 | 200 | 218 | 235 |
| EU | ppcc | 205 | 225 | 245 |
| EU | mvr | 305000 | 305000 | 328000 |
| EU | plp | 2.36984 | 2.80613 | 6.54612 |
| EU | plt | 0 | 2.08333 | 4.20772 |
| EU | hcl | 96.4 | 150 | 150 |
| KR | elec | 0.02 | 0.05 | 0.127972 |
| KR | capf | 0.8 | 1 | 1.3 |
| KR | ca | 1184 | 1405 | 1925 |
| KR | energy | 2047.59 | 2162.82 | 2641.48 |
| KR | maint | 0.03 | 0.03 | 0.05 |
| KR | pcaoh2 | 200 | 218 | 235 |
| KR | ppcc | 205 | 225 | 245 |
| KR | mvr | 305000 | 305000 | 328000 |
| KR | plp | 2.36984 | 2.80613 | 6.54612 |
| KR | plt | 0 | 2.08333 | 4.20772 |
| KR | hcl | 96.4 | 150 | 150 |
| JPK | elec | 0.02 | 0.05 | 0.0913151 |
| JPK | capf | 0.8 | 1 | 1.3 |
| JPK | ca | 1184 | 1405 | 1925 |
| JPK | energy | 2047.59 | 2162.82 | 2641.48 |
| JPK | maint | 0.03 | 0.03 | 0.05 |
| JPK | pcaoh2 | 200 | 218 | 235 |
| JPK | ppcc | 205 | 225 | 245 |
| JPK | mvr | 305000 | 305000 | 328000 |
| JPK | plp | 2.36984 | 2.80613 | 6.54612 |
| JPK | plt | 0 | 2.08333 | 4.20772 |
| JPK | hcl | 96.4 | 150 | 150 |

Results (SI Fig. S20): EU median -61.2 M$ (5-95 % -169.0 to +28.3), P(NPV > 0) 14.7 %; Japan median -86.6, 6.5 %;
Korea median -237.1, 0 %; US median -291.7 (-374.4 to -221.1), 0 %. The draws reach the higher cost values of the ranges, so the medians lie below the
base cases, which sit at the favourable ends of several ranges.
