# core/path_planner.py
import numpy as np

class PathPlanner:
    """คำนวณ Path Planning สำหรับการสแกนความลึกรู (Probing)"""

    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str) -> list:
        """
        คืนค่า list ของ layer dict สำหรับวาด probe path

        โหมด Zigzag (hole.zigzag_inspection == True):
            แต่ละ layer หมุนสะสมจาก layer ก่อนหน้า ตามองศาที่กำหนดใน hole.zigzag_degree
            Layer 0 → offset = 0°
            Layer 1 → offset = 1 × degree
            Layer 2 → offset = 2 × degree
            Layer N → offset = N × degree
        """
        use_zigzag  = getattr(hole, 'zigzag_inspection', False)
        step_deg    = getattr(hole, 'zigzag_degree',     45.0)   # องศาต่อ layer

        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        layers = []
        for layer_idx, t in enumerate(t_vals):
            pt = o + t * (d - o)
            dx, dy, depth = projector.project_point_to_view(*pt, view_name)
            r_layer = hole.radius_at(t)

            if use_zigzag:
                # หมุนสะสม: layer N = N × step_deg
                angle_offset = np.radians(layer_idx * step_deg)
            else:
                angle_offset = 0.0

            layers.append({
                'z_display':    depth,
                'x_display':    dx,
                'y_display':    dy,
                'radius':       r_layer,
                'angle_offset': angle_offset,
                'layer_idx':    layer_idx,
            })
        return layers
