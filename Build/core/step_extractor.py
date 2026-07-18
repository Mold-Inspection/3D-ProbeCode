# core/step_extractor.py
# VERSION: 23
#
# CHANGE LOG (v22 -> v23):
#   BUG FIX: SPHERE hole's "open" end (rim/mouth) reported too deep into
#   the part (e.g. 20.36 mm depth reported vs. the true 30.00 mm).
#     Root cause: a trimmed spherical face's edge loop contains not only
#     the real rim boundary edge(s), but also, for periodic (>180° swept)
#     caps, an internal SEAM_CURVE — CadQuery/OCC's UV-periodicity seam
#     for the sphere's parametrization. Geometrically this seam is ALSO a
#     'CIRCLE' edge, but it's a full great circle that runs from the pole
#     straight out to the rim, with radius == the sphere's own radius R.
#     The old code sampled `for f_edge in face.Edges(): ...` with no
#     filter, so seam-edge points (whose perpendicular distance from the
#     axis ranges from 0 at the pole up to the rim radius) got mixed into
#     the same average used for BOTH radius_open and the axial height
#     used to build rim_center (open_3d). That pulled rim_center's height
#     toward the pole — i.e. deeper into the part — and dragged
#     radius_open down, below the true rim radius.
#     Verified directly against smooth_perfect_bowl_mold.step: the face's
#     edge loop is (#379, #380, #384); #379/#380 are the true rim at
#     r=67.082mm, #384 is explicitly a SEAM_CURVE at r=90mm (== sphere R).
#     With the seam excluded, R=90 and r_rim=67.082 give the analytically
#     exact depth R - sqrt(R^2 - r_rim^2) = 30.00 mm.
#     Fix: rim sampling now only accepts CIRCLE edges whose radius is
#     meaningfully smaller than the sphere's own radius R (radius < R -
#     tolerance). A genuine latitude/rim edge is always strictly smaller
#     than R (equal only in the degenerate case of an exact hemisphere,
#     which the old center-offset heuristic couldn't disambiguate either
#     — not a concern here). A seam/meridian edge, passing through the
#     sphere's own center, is always exactly radius R and is now skipped.
#     Falls back to the existing vertex-sampling path if zero qualifying
#     rim edges are found, same safety net as before.
#
# CHANGE LOG (v21 -> v22):
#   BUG FIX: Total hole depth read too shallow (e.g. 20.36 mm reported vs
#   30 mm true), with the "open" end of the hole appearing deeper into
#   the part than the real surface.
#     Root cause: `_merge_counterbores()` only ran a SINGLE pass over all
#     hole pairs. This correctly merges a simple 2-segment composite hole
#     (e.g. one counterbore + one main bore, or a straight cylindrical
#     shank sitting on a spherical ball-nose bottom), but for a CHAIN of
#     3+ coaxial segments (e.g. entrance chamfer -> cylindrical shank ->
#     spherical tip), a single pass only performs one merge: segment A
#     merges into B, but the newly-combined A+B was never re-checked
#     against C within that same call — C was silently left behind as
#     its own separate, too-shallow StepHole. Since the shallowest
#     surviving segment (e.g. the sphere-to-cylinder transition circle)
#     then gets reported as the hole's `open_3d`, the tool appeared to
#     start measuring from partway down the real hole instead of from
#     the true part surface, undercounting total depth by whatever the
#     un-merged segment's length was.
#     Fix: `_merge_counterbores()` now repeats full merge passes until
#     one pass completes with zero merges (fixed-point iteration),
#     instead of returning after exactly one pass. A simple 2-segment
#     hole still resolves on the first pass exactly as before; chains of
#     any length now fully collapse into a single continuous StepHole.
#
# CHANGE LOG (v20 -> v21):
#   BUG FIX: Spherical-cap hole marker drifted off the dome's true visual
#   center in the UI.
#     Root cause: the SPHERE branch's rim_center was computed as a plain
#     arithmetic mean of sampled 3D rim points. A cap's rim is almost
#     always a single CLOSED circular edge, and for a closed edge
#     positionAt(0.0) == positionAt(1.0) (same point). Our sample set
#     t=(0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0) therefore double-weighted
#     whichever point sits at that seam while every other angle around
#     the circle was sampled once — pulling the raw-position average
#     sideways toward the duplicated point instead of landing on the
#     true circle center.
#     Fix: rim_center is now rebuilt analytically ON the axis using only
#     the scalar axial projection average (h_avg = mean of proj_len,
#     rim_center = c0 + h_avg*axis_vec) instead of averaging raw 3D
#     positions. A duplicated sample shares the same axial value as its
#     twin, so it only reduces noise in a scalar average — it can no
#     longer bias direction. This mirrors how deep_3d (the pole) was
#     already built analytically rather than from a raw sample average.
#     radius_open's perpendicular-distance averaging was NOT affected by
#     this bug (a duplicated point has the same radius as its twin, so
#     magnitude was already unbiased) — only rim_center's position needed
#     the fix.
#
# CHANGE LOG (v19 -> v20):
#   FEATURE: SPHERE faces are now extracted as holes (spherical-cap
#   recesses/dimples), alongside CYLINDER, CONE, TORUS.
#     - A sphere has no inherent axis; axis is derived from the trimmed
#       face's centroid relative to the sphere center, which reliably
#       points toward the cap's pole.
#     - deep_3d is set analytically to the pole point (center + R*axis) —
#       always exactly on the sphere surface — with radius_deep = 0.0,
#       matching the existing CONE-tip convention.
#     - open_3d is the sampled rim centroid; radius_open is the rim's
#       perpendicular distance from the pole axis.
#     - Falls through to the existing circle-edge fallback on failure,
#       same safety net as CONE/TORUS.
#     - Added disabled-by-default _MIN_SPHERE_CAP_RADIUS hook to filter
#       spherical fillets, since these are far more common than cylinder/
#       torus fillets in typical STEP models.
#     - No downstream changes needed: StepHole/models.py/path_planner.py/
#       projector.py/geometry_engine.py/UI tabs already tolerate differing
#       open/deep radii (built for CONE, reused by TORUS, now SPHERE).
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

# v20: NOT applied by default — documented hook only, same pattern as
# _MIN_TORUS_TUBE_RADIUS. Small ball-corner fillets are frequently modeled
# as SPHERE faces; if they start appearing as false-positive "holes",
# uncomment the guard inside extract()'s SPHERE branch that checks
# `R < _MIN_SPHERE_CAP_RADIUS` and `continue`s past them.
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
            merged[j]  = True
            break
    result = [h for i, h in enumerate(holes) if not merged[i]]
    return result

def _merge_counterbores(holes: list) -> list:
    # v22 FIX: iterate to a fixed point instead of a single O(n^2) pass.
    # A single pass correctly merges a simple 2-segment hole (e.g. one
    # counterbore + one main bore, or one cylindrical shank + one
    # spherical ball-nose bottom), but a CHAIN of 3+ coaxial segments
    # (e.g. entrance chamfer -> straight cylindrical shank -> spherical
    # tip) was only getting ONE merge per pass: segment A merges into B,
    # but the resulting combined A+B was never re-checked against C in
    # the same call, silently leaving C as its own separate, too-shallow
    # StepHole. That's what produced hole depths shorter than the true
    # part depth, with the reported "open" end sitting deeper than the
    # real surface — it was actually the boundary between two segments
    # that never got stitched together. Repeating full passes until one
    # produces zero merges resolves chains of any length; a simple
    # 2-segment hole still merges in the first pass exactly as before.
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
                made_merge      = True
                break

        current = [h for i, h in enumerate(current) if not merged_out[i]]
        if not made_merge:
            break

    return current

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

            # v20: SPHERE added alongside CYLINDER/CONE/TORUS
            if geom_type not in ('CYLINDER', 'CONE', 'TORUS', 'SPHERE'):
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

            # v20: ANALYTICAL SPHERE EXTRACTION (spherical-cap holes)
            # A sphere has no inherent axis — every direction through its
            # center is equivalent. The axis we need only exists because
            # the FACE is a trimmed cap: the rim (boundary edges) defines
            # a circle whose center lies on the cap's symmetry axis.
            #   - axis_vec: sphere center -> face centroid, this reliably
            #     points toward the cap's far side (the pole).
            #   - deep_3d (pole) = center + radius * axis_vec — this is
            #     analytically exact (always lies ON the sphere), not a
            #     sampled approximation. radius_deep = 0.0, same
            #     "point at the tip" convention already used for CONE.
            #   - open_3d = centroid of sampled rim points (real sampled
            #     boundary, not derived).
            #   - radius_open = perpendicular distance of rim points from
            #     the pole axis line through the center.
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

                    # v23 FIX: a trimmed spherical face's edge loop can
                    # include an internal SEAM_CURVE (the UV-periodicity
                    # seam), not just the true rim boundary. Geometrically
                    # the seam is ALSO a 'CIRCLE' edge, but it's a great
                    # circle running from the pole out to the rim, with
                    # radius exactly equal to the sphere's own radius R —
                    # a genuine latitude/rim edge is always strictly
                    # smaller than R. Sampling the seam alongside the real
                    # rim silently pulled both radius_open and the axial
                    # height of open_3d toward the pole (too deep).
                    # Filter: only accept CIRCLE edges with radius clearly
                    # < R as rim candidates; skip the seam.
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

                    # Sample the true rim (boundary) edges only.
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

                    # Axis direction: prefer the face's own centroid (biased
                    # toward the cap's far side incl. the pole) over the rim
                    # centroid, since a shallow cap's rim centroid sits close
                    # to the equatorial plane and is a noisier axis estimate.
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

                    # Analytical pole = deepest point of the cap, always on
                    # the sphere surface exactly.
                    pole_pt = c0 + R * axis_vec

                    # v21 FIX: rim_center is now rebuilt analytically ON the
                    # axis, instead of averaging raw sampled 3D positions.
                    # A spherical-cap rim is (almost always) ONE closed
                    # circular edge, and for a closed edge positionAt(0.0)
                    # and positionAt(1.0) are the SAME point — our sample
                    # set (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0) therefore
                    # double-weights whichever point sits at that seam,
                    # while the rest of the circle is sampled once each.
                    # Averaging raw positions directly (old code) pulled
                    # the centroid sideways toward that duplicated point —
                    # this is what caused the hole marker to drift off the
                    # dome's true visual center. A scalar axial average is
                    # immune to this: every rim point shares (almost) the
                    # same projection onto axis_vec regardless of angular
                    # sampling density, so duplicates only reduce noise,
                    # never bias direction. Rebuilding the point from
                    # c0 + h_avg*axis_vec guarantees it lands exactly on
                    # the symmetry axis, mirroring how deep_3d (the pole)
                    # is already built analytically rather than sampled.
                    rim_arr    = np.array(rim_pts)
                    rel        = rim_arr - c0
                    proj_len   = rel @ axis_vec
                    perp_vecs  = rel - np.outer(proj_len, axis_vec)

                    h_avg      = float(np.mean(proj_len))
                    rim_center = c0 + h_avg * axis_vec

                    # radius_open = perpendicular distance of rim points
                    # from the pole axis line through the sphere center.
                    # (unaffected by the seam-duplicate issue above — a
                    # duplicated point has the same radius as its twin,
                    # so it doesn't bias the magnitude, only direction.)
                    r_open     = float(np.mean(np.linalg.norm(perp_vecs, axis=1)))
                    r_deep     = 0.0  # pole is a single point, same as CONE tip

                    end_a      = tuple(rim_center)
                    end_b      = tuple(pole_pt)
                    r_a, r_b   = r_open, r_deep
                    face_depth = float(np.linalg.norm(pole_pt - rim_center))

                    # Optional fillet guard (disabled by default — small
                    # ball-corner fillets are very commonly modeled as
                    # SPHERE faces and are NOT real holes). Enable if
                    # fillets start showing up as false-positive "holes":
                    # if R < _MIN_SPHERE_CAP_RADIUS:
                    #     raise ValueError(f"Sphere radius {R:.2f} looks like a fillet, skipping")

                    analytical_success = True
                    _dbg(f"SPHERE ANALYTICAL SUCCESS face#{total_faces}: "
                         f"depth={face_depth:.2f} R={R:.2f} r_open={r_a:.2f}")
                except Exception as e:
                    _dbg(f"Sphere analytical extraction failed face#{total_faces}: {e!r}")

            # FALLBACK: ถ้าดึงสมการพลาด (หรือเป็น CONE, หรือ TORUS/SPHERE ที่ดึงสมการไม่สำเร็จ)
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
