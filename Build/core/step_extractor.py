# ==============================================================================
# core/step_extractor.py — สกัดข้อมูลรูจาก B-Rep ของไฟล์ STEP
# ==============================================================================
# หน้าที่หลัก:
#   1) extract()               อ่านทุก face ที่เป็น CYLINDER/CONE/TORUS/SPHERE
#      จากไฟล์ STEP แล้วคำนวณตำแหน่ง/รัศมี/ความลึกของรูแต่ละรูด้วยสมการ
#      วิเคราะห์ (analytical) ก่อน ถ้าล้มเหลวจึงถอยไปใช้วิธีหาเส้นขอบวงกลม (fallback)
#      จากนั้น merge หน้าตัดครึ่งวง (_merge_half_faces) และ merge รู counterbore
#      หลายระดับเข้าด้วยกัน (_merge_counterbores)
#   2) get_step_holes_in_view() แปลงรูที่สกัดได้ให้เป็นตำแหน่งบนจอ 2D ตามมุมมอง
#      ปัจจุบัน พร้อมตรวจสอบว่ารูถูกบัง/มองไม่เห็น/ตื้นเกินไปหรือไม่
#
# ตัวแปรสำคัญที่ปรับจูนได้ (ค่าคลาดเคลื่อน/threshold สำหรับตรวจจับ-รวมรู):
#   DEBUG               = เปิด/ปิดการพิมพ์ log และบันทึกไฟล์ log
#   _MIN_SWEEP_RAD       = มุมกวาดขั้นต่ำของเส้นขอบวงกลม (rad) ก่อนนับเป็นวงกลมจริง
#   _AXIS_TOL            = ค่าความคลาดเคลื่อนแกนขนาน เมื่อเทียบว่า 2 รูอยู่แกนเดียวกัน
#   _EXTENT_TOL          = ค่าความคลาดเคลื่อนความยาวช่วง (mm) เมื่อ merge หน้าครึ่งวง
#   _PERP_FRAC_TOL       = สัดส่วนความคลาดเคลื่อนระยะห่างตั้งฉากเมื่อ merge หน้าครึ่งวง
#   _STRICT_GAP_TOL      = ระยะห่างสูงสุด (mm) ที่ยอมให้ merge รูไม่ coaxial กัน
#   _MAX_RADIUS_RATIO    = อัตราส่วนรัศมีสูงสุดที่ยอมให้ merge รูไม่ coaxial กัน
#   _COAXIAL_PERP_TOL    = ระยะห่างตั้งฉากสูงสุด (mm) ที่นับว่า "แกนร่วมกัน" (coaxial)
#   _COAXIAL_PERP_FRAC   = สัดส่วนรัศมีเพิ่มเติมสำหรับเกณฑ์ coaxial
#   _COAXIAL_GAP_TOL     = ระยะห่างสูงสุด (mm) ที่ยอมให้ merge รู coaxial กัน
#   _MIN_TORUS_TUBE_RADIUS / _MIN_SPHERE_CAP_RADIUS = รัศมีขั้นต่ำ (mm) ก่อนนับเป็นรูจริง
#   MIN_DEPTH (ในฟังก์ชัน)      = ความลึกขั้นต่ำ (mm) ก่อนนับว่าเป็นรูที่วัดได้
#   SIDE_HOLE_AXIS_THRESHOLD    = มุมแกนขั้นต่ำที่นับว่าเป็น "รูด้านข้าง" เทียบมุมกล้อง
# ==============================================================================
import numpy as np
import math
import copy
import os
import datetime
import cadquery as cq
from core.models import StepHole, HoleSegment

DEBUG = True   # เปิด/ปิดการพิมพ์ + บันทึก log การสกัดรู — ปิดเพื่อลด overhead ตอนใช้งานจริง

# ---------------------------------------------------------------------------
# ตั้งค่าบันทึกไฟล์ log
# ---------------------------------------------------------------------------
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Log")
_LOG_FILE_HANDLE = None
_LOG_FILE_PATH = None
_LOG_INIT_ATTEMPTED = False

def _init_log_file():
    global _LOG_FILE_HANDLE, _LOG_FILE_PATH, _LOG_INIT_ATTEMPTED
    if _LOG_INIT_ATTEMPTED:
        return
    _LOG_INIT_ATTEMPTED = True
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _LOG_FILE_PATH = os.path.join(_LOG_DIR, f"Log_{timestamp}.txt")
        _LOG_FILE_HANDLE = open(_LOG_FILE_PATH, "w", encoding="utf-8")
        _LOG_FILE_HANDLE.write(f"=== step_extractor debug log started {timestamp} ===\n")
        _LOG_FILE_HANDLE.flush()
        print(f"[step_extractor] Logging to file: {_LOG_FILE_PATH}")
    except Exception as exc:
        _LOG_FILE_HANDLE = None
        print(f"[step_extractor] WARNING: could not initialize log file ({exc!r})")

def _dbg(msg):
    if not DEBUG:
        return
    line = f"[step_extractor] {msg}"
    print(line)
    if not _LOG_INIT_ATTEMPTED:
        _init_log_file()
    if _LOG_FILE_HANDLE is not None:
        try:
            _LOG_FILE_HANDLE.write(line + "\n")
            _LOG_FILE_HANDLE.flush()
        except Exception:
            pass

_MIN_SWEEP_RAD = math.pi   # มุมกวาดขั้นต่ำของเส้นขอบวงกลม (rad) ก่อนนับเป็นวงกลมจริง — ปรับได้
_AXIS_TOL       = 0.02     # ความคลาดเคลื่อนแกนขนาน เมื่อเทียบว่า 2 รูอยู่แกนเดียวกัน — ปรับได้
_EXTENT_TOL     = 0.5      # ความคลาดเคลื่อนความยาวช่วง (mm) เมื่อ merge หน้าครึ่งวง — ปรับได้
_PERP_FRAC_TOL  = 0.15     # สัดส่วนความคลาดเคลื่อนระยะห่างตั้งฉากเมื่อ merge หน้าครึ่งวง — ปรับได้

_STRICT_GAP_TOL    = 0.05  # ระยะห่างสูงสุด (mm) ที่ยอมให้ merge รูไม่ coaxial กัน — ปรับได้
_MAX_RADIUS_RATIO  = 1.2   # อัตราส่วนรัศมีสูงสุดที่ยอมให้ merge รูไม่ coaxial กัน — ปรับได้

_COAXIAL_PERP_TOL   = 0.3   # ระยะห่างตั้งฉากสูงสุด (mm) ที่นับว่าแกนร่วมกัน (coaxial) — ปรับได้
_COAXIAL_PERP_FRAC  = 0.15  # สัดส่วนรัศมีเพิ่มเติมสำหรับเกณฑ์ coaxial — ปรับได้
_COAXIAL_GAP_TOL    = 1.5   # ระยะห่างสูงสุด (mm) ที่ยอมให้ merge รู coaxial กัน — ปรับได้

_MIN_TORUS_TUBE_RADIUS = 2.0   # รัศมีท่อ torus ขั้นต่ำ (mm) ก่อนนับเป็นรูจริง — ปรับได้

_MIN_SPHERE_CAP_RADIUS = 2.0   # รัศมีขั้นต่ำของ sphere cap (mm) ก่อนนับเป็นรูจริง — ปรับได้

def _sweep_angle(edge) -> float:
    arc_len = edge.Length()
    if arc_len <= 0: return 0.0
    try:
        r = edge.radius()
        if r and r > 0: return arc_len / r
    except: pass
    r_approx = arc_len / (2 * math.pi)
    if r_approx > 0: return arc_len / r_approx
    return 0.0

def _arc_radius(edge) -> float:
    try:
        r = edge.radius()
        if r and r > 0: return float(r)
    except: pass
    arc_len = edge.Length()
    if arc_len > 0: return arc_len / (2 * math.pi)
    return 0.0

def _merge_half_faces(holes: list) -> list:
    """รวมรูที่ถูกตัดออกเป็น 2 หน้าครึ่งวง (เกิดจากขอบ B-Rep ขาดตอน) ให้กลับเป็นรูเดียว"""
    if not holes: return holes
    merged = [False] * len(holes)
    for i in range(len(holes)):
        if merged[i]: continue
        hi = holes[i]
        axis = np.array(hi.axis)
        proj = lambda pt: float(np.dot(np.array(pt), axis))
        for j in range(i + 1, len(holes)):
            if merged[j]: continue
            hj = holes[j]
            if abs(float(np.dot(hi.axis, hj.axis))) < 1 - _AXIS_TOL: continue
            if abs(hi.radius - hj.radius) > 0.1: continue

            ai0, ai1 = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            aj0, aj1 = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            if abs(ai0 - aj0) > _EXTENT_TOL or abs(ai1 - aj1) > _EXTENT_TOL: continue

            mid_i  = (np.array(hi.open_3d) + np.array(hi.deep_3d)) / 2.0
            mid_j  = (np.array(hj.open_3d) + np.array(hj.deep_3d)) / 2.0
            delta  = mid_j - mid_i
            perp   = delta - float(np.dot(delta, axis)) * axis
            perp_d = float(np.linalg.norm(perp))
            expected = 4.0 * hi.radius / math.pi
            if abs(perp_d - expected) > expected * _PERP_FRAC_TOL: continue

            true_open = (np.array(hi.open_3d) + np.array(hj.open_3d)) / 2.0
            true_deep = (np.array(hi.deep_3d) + np.array(hj.deep_3d)) / 2.0
            hi.open_3d = tuple(true_open)
            hi.deep_3d = tuple(true_deep)
            hi.depth   = float(np.linalg.norm(true_deep - true_open))
            hi.segments = [HoleSegment(hi.open_3d, hi.deep_3d, hi.radius_open, hi.radius_deep)]
            merged[j]  = True
            break
    result = [h for i, h in enumerate(holes) if not merged[i]]
    return result

def _merge_counterbores(holes: list) -> list:
    """รวมรูที่มีหลายระดับเส้นผ่านศูนย์กลาง (counterbore) ที่อยู่แกนเดียวกัน/ต่อเนื่องกัน
    ให้กลายเป็นรูเดียวที่มีหลาย segment"""
    if not holes: return holes
    current = holes
    while True:
        merged_out = [False] * len(current)
        made_merge = False

        for i in range(len(current)):
            if merged_out[i]: continue
            for j in range(len(current)):
                if i == j or merged_out[j]: continue
                hi, hj = current[i], current[j]
                dot = abs(float(np.dot(hi.axis, hj.axis)))
                if dot < 1.0 - _AXIS_TOL: continue

                axis   = np.array(hi.axis)
                mid_i  = (np.array(hi.open_3d) + np.array(hi.deep_3d)) / 2.0
                mid_j  = (np.array(hj.open_3d) + np.array(hj.deep_3d)) / 2.0
                delta  = mid_j - mid_i
                perp   = delta - float(np.dot(delta, axis)) * axis
                perp_d = float(np.linalg.norm(perp))

                r_large = max(hi.radius_open, hj.radius_open)
                r_small = min(hi.radius_open, hj.radius_open)
                coaxial_threshold = max(_COAXIAL_PERP_TOL, r_small * _COAXIAL_PERP_FRAC)
                is_coaxial = perp_d <= coaxial_threshold

                if not is_coaxial and (perp_d + r_small >= r_large): continue

                proj  = lambda pt: float(np.dot(np.array(pt), axis))
                seg_i = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
                seg_j = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
                gap   = max(seg_j[0] - seg_i[1], seg_i[0] - seg_j[1])

                gap_tol = _COAXIAL_GAP_TOL if is_coaxial else _STRICT_GAP_TOL

                if is_coaxial and abs(r_large - r_small) < 0.1 and perp_d < _COAXIAL_PERP_TOL:
                    # กรณีรูขนาดเท่ากันแกนเดียวกันแท้ ๆ (เช่น รูทะลุที่ถูกตัดข้อมูลขาดกลาง)
                    # ขยาย gap_tol ชั่วคราวเพื่อเชื่อมรูทั้งสองฝั่งเข้าด้วยกัน — ปรับสัดส่วน (×4.0) / ค่าต่ำสุด (50.0) ได้
                    extended_gap = max(gap_tol, r_large * 4.0, 50.0)
                    if gap_tol < extended_gap:
                        _dbg(f"  CROSS-HOLE BRIDGE ACTIVATED: extending gap_tol from {gap_tol} to {extended_gap:.2f}")
                        gap_tol = extended_gap

                if gap > gap_tol: continue

                if not is_coaxial:
                    radius_ratio = r_large / r_small if r_small > 0 else float('inf')
                    if radius_ratio > _MAX_RADIUS_RATIO: continue

                candidates = [
                    (hi.open_3d, proj(hi.open_3d), hi.radius_open),
                    (hi.deep_3d, proj(hi.deep_3d), hi.radius_deep),
                    (hj.open_3d, proj(hj.open_3d), hj.radius_open),
                    (hj.deep_3d, proj(hj.deep_3d), hj.radius_deep),
                ]
                candidates.sort(key=lambda c: c[1])
                shallow_pt, _, shallow_r = candidates[0]
                deep_pt,    _, deep_r    = candidates[-1]
                new_depth = float(np.linalg.norm(np.array(deep_pt) - np.array(shallow_pt)))
                if new_depth <= 1e-6: continue

                combined_segments = list(hi.segments) + list(hj.segments)
                combined_segments.sort(
                    key=lambda seg: min(proj(seg.open_3d), proj(seg.deep_3d)))

                hi.open_3d     = tuple(shallow_pt)
                hi.deep_3d     = tuple(deep_pt)
                hi.radius_open = float(shallow_r)
                hi.radius_deep = float(deep_r)
                hi.radius      = float(shallow_r)
                hi.depth       = new_depth
                hi.segments    = combined_segments
                merged_out[j]  = True
                made_merge      = True
                _dbg(f"  MERGE: combined into {len(combined_segments)} segment(s), "
                     f"total_depth={new_depth:.2f}")
                break

        current = [h for i, h in enumerate(current) if not merged_out[i]]
        if not made_merge:
            break

    return current

def _orient_segments_by_mesh(h, mesh):
    """เรียงลำดับ segment ให้ segment แรกอยู่ใกล้ผิว mesh จริง (ปากรู) เสมอ
    โดยเทียบระยะห่างจากผิว mesh ของปลายทั้งสองด้าน"""
    if mesh is None or not h.segments or len(h.segments) < 2:
        return
    try:
        first_pt = np.array([h.segments[0].open_3d])
        last_pt  = np.array([h.segments[-1].deep_3d])
        _, dist_first, _ = mesh.nearest.on_surface(first_pt)
        _, dist_last,  _ = mesh.nearest.on_surface(last_pt)
    except Exception as e:
        _dbg(f"  mesh orientation check failed: {e!r}")
        return

    if dist_last[0] < dist_first[0] - 1e-6:
        _dbg(f"  MESH ORIENT: reversing segment order "
             f"(surface dist first={dist_first[0]:.3f} last={dist_last[0]:.3f})")
        h.segments.reverse()
        for seg in h.segments:
            seg.open_3d, seg.deep_3d         = seg.deep_3d, seg.open_3d
            seg.radius_open, seg.radius_deep = seg.radius_deep, seg.radius_open
        h.open_3d, h.deep_3d         = h.deep_3d, h.open_3d
        h.radius_open, h.radius_deep = h.radius_deep, h.radius_open
        h.radius                     = h.radius_open

class StepExtractor:
    def __init__(self):
        self._step_holes_cache = []

    def extract(self, step_data, mesh_centroid, mesh=None):
        """อ่านทุก face ในไฟล์ STEP ที่เป็นทรง CYLINDER/CONE/TORUS/SPHERE
        แล้วสกัดเป็นรายการ StepHole (ตำแหน่ง/รัศมี/ความลึก/แกน)"""
        if step_data is None: return []

        cx_off, cy_off, cz_off = mesh_centroid
        holes = []
        seen  = {}

        total_faces       = 0

        for face in step_data.faces().vals():
            total_faces += 1
            geom_type = face.geomType()

            if geom_type not in ('CYLINDER', 'CONE', 'TORUS', 'SPHERE'):
                continue

            analytical_success = False

            # วิธีหลัก: ดึงสมการพื้นผิว (analytical) ตรงจากคณิตศาสตร์ B-Rep — แม่นยำและเร็วกว่า
            if geom_type == 'CYLINDER':
                try:
                    try:
                        from OCP.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)
                    except ImportError:
                        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)

                    cyl = adaptor.Cylinder()
                    ax = cyl.Axis()
                    loc = ax.Location()
                    d = ax.Direction()

                    c0 = np.array([loc.X() - cx_off, loc.Y() - cy_off, loc.Z() - cz_off])
                    axis_vec = np.array([d.X(), d.Y(), d.Z()])
                    ax_norm = np.linalg.norm(axis_vec)
                    if ax_norm < 1e-6: raise ValueError("Degenerate axis")
                    axis_vec = axis_vec / ax_norm
                    r_a = r_b = float(cyl.Radius())

                    projs = []
                    # ฉายจุดบนขอบที่เหลืออยู่ลงบนแกนรู
                    for f_edge in face.Edges():
                        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                            try:
                                pt = f_edge.positionAt(t)
                                vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                projs.append(float(np.dot(vec, axis_vec)))
                            except: pass

                    # กรณีขอบถูกทำลายหมด ให้ดึงจากจุดตัด (vertices) แทน
                    if not projs:
                        for v in face.Vertices():
                            try:
                                pt = v.Center() if hasattr(v, 'Center') else v.toTuple()
                                if isinstance(pt, tuple):
                                    vec = np.array([pt[0] - cx_off, pt[1] - cy_off, pt[2] - cz_off]) - c0
                                else:
                                    vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                projs.append(float(np.dot(vec, axis_vec)))
                            except: pass

                    if not projs: raise ValueError("No edge/vertex samples found")

                    min_p, max_p = min(projs), max(projs)
                    face_depth = max_p - min_p
                    end_a = tuple(c0 + min_p * axis_vec)
                    end_b = tuple(c0 + max_p * axis_vec)
                    ax, ay, az = axis_vec
                    analytical_success = True
                    _dbg(f"ANALYTICAL SUCCESS face#{total_faces}: depth={face_depth:.2f} r={r_a:.2f}")
                except Exception as e:
                    _dbg(f"Analytical extraction failed face#{total_faces}: {e!r}")

            elif geom_type == 'TORUS':
                try:
                    try:
                        from OCP.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)
                    except ImportError:
                        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)

                    tor = adaptor.Torus()
                    ax1 = tor.Axis()
                    loc = ax1.Location()
                    d   = ax1.Direction()

                    c0 = np.array([loc.X() - cx_off, loc.Y() - cy_off, loc.Z() - cz_off])
                    axis_vec = np.array([d.X(), d.Y(), d.Z()])
                    ax_norm = np.linalg.norm(axis_vec)
                    if ax_norm < 1e-6: raise ValueError("Degenerate torus axis")
                    axis_vec = axis_vec / ax_norm

                    R_major = float(tor.MajorRadius())
                    r_minor = float(tor.MinorRadius())

                    samples = []  # (axial_coord, local_radius_at_that_point)
                    for f_edge in face.Edges():
                        for t in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0):
                            try:
                                pt = f_edge.positionAt(t)
                                vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                axial    = float(np.dot(vec, axis_vec))
                                perp_vec = vec - axial * axis_vec
                                perp_r   = float(np.linalg.norm(perp_vec))
                                samples.append((axial, perp_r))
                            except: pass

                    if not samples:
                        for v in face.Vertices():
                            try:
                                pt = v.Center() if hasattr(v, 'Center') else v.toTuple()
                                if isinstance(pt, tuple):
                                    vec = np.array([pt[0] - cx_off, pt[1] - cy_off, pt[2] - cz_off]) - c0
                                else:
                                    vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                axial    = float(np.dot(vec, axis_vec))
                                perp_vec = vec - axial * axis_vec
                                perp_r   = float(np.linalg.norm(perp_vec))
                                samples.append((axial, perp_r))
                            except: pass

                    if not samples: raise ValueError("No edge/vertex samples found on torus face")

                    samples.sort(key=lambda s: s[0])
                    min_axial, r_at_min = samples[0]
                    max_axial, r_at_max = samples[-1]

                    face_depth = max_axial - min_axial
                    end_a = tuple(c0 + min_axial * axis_vec)
                    end_b = tuple(c0 + max_axial * axis_vec)
                    r_a, r_b = r_at_min, r_at_max
                    ax, ay, az = axis_vec
                    analytical_success = True
                    _dbg(f"TORUS ANALYTICAL SUCCESS face#{total_faces}: "
                         f"depth={face_depth:.2f} R={R_major:.2f} r_tube={r_minor:.2f} "
                         f"r_open={r_a:.2f} r_deep={r_b:.2f}")
                except Exception as e:
                    _dbg(f"Torus analytical extraction failed face#{total_faces}: {e!r}")

            elif geom_type == 'SPHERE':
                try:
                    try:
                        from OCP.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)
                    except ImportError:
                        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)

                    sph = adaptor.Sphere()
                    loc = sph.Location()
                    R   = float(sph.Radius())

                    c0 = np.array([loc.X() - cx_off, loc.Y() - cy_off, loc.Z() - cz_off])

                    _SEAM_RADIUS_TOL = max(R * 1e-4, 1e-3)

                    def _edge_radius(e):
                        try:
                            r = e.radius()
                            return float(r) if r else None
                        except Exception:
                            return None

                    rim_edges = []
                    seam_skipped = 0
                    for f_edge in face.Edges():
                        if f_edge.geomType() != 'CIRCLE':
                            continue
                        er = _edge_radius(f_edge)
                        if er is None:
                            continue
                        if er >= R - _SEAM_RADIUS_TOL:
                            seam_skipped += 1
                            continue
                        rim_edges.append(f_edge)

                    if seam_skipped:
                        _dbg(f"  face#{total_faces}: skipped {seam_skipped} "
                             f"seam/meridian edge(s) (radius≈R={R:.3f}) "
                             f"from sphere rim sampling")

                    rim_pts = []
                    for f_edge in rim_edges:
                        for t in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0):
                            try:
                                pt = f_edge.positionAt(t)
                                rim_pts.append(np.array(
                                    [pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]))
                            except: pass

                    if not rim_pts:
                        for v in face.Vertices():
                            try:
                                pt = v.Center() if hasattr(v, 'Center') else v.toTuple()
                                if isinstance(pt, tuple):
                                    rim_pts.append(np.array(
                                        [pt[0] - cx_off, pt[1] - cy_off, pt[2] - cz_off]))
                                else:
                                    rim_pts.append(np.array(
                                        [pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]))
                            except: pass

                    if not rim_pts: raise ValueError("No rim samples found on sphere face")

                    try:
                        fc = face.Center()
                        face_centroid = np.array(
                            [fc.x - cx_off, fc.y - cy_off, fc.z - cz_off])
                    except Exception:
                        face_centroid = np.mean(rim_pts, axis=0)

                    axis_raw  = face_centroid - c0
                    axis_norm = np.linalg.norm(axis_raw)
                    if axis_norm < 1e-6: raise ValueError("Degenerate sphere cap axis")
                    axis_vec  = axis_raw / axis_norm
                    ax, ay, az = axis_vec
                    pole_pt = c0 + R * axis_vec
                    rim_arr    = np.array(rim_pts)
                    rel        = rim_arr - c0
                    proj_len   = rel @ axis_vec
                    perp_vecs  = rel - np.outer(proj_len, axis_vec)

                    h_avg      = float(np.mean(proj_len))
                    rim_center = c0 + h_avg * axis_vec
                    r_open     = float(np.mean(np.linalg.norm(perp_vecs, axis=1)))
                    r_deep     = 0.0  # ขั้วบนเป็นจุดเดียว เหมือนปลายแหลมของ CONE

                    end_a      = tuple(rim_center)
                    end_b      = tuple(pole_pt)
                    r_a, r_b   = r_open, r_deep
                    face_depth = float(np.linalg.norm(pole_pt - rim_center))

                    analytical_success = True
                    _dbg(f"SPHERE ANALYTICAL SUCCESS face#{total_faces}: "
                         f"depth={face_depth:.2f} R={R:.2f} r_open={r_a:.2f}")
                except Exception as e:
                    _dbg(f"Sphere analytical extraction failed face#{total_faces}: {e!r}")

            # วิธีสำรอง (ใช้เมื่อดึงสมการไม่สำเร็จ หรือเป็น CONE): หาเส้นวงกลม (edge) แทน
            if not analytical_success:
                raw_circle_edges = [e for e in face.Edges() if e.geomType() == 'CIRCLE']
                if len(raw_circle_edges) < 1:
                    continue

                circle_edges = [e for e in raw_circle_edges if _sweep_angle(e) >= _MIN_SWEEP_RAD]
                if len(circle_edges) < 1:
                    continue

                circle_data = []
                for edge in circle_edges:
                    c = edge.Center()
                    circle_data.append((c.x - cx_off, c.y - cy_off, c.z - cz_off, _arc_radius(edge), edge))

                if len(circle_data) < 1:
                    continue

                if len(circle_data) >= 2:
                    c0, c1 = np.array(circle_data[0][:3]), np.array(circle_data[-1][:3])
                    diff = c1 - c0
                    dist = float(np.linalg.norm(diff))
                    if dist < 0.05:
                        continue
                    axis_vec = diff / dist
                    ax, ay, az = axis_vec
                    circle_data.sort(key=lambda d: ax * d[0] + ay * d[1] + az * d[2])
                    end_a, end_b = tuple(circle_data[0][:3]), tuple(circle_data[-1][:3])
                    r_a, r_b = circle_data[0][3], circle_data[-1][3]
                    face_depth = float(np.linalg.norm(np.array(end_b) - np.array(end_a)))
                else:
                    c0 = np.array(circle_data[0][:3])
                    r_a = r_b = circle_data[0][3]
                    ref_edge = circle_data[0][4]
                    try:
                        p0 = np.array(ref_edge.positionAt(0.0).toTuple())
                        p1 = np.array(ref_edge.positionAt(0.33).toTuple())
                        p2 = np.array(ref_edge.positionAt(0.66).toTuple())
                        raw_axis = np.cross(p1 - p0, p2 - p0)
                        ax_norm = np.linalg.norm(raw_axis)
                        if ax_norm < 1e-6:
                            continue
                        axis_vec = raw_axis / ax_norm
                        ax, ay, az = axis_vec
                        
                        projs = [0.0]
                        for f_edge in face.Edges():
                            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                                try:
                                    pt = f_edge.positionAt(t)
                                    vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                    projs.append(float(np.dot(vec, axis_vec)))
                                except: pass
                        min_p, max_p = min(projs), max(projs)
                        face_depth = max_p - min_p
                        end_a = tuple(c0 + min_p * axis_vec)
                        end_b = tuple(c0 + max_p * axis_vec)
                    except:
                        continue

            if face_depth < 0.1:
                continue

            mid = (np.array(end_a) + np.array(end_b)) / 2.0
            key = (round(mid[0], 1), round(mid[1], 1), round(mid[2], 1), round(max(r_a, r_b), 2))

            if key in seen:
                idx = seen[key]
                if face_depth > holes[idx].depth:
                    holes[idx] = StepHole(end_a, end_b, r_a, r_b, (ax, ay, az))
                continue

            seen[key] = len(holes)
            holes.append(StepHole(end_a, end_b, r_a, r_b, (ax, ay, az)))

        holes = _merge_half_faces(holes)
        holes = _merge_counterbores(holes)
        for h in holes:
            _orient_segments_by_mesh(h, mesh)

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    def _raycast_surface_depth(self, mesh, point_3d, dir_to_viewer, projector, view_name, screen_rot):
        try: bbox_diag = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0]))
        except: return None
        ray_origin = np.array(point_3d) + dir_to_viewer * (bbox_diag + 5.0)
        try: locs, _, _ = mesh.ray.intersects_location(ray_origins=[ray_origin], ray_directions=[-dir_to_viewer])
        except: return None
        if len(locs) == 0: return None
        hit = locs[int(np.argmin(np.linalg.norm(locs - ray_origin, axis=1)))]
        dx, dy, depth = projector.project_point_to_view(*hit, view_name, screen_rot)
        return dx, dy, depth, hit

    def _sample_side_hole_breach(self, h, dir_to_viewer, mesh, projector, view_name, screen_rot):
        MIN_DEPTH = 0.1   # ความลึกขั้นต่ำ (mm) ก่อนนับว่าพบจุดทะลุผิวของรูด้านข้าง — ปรับได้
        axis_vec = np.array(h.axis, dtype=float)
        norm = np.linalg.norm(axis_vec)
        if norm < 1e-9: return None
        axis_vec /= norm
        u = np.cross(axis_vec, dir_to_viewer)
        u_norm = np.linalg.norm(u)
        u = np.zeros(3) if u_norm < 1e-6 else u / u_norm

        r_ref = max(h.radius_open, h.radius_deep)
        open_pt, deep_pt = np.array(h.open_3d, dtype=float), np.array(h.deep_3d, dtype=float)
        mid_3d = (open_pt + deep_pt) / 2.0
        best = None

        for af in (0.5, 0.25, 0.75):
            base_pt = open_pt + af * (deep_pt - open_pt)
            for uf in (0.0, 0.5, -0.5, 0.85, -0.85):
                fb = self._raycast_surface_depth(mesh, base_pt + (uf * r_ref) * u, dir_to_viewer, projector, view_name, screen_rot)
                if fb is None: continue
                fb_x, fb_y, fb_depth, fb_hit = fb
                hit_rel = fb_hit - mid_3d
                perp_dist = float(np.linalg.norm(hit_rel - float(np.dot(hit_rel, axis_vec)) * axis_vec))
                if perp_dist <= r_ref * 1.5 and fb_depth > MIN_DEPTH:
                    if best is None or perp_dist < best[4]:
                        best = (fb_x, fb_y, fb_depth, fb_hit, perp_dist)
        return best

    def get_step_holes_in_view(self, projector, view_name: str, screen_rot: int = 0, mesh=None):
        """แปลงรูจาก cache ให้เป็นตำแหน่งบนจอ 2D ตามมุมมองปัจจุบัน พร้อมตรวจสอบ
        ว่ารูถูกบัง (occluded), ตื้นเกินไป, หรือมองไม่เห็นจากมุมนี้หรือไม่"""
        if not self._step_holes_cache: return []
        p = projector.get_view_params(view_name, screen_rot)
        dir_to_viewer = p['matrix'][:3, :3].T @ np.array([0.0, 0.0, 1.0])
        dir_to_viewer /= np.linalg.norm(dir_to_viewer)
        MIN_DEPTH, SIDE_HOLE_AXIS_THRESHOLD = 0.1, 0.3   # ความลึกขั้นต่ำ (mm) / มุมแกนขั้นต่ำที่นับเป็น "รูด้านข้าง" — ปรับได้
        result = []

        for cache_idx, h in enumerate(self._step_holes_cache):
            dx_a, dy_a, d_a = projector.project_point_to_view(*h.open_3d, view_name, screen_rot)
            dx_b, dy_b, d_b = projector.project_point_to_view(*h.deep_3d, view_name, screen_rot)

            if d_a <= d_b:
                open_depth, deep_depth, display_x, display_y = d_a, d_b, dx_a, dy_a
                r_open, r_deep, open_3d, deep_3d = h.radius_open, h.radius_deep, h.open_3d, h.deep_3d
            else:
                open_depth, deep_depth, display_x, display_y = d_b, d_a, dx_b, dy_b
                r_open, r_deep, open_3d, deep_3d = h.radius_deep, h.radius_open, h.deep_3d, h.open_3d

            actual_depth = deep_depth - open_depth

            def _make_rejected(reason: str):
                mid_3d = (np.array(open_3d) + np.array(deep_3d)) / 2.0
                try:
                    fx, fy, fdepth = projector.project_point_to_view(*mid_3d, view_name, screen_rot)
                    pos_ok = (math.isfinite(fx) and math.isfinite(fy) and math.isfinite(fdepth))
                except: pos_ok = False
                hc = copy.copy(h)
                hc.open_3d, hc.deep_3d, hc.radius_open, hc.radius_deep, hc.radius = open_3d, deep_3d, r_open, r_deep, r_open
                hc.is_rejected, hc.reject_reason, hc.position_unknown = True, reason, not pos_ok
                if pos_ok:
                    hc.display_x, hc.display_y, hc.depth_top, hc.depth_bot = fx, fy, max(0.0, fdepth - r_open), fdepth
                    hc.depth = max(0.0, hc.depth_bot - hc.depth_top)
                else:
                    hc.display_x, hc.display_y, hc.depth_top, hc.depth_bot, hc.depth = None, None, 0.0, 0.0, 0.0
                return hc

            if actual_depth < MIN_DEPTH:
                axis_align = abs(float(np.dot(np.array(h.axis), dir_to_viewer)))
                if mesh is not None and axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    best = self._sample_side_hole_breach(h, dir_to_viewer, mesh, projector, view_name, screen_rot)
                    if best is not None:
                        fb_x, fb_y, fb_depth, fb_hit, perp_dist = best
                        hc = copy.copy(h)
                        hc.open_3d, hc.deep_3d, hc.radius_open, hc.radius_deep, hc.radius = open_3d, deep_3d, r_open, r_deep, r_open
                        hc.display_x, hc.display_y, hc.depth_top, hc.depth_bot = fb_x, fb_y, max(0.0, fb_depth - max(r_open, r_deep)), fb_depth
                        hc.depth = max(MIN_DEPTH, hc.depth_bot - hc.depth_top)
                        hc.is_rejected, hc.reject_reason, hc.position_unknown = False, "", False
                        result.append(hc)
                        continue

                if axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    _dbg(f"  cache[{cache_idx}] DROPPED: irrelevant side-hole for this view.")
                    continue
                
                if open_depth > deep_depth:
                    _dbg(f"  cache[{cache_idx}] DROPPED: hole faces away from camera.")
                    continue

                result.append(_make_rejected("Too shallow / no breach found"))
                continue

            if mesh is not None:
                if mesh.ray.intersects_any(ray_origins=[np.array(open_3d) + (dir_to_viewer * 0.1)], ray_directions=[dir_to_viewer])[0]:
                    result.append(_make_rejected("Occluded by mesh from this view"))
                    continue

            hc = copy.copy(h)
            hc.open_3d, hc.deep_3d, hc.radius_open, hc.radius_deep, hc.radius = open_3d, deep_3d, r_open, r_deep, r_open
            hc.display_x, hc.display_y, hc.depth_top, hc.depth_bot, hc.depth = display_x, display_y, open_depth, deep_depth, actual_depth
            hc.is_rejected, hc.reject_reason, hc.position_unknown = False, "", False
            result.append(hc)

        def _sort_key(hh):
            if hh.display_x is None or hh.display_y is None: return (1, 0, 0)
            return (0, -round(hh.display_y / 5.0), hh.display_x)

        result.sort(key=_sort_key)
        return result
