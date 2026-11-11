# Life-cycle (GWP100) basis

Code: `src/ash_phswing/lca.py` (`inventory`, `ledger`, `assess`); factors: `data/parameters/lca_factors.csv`.
Method: attributional inventory of the cost model's own flows, ecoinvent 3.11 cut-off factors (authors' openLCA extract),
IPCC 2021 GWP100.

## 1. Two results (ISO 14044:2006/Amd 2:2020)

Substitution is applied only to co-products, never to the functional unit itself, so two quantities are reported:

* **Product footprint** (kg CO2-eq per kg of Ca(OH)2 + PCC, no credit) = burdens / products, where burdens = electricity +
  host heat + purchased HCl and NaOH + deionized water + soda ash + softening sludge + purge make-up water.
* **Net balance per t of dry ash received** (system expansion) = (burdens + landfill of the plant's residue and cake
  - avoided hazardous landfill of the ash received - displaced hydrated lime - displaced conventional PCC) / t ash.

Not counted: the surplus HCl sold (cut-off: no burden, no displacement credit), the CO2 mineralized in Stage V (it is released
from the ash carbonate in Stage I, 21.6 kt/yr; the 1.6 kt/yr that the carbonators vent is counted), the brine purge to deep-well injection (no factor), capital goods and the
ash haul (co-located plant).

## 2. Inventory (`lca.inventory`, EU base case, per year)

| flow | amount | from |
|---|---|---|
| Ca(OH)2 / PCC | 57.8 / 45.4 kt | ProductRevenue |
| ash received / residue + cake landfilled | 240.0 / 88.1 kt | ASH_gate_fee |
| electricity, cells / process | 279.8 / 48.0 GWh | Electrolysis, C_utilities (process power / price) |
| cooling-water service | 57.0 GWh_th x 0.021 kWh_e/kWh_th | C_utilities cooling / cooling-water price |
| host heat, dryers (LP) / low temperature | 154.8 / 47.0 TJ | HostHeat |
| deionized water (carbonator) | 651.3 kt | CarbonatorDesign |
| soda ash / softening sludge | 1.59 / 1.37 kt | BrineSoftening |
| purge make-up water | 132.7 kt | purge make-up cost / $0.35 per m3 |
| HCl and NaOH purchased | 0 | Electrolysis make-up |

## 3. Power and heat cases (`lca.power_cases`)

* Base: incinerator power, cut-off attributional, EF 0; host heat burden-free consistently (lost-electricity EF 0).
* EU renewable PPA 0.040 kg/kWh; France, Netherlands, Germany grids (ecoinvent medium voltage); Korean grid 0.693.
* Host heat is burdened with the electricity the host does not export: (dryer MJ x Cv_LP + low-temperature MJ x Cv_LT) / 3.6
  x EF of the power case. Sensitivities: heat cut-off (0) and natural-gas steam (EF_STEAM_MJ).
* `assess` also returns the power EF at which the net balance is zero (neutral, heat burdened at the NL factor) and the EF at
  which the product footprint equals the conventional route (parity).

## 4. Results (`scripts/run_base_case.py`)

| case | net (kg CO2-eq/t ash) | footprint (kg CO2-eq/kg) |
|---|---|---|
| incinerator power (base) | -446.2 | 0.0277 |
| EU renewable PPA | -389.6 | 0.1594 |
| France grid | -336.5 | 0.283 |
| Netherlands grid | +182.5 | 1.489 |
| Germany grid | +223.2 | 1.584 |
| Korean grid | +534.4 | 2.308 |

Neutral power EF 0.311 kg/kWh, parity EF 0.195 kg/kWh, conventional lime + PCC mix 0.696 kg/kg (SI Section S14).
Base-case ledger per t ash: plant landfill +92.1, avoided ash landfill -250.8, lime credit -224.1, PCC credit -75.3,
water, soda ash, sludge and purge water +5.1, CO2 vented by the carbonators +6.8.

## 5. Factors (`data/parameters/lca_factors.csv`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `EF_SOLAR` | 0.04 | kg CO2-eq/kWh | `nrel2021`, `ipcc_ar5_annex3`, `nrel2024` | EU renewable PPA (life-cycle solar PV) |
| `EF_GRID_KR` | 0.6928723324459998 | kg CO2-eq/kWh | `kpx2023` | Korean grid (sensitivity case) |
| `EF_GRID_NL` | 0.4441844449318104 | kg CO2-eq/kWh | `ecoinvent311` | Netherlands medium-voltage electricity (ecoinvent 3.11 cut-off; consequential reading of host power) |
| `EF_GRID_DE` | 0.4729561625295224 | kg CO2-eq/kWh | `ecoinvent311` | Germany medium-voltage electricity |
| `EF_GRID_FR` | 0.07752586955970169 | kg CO2-eq/kWh | `ecoinvent311` | France medium-voltage electricity |
| `EF_GRID_US` | 0.4844772129267511 | kg CO2-eq/kWh | `ecoinvent311` | US medium-voltage electricity (not used in the base cases) |
| `EF_GRID_JP` | 0.6307165704689475 | kg CO2-eq/kWh | `ecoinvent311` | Japan medium-voltage electricity (not used in the base cases) |
| `EF_STEAM_MJ` | 0.126779900830931 | kg CO2-eq/MJ | `ecoinvent311`, `ipcc2006` | Natural-gas steam (sensitivity: no host heat) |
| `CRED_LANDFILL` | 0.2508222299062598 | kg CO2-eq/kg | `ecoinvent311` | Hazardous-waste landfill (residue + cake landfilled; ash landfill avoided) |
| `EF_HCL` | 0.26105909353450546 | kg CO2-eq/kg solution | `ecoinvent311` | HCl 30 wt% purchased (zero at the design point) |
| `EF_NAOH` | 0.7040315626969751 | kg CO2-eq/kg solution | `ecoinvent311` | NaOH 50 wt% purchased (zero at the design point) |
| `EF_WATER` | 0.0004733269444279 | kg CO2-eq/kg | `ecoinvent311` | Deionized water (carbonator slurry) |
| `EF_TAP` | 0.0011991671576907 | kg CO2-eq/kg | `ecoinvent311` | Tap water (make-up of the anolyte purge) |
| `EF_SODA` | 0.4590610231113894 | kg CO2-eq/kg | `ecoinvent311` | Soda ash for brine softening |
| `EF_SLUDGE` | 0.0182814225784294 | kg CO2-eq/kg | `ecoinvent311` | Softening sludge to inert landfill |
| `COOL` | 0.021 | kWh_e/kWh_th | `model` | Electricity of the cooling-water service per kWh of heat removed |
| `CRED_CAOH2` | 0.93 | kg CO2-eq/kg | `laveglia2022` | Displaced hydrated lime (range 0.85-0.94) |
| `CRED_PCC` | 0.3980811347066764 | kg CO2-eq/kg | `ecoinvent311`, `ecoinvent312_change` | Displaced conventional PCC (provider reports the value as underestimated) |
| `CV_LP` | 0.2020414665610507 | kWh_e/kWh_th | `dea_cv` | Electricity the host loses per kWh of dryer (LP) steam |
| `CV_LT` | 0.15 | kWh_e/kWh_th | `dea_cv` | Electricity the host loses per kWh of low-temperature heat |

The pool columns `GWP_solar_t_ash` / `GWP_grid_t_ash` (EU PPA / Netherlands grid, heat burdened at the same factor) are
linear in the power factor, so the GWP of every campaign run at any other factor (e.g. incinerator power, EF 0) follows by
linear interpolation (`pool.gwp_at`), which is what the NSGA-II search uses.
