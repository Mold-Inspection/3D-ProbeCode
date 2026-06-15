# core/path_planner.py
import numpy as np

class PathPlanner:
    """คำนวณ Path Planning สำหรับการสแกนความลึกรู (Probing)"""
    
    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str) -> list:
        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        layers = []
        for t in t_vals:
            pt = o + t * (d - o)
            dx, dy, depth = projector.project_point_to_view(*pt, view_name)
            r_layer = hole.radius_at(t)

            layers.append({
                'z_display': depth,
                'x_display': dx,      
                'y_display': dy,      
                'radius':    r_layer, 
            })
        return layers