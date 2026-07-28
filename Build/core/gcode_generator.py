# core/gcode_generator.py
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FIX: _raw_layers_for_hole() multi-segment branch now SKIPS any
#   segment whose cfg.selected_for_inspection is False — same rule as
#   core/path_planner.py get_probe_path_layers_multi() (see
#   core/models.py validate_segment_reachability()), so a segment
#   deemed unreachable (counterbore neck too narrow above it) never
#   gets probed by the actual machine either. A comment line is emitted
#   per hole listing which segment(s) were excluded, for traceability
#   in the exported .gcode file itself.
#
# CHANGE LOG (v01 -> v02):
#   FIX: Per-point probing pattern now returns FULLY to the layer center
#   after every point (center -> probe touch -> pull-off -> RAPID BACK
#   TO CENTER -> next point), instead of the old pattern where the tool
#   only pulled off by `backoff` mm and then jumped diagonally, near the
#   wall, straight to the next point's probe target. Matches the
#   requested machine motion pattern exactly and removes the near-wall
#   diagonal travel risk. Layer visiting order (top -> bottom, i.e.
#   open_3d -> deep_3d) was already correct — no change there.
#   REFACTOR: Nearest-neighbor visit ordering (was local
#   _order_holes_nearest_neighbor) and the STEP-ready/skip split moved
#   to new shared module core/hole_ordering.py, so
#   ui/tabs/path_mapper_tab.py can compute the IDENTICAL travel order
#   for its preview — one source of truth for "which order do we visit
#   holes in", instead of two independent implementations.
#
# CHANGE LOG (v01):
#   FEATURE: Phase 2 — G-code Export (GRBL dialect). New file. Builds a
#   real, downloadable probe program from the currently
#   selected_for_inspection holes.
#
#     KEY DESIGN POINT: this file deliberately does NOT reuse
#     path_planner.py's get_probe_path_layers()/..._multi(). Those
#     functions run every point through projector.project_point_to_view()
#     — correct for drawing the on-screen preview in whatever view/
#     rotation the user happens to be looking at, but NOT the coordinate
#     frame a real machine understands. _raw_layers_for_hole() below
#     mirrors the same t-parameterization/segment-walk logic but works
#     entirely in raw CAD-space 3D (StepHole.open_3d/deep_3d/segments —
#     the same mesh-centroid-centered frame cad_loader.py already
#     produces), and derives its own perpendicular (u, v) basis from each
#     segment's own axis so points are placed correctly in true 3D even
#     for a hole axis that isn't aligned to any single world axis.
#
#     ASSUMPTIONS (documented, not yet configurable):
#       - Work offset: NOT applied. Output assumes mesh centroid =
#         machine zero (G54 origin) — explicit scoping decision, revisit
#         after real-machine testing.
#       - Hole axis is assumed close enough to the probe's straight-line
#         G38.2 approach capability (GRBL 3-axis linear probe move) —
#         no 5-axis/tool-orientation logic here.
#       - Visit order: greedy nearest-neighbor over raw XY (open_3d),
#         starting from whichever selected hole is closest to (0,0).
#       - Only holes with STEP geometry (h._step_hole is not None) can
#         be exported; mesh-only holes are skipped and reported back to
#         the caller so the UI can warn the user.
#       - Segment-level: any segment marked selected_for_inspection=False
#         (auto or manual, see core/models.py) is excluded from export.
#
#     Per-hole G-code pattern:
#       G0 Z[SafeZ]                      ; retract before travel
#       G0 X.. Y..                       ; travel over next hole (safe Z)
#       G0 X.. Y.. Z..                   ; plunge to entry point (open_3d
#                                           + entry_clearance along axis)
#       --- per layer (top -> bottom, selected segments only) ---
#         G0 X.. Y.. Z..                 ; move to layer center
#         --- per point (angle + zigzag offset) ---
#           G38.2 X.. Y.. Z.. F[feed]    ; probe outward to radius+overtravel
#           G91 / G0 (relative pull-off) / G90
#           G0 X.. Y.. Z..               ; rapid back to layer center
#     Full Safe-Z retract is only ever emitted between holes (start of
#     each hole's block) and once at program end — matching the user's
#     explicit "safety distance when hole changes" requirement.
import numpy as np

from core.hole_ordering import order_holes_nearest_neighbor, split_step_ready


class GCodeSettings:
    """Plain settings container consumed by generate_gcode()."""
    def __init__(self, safe_z: float, entry_clearance: float = 2.0,
                 probe_feedrate: float = 100.0, overtravel: float = 0.8,
                 backoff: float = 1.2):
        self.safe_z          = float(safe_z)
        self.entry_clearance = float(entry_clearance)
        self.probe_feedrate  = float(probe_feedrate)
        self.overtravel      = float(overtravel)
        self.backoff          = float(backoff)


def suggest_safe_z(mesh, margin: float = 10.0) -> float:
    """Default Safe Z suggestion: part's highest raw Z (mesh already
    centered by cad_loader.py) plus a clearance margin."""
    return float(mesh.bounds[1][2]) + margin


# ---------------------------------------------------------------------
def _orthonormal_basis(axis_vec):
    """Return (unit_axis, u, v) — u and v span the plane perpendicular
    to axis_vec, used to place probe points radially in true 3D
    regardless of which way the hole's real axis points."""
    axis = np.array(axis_vec, dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        axis = np.array([0.0, 0.0, 1.0])
    else:
        axis = axis / norm
    arbitrary = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, arbitrary)
    u_norm = np.linalg.norm(u)
    u = u / u_norm if u_norm > 1e-9 else np.array([1.0, 0.0, 0.0])
    v = np.cross(axis, u)
    return axis, u, v


def _raw_layers_for_hole(hole_feature):
    """
    Raw-3D (non-projected) layer/point plan for one hole.
    Sorts layers to guarantee Top-to-Bottom traversal (closest to mouth first).
    Segments with selected_for_inspection == False are skipped entirely.
    """
    sh = hole_feature._step_hole
    is_multi = bool(getattr(hole_feature, 'segments', None))
    layers = []

    if is_multi:
        for seg_idx, (seg, cfg) in enumerate(zip(sh.segments, hole_feature.segments)):
            if not getattr(cfg, 'selected_for_inspection', True):
                continue   # segment ถูกเลือกออก (unreachable/manual uncheck)

            axis, u, v = _orthonormal_basis(np.array(seg.deep_3d) - np.array(seg.open_3d))
            o = np.array(seg.open_3d)
            d = np.array(seg.deep_3d)
            t_vals = np.linspace(0.0, 1.0, cfg.layers + 2)[1:-1]
            for local_idx, t in enumerate(t_vals):
                center = o + t * (d - o)
                r      = seg.radius_at(t)
                offset = (np.radians(local_idx * cfg.zigzag_degree)
                         if cfg.zigzag_inspection else 0.0)
                layers.append(dict(
                    seg_idx=seg_idx, center=center, radius=r,
                    axis=axis, u=u, v=v, angle_offset=offset,
                    points_n=cfg.points_per_layer))
    else:
        axis, u, v = _orthonormal_basis(np.array(sh.deep_3d) - np.array(sh.open_3d))
        o = np.array(sh.open_3d)
        d = np.array(sh.deep_3d)
        n_layers = hole_feature.layers
        use_zz   = getattr(hole_feature, 'zigzag_inspection', False)
        deg      = getattr(hole_feature, 'zigzag_degree', 45.0)
        t_vals   = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        for idx, t in enumerate(t_vals):
            center = o + t * (d - o)
            r      = sh.radius_at(t)
            offset = np.radians(idx * deg) if use_zz else 0.0
            layers.append(dict(
                seg_idx=0, center=center, radius=r,
                axis=axis, u=u, v=v, angle_offset=offset,
                points_n=hole_feature.points_per_layer))

    # [FIX] การันตีลำดับชั้นจาก "บนลงล่าง" (Top to Bottom) เสมอ 
    # โดยอิงระยะห่างจากตำแหน่งปากรูบนสุด (sh.open_3d) ของชิ้นงาน
    top_pt = np.array(sh.open_3d)
    layers.sort(key=lambda lyr: float(np.linalg.norm(lyr['center'] - top_pt)))

    # [FIX] รันหมายเลข layer_idx ใหม่ให้คอมเมนต์ใน G-code เรียงต่อเนื่องสวยงามตามการวิ่งจริง
    for i, lyr in enumerate(layers):
        lyr['layer_idx'] = i

    return layers

# ---------------------------------------------------------------------
def _raw_layers_for_hole(hole_feature):
    """
    Raw-3D (non-projected) layer/point plan for one hole.
    Sorts layers to guarantee Top-to-Bottom traversal (closest to mouth first).
    Segments with selected_for_inspection == False are skipped entirely.
    """
    sh = hole_feature._step_hole
    is_multi = bool(getattr(hole_feature, 'segments', None))
    layers = []

    if is_multi:
        for seg_idx, (seg, cfg) in enumerate(zip(sh.segments, hole_feature.segments)):
            if not getattr(cfg, 'selected_for_inspection', True):
                continue   # segment ถูกเลือกออก (unreachable/manual uncheck)

            axis, u, v = _orthonormal_basis(np.array(seg.deep_3d) - np.array(seg.open_3d))
            o = np.array(seg.open_3d)
            d = np.array(seg.deep_3d)
            t_vals = np.linspace(0.0, 1.0, cfg.layers + 2)[1:-1]
            for local_idx, t in enumerate(t_vals):
                center = o + t * (d - o)
                r      = seg.radius_at(t)
                offset = (np.radians(local_idx * cfg.zigzag_degree)
                         if cfg.zigzag_inspection else 0.0)
                layers.append(dict(
                    seg_idx=seg_idx, center=center, radius=r,
                    axis=axis, u=u, v=v, angle_offset=offset,
                    points_n=cfg.points_per_layer))
    else:
        axis, u, v = _orthonormal_basis(np.array(sh.deep_3d) - np.array(sh.open_3d))
        o = np.array(sh.open_3d)
        d = np.array(sh.deep_3d)
        n_layers = hole_feature.layers
        use_zz   = getattr(hole_feature, 'zigzag_inspection', False)
        deg      = getattr(hole_feature, 'zigzag_degree', 45.0)
        t_vals   = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        for idx, t in enumerate(t_vals):
            center = o + t * (d - o)
            r      = sh.radius_at(t)
            offset = np.radians(idx * deg) if use_zz else 0.0
            layers.append(dict(
                seg_idx=0, center=center, radius=r,
                axis=axis, u=u, v=v, angle_offset=offset,
                points_n=hole_feature.points_per_layer))

    # จัดเรียงลำดับชั้นจาก "บนลงล่าง" (Top to Bottom) เสมอ โดยอิงระยะห่างจากปากรู
    top_pt = np.array(sh.open_3d)
    layers.sort(key=lambda lyr: float(np.linalg.norm(lyr['center'] - top_pt)))

    # รันหมายเลข layer_idx ใหม่ให้เรียงต่อเนื่องตามระยะจริง
    for i, lyr in enumerate(layers):
        lyr['layer_idx'] = i

    return layers


# ---------------------------------------------------------------------
def generate_gcode(holes, probe_profile, settings: GCodeSettings):
    """
    Build a GRBL probe program from `holes` (HoleFeature list, already
    filtered to selected_for_inspection by the caller).

    Returns (gcode_text: str, skipped: list, point_map: list)
    `point_map` holds metadata for every single G38.2 probe touch for post-processing.
    """
    valid, skipped = split_step_ready(holes)
    ordered = order_holes_nearest_neighbor(valid)

    lines = []
    point_map = []  # ตัวแปรสำหรับจัดเก็บลำดับการโพรบ

    lines.append("; ============================================")
    lines.append("; 3D ProbeCode - GRBL Probe Program (Phase 2)")
    lines.append(f"; Holes: {len(ordered)}  Safe Z: {settings.safe_z:.2f} mm  "
                 f"Probe Feed: {settings.probe_feedrate:.0f} mm/min")
    lines.append("; NOTE: work zero = mesh centroid (no G54 offset applied)")
    lines.append("; NOTE: assumes hole axis suits a straight-line G38.2 approach")
    lines.append("; NOTE: per-point motion = center -> probe touch -> pull-off -> return to center")
    if skipped:
        names = ", ".join(str(getattr(h, 'display_id', '?')) for h in skipped)
        lines.append(f"; WARNING: {len(skipped)} hole(s) skipped (no STEP geometry): {names}")
    lines.append("; ============================================")
    lines.append("G21 ; mm units")
    lines.append("G90 ; absolute positioning")
    lines.append("G94 ; feed rate mode: units/min")
    lines.append(f"G0 Z{settings.safe_z:.3f}")
    lines.append("")

    for hi, hole in enumerate(ordered):
        sh = hole._step_hole
        axis, _, _ = _orthonormal_basis(np.array(sh.deep_3d) - np.array(sh.open_3d))
        entry_pt = np.array(sh.open_3d) + settings.entry_clearance * axis

        lines.append(f"; --- Hole {getattr(hole, 'display_id', '?')} ({hi + 1}/{len(ordered)}) ---")

        excluded_segs = [i + 1 for i, cfg in enumerate(getattr(hole, 'segments', []))
                          if not getattr(cfg, 'selected_for_inspection', True)]
        if excluded_segs:
            lines.append(f"; NOTE: segment(s) {excluded_segs} excluded (unreachable — see UI warning)")

        lines.append(f"G0 Z{settings.safe_z:.3f}")
        lines.append(f"G0 X{sh.open_3d[0]:.3f} Y{sh.open_3d[1]:.3f}")
        lines.append(f"G0 X{entry_pt[0]:.3f} Y{entry_pt[1]:.3f} Z{entry_pt[2]:.3f}")

        for lyr in _raw_layers_for_hole(hole):
            c, r          = lyr['center'], lyr['radius']
            u, v          = lyr['u'], lyr['v']
            offset, n     = lyr['angle_offset'], lyr['points_n']
            seg_tag       = f" seg {lyr['seg_idx'] + 1}" if 'seg_idx' in lyr else ""

            lines.append(f"G0 X{c[0]:.3f} Y{c[1]:.3f} Z{c[2]:.3f} "
                         f"; layer {lyr['layer_idx'] + 1}{seg_tag} — center")

            angles = np.linspace(0, 2 * np.pi, n, endpoint=False) + offset
            for pt_i, a in enumerate(angles):
                radial = np.cos(a) * u + np.sin(a) * v
                target = c + (r + settings.overtravel) * radial
                back   = -radial * settings.backoff

                lines.append(f"G38.2 X{target[0]:.3f} Y{target[1]:.3f} "
                             f"Z{target[2]:.3f} F{settings.probe_feedrate:.0f} "
                             f"; point {pt_i + 1}/{n} — touch")
                
                # บันทึกข้อมูลของจุดนี้ลงใน List
                point_map.append({
                    "hole_id": getattr(hole, 'display_id', '?'),
                    "layer_idx": lyr['layer_idx'] + 1,
                    "point_idx": pt_i + 1,
                    "expected_x": round(target[0], 3),
                    "expected_y": round(target[1], 3),
                    "expected_z": round(target[2], 3)
                })

                lines.append("G91")
                lines.append(f"G0 X{back[0]:.3f} Y{back[1]:.3f} Z{back[2]:.3f} ; pull-off from wall")
                lines.append("G90")
                lines.append(f"G0 X{c[0]:.3f} Y{c[1]:.3f} Z{c[2]:.3f} ; return to center")
        lines.append("")

    lines.append(f"G0 Z{settings.safe_z:.3f}")
    lines.append("M30 ; program end")

    return "\n".join(lines), skipped, point_map