# ash-phswing: pH-swing calcium recovery from incineration fly ash with chlor-alkali reagent regeneration

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24123111.svg)](https://doi.org/10.5281/zenodo.24123111)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

Code and data behind the techno-economic, life cycle and optimization results of

> J. Choi, K. Jang, W. Hyun, K.B. Lee, C. Kim, U. Lee, *Circular pH-swing-based mineral carbonation process using municipal
> solid waste incineration fly ash with in situ electrolytic reagent regeneration*, manuscript submitted to Chemical
> Engineering Journal (2026).

## Overview

- The plant treats 240 kt/yr of dry fly ash received at the gate of a large host incinerator. Stage I leaches the ash with HCl
  at a dose calibrated on the measured neutralization endpoint, Stage II precipitates magnesium and the heavy metals with NaOH
  at pH 11.0, and Stage III precipitates Ca(OH)2 at pH 13.0.
- Stage IV concentrates the NaCl brine by mechanical vapor recompression (MVR), electrolyzes it in membrane chlor-alkali
  cells and burns the chlorine with the hydrogen to HCl, so the plant buys no HCl or NaOH. Stage V carbonates part of the
  Ca(OH)2 to CaCO3 with the CO2 released in Stage I.
- Aspen Plus V14 (ELECNRTL, RGibbs stages) solves the flowsheet. This package prices the saved solutions (equipment sizing,
  bare-module capital, operating cost, discounted cash flow), computes the global warming potential (ecoinvent 3.11 cut-off,
  IPCC 2021 GWP100) and repeats the regional cases, the sensitivity analyses, the Monte Carlo and the surrogate, SHAP and
  NSGA-II analyses of the design campaign.
- Everything except the flowsheet solves runs from saved data, without Aspen Plus.

## Installation

```bash
git clone https://github.com/nicechoi99/ash-phswing.git
cd ash-phswing
python -m pip install -r requirements.txt
```

Python 3.10 or newer (tested with Python 3.14.4 on Windows 11). `requirements.txt` pins the versions used for the recorded
outputs (numpy, pandas, scipy, scikit-learn, xgboost, shap, pymoo, pytest). The scripts and tests put `src/` on the path
themselves; `pip install -e .` is optional. The Aspen Plus drivers in `scripts/aspen/` also need pywin32.

## Reproducing the article

| command | reproduces | article item |
|---|---|---|
| `python -m pytest tests` | 20 checks against the published values (about 5 min) | all items below |
| `python scripts/run_base_case.py` | EU base case: capital, operating cost, revenue, NPV, levelized cost, break-even fee, GWP | Section 2.3, Fig. 4b-f, SI Tables S23-S25 and S35 |
| `python scripts/run_regions.py` | Europe, United States, Korea and Japan (50,000 and 65,000 JPY/t) | SI Table S27, SI Figs. S16-S17 |
| `python scripts/run_ph3_ladder.py` | Stage III pH 12.2-14.0 and the choice of the design pH | Section 2.4, SI Fig. S25a |
| `python scripts/run_sensitivity.py` | uniform +-20 % and sourced-range tornados (the uniform one also returns a total-capital bar, which Fig. 5a replaces with the Class 4 accuracy band of Section 2.4) | Fig. 5a, SI Fig. S19 |
| `python scripts/run_montecarlo.py` | 3,000 triangular draws per region on the sourced ranges | Section 2.4, SI Fig. S20 |
| `python scripts/run_surrogate_shap.py` | surrogate learning curve, Bayesian-optimization check, SHAP, elasticities | Fig. 5b, SI Figs. S28-S29 |
| `python scripts/run_nsga2.py` | NSGA-II fronts of EU NPV against net GWP | Fig. 6d, SI Fig. S30 |
| `python scripts/price_pool.py` | re-prices the 347 converged runs among the 348 saved campaign solutions into the 335-run pool | SI Section S15 |

Run the commands from the repository root (`python -X utf8 ...` on Windows consoles). Each script prints its results next to
the published values and writes JSON and CSV files to `results/`.

## Recorded outputs

Produced by the commands above with the pinned versions; every value agrees with the article to the printed precision.

| quantity | value |
|---|---|
| EU NPV over 20 years, credited tax / without the tax credit (M$) | +9.1 / +8.2 |
| TCI / TDC (M$) | 270.8 / 227.5 |
| cash OPEX / annualized CAPEX / annual cost (M$/yr) | 85.3 / 29.9 / 115.2 |
| revenue (M$/yr): total / treatment fee / surplus HCl / Ca(OH)2 / CaCO3 | 120.2 / 86.0 / 11.3 / 12.6 / 10.2 |
| calcium products Ca(OH)2 + CaCO3 (kt/yr) | 57.8 + 45.4 = 103.2 |
| levelized cost / net levelized cost ($/t) | 1,116 / 173 |
| common price of both products at NPV = 0 / break-even treatment fee, Europe ($/t) | 206 / 348 |
| electricity (GWh/yr) / chlorine capacity (kt/yr) | 328 / 114.7 |
| NPV United States / Korea / Japan 50,000 JPY/t / Japan 65,000 JPY/t (M$) | -253.3 / -150.2 / -21.2 / +61.4 |
| net GWP, incinerator power / EU renewable PPA (kg CO2-eq/t ash) | -446 / -390 |
| product footprint, incinerator power / EU renewable PPA (kg CO2-eq/kg) | 0.028 / 0.159 |
| EU NPV at Stage III pH 12.5 / 13.0 / 13.2 / 13.4 / 14.0 (M$) | -42.9 / +9.1 / +9.2 / +4.8 / -54.6 |
| Monte Carlo, 3,000 draws: EU median (5-95 %) / P(NPV > 0) | -61.2 M$ (-169.0 to +28.3) / 14.7 % |
| Monte Carlo median and P(NPV > 0): Japan 50,000 JPY/t / Korea / United States | -86.6 (6.5 %) / -237.1 (0 %) / -291.7 (0 %) |
| campaign pool: retained runs / runs with positive EU NPV / best EU NPV (M$) | 335 / 44 / +30.6 |
| surrogate hold-out MAE, levelized cost (sigma) / Bayesian optimization reaches the minimum after | 0.434 -> 0.069 / 13 iterations |
| mean abs. SHAP on EU NPV: NaOH dose Stage III / HCl concentration / T Stage III (M$); operating share | 42.8 / 37.9 / 14.4; 96.9 % |
| NSGA-II front, incinerator power: NPV (M$) / net GWP (kg CO2-eq/t ash) | -150.2 to +26.7 / -511.2 to -506.7 |
| re-pricing the 347 converged solutions: largest relative difference from the pool table | 1.6e-13 |

## Data

- `data/aspen/design_COMP_p130.json`: saved Aspen Plus solution of the design point (streams and blocks of Stages I-III,
  exported with `ash_phswing.flowsheet.export_pickle`); `data/aspen/ladder/`: the Stage III pH ladder;
  `data/aspen/feeds.json`: feed compositions and acid doses.
- `data/aspen/model/261106_AshpHSwing5M-NaOH5N_Run2Feed_MVR-HClAbsorber-StageVBatch-PaperTags.bkp`: the full design-point
  flowsheet with the block and stream names of the article (SI Fig. S7, SI Table S18).
  `data/aspen/model/261026_AshpHSwing5M-NaOH5N_MVR-Converged.bkp`: the template that the drivers in `scripts/aspen/` open.
- `data/pool/aspen_pool_261026n5.zip`: the 348 saved campaign solutions (347 meet the convergence gate) and the 350-run log;
  `data/pool/pool_261026n5.csv`: the 335 retained designs priced on the European and US cases.
- `data/parameters/`: every cost, region, sensitivity, Monte Carlo and emission-factor input with its source key;
  sources are resolved in `data/parameters/sources.csv`.
- `data/reference/canon_261026n5_reference.json`: the published values that the tests and scripts compare against.
- The tag `261026n5` in file names is the internal build label of this basis.

Method notes: `docs/TEA_basis.md`, `docs/LCA_basis.md`, `docs/optimization_sensitivity.md`.

## What needs Aspen Plus

Only `scripts/aspen/` (Aspen Plus V14 through COM, Windows, pywin32): `run_design_point.py` (design point and Stage III pH
ladder), `run_campaign.py` (350-run Latin-hypercube campaign) and `run_feed_grid.py` (HCl x NaOH feed-concentration grid).
They write the same solution pickles and JSON files that the cost model reads. Stage II and Stage III set-points are met by
bisection on the NaOH feed outside the flowsheet; Stage I is pinned at the calibrated acid dose.

## Not included

- The scenario and siting tables of the Supporting Information (purchased reagents, BMED, hub with trucked ash, grant,
  non-hazardous residue route, peer cost conventions, carbon credit), which ran on separate scripts.
- Figure scripts and the experimental data (ICP-OES, XRD, TGA); the experimental results are reported in the Supporting
  Information.

## Changes

- 1.0.1 (2026-11-12): documentation brought in line with the article (Stage I dose 10.42 mol HCl per kg in
  `docs/optimization_sensitivity.md`, Stage III NaOH 75.0 t/h in `docs/TEA_basis.md`, 347 of the 350 campaign runs meet the
  convergence gate); the Stage III pH ladder extended to pH 14.0 with three saved solutions (SI Fig. S25a). Every
  published value is unchanged.
- 1.0.0 (2026-11-11): first release.

## License

MIT for the code (see `LICENSE` and `NOTICE`). The emission factors in `data/parameters/lca_factors.csv` are aggregated
GWP100 values extracted from ecoinvent 3.11; the ecoinvent datasets themselves are licensed and are not distributed here.

## How to cite

Please cite the article above and this archive (https://doi.org/10.5281/zenodo.24123111, which resolves to the latest version; the DOI of each version is listed on that page); `CITATION.cff` holds the archive DOI.
