"""Purchase-cost and bare-module correlations (Seider et al., Product and Process Design Principles, 4th ed.,
Wiley, 2016; CE index 567).  Bare-module cost, Seider Eq. (16.12):
    C_BM = C_P,base * (I / I_b) * [F_BM + (F_d F_p F_M - 1)]
Guthrie bare-module factors from Seider Table 16.11 (storage 2.00 is an assumption).

    vertical pressure vessel   Eq. (16.52)(16.54)(16.56), wall per Eq. (16.59) + minimum-wall table
    agitator (turbine, closed) Table 16.32  C_P = 4,105 S^0.57, S = hp (2-60 hp)
    centrifuge (solid bowl)    Table 16.32  C_P = 68,040 S^0.50, S = short ton solids/h (2-40)
    rotary dryer (direct)      Table 16.32  C_P = exp{10.522 + 0.1003 lnA + 0.04303 ln^2 A}, A ft2 (200-3,000)
    evaporator (forced circ.)  Table 16.32  C_P = exp{8.0369 + 0.6994 lnA - 0.00004 ln^2 A}, A ft2 (150-8,000)
    centrifugal compressor     Eq. (16.36)  C_B = exp{9.1553 + 0.63 ln Pc}, Pc hp
    centrifugal blower         Eq. (16.31)  C_B = exp{7.0187 + 0.7900 ln Pc}, Pc hp
    centrifugal pump + motor   Eq. (16.14)-(16.19)
    storage bin                Table 16.32  C_P = 646 S^0.46, S ft3
    cone-roof tank             Table 16.32  C_P = 265 V^0.513, V gal
"""
import math

CE_BASE = 567.0
CE_NOW = 800.0
IDX = CE_NOW / CE_BASE

FBM = dict(vessel=4.16, pump=3.30, compressor=2.15, centrifuge=2.03, dryer=2.06,
           evaporator=2.45, filter=2.32, agitator=2.03, storage=2.00)

M3_TO_GAL = 264.172
M3_TO_FT3 = 35.3147
M_TO_FT = 3.28084
KG_TO_LB = 2.20462
KW_TO_HP = 1.34102


def bare_module(cp_base, fbm, fm=1.0, fp=1.0):
    return cp_base * IDX * (fbm + (fp * fm - 1.0))


def _split(x, xmax):
    n = max(1, math.ceil(x / xmax))
    return n, x / n


def _min_wall_in(D_ft):
    if D_ft <= 4:
        return 0.25
    if D_ft <= 6:
        return 5 / 16
    if D_ft <= 8:
        return 0.375
    if D_ft <= 10:
        return 7 / 16
    return 0.5


def vessel_vertical(V_m3, P_bar=1.01, LD=1.5, fill=0.8):
    """One vertical carbon-steel vessel (Seider Eq. 16.54-16.60), C_V + C_PL at CE 567.
    The material factor is added in the bare-module step.  Returns (C_P, D_ft, L_ft)."""
    Vtot = V_m3 / fill
    D = (4 * Vtot / (math.pi * LD)) ** (1 / 3)
    L = LD * D
    D_ft, L_ft = D * M_TO_FT, L * M_TO_FT
    Pd = max(10.0, (P_bar - 1.013) * 14.5038 * 1.1 + 10)
    S, E = 15000.0, 0.85
    tp = Pd * D_ft * 12 / (2 * S * E - 1.2 * Pd)
    ts = max(tp, _min_wall_in(D_ft)) + 0.125
    Di, Lin = D_ft * 12, L_ft * 12
    W = math.pi * (Di + ts) * (Lin + 0.8 * Di) * ts * 0.284
    W = max(W, 4200.0)
    CV = math.exp(7.1390 + 0.18255 * math.log(W) + 0.02297 * math.log(W) ** 2)
    CPL = 410.0 * max(D_ft, 3) ** 0.73960 * min(max(L_ft, 12), 40) ** 0.70684
    return CV + CPL, D_ft, L_ft


def agitator(V_m3, hp_per_kgal):
    """Turbine agitator, closed vessel.  Returns (C_P, kW)."""
    hp = hp_per_kgal * V_m3 * M3_TO_GAL / 1000.0
    n = max(1, math.ceil(hp / 60.0))
    cp = 4105.0 * (hp / n if hp / n >= 2 else 2.0) ** 0.57 * n
    return cp, hp / KW_TO_HP


def agitated_tank_bm(V_m3, hp_per_kgal, fm=2.1, Vmax=50.0, P_bar=1.01):
    """Agitated vessel train.  Returns (C_BM, number of vessels, total kW)."""
    if V_m3 < 0.01:
        return 0.0, 0, 0.0
    n, Vu = _split(V_m3, Vmax)
    cpv, _, _ = vessel_vertical(Vu, P_bar)
    cpa, kw = agitator(Vu, hp_per_kgal)
    bm_v = bare_module(cpv, FBM['vessel'], fm=fm)
    bm_a = bare_module(cpa, FBM['agitator'], fm=(1.0 if fm <= 1.0 else 2.0))
    return n * (bm_v + bm_a), n, n * kw


def centrifuge_bm(solids_kg_hr):
    """Continuous scroll solid-bowl centrifuge, stainless.  Returns (C_BM, n)."""
    if solids_kg_hr <= 0:
        return 0.0, 0
    S = solids_kg_hr / 907.185
    n, Su = _split(S, 40.0)
    Su = max(Su, 2.0)
    return n * bare_module(68040.0 * Su ** 0.50, FBM['centrifuge']), n


def rotary_dryer_bm(water_kg_hr, material='CS'):
    """Direct-heat rotary dryer sized at 2 lb water/h per ft3 (Seider Example 16.14), L/D 5.7; carbon steel = SS / 2."""
    if water_kg_hr <= 0:
        return 0.0, 0, 0.0
    V_ft3 = water_kg_hr * KG_TO_LB / 2.0
    D = (4 * V_ft3 / (math.pi * 5.7)) ** (1 / 3)
    A = math.pi * D * 5.7 * D
    n, Au = _split(A, 3000.0)
    Au = max(Au, 200.0)
    cp = math.exp(10.522 + 0.1003 * math.log(Au) + 0.04303 * math.log(Au) ** 2)
    if material == 'CS':
        cp /= 2.0
    return n * bare_module(cp, FBM['dryer']), n, A


def storage_bin_bm(V_m3):
    if V_m3 <= 0:
        return 0.0
    n, Vu = _split(V_m3 * M3_TO_FT3, 100000.0)
    return n * bare_module(646.0 * Vu ** 0.46, FBM['storage'])


def cone_roof_tank_bm(V_m3, fm=2.0):
    if V_m3 <= 0:
        return 0.0
    n, Vu = _split(V_m3 * M3_TO_GAL, 1.0e6)
    Vu = max(Vu, 10000.0)
    return n * bare_module(265.0 * Vu ** 0.513, FBM['storage'], fm=fm)


def pump_bm(Q_m3_hr, H_m=30.0, sg=1.1, fm=2.0, spares=1):
    """Centrifugal pump + motor with one installed spare.  Returns (C_BM, kW)."""
    if Q_m3_hr <= 0:
        return 0.0, 0.0
    Qg = Q_m3_hr * M3_TO_GAL / 60.0
    n, Qu = _split(Qg, 3000.0)
    Hf = H_m * M_TO_FT
    S = max(Qu * Hf ** 0.5, 400.0)
    cb = math.exp(12.1656 - 1.1448 * math.log(S) + 0.0862 * math.log(S) ** 2)
    eta_p = -0.316 + 0.24015 * math.log(Qu) - 0.01199 * math.log(Qu) ** 2
    eta_p = min(max(eta_p, 0.5), 0.9)
    PB = Qu * Hf * sg / (3960.0 * eta_p)
    eta_m = 0.80 + 0.0319 * math.log(PB) - 0.00182 * math.log(PB) ** 2
    PC = PB / eta_m
    lp = math.log(min(max(PC, 1.0), 700.0))
    cm = math.exp(5.9332 + 0.16829 * lp - 0.110056 * lp ** 2 + 0.071413 * lp ** 3 - 0.0063788 * lp ** 4)
    units = n * (1 + spares)
    bm = units * (bare_module(cb, FBM['pump'], fm=fm) + bare_module(cm, FBM['pump']))
    return bm, n * PC / KW_TO_HP


def compressor_bm(kW, fm=2.5):
    """Centrifugal compressor incl. motor (Eq. 16.36)."""
    if kW <= 0:
        return 0.0
    hp = kW * KW_TO_HP
    n, hpu = _split(hp, 30000.0)
    return n * bare_module(math.exp(9.1553 + 0.63 * math.log(hpu)), FBM['compressor'], fm=fm)


def blower_bm(kW, fm=2.5):
    """Centrifugal blower incl. motor (Eq. 16.31), compression ratio <= 2."""
    if kW <= 0:
        return 0.0
    hp = kW * KW_TO_HP
    return bare_module(math.exp(7.0187 + 0.7900 * math.log(hp)), FBM['compressor'], fm=fm)


def evaporator_bm(area_m2, tube='SS'):
    """Forced-circulation evaporator with the tube-material factor of Seider Table 16.25 (CS shell)."""
    if area_m2 <= 0:
        return 0.0, 0
    A = area_m2 * 10.7639
    n, Au = _split(A, 8000.0)
    Au = max(Au, 150.0)
    cp = math.exp(8.0369 + 0.6994 * math.log(Au) - 0.00004 * math.log(Au) ** 2)
    a, b = {'SS': (1.75, 0.13), 'Monel': (2.1, 0.13), 'Ti': (5.2, 0.16)}[tube]
    fm = a + (Au / 100.0) ** b
    return n * bare_module(cp, FBM['evaporator'], fm=fm), n


def hx_bm_ti(duty_W, lmtd_K, U=850.0):
    """Fixed-head shell-and-tube exchanger with Ti tubes (Eq. 16.40, Table 16.25), F_BM 3.17."""
    A_ft2 = duty_W / (U * lmtd_K) * 10.7639
    n = max(1, math.ceil(A_ft2 / 12000.0))
    A = A_ft2 / n
    cb = math.exp(11.4185 - 0.9228 * math.log(A) + 0.09861 * math.log(A) ** 2)
    fm = 5.2 + (A / 100.0) ** 0.16
    return n * cb * IDX * (3.17 + fm - 1.0)
