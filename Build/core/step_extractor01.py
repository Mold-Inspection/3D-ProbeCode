# ==============================================================================
# core/step_extractor.py — สกัดข้อมูลรูจาก B-Rep ของไฟล์ STEP
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FIX (PLAN_segment-diameter-direction-fix.md): new helper
#   _orient_each_segment_to_hole_mouth(h) — forces EVERY individual
#   segment's own open_3d/radius_open to always be the end that is
#   closer to the whole hole's true mouth (h.open_3d), and
#   deep_3d/radius_deep to always be the farther/deeper end — decided
#   purely by axial projection distance from h.open_3d along h.axis,
#   independent of whether that segment happens to be the deepest or
#   shallowest segment of the hole.
#   Previously only two corrections existed: _orient_segments_by_mesh()
#   (fixes which end is the mouth for the WHOLE hole, via mesh surface
#   distance) and _order_segments_deepest_first() (fixes the LIST INDEX
#   order so segments[0] = deepest) — neither of these guaranteed that
#   a given segment's OWN open_3d/deep_3d labels pointed mouth-ward vs
#   deep-ward consistently with its neighbors. That gap is why the
#   Customization tab's per-segment diameter label
#   (⌀radius_open*2 → ⌀radius_deep*2) could show two adjacent segments
#   both displaying the SAME value as their "open" (mouth-side) figure,
#   even though physically that shared value is one segment's mouth-side
#   boundary and the other segment's deep-side boundary at the same
#   junction point — i.e. the diameters looked discontinuous / hard to
#   read. Called right after _order_segments_deepest_first(h) for every
#   hole in extract(). Downstream consumers (path_planner.py,
#   gcode_generator.py) already re-sort/re-derive layer order and
#   min/max bounds independently of per-segment open/deep labeling, so
#   this fix does not change probe path point sets or G-code travel —
#   only makes the displayed/underlying open->deep radius direction of
#   each segment consistent and physically continuous across the hole.
# ==============================================================================
# VERSION: 01 (superseded by v02 above — kept for history)
# CHANGE LOG (no marker -> v01):
#   FEATURE (Fix 1 of PLAN_segment-order-and-rotation-fixes.md): new helper
#   _order_segments_deepest_first(h) — always re-sorts h.segments so index 0
#   is the DEEPEST segment (farthest along h.axis from h.open_3d) and the
#   LAST index is the shallowest/mouth segment, regardless of whether a mesh
#   was available. Called unconditionally right after
#   _orient_segments_by_mesh(h, mesh) for every hole in extract(), since by
#   that point h.open_3d (mouth) and h.axis are already correctly established
#   at the whole-hole level. This is a pure ordering fix — does not change
#   which end is the mouth (that's still _orient_segments_by_mesh's job).
#   See core/models.py v03 for the matching downstream fix in
#   validate_segment_reachability().
# ==============================================================================
import numpy as np
import math
import copy
import os
import datetime
import cadquery as cq
from core.models import StepHole, HoleSegment

DEBUG = True

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

_MIN_SWEEP_RAD = math.pi
_AXIS_TOL       = 0.02
_EXTENT_TOL     = 0.5
_PERP_FRAC_TOL  = 0.15

_STRICT_GAP_TOL    = 0.05
_MAX_RADIUS_RATIO  = 1.2

_COAXIAL_PERP_TOL   = 0.3
_COAXIAL_PERP_FRAC  = 0.15
_COAXIAL_GAP_TOL    = 1.5

_MIN_TORUS_TUBE_RADIUS = 2.0
_MIN_SPHERE_CAP_RADIUS = 2.0

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
    โดยเทียบระยะห่างจากผิว mesh ของปลายทั้งสองด้าน — หมายเหตุ: ฟังก์ชันนี้
    จัดการเฉพาะ "ปลายไหนคือปาก" (h.open_3d) เท่านั้น ส่วนลำดับ index ใน
    h.segments list จะถูกจัดใหม่อีกทีโดย _order_segments_deepest_first()
    ที่ทำงานต่อจากนี้เสมอ (ดู extract())"""
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

def _order_segments_deepest_first(h):
    """เรียง h.segments ใหม่เสมอให้ index 0 = segment ที่ลึกที่สุด (ไกลจากปากรู
    h.open_3d ที่สุดตามแกน h.axis) และ index สุดท้าย = segment ที่ตื้นที่สุด
    (ปากรู) โดยไม่พึ่งพา mesh — ใช้ระยะ projection ตามแกนรู เทียบกับ h.open_3d
    ที่ถูกกำหนดไว้แล้วในระดับรูทั้งก้อน (มาจาก _merge_counterbores /
    _orient_segments_by_mesh) ทำงานเสมอไม่ว่าจะมี mesh หรือไม่

    หมายเหตุ: ฟังก์ชันนี้จัดแค่ "ลำดับ index ใน list" เท่านั้น ไม่ได้แก้ทิศ
    open/deep ภายในแต่ละ segment เอง — ดู _orient_each_segment_to_hole_mouth()
    (v02) สำหรับส่วนนั้น"""
    if not h.segments or len(h.segments) < 2:
        return
    axis = np.array(h.axis, dtype=float)
    ref  = np.array(h.open_3d, dtype=float)   # known mouth point at hole level

    def _proj_depth(seg):
        mid = (np.array(seg.open_3d) + np.array(seg.deep_3d)) / 2.0
        return float(np.dot(mid - ref, axis))

    h.segments.sort(key=_proj_depth, reverse=True)   # largest projected distance = deepest -> index 0
    _dbg(f"  SEGMENT ORDER: sorted {len(h.segments)} segment(s) deepest-first "
         f"(index 0 = deepest, index {len(h.segments)-1} = mouth)")

def _orient_each_segment_to_hole_mouth(h):
    """v02 (PLAN_segment-diameter-direction-fix.md): บังคับให้ seg.open_3d /
    seg.radius_open ของ "ทุก" segment อยู่ฝั่งที่ใกล้ปากรูจริงของทั้งรู
    (h.open_3d) เสมอ และ seg.deep_3d / seg.radius_deep คือฝั่งตรงข้าม (ลึกเข้า
    ไปในรูมากกว่า) — ตัดสินด้วยระยะ projection ตามแกน h.axis เทียบกับ
    h.open_3d ทำงานเป็นรายตัว ไม่ขึ้นกับว่า segment นั้นเป็น segment ที่ลึกสุด
    หรือตื้นสุดของทั้งรู (ต่างจาก _order_segments_deepest_first ที่จัดแค่
    "ลำดับ index ใน list" เท่านั้น)

    เหตุผลที่ต้องมีฟังก์ชันนี้: ก่อนหน้านี้แต่ละ segment สืบทอดทิศ open/deep
    ของตัวเองมาจากตอน extract แบบดิบ (อิงทิศทางที่เจอ circle ก่อน-หลัง ไม่ผูก
    กับปากรูจริง) ทำให้ segment ที่ติดกัน 2 อัน อาจแสดงไดอามิเตอร์ฝั่ง "open"
    เป็นค่าเดียวกัน ทั้งที่ควรเป็นคนละฝั่งของรอยต่อ (ฝั่ง deep ของ segment ที่
    ตื้นกว่า ต้อง = ฝั่ง open ของ segment ที่ลึกกว่าที่ติดกัน) — แก้ที่นี่ทำให้
    ไดอามิเตอร์ที่แสดงต่อเนื่องกันจริงตลอดความลึกของรู"""
    if not h.segments:
        return
    axis = np.array(h.axis, dtype=float)
    ref  = np.array(h.open_3d, dtype=float)

    flipped = 0
    for seg in h.segments:
        d_open = float(np.dot(np.array(seg.open_3d) - ref, axis))
        d_deep = float(np.dot(np.array(seg.deep_3d) - ref, axis))
        if d_open > d_deep:
            # open_3d ปัจจุบันอยู่ "ลึกกว่า" deep_3d เมื่อเทียบกับปากรูจริง -> ผิดทิศ ต้องสลับ
            seg.open_3d, seg.deep_3d         = seg.deep_3d, seg.open_3d
            seg.radius_open, seg.radius_deep = seg.radius_deep, seg.radius_open
            flipped += 1

    if flipped:
        _dbg(f"  SEGMENT MOUTH-ORIENT: flipped open/deep on {flipped}/{len(h.segments)} "
             f"segment(s) so radius_open always faces the hole's true mouth")

class StepExtractor:
    def __init__(self):
        self._step_holes_cache = []

    def extract(self, step_data, mesh_centroid, mesh=None):
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
                    for f_edge in face.Edges():
                        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                            try:
                                pt = f_edge.positionAt(t)
                                vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                projs.append(float(np.dot(vec, axis_vec)))
                            except: pass

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

                    samples = []
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
                    r_deep     = 0.0

                    end_a      = tuple(rim_center)
                    end_b      = tuple(pole_pt)
                    r_a, r_b   = r_open, r_deep
                    face_depth = float(np.linalg.norm(pole_pt - rim_center))

                    analytical_success = True
                    _dbg(f"SPHERE ANALYTICAL SUCCESS face#{total_faces}: "
                         f"depth={face_depth:.2f} R={R:.2f} r_open={r_a:.2f}")
                except Exception as e:
                    _dbg(f"Sphere analytical extraction failed face#{total_faces}: {e!r}")

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
            _order_segments_deepest_first(h)          # v01: always run — mesh-independent, keeps segments[0] = deepest
            _orient_each_segment_to_hole_mouth(h)      # v02: always run — keeps radius_open facing the hole's true mouth per segment

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
        MIN_DEPTH = 0.1
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
        if not self._step_holes_cache: return []
        p = projector.get_view_params(view_name, screen_rot)
        dir_to_viewer = p['matrix'][:3, :3].T @ np.array([0.0, 0.0, 1.0])
        dir_to_viewer /= np.linalg.norm(dir_to_viewer)
        MIN_DEPTH, SIDE_HOLE_AXIS_THRESHOLD = 0.1, 0.3
        result = []

        for cache_idx, h in enumerate(self._step_holes_cache):
            dx_a, dy_a, d_a = projector.project_point_to_view(*h.open_3d, view_name, screen_rot)
            dx_b, dy_b, d_b = projector.project_point_to_view(*h.deep_3d, view_name, screen_rot)

            hc = copy.deepcopy(h) # Deep copy เพื่อปรับแต่ง segment สำหรับ view นี้โดยเฉพาะ

            # ถ้ากล้องมองมาจากอีกด้านของปากรูหลัก (ทะลุ) ให้ดึงปากรูมาอยู่ฝั่งที่ใกล้กล้อง
            is_facing_away = d_a > d_b
            
            if not is_facing_away:
                open_depth, deep_depth, display_x, display_y = d_a, d_b, dx_a, dy_a
            else:
                # 1. สลับคุณสมบัติของรูหลักให้ปากรูมาอยู่ฝั่งมุมมองกล้อง
                open_depth, deep_depth, display_x, display_y = d_b, d_a, dx_b, dy_b
                hc.open_3d, hc.deep_3d = hc.deep_3d, hc.open_3d
                hc.radius_open, hc.radius_deep = hc.radius_deep, hc.radius_open
                
                # 2. แก้ไขจุดที่เป็นบั๊ก: สลับ Segment ย่อยทั้งหมดให้ตรงกับปากรูใหม่
                hc.segments.reverse() # สลับ Segment เดิมที่ลึกสุด ให้ขึ้นมาตื้นสุด
                for seg in hc.segments:
                    # สลับ open/deep ของแต่ละ Segment ให้สอดคล้องกับทิศทางใหม่
                    seg.open_3d, seg.deep_3d = seg.deep_3d, seg.open_3d
                    seg.radius_open, seg.radius_deep = seg.radius_deep, seg.radius_open

            actual_depth = deep_depth - open_depth

            def _make_rejected(reason: str):
                mid_3d = (np.array(hc.open_3d) + np.array(hc.deep_3d)) / 2.0
                try:
                    fx, fy, fdepth = projector.project_point_to_view(*mid_3d, view_name, screen_rot)
                    pos_ok = (math.isfinite(fx) and math.isfinite(fy) and math.isfinite(fdepth))
                except: pos_ok = False
                
                hr = copy.deepcopy(hc)
                hr.is_rejected, hr.reject_reason, hr.position_unknown = True, reason, not pos_ok
                if pos_ok:
                    hr.display_x, hr.display_y = fx, fy
                    hr.depth_top, hr.depth_bot = max(0.0, fdepth - hr.radius_open), fdepth
                    hr.depth = max(0.0, hr.depth_bot - hr.depth_top)
                else:
                    hr.display_x, hr.display_y, hr.depth_top, hr.depth_bot, hr.depth = None, None, 0.0, 0.0, 0.0
                return hr

            if actual_depth < MIN_DEPTH:
                axis_align = abs(float(np.dot(np.array(hc.axis), dir_to_viewer)))
                if mesh is not None and axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    best = self._sample_side_hole_breach(hc, dir_to_viewer, mesh, projector, view_name, screen_rot)
                    if best is not None:
                        fb_x, fb_y, fb_depth, fb_hit, perp_dist = best
                        hc.display_x, hc.display_y = fb_x, fb_y
                        hc.depth_top = max(0.0, fb_depth - max(hc.radius_open, hc.radius_deep))
                        hc.depth_bot = fb_depth
                        hc.depth = max(MIN_DEPTH, hc.depth_bot - hc.depth_top)
                        hc.is_rejected, hc.reject_reason, hc.position_unknown = False, "", False
                        result.append(hc)
                        continue

                if axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    continue

                result.append(_make_rejected("Too shallow / no breach found"))
                continue

            if mesh is not None:
                if mesh.ray.intersects_any(ray_origins=[np.array(hc.open_3d) + (dir_to_viewer * 0.1)], ray_directions=[dir_to_viewer])[0]:
                    result.append(_make_rejected("Occluded by mesh from this view"))
                    continue

            hc.display_x, hc.display_y = display_x, display_y
            hc.depth_top, hc.depth_bot = open_depth, deep_depth
            hc.depth = actual_depth
            hc.is_rejected, hc.reject_reason, hc.position_unknown = False, "", False
            result.append(hc)

        def _sort_key(hh):
            if hh.display_x is None or hh.display_y is None: return (1, 0, 0)
            return (0, -round(hh.display_y / 5.0), hh.display_x)

        result.sort(key=_sort_key)
        return result
