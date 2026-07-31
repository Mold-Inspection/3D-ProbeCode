# core/gcode_generator.py
# VERSION: 04
import numpy as np
import copy  # ต้อง import copy เพื่อใช้ในการจำลองพิกัด

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
        self.backoff         = float(backoff)

def suggest_safe_z(mesh, margin: float = 10.0, view_name: str = "Top") -> float:
    """
    เสนอค่า Safe Z โดยคำนวณจากจุดที่สูงที่สุดของ Bounding Box 
    หลังจากจำลองการพลิกชิ้นงาน (Transform) ตามมุมมองปัจจุบันแล้ว
    """
    b_min, b_max = mesh.bounds
    
    # สร้างพิกัดมุมทั้ง 8 ของกล่อง Bounding Box 
    corners = [
        np.array([x, y, z])
        for x in (b_min[0], b_max[0])
        for y in (b_min[1], b_max[1])
        for z in (b_min[2], b_max[2])
    ]
    
    # จับมุมทั้ง 8 มาหมุนตาม View ที่กำลังเลือกอยู่
    transformed_corners = [apply_view_transform(c, view_name) for c in corners]
    
    # หาค่า Z ที่สูงที่สุดจากด้านที่ถูกหงายขึ้นมา
    max_z = max(c[2] for c in transformed_corners)
    
    return float(max_z) + margin

# ---------------------------------------------------------------------
# ระบบแปลงพิกัด 3D เพื่อจำลองการ "พลิกชิ้นงาน" ตามมุมมอง
# ---------------------------------------------------------------------
def apply_view_transform(pt, view_name):
    """แปลงพิกัด 3D เพื่อตั้งชิ้นงานให้ด้านที่ต้องการหงายขึ้นด้านบน (เข้าหาโพรบ Z+)"""
    x, y, z = pt
    view = str(view_name).lower()
    if view == "bottom":
        # พลิกชิ้นงาน 180 องศา รอบแกน X (สลับบน-ล่าง)
        return np.array([x, -y, -z], dtype=float)
    elif view == "front":
        # พลิก 90 องศา เอาด้านหน้าหงายขึ้น
        return np.array([x, z, -y], dtype=float)
    elif view == "back":
        return np.array([-x, z, y], dtype=float)
    elif view == "left":
        return np.array([-z, y, x], dtype=float)
    elif view == "right":
        return np.array([z, y, -x], dtype=float)
    
    # Default: Top (ไม่มีการหมุน)
    return np.array([x, y, z], dtype=float)

def transform_hole_feature_for_machining(hf_orig, view_name):
    """Deep copy รูและแปลงพิกัดทั้งหมดตามมุมมองปัจจุบัน ก่อนส่งไปเขียน G-code"""
    hf = copy.deepcopy(hf_orig)
    if hf._step_hole:
        sh = hf._step_hole
        sh.open_3d = apply_view_transform(sh.open_3d, view_name)
        sh.deep_3d = apply_view_transform(sh.deep_3d, view_name)
        sh.axis    = apply_view_transform(sh.axis, view_name) 
        for seg in getattr(sh, 'segments', []):
            seg.open_3d = apply_view_transform(seg.open_3d, view_name)
            seg.deep_3d = apply_view_transform(seg.deep_3d, view_name)
            
    return hf

# ---------------------------------------------------------------------
def _orthonormal_basis(axis_vec):
    """Return (unit_axis, u, v)"""
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
    sh = hole_feature._step_hole
    is_multi = bool(getattr(hole_feature, 'segments', None))
    layers = []

    if is_multi:
        for seg_idx, (seg, cfg) in enumerate(zip(sh.segments, hole_feature.segments)):
            if not getattr(cfg, 'selected_for_inspection', True):
                continue   

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

    # จัดเรียงลำดับชั้นจาก "บนลงล่าง" (Top to Bottom) เสมอ
    top_pt = np.array(sh.open_3d)
    layers.sort(key=lambda lyr: float(np.linalg.norm(lyr['center'] - top_pt)))

    for i, lyr in enumerate(layers):
        lyr['layer_idx'] = i

    return layers

# ---------------------------------------------------------------------
# เพิ่มอาร์กิวเมนต์ view_name เข้ามาในฟังก์ชันหลัก
def generate_gcode(holes, probe_profile, settings: GCodeSettings, view_name: str = "Top"):
    """
    Build a GRBL probe program from `holes`.
    """
    # 1. จำลองการพลิกชิ้นงานก่อนทำงานเสมอ
    transformed_holes = [transform_hole_feature_for_machining(h, view_name) for h in holes]
    
    valid, skipped = split_step_ready(transformed_holes)
    ordered = order_holes_nearest_neighbor(valid)

    lines = []
    point_map = [] 

    lines.append("; ============================================")
    lines.append(f"; 3D ProbeCode - GRBL Probe Program (View: {view_name})")
    lines.append(f"; Holes: {len(ordered)}  Safe Z: {settings.safe_z:.2f} mm  "
                 f"Probe Feed: {settings.probe_feedrate:.0f} mm/min")
    lines.append("; NOTE: work zero = mesh centroid (no G54 offset applied)")
    if str(view_name).lower() != "top":
        lines.append(f"; NOTE: Coordinate system transformed for {view_name} view machining")
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
        # axis ชี้จากปากรู (open) เข้าไปสู่ก้นรู (deep) -> เป็นเวกเตอร์พุ่งเข้าด้านใน
        axis, _, _ = _orthonormal_basis(np.array(sh.deep_3d) - np.array(sh.open_3d))
        
        # [FIX] เปลี่ยนเป็นลบ (-) เพื่อถอย entry_pt ออกมาจากปากรูสู่อากาศ (Clearance) ไม่ใช่จมลงไปในรู
        entry_pt = np.array(sh.open_3d) - settings.entry_clearance * axis

        lines.append(f"; --- Hole {getattr(hole, 'display_id', '?')} ({hi + 1}/{len(ordered)}) ---")

        excluded_segs = [i + 1 for i, cfg in enumerate(getattr(hole, 'segments', []))
                          if not getattr(cfg, 'selected_for_inspection', True)]
        if excluded_segs:
            lines.append(f"; NOTE: segment(s) {excluded_segs} excluded (unreachable)")

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