# core/step_extractor.py
# VERSION: 19
#
# CHANGE LOG (v18 -> v19):
#   FEATURE: TORUS faces are now extracted as holes, alongside CYLINDER
#   and CONE.
#     - geom_type filter now accepts 'CYLINDER', 'CONE', 'TORUS'.
#     - New analytical branch for TORUS (mirrors the CYLINDER branch):
#       pulls gp_Torus from BRepAdaptor_Surface (MajorRadius/MinorRadius/
#       Axis), then samples the face's edges/vertices and, for EACH
#       sample point, computes both its axial coordinate (projection onto
#       the main axis) and its LOCAL radius (perpendicular distance from
#       the axis). This matters because — unlike a cylinder — a torus
#       does NOT have a constant radius along its axis: at the "equator"
#       of the tube the local radius is (R + r), at the innermost point
#       it's (R - r). Using per-sample local radius instead of one shared
#       radius keeps radius_open / radius_deep faithful to the actual
#       surface instead of distorting a cone-like taper onto a torus.
#     - The two axial extremes (min/max projected sample) become
#       end_a/end_b exactly as in the CYLINDER branch, each keeping its
#       own local radius as r_a/r_b. This flows into the existing
#       StepHole(open_3d, deep_3d, radius_open, radius_deep, axis)
#       constructor unchanged — no changes needed elsewhere (models.py,
#       _merge_half_faces, _merge_counterbores, get_step_holes_in_view,
#       view filtering) since they already tolerate differing
#       open/deep radii (this path was built for CONE).
#     - If the analytical gp_Torus path fails for any reason, execution
#       falls through to the existing generic circle-edge fallback
#       (unchanged) — same safety net CONE already relies on.
#   NOTE: no fillet-vs-real-hole filtering was added — a small-tube-radius
#   TORUS face (typical of a rounded hole mouth) is currently counted the
#   same as a real toroidal groove/bore. _MIN_TORUS_TUBE_RADIUS is left
#   as a documented, unused-by-default hook below in case fillets start
#   showing up as false-positive "holes" in testing.
#
# CHANGE LOG (v17 -> v18):
#   Dead-code cleanup only, no behavior change:
#     1. Removed unused constant _DEPTH_TOL (never referenced — the actual
#        depth-reject check hardcodes 0.1).
#     2. Removed write-only rejection counters (rejected_geomtype,
#        rejected_edges, rejected_sweep, rejected_dist, rejected_depth,
#        rejected_dup, rejected_other) — incremented throughout extract()
#        but never read, printed, or returned anywhere. total_faces is
#        KEPT since it's used inside a _dbg() debug message.
#     3. Removed pre_merge_count / post_half_face_count in extract() —
#        computed, never used afterward.
#     4. Removed the `h._id = i + 1` assignment at the end of
#        get_step_holes_in_view() — nothing in core/* or ui/* reads
#        StepHole._id; the UI layer uses HoleFeature.id/.display_id
#        instead, assigned separately in main_window.show_view().
#
# CHANGE LOG (v16 -> v17):
#   1. BUG FIX: Removed the flawed `_geomAdaptor()` branch entirely. Now strictly 
#      enforcing `BRepAdaptor_Surface` which correctly wraps trimmed B-Rep faces 
#      and exposes the `.Cylinder()` mathematical equations.
#   2. ENHANCEMENT: Increased the Cross-Hole Bridge gap tolerance to 50.0mm specifically 
#      for fragmented coaxial holes with identical radii to survive large perpendicular pin bores.
#   3. UX FILTER: Added view-based filtering in `get_step_holes_in_view()`. 
#      Irrelevant side-holes and holes facing away from the camera are now dropped completely 
#      instead of cluttering the "Unselected" UI list.

import numpy as np
import math
import copy
import os
import datetime
import cadquery as cq
from core.models import StepHole

DEBUG = True

# ---------------------------------------------------------------------------
# file logging setup
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

_MIN_SWEEP_RAD = math.pi
_AXIS_TOL       = 0.02
_EXTENT_TOL     = 0.5
_PERP_FRAC_TOL  = 0.15

_STRICT_GAP_TOL    = 0.05  
_MAX_RADIUS_RATIO  = 1.2   

_COAXIAL_PERP_TOL   = 0.3   
_COAXIAL_PERP_FRAC  = 0.15  
_COAXIAL_GAP_TOL    = 1.5   

# v19: NOT applied by default — documented hook only. If small-fillet
# TORUS faces start appearing as false-positive "holes", uncomment the
# guard inside extract()'s TORUS branch that checks
# `r_minor < _MIN_TORUS_TUBE_RADIUS` and `continue`s past them.
_MIN_TORUS_TUBE_RADIUS = 2.0

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
            merged[j]  = True
            break
    result = [h for i, h in enumerate(holes) if not merged[i]]
    return result

def _merge_counterbores(holes: list) -> list:
    if not holes: return holes
    merged_out = [False] * len(holes)
    for i in range(len(holes)):
        if merged_out[i]: continue
        for j in range(len(holes)):
            if i == j or merged_out[j]: continue
            hi, hj = holes[i], holes[j]
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
            
            # V17 CROSS-HOLE BRIDGE: ถ้ารูร่วมแกนและรัศมีเท่ากัน ให้ขยายระยะสะพานเชื่อมเป็น 50mm
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

            hi.open_3d     = tuple(shallow_pt)
            hi.deep_3d     = tuple(deep_pt)
            hi.radius_open = float(shallow_r)
            hi.radius_deep = float(deep_r)
            hi.radius      = float(shallow_r)
            hi.depth       = new_depth
            merged_out[j]  = True
            break
    result = [h for i, h in enumerate(holes) if not merged_out[i]]
    return result

class StepExtractor:
    def __init__(self):
        self._step_holes_cache = []

    def extract(self, step_data, mesh_centroid):
        if step_data is None: return []

        cx_off, cy_off, cz_off = mesh_centroid
        holes = []
        seen  = {}

        total_faces       = 0

        for face in step_data.faces().vals():
            total_faces += 1
            geom_type = face.geomType()

            # v19: TORUS added alongside CYLINDER/CONE
            if geom_type not in ('CYLINDER', 'CONE', 'TORUS'):
                continue

            analytical_success = False

            # V17: PURE ANALYTICAL SURFACE EXTRACTION (ดึงสมการจากคณิตศาสตร์ B-Rep)
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
                    # 1. ลองฉายแสง (Project) ขอบที่หลงเหลืออยู่ลงบนแกนรู
                    for f_edge in face.Edges():
                        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                            try:
                                pt = f_edge.positionAt(t)
                                vec = np.array([pt.x - cx_off, pt.y - cy_off, pt.z - cz_off]) - c0
                                projs.append(float(np.dot(vec, axis_vec)))
                            except: pass

                    # 2. ถ้าขอบถูกทำลายเละหมด ให้ดึงจากจุดตัด (Vertices) แทน
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

            # v19: ANALYTICAL TORUS EXTRACTION
            # A torus does NOT have a constant radius along its axis like a
            # cylinder does, so we cannot reuse a single r_a=r_b value. For
            # every sampled point on the face we compute BOTH its axial
            # position (projection onto the main axis) and its own local
            # radius (perpendicular distance from the axis). The two axial
            # extremes become end_a/end_b, each carrying its own local
            # radius as r_a/r_b — this then flows into the same
            # StepHole(open, deep, radius_open, radius_deep, axis)
            # constructor already used for CONE, so no downstream code
            # (merging, view filtering, UI) needs to change.
            elif geom_type == 'TORUS':
                try:
                    try:
                        from OCP.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)
                    except ImportError:
                        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
                        adaptor = BRepAdaptor_Surface(face.wrapped)

                    tor = adaptor.Torus()
                    ax1 = tor.Axis()          # main revolution axis of the torus
                    loc = ax1.Location()
                    d   = ax1.Direction()

                    c0 = np.array([loc.X() - cx_off, loc.Y() - cy_off, loc.Z() - cz_off])
                    axis_vec = np.array([d.X(), d.Y(), d.Z()])
                    ax_norm = np.linalg.norm(axis_vec)
                    if ax_norm < 1e-6: raise ValueError("Degenerate torus axis")
                    axis_vec = axis_vec / ax_norm

                    R_major = float(tor.MajorRadius())
                    r_minor = float(tor.MinorRadius())

                    # Optional fillet guard (disabled by default — see
                    # _MIN_TORUS_TUBE_RADIUS docstring above):
                    # if r_minor < _MIN_TORUS_TUBE_RADIUS:
                    #     raise ValueError(f"Tube radius {r_minor:.2f} looks like a fillet, skipping")

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

            # FALLBACK: ถ้าดึงสมการพลาด (หรือเป็น CONE, หรือ TORUS ที่ดึงสมการไม่สำเร็จ)
            # จะกลับมาใช้วิธีหาเส้นวงกลม (Edge) — เหมือนเดิม ไม่แก้
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

                # V17 UI FILTER: กรองรูเจาะด้านข้าง (Side-holes) ทิ้ง ไม่แสดงในลิสต์ Unselected
                if axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    _dbg(f"  cache[{cache_idx}] DROPPED: irrelevant side-hole for this view.")
                    continue
                
                # V17 UI FILTER: กรองรูที่เจาะจากอีกฝั่ง (Facing away) ทิ้ง ไม่แสดงในลิสต์
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