"""Aspen Plus V14 COM session used by the flowsheet drivers (scripts/aspen).  Requires Windows, Aspen Plus and pywin32.

Every driver works on a private copy of the template .bkp, closes every document it opens, and pins the three pH
design specifications DS-STG1/2/3 by narrowing their manipulated-variable bounds to x * (0.999, 1.001):
    DS-STG1  HCl feed (kg/h)      -> Stage I pH     (Stage I is specified by the acid dose, so the pin is the dose)
    DS-STG2  NaOH1 feed (kg/h)    -> Stage II pH
    DS-STG3  NaOH2 feed (kg/h)    -> Stage III pH
Stage II and III are solved by an OUTSIDE bisection on the pinned flow (the inside secant of Aspen diverges on the
Ca(OH)2 buffer), and every pin is read back after it is written.
"""
import os
import shutil
import time

BS = '\\'
DS_IN = {n: BS.join(['', 'Data', 'Flowsheeting Options', 'Design-Spec', 'DS-STG%d' % n, 'Input']) for n in (1, 2, 3)}
DS_OUT = {n: BS.join(['', 'Data', 'Flowsheeting Options', 'Design-Spec', 'DS-STG%d' % n, 'Output']) for n in (1, 2, 3)}
STREAMS = BS.join(['', 'Data', 'Streams'])


def path(*parts):
    return BS.join([''] + list(parts))


class Clip(Exception):
    """A design specification returned a manipulated value outside its pinned box."""


class Session:
    def __init__(self, template_bkp, work_bkp, log=print):
        self.template, self.work, self.log = template_bkp, work_bkp, log
        self.h = self.t = None

    # ---------------------------------------------------------------- document
    def open(self):
        import pythoncom
        import win32com.client as win32
        pythoncom.CoInitialize()
        os.makedirs(os.path.dirname(os.path.abspath(self.work)), exist_ok=True)
        shutil.copy(self.template, self.work)
        self.h = win32.Dispatch('Apwn.Document')
        self.h.InitFromArchive2(os.path.abspath(self.work))
        self.h.Visible = 0
        self.t = self.h.Tree
        time.sleep(2)                     # writes issued right after opening can be dropped

    def close(self):
        if self.h is not None:
            try:
                self.h.Close()
            except Exception:
                pass
        self.h = self.t = None
        time.sleep(2)

    def save_as(self, bkp):
        try:
            self.h.SaveAs(os.path.abspath(bkp))
        except Exception as ex:
            self.log('SaveAs failed: %s' % str(ex)[:80])

    # ---------------------------------------------------------------- tree access
    def W(self, p, v):
        n = self.t.FindNode(p)
        if n is None:
            raise RuntimeError('node missing: ' + p)
        n.Value = v

    def R(self, p):
        n = self.t.FindNode(p)
        return None if n is None else n.Value

    def pin(self, n, x, tol=0.02):
        self.W(DS_IN[n] + BS + 'LOWER', x * 0.999)
        self.W(DS_IN[n] + BS + 'UPPER', x * 1.001)
        self.W(DS_IN[n] + BS + 'TOL', tol)
        for k, f in (('LOWER', 0.999), ('UPPER', 1.001)):
            got = float(self.R(DS_IN[n] + BS + k))
            assert abs(got - x * f) < 1e-6 * max(1.0, x), ('pin not taken', n, k, got, x)

    def ds(self, n):
        """(manipulated value, achieved pH) of DS-STGn."""
        return float(self.R(DS_OUT[n] + BS + 'FINAL_VAL' + BS + '1')), float(self.R(DS_OUT[n] + BS + 'FINAL_VAL' + BS + '2'))

    def set_feed(self, cis_kg_h, mix_kg_h, ash_water_kg_h, hcl_wt):
        """ASH stream (CISOLID composition in kg/h, MIXED water + dissolved K+/Cl-) and the HCl strength."""
        cis = self.t.FindNode(path('Data', 'Streams', 'ASH', 'Input', 'FLOW', 'CISOLID'))
        for e in cis.Elements:
            try:
                if e.Value is not None and float(e.Value) != 0:
                    e.Value = 0.0
            except Exception:
                pass
        tc = sum(cis_kg_h.values())
        A = path('Data', 'Streams', 'ASH', 'Input') + BS
        self.W(A + 'TOTFLOW' + BS + 'CISOLID', tc)
        for c, v in cis_kg_h.items():
            self.W(A + 'FLOW' + BS + 'CISOLID' + BS + c, v / tc)
        for c, v in cis_kg_h.items():
            got = float(self.R(A + 'FLOW' + BS + 'CISOLID' + BS + c))
            assert abs(got - v / tc) < 1e-9, ('feed read-back', c, got, v / tc)
        tm = ash_water_kg_h + sum(mix_kg_h.values())
        self.W(A + 'FLOW' + BS + 'MIXED' + BS + 'WATER', ash_water_kg_h / tm)
        for c, v in mix_kg_h.items():
            self.W(A + 'FLOW' + BS + 'MIXED' + BS + c, v / tm)
        self.W(A + 'TOTFLOW' + BS + 'MIXED', tm)
        H = path('Data', 'Streams', 'HCL', 'Input', 'FLOW', 'MIXED') + BS
        self.W(H + 'HCL', hcl_wt)
        self.W(H + 'WATER', 1.0 - hcl_wt)

    def set_targets(self, ph1, ph2, ph3, T1=25.0, T2=25.0, T3=25.0):
        self.W(DS_IN[1] + BS + 'EXPR2', str(ph1))
        self.W(DS_IN[2] + BS + 'EXPR2', str(ph2))
        self.W(DS_IN[3] + BS + 'EXPR2', str(ph3))
        for b, T in (('B1', T1), ('B13', T2), ('B14', T3)):
            self.W(path('Data', 'Blocks', b, 'Input', 'TEMP'), T)

    # ---------------------------------------------------------------- solving
    def run(self, timeout=3600, check=None, recover=None):
        """Run and wait; check() returns None when the results belong to this run.  Escalation: rerun ->
        Reinit + run -> recover() (reopen the copy and re-apply the inputs) + run."""
        why = None
        for attempt in range(4):
            try:
                if attempt == 2:
                    self.h.Reinit()
                if attempt == 3 and recover is not None:
                    recover()
                self.h.Engine.Run2()
                for _ in range(timeout):
                    if not self.h.Engine.IsRunning:
                        break
                    time.sleep(1)
                if self.h.Engine.IsRunning:
                    why = 'engine still running after %d s' % timeout
                    try:
                        self.h.Engine.Stop()
                    except Exception:
                        pass
                    continue
                why = check() if check else None
                if why is None:
                    return
            except Exception as ex:
                why = 'COM: ' + str(ex)[:60]
            self.log('retry %d: %s' % (attempt + 1, why))
        raise RuntimeError('Aspen run failed 4x (%s)' % why)

    def pins_ok(self, pins):
        def check():
            for n, x in pins:
                a = self.R(DS_OUT[n] + BS + 'FINAL_VAL' + BS + '1')
                if a is None:
                    return 'DS-STG%d result missing' % n
                if abs(float(a) - x) >= 0.002 * x:
                    return 'DS-STG%d FINAL_VAL[1] %.1f vs pin %.1f' % (n, float(a), x)
            return None
        return check

    def bisect(self, n, target, lo, hi, pins=(), iters=22, tol=0.02, recover=None, hist=None, clip_tol=0.002):
        """Outside bisection of DS-STGn's pinned flow on the achieved pH (pH rises with the NaOH flow).
        clip_tol: raise Clip when the converged flow leaves the pin by more than this fraction (None: no check)."""
        ach = val = mid = None
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            self.pin(n, mid)
            allp = tuple(pins) + ((n, mid),)
            self.run(check=self.pins_ok(allp), recover=recover)
            val, ach = self.ds(n)
            if hist is not None:
                hist.append((round(mid, 2), round(ach, 4)))
            if clip_tol is not None and abs(val - mid) >= clip_tol * mid:
                raise Clip('DS-STG%d clipped: FINAL_VAL[1] %.1f vs pin %.1f' % (n, val, mid))
            if ach > target:
                hi = mid
            else:
                lo = mid
            if abs(ach - target) < tol:
                break
        return ach, val, lo, hi


def ca_kg_hr(sc, sname):
    """Elemental Ca flow (kg/h, MIXED + CISOLID) of one stream from its component flows."""
    MW = {'CA++': 40.078, 'CA(OH)2': 74.093, 'CACO3': 100.087, 'CASO4': 136.14, 'CASO4(S)': 136.14, 'CACL2(S)': 110.98,
          'CACL2': 110.98, 'CAO': 56.077}
    FCA = {k: 40.078 / v for k, v in MW.items()}
    tot = 0.0
    for sub, d in (sc.get(sname) or {}).items():
        mf = d.get('mass_flow') or {}
        for comp, f in FCA.items():
            tot += (mf.get(comp) or 0.0) * f
    return tot
