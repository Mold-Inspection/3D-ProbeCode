# core/path_planner.py
import numpy as np

class PathPlanner:
    """คำนวณ Path Planning สำหรับการสแกนความลึกรู (Probing)"""

    # มุมหมุน zigzag ระหว่างชั้นคู่/คี่ (องศา)
    ZIGZAG_ANGLE_DEG = 45.0

    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str) -> list:
        """
        คืนค่า list ของ layer dict สำหรับวาด probe path

        โหมด Zigzag (hole.zigzag_inspection == True):
            Layer คู่  (0, 2, 4, …) → angle_offset = 0°   (ตำแหน่งจุดปกติ)
            Layer คี่  (1, 3, 5, …) → angle_offset = 45°  (หมุน 45° รอบแกน Z)
            รัศมีและความลึก Z เหมือนเดิมทุกชั้น — แค่จุดบนวงกลมเลื่อนมุม
        """
        use_zigzag = getattr(hole, 'zigzag_inspection', False)
        zigzag_offset_rad = np.radians(self.ZIGZAG_ANGLE_DEG)

        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        layers = []
        for layer_idx, t in enumerate(t_vals):
            pt = o + t * (d - o)
            dx, dy, depth = projector.project_point_to_view(*pt, view_name)
            r_layer = hole.radius_at(t)

            if use_zigzag and (layer_idx % 2 == 1):
                angle_offset = zigzag_offset_rad   # ชั้นคี่ → หมุน 45°
                zigzag_phase = 'rotated'
            else:
                angle_offset = 0.0                 # ชั้นคู่ / โหมดปกติ → 0°
                zigzag_phase = 'normal' if not use_zigzag else 'base'

            layers.append({
                'z_display':    depth,
                'x_display':    dx,
                'y_display':    dy,
                'radius':       r_layer,
                'angle_offset': angle_offset,   # ← ใหม่: customization_tab ใช้ค่านี้
                'zigzag_phase': zigzag_phase,
            })
        return layers
