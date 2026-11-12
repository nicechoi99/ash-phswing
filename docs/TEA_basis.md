# Techno-economic basis

Every number below is read by the code from `data/parameters/*.csv`; the tables in this file are rendered from those
CSV files, so the CSV is the single source. Source keys resolve in `data/parameters/sources.csv` (reproduced at the end).
Design-point values quoted in the text are the outputs of `scripts/run_base_case.py` (EU base case of the article).

## 1. Scope and plant

* Co-located plant at the host incinerator: 240 kt/yr of dry fly ash received at the gate (30 t/h dry ash, fed as a slurry
  with 30 t/h process water), 8,000 h/yr, 5 M HCl (16.83 wt%), Stage III pH 13.0, Stage III NaOH (NAOH2) at 5 N (17 wt%, 75.0 t/h), measured CaCl2 in
  the feed (14.7 wt%).
* Flowsheet results come from Aspen Plus V14 (ELECNRTL, RGibbs stages); the cost model reads the saved results
  (`data/aspen/design_COMP_p130.json`). Stage V carbonation is costed outside the flowsheet: the Ca(OH)2 of stream CAOH2 is
  carbonated with the CO2 released in Stages I-III (streams 1CO2/2CO2/3CO2), the rest is sold as Ca(OH)2.
* Code path: `tea.evaluate(case)` = `tea.prepare` (plant additions) -> `capex.estimate` (sizing, bare-module cost) ->
  `opex.estimate` (reagents, utilities, revenue) -> `opex.brine_acid` -> `opex.host_steam` -> `opex.bill_all_ash` -> `cashflow.capital_and_cashflow`
  -> `tea.summary` (NPV, LC, MSP).

## 2. Plant additions on top of the flowsheet (`tea.prepare`)

* Cake wash: 2 bed volumes on the Ca(OH)2 product, the Stage II cake and the Stage I residue at 30 % moisture; the wash
  water (19.3 t/h) joins the Stage III brine (stream 3OUT3) before the brine loop.
* Stage I cooler: the RGibbs leach B1 is held at 25 C; its heat removal (5.0 MW) is costed as a Ti-tube shell-and-tube
  exchanger (Seider Eq. 16.40, U = 850 W/m2K) on chilled water (return min(15 C, T1 - 3 C)); the chilled-water increment
  $5.00/GJ less the cooling-water charge already in the duty costing ($0.212/GJ) enters the utilities.
* PCC filtrate recycled to the carbonator; its make-up water is priced at $0.50/m3.
* Brine loop (need-based regeneration): cell duty N = max(Stage I HCl need, Stage II + III NaOH need) / 0.985 (HCl synthesis
  efficiency); here NaOH binds (398.2 vs 312.7 kmol/h) -> 16.17 t/h NaOH made, 14.52 t/h HCl made, 11.40 t/h used in Stage I.
  Brine cations beyond the duty leave with a purge of depleted anolyte (220 g/L NaCl, 1.148 kg/L): 17.9 m3/h to deep-well
  disposal ($0.54/m3) plus its make-up water ($0.35/m3). A brine with fewer cations than the need ('salt deficit', some
  campaign runs only) is priced with full regeneration (cells on all NaCl, no purge).
* Brine acidification (`opex.brine_acid`): the Stage III filtrate carries the free NaOH left after
  Ca(OH)2 precipitation to the cells, and membrane practice acidifies the inlet brine with HCl (Schmittinger 2011, 7.2-7.3).
  One mol of cell HCl per mol of free OH- in stream 3OUT3 is taken before the surplus is sold: 7.92 kmol/h, 0.29 t/h HCl at the
  design point, so the surplus is 2.83 t/h (75.4 kt/yr of 30 wt% acid). The NaCl formed returns to the cells, and the chloride
  cap (cell HCl <= brine Cl- + acid Cl-) is recorded in `q['BrineAcid']`. A shortfall would be bought as 30 wt% HCl. Without it, NaOH
  dosed beyond the calcium demand would appear as cell HCl that can be sold.

## 3. Capital (`capex.estimate`, `cashflow.capital_and_cashflow`)

### 3.1 Bare-module costs (Seider et al. 2016, CEPCI 567 -> 800)

`equipment.py` implements the Seider purchase-cost correlations and the bare-module rule
C_BM = C_P x (800/567) x [F_BM + (F_M - 1)] (material factor added, not multiplied).

| item | sizing basis | material | correlation |
|---|---|---|---|
| Stage I-III RGibbs reactors | 30 min residence on the outlet slurry, 1,100 kg/m3, trains of <= 50 m3, turbine agitator 10 hp/1000 gal | SS316 F_M 2.1 (rubber-lined CS costed as SS316 in acid service) | vertical vessel Eq. 16.52-16.60 + agitator Table 16.32 |
| mixers | 5 min, agitator 0.5 hp/1000 gal | SS316 | as above |
| CO2 disengagement drums (Flash2) | 5 min liquid hold-up at half full | SS316 | vertical vessel |
| solid separations (Filter blocks) | solids t/h | stainless | solid-bowl centrifuge Table 16.32 |
| pumps (12 process streams + regenerated lye and acid) | volumetric flow, 30 m head, one installed spare | Hastelloy C 2.95 (acid), SS 2.0 | Eqs. 16.14-16.19 |
| Stage V carbonators | four batch vessels in rotation, 5 wt% slurry, sized from the measured CO2 uptake (`design.stage5_*`) | carbon steel | agitated vessel, 10 hp/1000 gal |
| CO2 blower | 1 -> 2 bar, k 1.29, 313 K, eta 0.75 | stainless 2.5 | Eq. 16.31 |
| PCC centrifuge, Ca(OH)2 and PCC dryers | solids; 30 % cake moisture, 2 lb water/h/ft3 | stainless / CS | Table 16.32 |
| product silo (7 d), HCl and NaOH day tanks (1 d) | bulk density 0.5 t/m3 | CS; HCl tank F_M 2.0 | storage bin / cone-roof tank |
| Stage I cooler | see section 2 | Ti tubes | Eq. 16.40 |

Design point: reactors 6.30, mixers 1.31, drums 1.67, centrifuges 1.64, pumps 1.22, blower 0.15, Stage V 4.07,
storage 2.15, miscellaneous + cooler 0.55, MVR 42.09 -> TBM $61.16 M (SI Table S21).

### 3.2 Brine concentration (MVR)

Single-effect MVR evaporates the brine water not carried through the membranes (4.0 mol H2O per mol Na, Schmittinger):
142.1 t/h at the design point. Installed cost = $305k per t/h at the USBR Report 149 reference 132.1 t/h, scaled with the
six-tenths rule; the Seider evaporator (U 3 kW/m2K, dT 10 K, BPE 6.5 K, SS tubes) and compressor (isentropic 0.85, motor
0.95, F_M 2.5) correlations only split that total and give the compressor power (4.84 MW).
The MVR is also modelled as an open section of the template flowsheet `261026_...MVR-Converged.bkp` (F-410 Flash2,
C-410 compressor, E-413 condenser, E-414 cooler); on the earlier 5 N design point it evaporated 139.6 t/h with a 4.75 MW
compressor, against 139.6 t/h and 4.76 MW from the cost model. The cost model does not read that section.

### 3.3 Chlor-alkali plant

The membrane chlor-alkali plant enters at total-direct-capital level: $1,405 per (t Cl2/yr) (Schmittinger, Ullmann's),
with its rectifier re-costed from the Stinn Eq. 7 value ($1,155.5/kW) to the BREF electricity-supply value ($506/kW) at
0.27875 kW DC per t Cl2/yr: 1,405 - (1,155.5 - 506) x 0.27875 = $1,223.9 per t Cl2/yr, times the installed capacity
(NaOH duty x 8,000 h / 1.128 = 114.7 kt Cl2/yr) = $140.4 M (`tea.chlor_alkali_usd_per_t`). It carries the location factor
but not site, service, allocation or contingency (it is a TDC-level value). The cells: CE 0.96, 2.832 V, 6 kA/m2,
1,881 m2 active area, 32.0 MW DC.

### 3.4 Factor stack (Seider)

TDC = [TBM + site 10 % + service 5 % + allocated (5 % TBM + utility-plant allocation)] x 1.18 (contingency 15 % + fee 3 %)
+ chlor-alkali, times the location factor; TCI = TDC + land 2 % + start-up 10 % + working capital.
Design point: TDC $227.5 M (chlor-alkali 140.4, MVR share 60.0, rest 27.2), TCI $270.8 M.
The AACE 18R-97 Class 4 band (-20 / +30 %) is applied to the location factor as uncertainty only (sensitivity), never as a lever.

## 4. Operating cost and revenue (`opex.estimate`, `cashflow`)

* Electrolysis power = NaOH made x 2,162.8 kWh/t (2.4 MWh AC/t Cl2, BREF, + 35.5 kWh/t other loads) at the host power
  price $0.05/kWh (328 GWh/yr incl. process power, $14.0 M cell power).
* Membranes: 0.01454 m2 per t NaOH/yr, $1,000/m2 every 4 years ($0.47 M/yr); the initial membrane set is excluded from
  the maintenance base.
* Process power: agitators, pumps, MVR compressor, CO2 blower, centrifuges (1 kWh/m3) at the same price.
* Heat: Aspen block duties at $6.8/GJ (temperature-banded), dryer steam 3.5 MJ/kg water; then re-priced at the host's
  lost-electricity cost: dryer (LP) steam $2.806/GJ = Cv 0.202 x $0.05/kWh / 3.6, low-temperature heat $2.083/GJ
  (Cv 0.15) (`opex.host_steam`). Cooling water $0.212/GJ.
* Brine softening: soda ash 1.1 x stoichiometric on the Ca + Mg of the cell feed ($150/t), CaCO3/Mg(OH)2 sludge landfilled
  at the treatment fee.
* Residue and cake: the plant bills the fee on all 240 kt/yr received and landfills its Stage I residue and Stage II cake
  (88.1 kt/yr) at the same rate ($31.6 M in Europe) (`opex.bill_all_ash`).
* Labor (Seider Eq. 17.2): 15 operators per shift x 5 shifts x 2,080 h x wage; + 15 % supervision, 6 % supplies,
  $60k technical assistance and $65k control laboratory per operator post ($9.43 M in Europe).
* Maintenance: 3 % of TDC in total (wages + salaries 0.25 + materials 1.0 + overhead 0.05 = 2.3 parts of the wage term),
  applied to the chlor-alkali block (net of the initial membranes), the MVR share and the rest of the plant ($6.77 M).
* Operating overhead 7.1 / 2.4 / 5.9 / 7.4 % of (labor wages + supervision + maintenance wages + salaries); property tax and
  insurance 2 % of TDC; general expenses 9.55 % of sales (selling 1 %, research 4.8 %, allocated research 0.5 %,
  administration 2 %, incentives 1.25 %).
* Revenue: Ca(OH)2 $218/t (57.8 kt/yr), PCC $225/t (45.4 kt/yr), surplus HCl $150/t as 30 wt% (75.4 kt/yr, after brine acidification),
  treatment fee on all ash received; surplus NaOH, Mg(OH)2 cake, zinc and CO2 credits are not priced.
  EU: $120.2 M/yr against an annual cost of $115.2 M/yr (OPEX $85.3 M + annualized CAPEX $29.9 M).

## 5. Discounted cash flow (`cashflow`, `tea.summary`)

* 20 years incl. 2 construction years (TDC spent evenly), 8.5 % real discount rate, 21 % tax, MACRS 7-year depreciation of
  the TDC from the first operating year; working capital, land and start-up paid at the end of construction; working capital
  and land recovered in the last year. Year 1 is undiscounted (factor (1 + r)^-(year - 1)).
* Credited-tax convention: negative taxable income earns a tax credit (model NPV); `NPV_standalone` carries losses forward
  instead (EU +8.2 M$).
* Working capital = 0.0833 COM + 0.0192 S + 0.0833 S - 0.0833 feed cost (Seider), with COM incl. book depreciation
  (8 % of TDC net of allocation, 6 % of allocation); the book depreciation is removed from the cash OPEX.
* CRF over the 18 operating years = 0.11043; levelized cost LC = (CRF x TCI + OPEX) / calcium products; net levelized cost
  (engine key `MSP`) = LC - (fee + surplus HCl revenue) / products; the common product price at NPV = 0 and the break-even fee
  follow from two runs because the NPV is affine in both (`tea.breakevens`).

## 6. Regional cases (`data/parameters/regions.csv`)

Every region keeps the co-located plant and host power at $0.05/kWh; the grid price enters only the sensitivity. FX 2025:
1.1306 USD/EUR, 1,421.4 KRW/USD, 149.57 JPY/USD.

| region | label | fee ($/t) | local fee | wage ($/h) | location factor | power ($/kWh) | grid ($/kWh, sensitivity) | sources |
|---|---|---|---|---|---|---|---|---|
| EU | EU, co-located with the incinerator | 358.52 | EUR 317/t | 40.0 | 1.0 | 0.05 | 0.1075 | fee `bref_wi2019`, `eurostat_hicp`; wage `eurostat_lc`; grid `eurostat_nrg` |
| US | US Gulf Coast | 40.00 | $40/t | 40.0 | 1.0 | 0.05 | 0.0610 | fee `fairfax2016`, `eref2024`; wage `seider2016`; grid `eia_epm` |
| KR | Korea 2027 | 147.74 | 210,000 KRW/t | 30.6 | 1.0 | 0.05 | 0.1280 | fee `mcee2026`; wage `moel2024`; grid `kpx2025` |
| JPK | Japan, typical off-site disposal fee | 334.29 | 50,000 JPY/t | 18.1 | 1.15 | 0.05 | 0.0913 | fee `moe_jp_ertdf`; wage `mhlw2021`; grid `jepx2024` |
| JPK65 | Japan, fee agreed in Chiba Prefecture | 434.58 | 65,000 JPY/t | 18.1 | 1.15 | 0.05 | 0.0913 | fee `moe_jp_ertdf`; wage `mhlw2021`; grid `jepx2024` |

Results (`scripts/run_regions.py`): NPV EU +9.1, US -253.3, Korea -150.2, Japan -21.2 (50,000 JPY/t) and +61.4 M$
(65,000 JPY/t, Chiba Prefecture); break-even fee $348/t in Europe and the United States (0.97 and 8.7 times their fees),
$330/t in Korea (2.2 times) and $360/t in Japan (1.08 times the 50,000 JPY/t fee).

## 7. All TEA parameters (`data/parameters/tea_parameters.csv`)


**plant** (used in `tea.prepare / opex / cashflow (operating hours)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `plant.operating_hours` | 8000 | h/yr | `seider2016` | Annual operating hours (Seider utility basis) |
| `plant.dry_ash_kt_yr` | 240 | kt/yr | `model` | Dry fly ash received at the gate (30 t/h dry ash in the Aspen feed x 8000 h) |

**financial** (used in `cashflow.capital_and_cashflow, tea.summary`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `financial.discount_rate` | 0.085 | - | `model` | Real discount rate |
| `financial.plant_life_yr` | 20 | yr | `model` | Project horizon including construction |
| `financial.construction_yr` | 2 | yr | `model` | Construction period; capital spent evenly |
| `financial.tax_rate` | 0.21 | - | `model` | Income tax; negative taxable income credited (credited-tax NPV) |
| `financial.macrs` | [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446] | - | `irs_macrs` | MACRS 7-year depreciation of the TDC from the first operating year |
| `financial.working_capital_com_frac` | 0.0833 | - | `seider2016` | Working capital = 0.0833 COM + 0.0192 S + 0.0833 S - 0.0833 feed cost (Seider) |
| `financial.working_capital_sales_frac_a` | 0.0192 | - | `seider2016` | See above |
| `financial.working_capital_sales_frac_b` | 0.0833 | - | `seider2016` | See above |

**capital** (used in `cashflow.capital_and_cashflow`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `capital.cepci_now` | 800 | - | `cepci` | CEPCI 2024 basis for all correlations |
| `capital.cepci_seider` | 567 | - | `seider2016` | CEPCI of the Seider correlations (2013) |
| `capital.misc_equipment_usd` | 20000 | $ | `model` | Fixed miscellaneous equipment item added to the bare-module cost |
| `capital.site_frac` | 0.10 | - | `seider2016` | Site preparation (fraction of TBM + direct items) |
| `capital.service_frac` | 0.05 | - | `seider2016` | Service facilities |
| `capital.allocation_frac` | 0.05 | - | `seider2016` | Generic allocated cost (fraction of TBM) |
| `capital.contingency_frac` | 0.18 | - | `seider2016` | Contingency 15 % + contractor fee 3 % (Seider Eq. 16.11) |
| `capital.land_frac` | 0.02 | - | `seider2016` | Land (fraction of TDC) |
| `capital.startup_frac` | 0.10 | - | `seider2016` | Start-up allowance (fraction of TDC) |
| `capital.location_factor` | 1.0 | - | `seider2016` | Location factor on the TDC (regional value in regions.csv) |
| `capital.utility_alloc_steam_coef` | 930 | $ | `seider2016` | Utility-plant allocation: 930 S_steam^0.81 (S in 1000 lb/h) x CEPCI ratio |
| `capital.utility_alloc_steam_exp` | 0.81 | - | `seider2016` | See above |
| `capital.utility_alloc_elec_coef` | 2900000 | $ | `seider2016` | Utility-plant allocation: 2.9e6 S_elec^0.83 (S in MW) x CEPCI ratio |
| `capital.utility_alloc_elec_exp` | 0.83 | - | `seider2016` | See above |
| `capital.utility_alloc_cw_coef` | 1100 | $ | `seider2016` | Utility-plant allocation: 1100 S_cw^0.68 (S in gpm) x CEPCI ratio |
| `capital.utility_alloc_cw_exp` | 0.68 | - | `seider2016` | See above |

**chloralkali** (used in `tea.chlor_alkali_usd_per_t, capex.estimate (Cl2 capacity)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `chloralkali.capital_usd_per_t_cl2` | 1405 | $/(t Cl2/yr) | `schmittinger2011` | Chlor-alkali plant at total-direct-capital level; range 1184 (Hanwha 2021) to 1925 (BREF) |
| `chloralkali.rectifier_stinn_usd_kw` | 1155.535 | $/kW | `stinn2020` | Rectifier cost of Stinn Eq. 7 at this plant (contained in the per-t value above) |
| `chloralkali.rectifier_bref_usd_kw` | 506 | $/kW | `bref_cak2014` | BREF CAK 2014 Table 4.4 electricity supply EUR 81/t Cl2 at 38.9 MW; replaces the Stinn rectifier |
| `chloralkali.dc_kw_per_t_cl2_yr` | 0.27875 | kW/(t Cl2/yr) | `stinn2020` | DC power per annual t Cl2 at the reference design (37055.507 kW / 132934.553 t/yr) |
| `chloralkali.naoh_per_cl2` | 1.128 | t NaOH/t Cl2 | `stoich` | Mass ratio used for the installed Cl2 capacity |

**electrolysis** (used in `tea.cost_dict -> capex.estimate (cells), opex.estimate (power, membranes)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `electrolysis.energy_kwh_per_t_naoh` | 2162.8209929078016 | kWh/t NaOH | `bref_cak2014` | 2400 kWh AC/t Cl2 (BREF bipolar membrane) / 1.12816 + 35.46 kWh/t other loads; range 2.27-2.94 MWh/t Cl2 (Euro Chlor IS12) |
| `electrolysis.current_efficiency` | 0.96 | - | `schmittinger2011` | Membrane cell NaOH current efficiency (3-7 % loss -> 0.93-0.97) |
| `electrolysis.cell_voltage` | 2.8322860548271755 | V | `eurochlor_is12`, `schmittinger2011` | U = 1976.9 kWh DC/t NaOH x CE / 670.07 kAh/t (DC = Euro Chlor 2.27 MWh/t Cl2 / 1.128 - 35.5 kWh rectifier loss); sizes the DC power only |
| `electrolysis.current_density` | 6000 | A/m2 | `tk_nucera` | Membrane current density |
| `electrolysis.element_area_m2` | 2.72 | m2 | `tk_nucera` | Active area per element (reporting only) |
| `electrolysis.hcl_synthesis_efficiency` | 0.985 | - | `energystar2025` | Cl2 + H2 -> HCl synthesis conversion 98-99 % (also divides the cell duty) |
| `electrolysis.membrane_area_per_t_yr` | 0.014541774709106267 | m2/(t NaOH/yr) | `stoich` | 1 / (j x 8000 h x 3600 s x CE / F x M_NaOH) |
| `electrolysis.membrane_usd_m2` | 1000 | $/m2 | `bref_cak2014` | Membrane replacement (assumption); 1925 $/m2 with gaskets (BREF p.177) as the high end |
| `electrolysis.membrane_life_yr` | 4 | yr | `bref_cak2014` | Membrane replacement interval |

**regen** (used in `tea.prepare (purge), capex (brine water), opex (purge cost)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `regen.anolyte_g_l` | 220 | g/L NaCl | `schmittinger2011` | Depleted anolyte purged to control sulfate |
| `regen.anolyte_density` | 1.148 | kg/L | `schmittinger2011` | Density of the depleted anolyte |
| `regen.purge_disposal_usd_m3` | 0.54 | $/m3 | `usbr149` | Deep-well disposal of the anolyte purge |
| `regen.water_usd_m3` | 0.35 | $/m3 | `seider2016` | Process/make-up water price |
| `regen.water_transport_mol_per_mol` | 4.0 | mol H2O/mol Na | `schmittinger2011` | Water carried through the membrane to the catholyte (3.5-4.5) |

**mvr** (used in `capex.estimate (brine concentration)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `mvr.usd_per_tph` | 305000 | $/(t/h) | `usbr149` | Installed brine-concentrator cost per t/h evaporated (USBR Report 149 Table 4.7); 328k high end |
| `mvr.ref_tph` | 132.1 | t/h | `usbr149` | Reference evaporation rate of the six-tenths scaling |
| `mvr.scale_exp` | 0.6 | - | `seider2016` | Six-tenths rule |
| `mvr.U_w_m2k` | 3000 | W/(m2 K) | `randon2020` | Overall heat-transfer coefficient (split of the MVR cost between evaporator and compressor) |
| `mvr.dT_K` | 10 | K | `randon2020` | Temperature lift |
| `mvr.bpe_K` | 6.5 | K | `schmittinger2011` | Boiling-point elevation at 300 g/L |
| `mvr.eta_isentropic` | 0.85 | - | `randon2020` | Compressor isentropic efficiency |
| `mvr.eta_motor` | 0.95 | - | `seider2016` | Motor efficiency |
| `mvr.tube_material` | SS | - | `seider2016` | Evaporator tube material (SS / Monel / Ti) |
| `mvr.compressor_fm` | 2.5 | - | `seider2016` | Compressor material factor (stainless) |

**design** (used in `capex.estimate / tea.prepare`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `design.tau_reactor_min` | 30 | min | `seider2016` | Residence time of the Stage I-III RGibbs reactors |
| `design.tau_mixer_min` | 5 | min | `seider2016` | Residence time of mixers |
| `design.slurry_density` | 1100 | kg/m3 | `model` | Slurry density for vessel volumes |
| `design.hp_per_kgal_suspension` | 10 | hp/1000 gal | `seider2016` | Agitation power for solids suspension and gas dispersion (Seider p.470) |
| `design.hp_per_kgal_blend` | 0.5 | hp/1000 gal | `seider2016` | Agitation power for blending |
| `design.hp_per_kgal_gas` | 10 | hp/1000 gal | `seider2016` | Carbonator agitation power |
| `design.vessel_max_m3` | 50 | m3 | `model` | Largest single vessel; trains are split above |
| `design.pump_head_m` | 30 | m | `seider2016` | Pump head |
| `design.cake_moisture` | 0.30 | - | `model` | Moisture of the product cakes entering the dryers |
| `design.dryer_mj_per_kg_water` | 3.5 | MJ/kg | `seider2016` | Dryer heat per kg water evaporated |
| `design.bulk_density_t_m3` | 0.5 | t/m3 | `model` | Product bulk density (silos) |
| `design.silo_days` | 7 | d | `model` | Product storage |
| `design.reagent_tank_days` | 1 | d | `model` | HCl and NaOH day tanks |
| `design.centrifuge_kwh_per_m3` | 1.0 | kWh/m3 | `seider2016` | Centrifuge power per m3 of feed |
| `design.co2_pressure_ratio` | 2.0 | - | `model` | CO2 blower 1 -> 2 bar |
| `design.co2_k` | 1.29 | - | `model` | Heat-capacity ratio of CO2 |
| `design.co2_T_K` | 313 | K | `model` | Blower inlet temperature |
| `design.co2_eta` | 0.75 | - | `seider2016` | Blower efficiency |
| `design.carbonator_wt_solid` | 0.05 | - | `model` | Carbonator slurry solids fraction |
| `design.carbonator_residence_min` | 30 | min | `model` | Carbonator residence time |
| `design.carbonator_density` | 1100 | kg/m3 | `model` | Carbonator slurry density |
| `design.wash_bed_volumes` | 2.0 | - | `model` | Cake wash water (bed volumes) on Ca(OH)2 / Mg(OH)2 cake / leach residue; filtrate joins the brine |
| `design.wash_cake_moisture` | 0.30 | - | `model` | Cake moisture used for the wash volume |
| `design.stage1_hx_U` | 850 | W/(m2 K) | `seider2016` | Stage I cooler (Ti tubes) heat-transfer coefficient |
| `design.carbonation_makeup_water_t_h` | 4.15 | t/h | `model` | Make-up water of the PCC filtrate recycle |
| `design.bfw_usd_m3` | 0.50 | $/m3 | `seider2016` | Make-up water price for the carbonator loop |

**labor** (used in `cashflow (labor)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `labor.operators_per_shift` | 15 | - | `seider2016` | Operators per shift (ceil(15 f^0.25) at f = 1) |
| `labor.shifts` | 5 | - | `seider2016` | Shift crews (Seider Eq. 17.2) |
| `labor.hours_per_shift_yr` | 2080 | h | `seider2016` | Paid hours per operator per year |
| `labor.wage_usd_h` | 40 | $/h | `eurostat_lc` | Operating labor rate (regional value in regions.csv) |
| `labor.supervision_frac` | 0.15 | - | `seider2016` | Direct supervision and clerical labor (fraction of DW&B) |
| `labor.supplies_frac` | 0.06 | - | `seider2016` | Operating supplies and services (fraction of DW&B) |
| `labor.tech_assist_usd` | 60000 | $/operator-yr | `seider2016` | Technical assistance to manufacturing per operator post |
| `labor.control_lab_usd` | 65000 | $/operator-yr | `seider2016` | Control laboratory per operator post |

**maintenance** (used in `tea.base_case -> cashflow (maintenance)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `maintenance.frac_tdc` | 0.03 | - | `towler2021` | Total maintenance = 3 % of TDC (wages 1 + salaries 0.25 + materials 1 + overhead 0.05 = 2.3 parts); 5 % high end |

**overhead** (used in `cashflow`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `overhead.frac` | [0.071, 0.024, 0.059, 0.074] | - | `seider2016` | Operating overhead fractions of (labor wages + supervision + maintenance wages + salaries) |

**property** (used in `cashflow`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `property.tax_insurance_frac` | 0.02 | - | `seider2016` | Property tax and insurance (fraction of TDC) |

**depreciation** (used in `cashflow (COM)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `depreciation.frac_tdc` | 0.08 | - | `seider2016` | Book depreciation inside the COM (removed from the cash OPEX) |
| `depreciation.frac_alloc` | 0.06 | - | `seider2016` | Book depreciation on the allocated capital |

**general** (used in `cashflow (general expenses)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `general.selling_frac` | 0.01 | - | `seider2016` | Selling expenses (fraction of sales); 3 % for external buyers as the high end |
| `general.rd_frac` | 0.048 | - | `seider2016` | Direct research |
| `general.allocated_rd_frac` | 0.005 | - | `seider2016` | Allocated research |
| `general.admin_frac` | 0.02 | - | `seider2016` | Administrative expenses |
| `general.incentive_frac` | 0.0125 | - | `seider2016` | Management incentive compensation |

**utility** (used in `tea.cost_dict -> opex / cashflow`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `utility.electricity_usd_kwh` | 0.05 | $/kWh | `zhang2024` | Host incinerator power for the whole demand (regional grid price in regions.csv) |
| `utility.steam_lp_usd_j` | 6.8e-09 | $/J | `seider2016` | Aspen-level steam price used to cost heat duties before the host-steam re-pricing |
| `utility.steam_mp_usd_j` | 7.9e-09 | $/J | `seider2016` | 150 psig steam (utility allocation basis) |
| `utility.steam_hp_usd_j` | 9.0e-09 | $/J | `seider2016` | 450 psig steam |
| `utility.heat_oil_usd_j` | 3.5e-09 | $/J | `seider2016` | Fired heat above 250 C |
| `utility.chilled_water_usd_j` | 2.2e-09 | $/J | `seider2016` | Refrigerated water below 4.4 C |
| `utility.cooling_water_usd_j` | 2.12e-10 | $/J | `seider2016` | Cooling water |
| `utility.process_water_usd_kg` | 0.00035 | $/kg | `seider2016` | Process water (utility allocation basis) |
| `utility.chilled_water_increment_usd_gj` | 5.00 | $/GJ | `seider2016` | Chilled-water cost of the Stage I cooler |
| `utility.cooling_water_usd_gj` | 0.212 | $/GJ | `seider2016` | Cooling-water charge already in the Aspen duty costing (blocks at or below 25 C) |
| `utility.cooling_water_above25_usd_gj` | 0.0212 | $/GJ | `seider2016` | Cooling-water charge in the Aspen duty costing for blocks above 25 C (cw / 10) |

**host_steam** (used in `opex.host_steam`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `host_steam.lp_usd_gj` | 2.806131480014593 | $/GJ | `dea_cv` | Dryer steam priced at the electricity the host loses (Cv 0.202 x 5 c/kWh / 3.6) |
| `host_steam.lt_usd_gj` | 2.083333333333333 | $/GJ | `dea_cv` | Low-temperature heat (Cv 0.15 x 5 c/kWh / 3.6) |

**price** (used in `tea.cost_dict -> opex (revenue, make-up)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `price.caoh2_usd_t` | 218 | $/t | `usgs_lime`, `comtrade` | Commodity hydrated lime (band 200-235) |
| `price.pcc_usd_t` | 225 | $/t | `usgs_lime`, `comtrade` | Commodity PCC (band 205-245) |
| `price.hcl_30pct_usd_t` | 150 | $/t solution | `comtrade_hcl` | Surplus HCl sold as 30 wt% solution (2025 German import unit value); 96.4 index as the low end |
| `price.naoh_50pct_usd_t` | 0 | $/t solution | `model` | Surplus NaOH is not priced |
| `price.soda_ash_usd_t` | 150 | $/t | `usgs_soda` | Soda ash for brine softening |

**softening** (used in `opex.estimate (brine softening)`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `softening.soda_ash_excess` | 1.1 | - | `model` | Soda ash dose relative to the Ca + Mg in the cell-feed brine |
| `softening.sludge_at_fee` | true | - | `model` | Softening sludge landfilled at the treatment fee |

**fee** (used in `regions.csv / tea.base_case`)

| key | value | unit | source | note |
|---|---|---|---|---|
| `fee.eu_usd_t` | 358.5158456898718 | $/t dry ash | `bref_wi2019`, `eurostat_hicp` | EUR 196 (WI BREF midpoint 2001-03) x HICP 1.6179 x 1.1306 $/EUR |

## 8. Sources

| key | reference | DOI / URL |
|---|---|---|
| `model` | Model assumption or value set in this work (see docs/TEA_basis.md for the rationale) |  |
| `stoich` | Stoichiometry / unit conversion |  |
| `seider2016` | Seider, W.D., Lewin, D.R., Seader, J.D., Widagdo, S., Gani, R., Ng, K.M., Product and Process Design Principles: Synthesis, Analysis and Evaluation, 4th ed., Wiley, 2016 | ISBN 978-1-119-35524-3 |
| `towler2021` | Towler, G., Sinnott, R., Chemical Engineering Design, 3rd ed., Butterworth-Heinemann, 2021 (maintenance 3-5 % of TDC, p.280) |  |
| `cepci` | Jenkins, S., 2024 CEPCI Updates, Chemical Engineering 131 (2024) 48-49 (CEPCI 800 basis) |  |
| `irs_macrs` | US IRS Publication 946, MACRS 7-year property (half-year convention table) | https://www.irs.gov/publications/p946 |
| `aace18r97` | AACE International Recommended Practice 18R-97, Cost estimate classification system (Class 4: -15 to -30 % / +20 to +50 %; -20/+30 % used) |  |
| `schmittinger2011` | Schmittinger, P. et al., Chlorine, Ullmann's Encyclopedia of Industrial Chemistry, Wiley-VCH, 2011 | https://doi.org/10.1002/14356007.a06_399.pub3 |
| `stinn2020` | Stinn, C., Allanore, A., Estimating the capital costs of electrowinning processes, Electrochem. Soc. Interface 29 (2020) 44-49 (Eq. 7 rectifier term) | https://doi.org/10.1149/2.F06202IF |
| `bref_cak2014` | European Commission JRC, Best Available Techniques Reference Document for the Production of Chlor-alkali, 2014 (Table 4.4 electricity supply EUR 81-121/t Cl2; 2.4 MWh AC/t Cl2 new bipolar membrane cells; membranes EUR 500/m2, doubled with gaskets p.177) | https://doi.org/10.2791/13138 |
| `eurochlor_is12` | Euro Chlor, Electrolysis and production costs, Information Sheet 12, November 2023 (electricity 2.27-2.94 MWh/t Cl2) | https://www.eurochlor.org |
| `hanwha2021` | Korea Herald, 21 Dec 2021: Hanwha Solutions to spend KRW 338 billion ($283.3 million) to add 270,000 t of chlor-alkali capacity (Yeosu) -> $1,184/t Cl2/yr nominal (code comment; full citation to be completed by the authors) |  |
| `tk_nucera` | thyssenkrupp nucera, BM2.7 v7 membrane electrolyser specification: 1,960 kWh DC/t NaOH at 6 kA/m2 (code comment; full citation to be completed by the authors) |  |
| `usbr149` | Juby, G. et al., Evaluation and Selection of Available Processes for a Zero-Liquid Discharge System for the Perris, California, Ground Water Basin, DWPR Report No. 149, U.S. Bureau of Reclamation, 2008 (Table 4.7 brine concentrator) | https://www.usbr.gov/research/dwpr/reportpdfs/report149.pdf |
| `randon2020` | Randon et al., Int. J. Thermodynamics 23 (2020) 128 (single-effect MVR: U, dT, isentropic efficiency) (code comment) |  |
| `eurostat_lc` | Eurostat, Labour cost levels by NACE Rev. 2 activity [lc_lci_lev], EU27 manufacturing 2025 EUR 35.0/h; NL 2024 EUR 47.3/h | https://ec.europa.eu/eurostat/databrowser/view/lc_lci_lev/default/table |
| `eurostat_nrg` | Eurostat, Electricity prices for non-household consumers [nrg_pc_205], band IG, excl. VAT and recoverable taxes, 2025-S2 (NL EUR 0.0951/kWh) | https://doi.org/10.2908/NRG_PC_205 |
| `eurostat_hicp` | Eurostat, HICP annual data [prc_hicp_aind], euro area 2025/2002 = 1.6179 | https://doi.org/10.2908/PRC_HICP_AIND |
| `bref_wi2019` | Neuwahl, F. et al., Best Available Techniques Reference Document for Waste Incineration, EUR 29971 EN, 2019 (Table 1.8 APC residue treatment EUR 29-363/t, midpoint EUR 196) | https://doi.org/10.2760/761437 |
| `zhang2024` | Zhang, D. et al., Toward zero-waste resource recovery from MSWI ash by electrochemical and chemical mining, Cell Rep. Sustain. 1 (2024) 100120 (host incinerator power 5 c/kWh convention) | https://doi.org/10.1016/j.crsus.2024.100120 |
| `baidoo2026` | Baidoo, J.E. et al., Process-based cost assessment of electrochemical metals recovery from MSWI ash, Waste Manag. 217 (2026) 115500 (co-located power 2 c/kWh) | https://doi.org/10.1016/j.wasman.2026.115500 |
| `dea_cv` | Danish Energy Agency, Technology Data for Energy Plants: Cv value (electricity lost per unit of heat extracted from an extraction steam turbine); turbine brackets are assumptions (code comment) | https://ens.dk/en/our-services/projections-and-models/technology-data |
| `usgs_lime` | U.S. Geological Survey, Mineral Commodity Summaries 2026: Lime; 2023 Minerals Yearbook: Lime, Table 5 | https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-lime.pdf |
| `comtrade` | United Nations Statistics Division, UN Comtrade database, HS 252220 and 283650, reporters Germany, Korea and United States, 2023-2025 | https://comtradeplus.un.org |
| `comtrade_hcl` | United Nations Statistics Division, UN Comtrade database, HS 280610, reporter Germany, imports 2025 ($150/t 30 wt% HCl) | https://comtradeplus.un.org |
| `intratec2025` | Intratec, hydrochloric acid and caustic soda market index prices, November 2025 ($96/t HCl 30 %, $199/t NaOH 50 %) (code comment; full citation to be completed by the authors) |  |
| `usgs_soda` | U.S. Geological Survey, Mineral Commodity Summaries 2026: Soda Ash ($150/t) | https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-soda-ash.pdf |
| `fairfax2016` | Fairfax County (VA) FY2016 ash disposal at the county landfill, $29.76/t (code comment; full citation to be completed by the authors) |  |
| `eref2024` | Environmental Research & Education Foundation, Analysis of MSW Landfill Tipping Fees (2024): $68.65/t | https://erefdn.org |
| `eia_epm` | U.S. EIA, Electric Power Monthly, Table 5.6.B, industrial electricity price 2025 | https://www.eia.gov/electricity/monthly/ |
| `bls` | US Bureau of Labor Statistics, BLS-derived Texas manufacturing labor cost $68.7/h (code comment; full citation to be completed by the authors) |  |
| `mcee2026` | Ministry of Climate, Energy and Environment (Republic of Korea), Notice No. 2026-67: designated incineration residue 210,000 KRW/t from 2027 |  |
| `moel2024` | Ministry of Employment and Labor (Republic of Korea), FY2024 labor cost survey, manufacturing ($30.6/h derived) (code comment) |  |
| `kpx2025` | Korea Power Exchange EPSIS, KEPCO industrial sales unit price 2025, 181.90 KRW/kWh | https://epsis.kpx.or.kr |
| `kpx2023` | Korea Power Exchange EPSIS, grid greenhouse-gas emission factor (0.693 kg CO2-eq/kWh used as the Korean-grid case) | https://epsis.kpx.or.kr |
| `moe_jp_ertdf` | Higuchi, S., Environment Research and Technology Development Fund final report 3K133007, Ministry of the Environment Japan, 2016, p.74: fly-ash off-site disposal 50,000 JPY/t; Chiba agreement 65,000 JPY/t | https://www.env.go.jp |
| `mhlw2021` | Ministry of Health, Labour and Welfare (Japan), 2021 General Survey on Working Conditions, manufacturing ($18.1/h derived) (code comment) |  |
| `jepx2024` | Japan Electric Power Exchange, spot market results FY2024, Tokyo area mean 13.66 JPY/kWh | https://www.jepx.jp |
| `ecoinvent311` | ecoinvent Association, ecoinvent database v3.11, cut-off system model, IPCC 2021 GWP100 (authors' openLCA extract) | https://ecoinvent.org |
| `ecoinvent312_change` | ecoinvent Association, Change Report v3.12, Section 5.9.1 (PCC value reported as underestimated) | https://support.ecoinvent.org |
| `laveglia2022` | Laveglia, A. et al., Hydrated lime life-cycle assessment: current and future scenarios in four EU countries, J. Clean. Prod. 369 (2022) 133224 | https://doi.org/10.1016/j.jclepro.2022.133224 |
| `nrel2021` | NREL, Life Cycle Greenhouse Gas Emissions from Electricity Generation: Update, NREL/FS-6A50-80580, 2021 | https://www.nrel.gov/docs/fy21osti/80580.pdf |
| `nrel2024` | Smith, B.L. et al., An Updated Life Cycle Assessment of Utility-Scale Solar PV Systems Installed in the United States, NREL/TP-7A40-87372, 2024 |  |
| `ipcc_ar5_annex3` | Schlomer, S. et al., Annex III: Technology-specific cost and performance parameters, IPCC AR5 WGIII, 2014 |  |
| `ipcc2006` | Gomez, D.R., Watterson, J.D. et al., Chapter 2: Stationary Combustion, 2006 IPCC Guidelines, Vol. 2 Energy |  |
| `ipcc2021` | IPCC, Climate Change 2021: The Physical Science Basis (GWP100) | https://doi.org/10.1017/9781009157896 |
| `iso14044` | ISO 14044:2006 Environmental management - Life cycle assessment - Requirements and guidelines, incl. Amd 1:2017 and Amd 2:2020 |  |
| `doka2003` | Doka, G., Life Cycle Inventories of Waste Treatment Services, Part III: Landfills, ecoinvent report No. 13, 2003 | https://www.doka.ch/13_III_Landfills.pdf |
| `energystar2025` | US EPA ENERGY STAR, Energy Efficiency and Cost-Saving Opportunities for the Chlor-Alkali Industry, January 2025 (HCl synthesis 98-99 %) | https://www.energystar.gov |
