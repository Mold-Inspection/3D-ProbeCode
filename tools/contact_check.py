# ==============================================================================
# tools/contact_check.py — Contact check: ตรวจจุดแตะของลูกบอลหัววัดที่โปรแกรมคำนวณจาก B-Rep
# ==============================================================================
# VERSION: 01
# โปรแกรมแยก (stand-alone) ไม่ได้ต่อเข้าแอปหลัก — เปิดไฟล์ STEP แล้วกด Run
#
#   python tools/contact_check.py                          → หน้าต่าง UI
#   python tools/contact_check.py file.step --cli          → พิมพ์ตารางในคอนโซล
#   python tools/contact_check.py file.step --cli --csv out.csv --r 1.0 --layers 3 --points 4
#
# ใช้โค้ดของแอปหลัก (Build/core) เพื่อ "สร้างจุดวัดแบบเดียวกับที่แอปส่งไปเครื่อง" เท่านั้น
# ส่วนที่ใช้ตรวจเขียนใหม่ในไฟล์นี้ทั้งหมด แต่ละจุดวัดคำนวณ 4 ค่า:
#
#   1) |E − CAD|  : จุดคาดหวัง E (จุดที่เส้นทางเดินของหัววัดทะลุผิว CAD) ห่างผิว B-Rep เท่าไร
#                   → ควรเป็น 0 (ยืนยันว่าแอปวางจุดบนผิวถูก)
#   2) อ้างอิง    : ระยะเดิน s_ref ที่ลูกบอลรัศมี R แตะผิว หาเองด้วยวิธีที่ไม่ใช้โค้ดของแอป —
#                   เลื่อนศูนย์ลูกบอลไปตามเส้นทางทีละ R/4 จน "ระยะถึงผิวที่ใกล้ที่สุด ≤ R"
#                   แล้วแบ่งครึ่งช่วง (bisection) หาตำแหน่งที่ระยะ = R พอดี
#   3) สูตรตรง    : ถ้าผิวที่แตะเป็นรูปทรงพื้นฐาน (ระนาบ ทรงกระบอก ทรงกรวย ทรงกลม) คำนวณจุดแตะ
#                   ด้วยสมการปิด (ศูนย์ลูกบอลอยู่บนผิวที่ขยายออกไป R) — ไม่ใช้การหาระยะของ
#                   OpenCascade เลย จึงเป็นวิธีที่สามที่แยกขาดจากข้อ 2 และจากแอป
#   4) กรวย       : สูตรประมาณแบบเดิม — ถือว่าผนังเป็นระนาบสัมผัสที่ E (= กรวยที่ระดับชั้น)
#                   s_cone = s_E − R / (m·n)   m = ทิศตั้งฉากผิวที่ E (ชี้เข้าเนื้อ), n = ทิศเดิน
#
#   แล้วเทียบ: แอป − อ้างอิง (ควร ≈ 0), สูตรตรง − อ้างอิง (ควร ≈ 0), กรวย − อ้างอิง (= ความคลาด
#   ของการประมาณ — 0 บนผนังที่ชันคงที่, โตขึ้นบนผิวโค้ง)
#
# ตัวแปรที่ปรับได้:
#   PASS_TOL   = เกณฑ์ "ผ่าน" ของ |E − CAD|, แอป − อ้างอิง และสูตรตรง − อ้างอิง (mm)
#   CONE_WARN  = ไฮไลต์แถวที่สูตรกรวยคลาดเกินค่านี้ (mm)
#   BISECT_N   = จำนวนรอบแบ่งครึ่ง (40 รอบ ช่วง ~R/4 → ละเอียดกว่า 1e-12 mm)
# ==============================================================================
import argparse
import csv
import math
import os
import queue
import sys
import threading
from pathlib import Path

import numpy as np

BUILD = Path(__file__).resolve().parents[1] / "Build"
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

PASS_TOL = 0.001     # mm (1 µm)
CONE_WARN = 0.010    # mm
BISECT_N = 40
VIEWS = ("Top", "Bottom", "Front", "Back", "Left", "Right")


# ==============================================================================
# ส่วนที่ 1 — เรขาคณิตด้วย OpenCascade (ไม่ใช้ core/surface_oracle.py)
# ==============================================================================
def _gp(p):
    from OCP.gp import gp_Pnt
    return gp_Pnt(*map(float, p))


def _vec(v):
    return np.array([v.X(), v.Y(), v.Z()], dtype=float)


class Surfaces:
    """ผิวทุกผิวของชิ้นงาน + กล่องครอบ (เลือกเฉพาะผิวใกล้เส้นทางเดินเพื่อให้เร็ว)"""

    def __init__(self, step_data):
        self.faces = []
        for f in step_data.faces().vals():
            bb = f.BoundingBox()
            self.faces.append((f.wrapped, np.array([bb.xmin, bb.ymin, bb.zmin]),
                               np.array([bb.xmax, bb.ymax, bb.zmax])))

    def near(self, lo, hi):
        """compound ของผิวที่กล่องครอบตัดกับกล่อง [lo, hi]"""
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound
        comp, b = TopoDS_Compound(), BRep_Builder()
        b.MakeCompound(comp)
        n = 0
        for f, flo, fhi in self.faces:
            if np.all(fhi >= lo) and np.all(flo <= hi):
                b.Add(comp, f)
                n += 1
        return comp if n else None


def nearest(shape, p):
    """(ระยะที่ใกล้ที่สุดถึงผิว, จุดบนผิว, ผิวที่จุดนั้นอยู่ หรือ None ถ้าอยู่บนขอบ/มุม)"""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_SupportType
    from OCP.TopoDS import TopoDS
    ext = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(_gp(p)).Vertex(), shape)
    ext.Perform()
    if not ext.IsDone() or ext.NbSolution() < 1:
        return None, None, None
    d, q, face = float(ext.Value()), _vec(ext.PointOnShape2(1)), None
    if ext.SupportTypeShape2(1) == BRepExtrema_SupportType.BRepExtrema_IsInFace:
        face = TopoDS.Face_s(ext.SupportOnShape2(1))
    else:
        # จุดใกล้สุดอยู่บนขอบ — มักเป็นรอยต่อ (seam) ที่ CAD แบ่งผิวเดียวกันเป็นสองซีก
        # ใช้ผิวแรกที่อยู่ห่างเท่ากัน (ถ้าเป็นขอบจริงของสองผิวต่างชนิด การตรวจสูตรตรงจะฟ้องเอง)
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            f = TopoDS.Face_s(exp.Current())
            e2 = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(_gp(p)).Vertex(), f)
            e2.Perform()
            if e2.IsDone() and e2.NbSolution() and abs(float(e2.Value()) - d) < 1e-7:
                face = f
                break
            exp.Next()
    return d, q, face


def face_normal(face, p):
    """ทิศตั้งฉากผิวขาออกจากเนื้องาน (ตามทิศของผิวใน B-Rep) ที่จุด p บนผิว"""
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    uv = ShapeAnalysis_Surface(BRep_Tool.Surface_s(face)).ValueOfUV(_gp(p), 1e-7)
    pnt, vec = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(uv.X(), uv.Y(), pnt, vec)
    v = _vec(vec)
    return v / np.linalg.norm(v)


def reference_touch(shape, S, n, R, max_travel):
    """วิธีอ้างอิง: s ที่ลูกบอลรัศมี R (ศูนย์ที่ S + s·n) แตะผิวครั้งแรก
    เดินทีละ R/4 — ลูกบอลกว้าง 2R จึงข้ามผิวไปไม่ได้ — จนระยะถึงผิว ≤ R แล้วแบ่งครึ่ง
    คืน (s, จุดแตะบนผิว, ผิวที่แตะ) หรือ None พร้อมเหตุผล"""
    d0 = nearest(shape, S)[0]
    if d0 is None:
        return None, "หาระยะไม่ได้"
    if d0 <= R:
        return None, "ลูกบอลแตะผิวตั้งแต่จุดเริ่ม"
    step = R / 4.0
    lo, s = 0.0, step
    while s <= max_travel:
        if nearest(shape, S + s * n)[0] <= R:
            hi = s
            for _ in range(BISECT_N):
                mid = 0.5 * (lo + hi)
                if nearest(shape, S + mid * n)[0] > R:
                    lo = mid
                else:
                    hi = mid
            _d, q, face = nearest(shape, S + hi * n)
            return (hi, q, face), None
        lo, s = s, s + step
    return None, "ไม่แตะผิวภายในระยะเดิน"


def _roots(a, b, c):
    """รากจริงของ a·s² + b·s + c = 0"""
    if abs(a) < 1e-14:
        return [] if abs(b) < 1e-14 else [-c / b]
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    r = math.sqrt(disc)
    return [(-b - r) / (2 * a), (-b + r) / (2 * a)]


def analytic_touch(face, S, n, R):
    """วิธีสูตรตรง: ศูนย์ลูกบอลที่แตะผิวรูปทรงพื้นฐานอยู่บนผิวที่ขยายออกไป R (offset surface)
    ฝั่งเดียวกับจุดเริ่ม S → แก้สมการเส้นตรงตัดผิวนั้น คืน (s, ชื่อผิว) — s = None ถ้าไม่ใช่รูปทรงพื้นฐาน"""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType as T
    srf = BRepAdaptor_Surface(face)
    kind = srf.GetType()
    roots = []
    if kind == T.GeomAbs_Plane:
        pln = srf.Plane()
        P0, N = _vec(pln.Location()), _vec(pln.Axis().Direction())
        f0 = float((S - P0) @ N)
        dn = float(n @ N)
        if abs(dn) > 1e-12:
            roots = [(math.copysign(R, f0) - f0) / dn]
        name = "ระนาบ"
    elif kind == T.GeomAbs_Sphere:
        sph = srf.Sphere()
        d0, Rs = S - _vec(sph.Location()), sph.Radius()
        t = Rs - R if np.linalg.norm(d0) < Rs else Rs + R
        roots = _roots(1.0, 2 * float(d0 @ n), float(d0 @ d0) - t * t)
        name = f"ทรงกลม R{Rs:g}"
    elif kind == T.GeomAbs_Cylinder:
        ax = srf.Cylinder().Axis()
        A, a, Rc = _vec(ax.Location()), _vec(ax.Direction()), srf.Cylinder().Radius()
        d0 = (S - A) - ((S - A) @ a) * a
        dn = n - (n @ a) * a
        t = Rc - R if np.linalg.norm(d0) < Rc else Rc + R
        roots = _roots(float(dn @ dn), 2 * float(d0 @ dn), float(d0 @ d0) - t * t)
        name = f"ทรงกระบอก R{Rc:g}"
    elif kind == T.GeomAbs_Cone:
        cone = srf.Cone()
        ax = cone.Axis()
        L, a = _vec(ax.Location()), _vec(ax.Direction())
        R0, alpha = cone.RefRadius(), cone.SemiAngle()
        tan_a, cos_a = math.tan(alpha), math.cos(alpha)
        t0, ta = float((S - L) @ a), float(n @ a)
        d0 = (S - L) - t0 * a
        dn = n - ta * a
        inside = np.linalg.norm(d0) < R0 + t0 * tan_a
        k0 = R0 + t0 * tan_a + (-R if inside else R) / cos_a   # รัศมีของกรวยที่ขยายออกไป R (ฉากกับผิว)
        k1 = ta * tan_a
        roots = [s for s in _roots(float(dn @ dn) - k1 * k1, 2 * (float(d0 @ dn) - k0 * k1),
                                   float(d0 @ d0) - k0 * k0) if k0 + k1 * s >= 0]
        name = f"ทรงกรวย {math.degrees(abs(alpha)):g}°"
    else:
        names = {T.GeomAbs_Torus: "ทอรัส", T.GeomAbs_BSplineSurface: "B-spline",
                 T.GeomAbs_BezierSurface: "Bezier", T.GeomAbs_SurfaceOfRevolution: "ผิวหมุน",
                 T.GeomAbs_SurfaceOfExtrusion: "ผิวกวาด", T.GeomAbs_OffsetSurface: "ผิว offset"}
        return None, names.get(kind, "ผิวอิสระ")
    roots = [s for s in roots if s >= -1e-9]
    return (min(roots) if roots else None), name


# ==============================================================================
# ส่วนที่ 2 — สร้างจุดวัดด้วยโค้ดของแอป แล้วตรวจทีละจุด
# ==============================================================================
class Model:
    """ไฟล์ STEP ที่โหลดด้วยตัวโหลดของแอป (core.geometry_engine.MoldGeometry)"""

    def __init__(self, path):
        import contextlib
        import io
        from core.geometry_engine import MoldGeometry
        with contextlib.redirect_stdout(io.StringIO()):   # ตัวโหลดพิมพ์ข้อความเยอะ
            self.geo = MoldGeometry(str(path))
        if self.geo.step_data is None:
            raise ValueError("ไม่ใช่ไฟล์ STEP หรืออ่าน B-Rep ไม่ได้ (ต้องเป็น .step/.stp)")
        self.path = Path(path)
        self.surfaces = Surfaces(self.geo.step_data)
        self.views = {}
        for v in VIEWS:
            with contextlib.redirect_stdout(io.StringIO()):
                hs = [h for h in self.geo.get_step_holes_in_view(v) if not getattr(h, 'is_rejected', False)]
            if hs:
                self.views[v] = hs


def _hole_features(step_holes, layers, points):
    """HoleFeature แบบเดียวกับที่แอปสร้างจากรูที่สกัดได้ (ui/main_window.py)"""
    from core.models import HoleFeature, HoleSegmentSetting, validate_segment_reachability
    out = []
    for i, sh in enumerate(step_holes, 1):
        hf = HoleFeature(i, sh.display_x, sh.display_y, sh.depth_top, sh.depth_bot, sh.depth, sh.radius)
        hf._step_hole, hf.display_id = sh, i
        segs = getattr(sh, 'segments', None) or []
        hf.segments = []
        if len(segs) > 1:
            hf.segments = [HoleSegmentSetting(k, s.radius_open, s.radius_deep, s.depth)
                           for k, s in enumerate(segs)]
            validate_segment_reachability(hf.segments)
        hf.selected_for_inspection = True
        hf.layers, hf.points_per_layer = int(layers), int(points)
        for s in hf.segments:
            s.layers, s.points_per_layer = int(layers), int(points)
        out.append(hf)
    return out


def run_check(model, view, R, layers=3, points=4, progress=None, cancel=None):
    """ตรวจทุกจุดผนังของทุกรูในมุมมอง view — คืน (rows, summary)"""
    import contextlib
    import io
    from core.gcode_generator import build_point_map, _step_frame
    holes = _hole_features(model.views[view], layers, points)
    with contextlib.redirect_stdout(io.StringIO()):
        pmap = [p for p in build_point_map(holes, view, 0, None, z_trigger=False, probe_r=float(R))
                if p.get('shape') not in ('calib', 'floor')]
    to_step, dir_to_step, dir_from_step = _step_frame(view, 0, None)
    rows = []
    for i, p in enumerate(pmap):
        if cancel is not None and cancel.is_set():
            break
        if progress:
            progress(i, len(pmap))
        rows.append(_check_point(model, p, float(R), to_step, dir_to_step, dir_from_step))
    if progress:
        progress(len(pmap), len(pmap))
    return rows, summarize(rows)


def _check_point(model, p, R, to_step, dir_to_step, dir_from_step):
    row = {'hole': p['hole_id'], 'seg': p.get('seg_idx', 0), 'layer': p['layer_idx'] + 1,
           'point': p['point_idx'] + 1, 'surface': '', 'e_cad': None, 'dz': None, 'prog': None,
           'analytic': None, 'cone': None, 'nerr': None, 'note': ''}
    trig = p.get('trig')
    if not trig:
        row['note'] = f"แอปไม่มีตารางจุดแตะ ({p.get('exact_fail', 'no_contact')})"
        return row
    S = to_step([p['sx'], p['sy'], p['sz']])
    n = dir_to_step([p['nx'], p['ny'], p['nz']])
    n = n / np.linalg.norm(n)
    E = to_step([p['x'], p['y'], p['z']])
    s_E = float((E - S) @ n)
    travel = s_E + 2 * R + 5.0
    end = S + travel * n
    shape = model.surfaces.near(np.minimum(S, end) - (R + 1), np.maximum(S, end) + (R + 1))
    if shape is None:
        row['note'] = "ไม่มีผิวใกล้เส้นทางเดิน"
        return row

    # 1) จุดคาดหวังอยู่บนผิวไหม + ทิศตั้งฉากผิวที่ E (ชี้เข้าเนื้องาน)
    d_E, q_E, f_E = nearest(shape, E)
    row['e_cad'] = d_E
    m_E = None
    if f_E is not None:
        m_E = -face_normal(f_E, q_E)
        if m_E @ n < 0:      # ทิศของผิวใน B-Rep กลับด้าน — ลูกบอลต้องเดินเข้าหาเนื้องาน
            m_E = -m_E

    # 2) อ้างอิง
    ref, why = reference_touch(shape, S, n, R, travel)
    if ref is None:
        row['note'] = why
        return row
    s_ref, q_ref, f_ref = ref
    C_ref = S + s_ref * n
    m_ref = (q_ref - C_ref) / np.linalg.norm(q_ref - C_ref)
    row['dz'] = float(dir_from_step(E - q_ref)[2])          # + = ลูกบอลแตะต่ำกว่าระดับชั้น

    # แอป: แถวสุดท้ายของตาราง = ลูกบอลรัศมี R
    row['prog'] = float(trig[-1][1]) - s_ref
    if abs(float(trig[-1][0]) - R) > 1e-6:
        row['note'] = f"ตารางของแอปจบที่ r = {trig[-1][0]}"

    # 3) สูตรตรง
    notes = []
    if f_ref is not None:
        s_an, row['surface'] = analytic_touch(f_ref, S, n, R)
        if s_an is not None:
            d_an = nearest(shape, S + s_an * n)[0]
            if d_an is not None and abs(d_an - R) <= 1e-5:
                row['analytic'] = s_an - s_ref
            else:
                notes.append("สูตรตรงแตะนอกขอบผิว")
    else:
        row['surface'] = "ขอบ/มุม"
        notes.append("ลูกบอลแตะขอบของผิว")
    if p.get('edge_first'):
        notes.append("แอปเตือน: แตะขอบก่อนผนัง")

    # 4) สูตรกรวย
    if m_E is not None and m_E @ n > 1e-6:
        row['cone'] = (s_E - R / float(m_E @ n)) - s_ref
        row['nerr'] = math.degrees(math.acos(max(-1.0, min(1.0, float(m_E @ m_ref)))))
    if notes:
        row['note'] = "; ".join([row['note']] + notes if row['note'] else notes)
    return row


def row_ok(r):
    vals = [r['e_cad'], r['prog']] + ([r['analytic']] if r['analytic'] is not None else [])
    return r['prog'] is not None and all(v is not None and abs(v) <= PASS_TOL for v in vals)


def summarize(rows):
    def worst(key):
        vals = [(abs(r[key]), r) for r in rows if r[key] is not None]
        return max(vals, key=lambda t: t[0]) if vals else (None, None)
    return {
        'n': len(rows),
        'n_ok': sum(row_ok(r) for r in rows),
        'n_analytic': sum(r['analytic'] is not None for r in rows),
        'e_cad': worst('e_cad'), 'prog': worst('prog'), 'analytic': worst('analytic'),
        'cone': worst('cone'),
    }


def summary_text(s, R):
    def where(r):
        return f"รู {r['hole']} ชั้น {r['layer']} จุด {r['point']}" if r else ""
    lines = [f"จุดผนังทั้งหมด {s['n']} จุด (ลูกบอล R = {R:g} มม.) — ผ่าน {s['n_ok']} / {s['n']} "
             f"(เกณฑ์ {PASS_TOL * 1000:g} µm)"]
    if s['e_cad'][0] is not None:
        lines.append(f"• จุดคาดหวังห่างผิว CAD สูงสุด {s['e_cad'][0] * 1000:.3f} µm")
    if s['prog'][0] is not None:
        lines.append(f"• จุดแตะของแอปต่างจากวิธีอ้างอิงสูงสุด {s['prog'][0] * 1000:.3f} µm  ({where(s['prog'][1])})")
    if s['analytic'][0] is not None:
        lines.append(f"• สูตรตรงต่างจากวิธีอ้างอิงสูงสุด {s['analytic'][0] * 1000:.3f} µm  "
                     f"({s['n_analytic']} จุดที่เป็นรูปทรงพื้นฐาน)")
    if s['cone'][0] is not None:
        lines.append(f"• สูตรประมาณแบบกรวยคลาดสูงสุด {s['cone'][0]:.4f} มม.  ({where(s['cone'][1])})")
    return "\n".join(lines)


COLUMNS = [  # (key, หัวคอลัมน์, ความกว้าง, รูปแบบ)
    ('hole', "รู", 40, "{}"), ('layer', "ชั้น", 40, "{}"), ('point', "จุด", 40, "{}"),
    ('surface', "ผิวที่แตะ", 130, "{}"),
    ('e_cad', "|E−CAD| (µm)", 120, "um_abs"), ('dz', "แตะต่ำกว่าชั้น (มม.)", 150, "{:+.3f}"),
    ('prog', "แอป−อ้างอิง (µm)", 140, "um"), ('analytic', "สูตรตรง−อ้างอิง (µm)", 160, "um"),
    ('cone', "กรวย−อ้างอิง (มม.)", 150, "{:+.4f}"), ('nerr', "ทิศผิวคลาด (°)", 120, "{:.2f}"),
    ('note', "หมายเหตุ", 200, "{}"),
]


def fmt(key, v):
    f = next(c[3] for c in COLUMNS if c[0] == key)
    if key == 'note':
        return v or ""
    if v is None or v == '':
        return "—"
    if f == "um_abs":
        return f"{abs(v) * 1000:.3f}"
    return f"{v * 1000:+.3f}" if f == "um" else f.format(v)


def write_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as fh:   # utf-8-sig: Excel อ่านภาษาไทยได้
        w = csv.writer(fh)
        w.writerow(['hole', 'segment', 'layer', 'point', 'surface', 'e_cad_mm', 'contact_below_layer_mm',
                    'app_minus_ref_mm', 'analytic_minus_ref_mm', 'cone_minus_ref_mm', 'normal_err_deg',
                    'pass', 'note'])
        for r in rows:
            w.writerow([r['hole'], r['seg'], r['layer'], r['point'], r['surface']] +
                       ['' if r[k] is None else f"{r[k]:.7f}" for k in ('e_cad', 'dz', 'prog', 'analytic', 'cone', 'nerr')] +
                       [int(row_ok(r)), r['note']])


# ==============================================================================
# ส่วนที่ 3 — คอนโซล
# ==============================================================================
def main_cli(args):
    model = Model(args.step)
    if not model.views:
        print("ไม่พบรูในไฟล์นี้")
        return 1
    view = args.view or next(iter(model.views))
    if view not in model.views:
        print(f"มุมมอง {view} ไม่มีรู — มีรูใน: {', '.join(model.views)}")
        return 1
    rows, s = run_check(model, view, args.r, args.layers, args.points,
                        progress=lambda i, n: print(f"\r  {i}/{n}", end="", file=sys.stderr))
    print(file=sys.stderr)
    print(f"{model.path.name}  มุมมอง {view}")
    print("  ".join(c[1] for c in COLUMNS[:-1]))
    for r in rows:
        print("  ".join(fmt(c[0], r[c[0]]) for c in COLUMNS[:-1]) + ("  " + r['note'] if r['note'] else ""))
    print()
    print(summary_text(s, args.r))
    if args.csv:
        write_csv(args.csv, rows)
        print(f"บันทึก {args.csv}")
    return 0


# ==============================================================================
# ส่วนที่ 4 — หน้าต่าง UI (customtkinter ชุดเดียวกับแอป)
# ==============================================================================
HELP = (
    "ความหมายของคอลัมน์\n"
    "• |E−CAD| — จุดคาดหวังที่แอปวาง ห่างผิว CAD เท่าไร (ควรเป็น 0)\n"
    "• แตะต่ำกว่าชั้น — ลูกบอลแตะผนังต่ำกว่าระดับชั้นที่ตั้งไว้กี่ มม. (ผิวเอียงหรือโค้ง)\n"
    "• แอป−อ้างอิง — จุดแตะที่แอปคำนวณ เทียบกับวิธีอ้างอิง (เดินทีละ R/4 + แบ่งครึ่ง) ควร ≈ 0\n"
    "• สูตรตรง−อ้างอิง — สมการปิดของระนาบ/ทรงกระบอก/ทรงกรวย/ทรงกลม เทียบกับวิธีอ้างอิง ควร ≈ 0\n"
    "• กรวย−อ้างอิง — ความคลาดของสูตรประมาณแบบเดิม (ผนังเป็นกรวยที่ระดับชั้น)\n"
    "• ทิศผิวคลาด — มุมระหว่างทิศตั้งฉากผิวที่ระดับชั้นกับที่จุดแตะจริง\n"
    "แถวแดง = เกินเกณฑ์ผ่าน, แถวเหลือง = สูตรกรวยคลาดเกิน "
    f"{CONE_WARN:g} มม. — ผลนี้เป็นการตรวจเชิงคำนวณ ไม่ใช่ผลวัดจากเครื่อง"
)


def main_ui(initial=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import customtkinter as ctk

    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    root.title("Contact check — ตรวจจุดแตะลูกบอลหัววัดจาก B-Rep")
    root.geometry("1300x700")
    root.minsize(1000, 560)
    state = {'model': None, 'rows': [], 'cancel': None}
    q = queue.Queue()

    # --- แถวบน: ไฟล์ + ค่าตั้ง ---
    top = ctk.CTkFrame(root)
    top.pack(fill="x", padx=10, pady=(10, 4))
    file_lbl = ctk.CTkLabel(top, text="ยังไม่ได้เปิดไฟล์", anchor="w", width=360)
    view_var = tk.StringVar(value="—")
    view_menu = ctk.CTkOptionMenu(top, variable=view_var, values=["—"], width=110)
    r_var, l_var, p_var = tk.StringVar(value=_default_r()), tk.StringVar(value="3"), tk.StringVar(value="4")

    def open_file(path=None):
        path = path or filedialog.askopenfilename(
            title="เปิดไฟล์ STEP", filetypes=[("STEP", "*.step *.stp *.STEP *.STP"), ("ทุกไฟล์", "*.*")])
        if not path:
            return
        file_lbl.configure(text=f"กำลังโหลด {Path(path).name} …")
        run_btn.configure(state="disabled")
        root.update_idletasks()
        try:
            m = Model(path)
        except Exception as e:
            file_lbl.configure(text="ยังไม่ได้เปิดไฟล์")
            messagebox.showerror("เปิดไฟล์ไม่ได้", str(e))
            return
        state['model'] = m
        views = list(m.views) or ["—"]
        view_menu.configure(values=views)
        view_var.set(views[0])
        nh = len(m.views.get(views[0], []))
        file_lbl.configure(text=f"{m.path.name}  —  พบรูใน {len(m.views)} มุมมอง" if m.views
                           else f"{m.path.name}  —  ไม่พบรู")
        run_btn.configure(state="normal" if m.views else "disabled")
        status.configure(text=f"มุมมอง {views[0]}: {nh} รู — กด Run" if m.views else "ไม่พบรูในไฟล์นี้")

    ctk.CTkButton(top, text="เปิดไฟล์ STEP…", width=130, command=open_file).pack(side="left", padx=6, pady=8)
    file_lbl.pack(side="left", padx=6)
    for label, var, w in (("มุมมอง", None, None), ("รัศมีลูกบอล R (มม.)", r_var, 60),
                          ("ชั้น", l_var, 45), ("จุด/ชั้น", p_var, 45)):
        ctk.CTkLabel(top, text=label).pack(side="left", padx=(12, 4))
        if var is None:
            view_menu.pack(side="left")
        else:
            ctk.CTkEntry(top, textvariable=var, width=w).pack(side="left")

    def start():
        m = state['model']
        try:
            R, L, P = float(r_var.get()), int(l_var.get()), int(p_var.get())
            assert R > 0 and L > 0 and P > 0
        except Exception:
            messagebox.showerror("ค่าไม่ถูกต้อง", "รัศมีต้องเป็นตัวเลขบวก ชั้นและจุดต้องเป็นจำนวนเต็มบวก")
            return
        view = view_var.get()
        tree.delete(*tree.get_children())
        summary.configure(state="normal")
        summary.delete("1.0", "end")
        summary.configure(state="disabled")
        run_btn.configure(state="disabled")
        csv_btn.configure(state="disabled")
        stop_btn.configure(state="normal")
        cancel = threading.Event()
        state['cancel'] = cancel
        state['R'] = R

        def work():
            try:
                rows, s = run_check(m, view, R, L, P, progress=lambda i, n: q.put(('prog', i, n)),
                                    cancel=cancel)
                q.put(('done', rows, s))
            except Exception as e:
                q.put(('error', repr(e)))
        threading.Thread(target=work, daemon=True).start()

    run_btn = ctk.CTkButton(top, text="Run", width=80, state="disabled", command=start)
    run_btn.pack(side="left", padx=(16, 4))
    stop_btn = ctk.CTkButton(top, text="หยุด", width=60, state="disabled", fg_color="#9e9e9e",
                             command=lambda: state['cancel'] and state['cancel'].set())
    stop_btn.pack(side="left", padx=4)

    def export():
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=f"contact_check_{state['model'].path.stem}.csv")
        if path:
            write_csv(path, state['rows'])
            status.configure(text=f"บันทึก {path}")
    csv_btn = ctk.CTkButton(top, text="บันทึก CSV…", width=110, state="disabled", command=export)
    csv_btn.pack(side="left", padx=4)

    # --- แถบสถานะ ---
    bar = ctk.CTkFrame(root, fg_color="transparent")
    bar.pack(fill="x", padx=10)
    progress = ctk.CTkProgressBar(bar, width=260)
    progress.set(0)
    progress.pack(side="left", padx=4, pady=4)
    status = ctk.CTkLabel(bar, text="เปิดไฟล์ STEP เพื่อเริ่ม", anchor="w")
    status.pack(side="left", padx=8)

    # --- สรุป + คำอธิบาย (จองพื้นที่ล่างก่อน ตารางจึงไม่ดันออกนอกจอ) ---
    bottom = ctk.CTkFrame(root, fg_color="transparent")
    bottom.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
    summary = ctk.CTkTextbox(bottom, height=130, font=("Leelawadee UI", 13))
    summary.pack(side="left", fill="both", expand=True, padx=(0, 6))
    summary.configure(state="disabled")
    helpbox = ctk.CTkTextbox(bottom, height=130, width=600, font=("Leelawadee UI", 12), wrap="word")
    helpbox.insert("1.0", HELP)
    helpbox.configure(state="disabled")
    helpbox.pack(side="right", fill="both")

    # --- ตาราง ---
    mid = ctk.CTkFrame(root)
    mid.pack(fill="both", expand=True, padx=10, pady=4)
    style = ttk.Style()
    style.configure("CC.Treeview", rowheight=24, font=("Leelawadee UI", 10))
    style.configure("CC.Treeview.Heading", font=("Leelawadee UI", 10, "bold"))
    tree = ttk.Treeview(mid, columns=[c[0] for c in COLUMNS], show="headings", style="CC.Treeview")
    for key, title, width, _f in COLUMNS:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor="w" if key in ('surface', 'note') else "e",
                    stretch=key == 'note')
    tree.tag_configure("fail", background="#f8d7da")
    tree.tag_configure("cone", background="#fff3cd")
    sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def poll():
        try:
            while True:
                msg = q.get_nowait()
                if msg[0] == 'prog':
                    _k, i, n = msg
                    progress.set(i / n if n else 1)
                    status.configure(text=f"กำลังตรวจ {i}/{n} จุด …")
                elif msg[0] == 'done':
                    _k, rows, s = msg
                    state['rows'] = rows
                    for r in rows:
                        tag = "fail" if not row_ok(r) else ("cone" if r['cone'] is not None and abs(r['cone']) > CONE_WARN else "")
                        tree.insert("", "end", values=[fmt(c[0], r[c[0]]) for c in COLUMNS], tags=(tag,))
                    summary.configure(state="normal")
                    summary.insert("1.0", summary_text(s, state['R']))
                    summary.configure(state="disabled")
                    stopped = state['cancel'].is_set()
                    status.configure(text=("หยุดแล้ว — " if stopped else "เสร็จ — ") + f"{len(rows)} จุด")
                    run_btn.configure(state="normal")
                    stop_btn.configure(state="disabled")
                    csv_btn.configure(state="normal" if rows else "disabled")
                elif msg[0] == 'error':
                    messagebox.showerror("ตรวจไม่สำเร็จ", msg[1])
                    status.configure(text="ผิดพลาด")
                    run_btn.configure(state="normal")
                    stop_btn.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(100, poll)

    poll()
    if initial:
        root.after(200, lambda: open_file(initial))
    root.mainloop()


def _default_r():
    """รัศมีลูกบอลจากค่าเริ่มต้นของแอป (core/probe_profile.py)"""
    try:
        from core.probe_profile import ProbeProfile
        return f"{ProbeProfile().tip_radius:g}"
    except Exception:
        return "1"


def main():
    ap = argparse.ArgumentParser(description="Contact check — ตรวจจุดแตะลูกบอลหัววัดจาก B-Rep")
    ap.add_argument("step", nargs="?", help="ไฟล์ STEP")
    ap.add_argument("--cli", action="store_true", help="พิมพ์ผลในคอนโซล ไม่เปิดหน้าต่าง")
    ap.add_argument("--view", help="มุมมอง (Top/Bottom/Front/Back/Left/Right) — ค่าเริ่มต้น: มุมมองแรกที่มีรู")
    ap.add_argument("--r", type=float, default=float(_default_r()), help="รัศมีลูกบอล (มม.)")
    ap.add_argument("--layers", type=int, default=3)
    ap.add_argument("--points", type=int, default=4)
    ap.add_argument("--csv", help="บันทึกผลเป็น CSV")
    args = ap.parse_args()
    if args.cli:
        if not args.step:
            ap.error("--cli ต้องระบุไฟล์ STEP")
        sys.exit(main_cli(args))
    main_ui(args.step)


if __name__ == "__main__":
    main()
