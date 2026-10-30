# ==============================================================================
# core/surface_oracle.py — จุดแตะของลูกบอลโพรบ คำนวณจาก B-Rep ของไฟล์ STEP ตรง ๆ
# ==============================================================================
# VERSION: 01
# หน้าที่: ทุกจุดโพรบคือ "ลูกบอลเดินเป็นเส้นตรงจาก start ตามทิศ n" — ไฟล์นี้หาว่าลูกบอลรัศมี r
# จะแตะผิว CAD ที่ระยะเดิน s(r) เท่าไหร่ และแตะด้วยทิศตั้งฉากผิว m(r) ทิศไหน โดยวัดระยะจริงถึง
# ผิว B-Rep (BRepExtrema) แทนการเดาจากรัศมีที่ความลึกเดียว (ผนังเอียง/โค้ง ลูกบอลแตะต่ำหรือสูง
# กว่าระดับชั้น — แบบเดิมคิดผิวเป็นกรวยที่ระดับชั้น คลาดได้ 0.1 มม. ในหลุมทรงกลม)
#
#   s(r) : ระยะเดินที่ "ระยะจากศูนย์กลางลูกบอลถึงผิวที่ใกล้ที่สุด = r" ครั้งแรก
#          (sphere tracing — ก้าวทีละ d − r ไม่มีทางก้าวเลยจุดแตะแรก)
#   m(r) : ทิศจากศูนย์กลางลูกบอลไปจุดแตะ (ชี้เข้าเนื้องาน) — r = 0 ใช้ทิศที่ r = R_NORMAL
#   s(0) : จุดที่เส้นทางทะลุผิว CAD = จุดคาดหวังบนผิว (ไม่ขึ้นกับขนาดลูกบอล)
#
# เก็บเป็นตาราง r = 0 … r_max (TABLE_SAMPLES ค่า) ต่อจุด → หน้า Evaluation interpolate ที่ Effective
# Tip จริงได้โดยไม่ต้องมีไฟล์ STEP (ตารางอยู่ใน Schema)
#
# พิกัดในไฟล์นี้เป็นพิกัดของไฟล์ STEP (ยังไม่ย้าย centroid ไม่หมุนตามมุมมอง) — ผู้เรียกแปลงเอง
# (core/gcode_generator.py::build_point_map)
#
# ตัวแปรที่ปรับได้:
#   TABLE_SAMPLES = จำนวนค่า r ในตาราง (interpolate เชิงเส้นระหว่างค่า — 9 ค่าคลาด < 0.1 µm บนหลุม R10)
#   TOL           = เกณฑ์หยุด sphere tracing (mm)
# ==============================================================================
import numpy as np

TABLE_SAMPLES = 9
TOL = 1e-6
R_NORMAL = 1e-3      # ทิศตั้งฉากผิวที่ r = 0 วัดจากลูกบอลรัศมีนี้ (ห่างผิว 1 µm)
MIN_STEP = 0.05     # ก้าวขั้นต่ำของ sphere tracing (mm) — ดู _trace()
_MAX_STEPS = 2000

_MODEL = {'faces': None, 'centroid': np.zeros(3)}
last_reason = None   # เหตุผลที่ touch_table() คืน None ครั้งล่าสุด: 'start_touching' / 'no_contact'


def set_model(step_data, centroid) -> None:
    """เรียกทุกครั้งที่โหลดไฟล์ STEP (core/geometry_engine.py)"""
    faces = []
    if step_data is not None:
        for f in step_data.faces().vals():
            bb = f.BoundingBox()
            faces.append((f.wrapped, np.array([bb.xmin, bb.ymin, bb.zmin]),
                          np.array([bb.xmax, bb.ymax, bb.zmax])))
    _MODEL['faces'] = faces or None
    _MODEL['centroid'] = np.asarray(centroid, dtype=float)


def available() -> bool:
    return bool(_MODEL['faces'])


def centroid() -> np.ndarray:
    return _MODEL['centroid']


def _local_shape(lo, hi):
    """compound ของผิวที่กล่องครอบตัดกับกล่องของเส้นทาง — เร็วกว่าทั้งชิ้นมาก"""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    comp, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(comp)
    n = 0
    for f, flo, fhi in _MODEL['faces']:
        if np.all(fhi >= lo) and np.all(flo <= hi):
            builder.Add(comp, f)
            n += 1
    return comp if n else None


def _nearest(shape, p):
    """(ระยะถึงผิวที่ใกล้ที่สุด, จุดบนผิว)"""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    ext = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, p))).Vertex(), shape)
    ext.Perform()
    if not ext.IsDone() or ext.NbSolution() < 1:
        return None, None
    q = ext.PointOnShape2(1)
    return float(ext.Value()), np.array([q.X(), q.Y(), q.Z()])


def _trace(shape, start, n, r, s0, max_travel):
    """ระยะเดิน s ≥ s0 ที่ลูกบอลรัศมี r แตะผิวครั้งแรก + ทิศแตะ m — None ถ้าไม่แตะภายใน max_travel
    ก้าวอย่างน้อย min(MIN_STEP, r/2) (ลูกบอลวิ่งขนานเฉียดขั้น/พื้น ก้าว d − r จะเล็กจนไม่ถึงไหน)
    ถ้าก้าวนั้นทำให้ลูกบอลจมผิว จึงแบ่งครึ่งย้อนหาจุดแตะแรก — ก้าว ≤ r/2 ข้ามผิวไปทั้งชิ้นไม่ได้"""
    s_safe = s = s0
    for _ in range(_MAX_STEPS):
        c = start + s * n
        d, q = _nearest(shape, c)
        if d is None:
            return None
        gap = d - r
        if gap < -TOL:   # ก้าวขั้นต่ำเลยจุดแตะ — แบ่งครึ่งระหว่างจุดที่ยังไม่แตะกับจุดนี้
            lo, hi = s_safe, s
            while hi - lo > 1e-8:
                mid = 0.5 * (lo + hi)
                if _nearest(shape, start + mid * n)[0] - r > 0.0:
                    lo = mid
                else:
                    hi = mid
            s = hi
            c = start + s * n
            d, q = _nearest(shape, c)
            gap = 0.0
        if gap <= TOL:
            if r <= 0.0:
                return s, None
            return s, (q - c) / max(d, 1e-12)
        s_safe = s
        s += max(gap, min(MIN_STEP, 0.5 * r))
        if s > max_travel:
            return None
    return None


def touch_table(start, n, r_max: float, max_travel: float, samples: int = TABLE_SAMPLES):
    """ตาราง [(r, s, m), ...] เรียง r จากน้อยไปมาก (พิกัด STEP) — None ถ้าเส้นทางนี้ไม่แตะผิว
    หรือลูกบอลชนผิวตั้งแต่จุดเริ่ม (จุดเริ่มต้องอยู่ห่างผิวเกิน r_max)"""
    global last_reason
    last_reason = None
    if not available():
        return None
    start = np.asarray(start, dtype=float)
    n = np.asarray(n, dtype=float)
    n = n / np.linalg.norm(n)
    pad = float(r_max) + 1.0
    end = start + max_travel * n
    shape = _local_shape(np.minimum(start, end) - pad, np.maximum(start, end) + pad)
    if shape is None:
        last_reason = 'no_contact'
        return None
    d0, _q = _nearest(shape, start)
    if d0 is None or d0 <= r_max + TOL:
        last_reason = 'start_touching'   # ลูกบอลแตะ/จมผิว CAD ตั้งแต่จุดเริ่ม (ชั้นลึกเกิน/ชิดพื้น)
        return None
    rs = np.linspace(0.0, float(r_max), int(samples))
    out, s_prev = [], 0.0
    for r in rs[::-1]:   # r มาก → แตะก่อน (s น้อย) แล้วไล่ต่อจากตรงนั้นสำหรับ r ที่เล็กลง
        hit = _trace(shape, start, n, float(r), s_prev, max_travel)
        if hit is None:
            last_reason = 'no_contact'
            return None
        s_prev, m = hit
        out.append([float(r), float(s_prev), m])
    out.reverse()
    hit = _trace(shape, start, n, R_NORMAL, out[1][1] if len(out) > 1 else 0.0, max_travel)
    out[0][2] = hit[1] if hit is not None else out[1][2]
    return [(r, s, np.asarray(m, dtype=float)) for r, s, m in out]
