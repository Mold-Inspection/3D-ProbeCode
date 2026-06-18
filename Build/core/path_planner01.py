# core/path_planner.py
import numpy as np

class PathPlanner:
    """คำนวณ Path Planning สำหรับการสแกนความลึกรู (Probing)"""

    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str) -> list:
        """
        คืนค่า list ของ layer dict สำหรับวาด probe path

        ถ้า hole.zigzag_inspection == True จะสลับทิศทางรัศมีในแต่ละ layer
        เพื่อให้เส้นทางตรวจสอบเป็นแบบ Zigzag ในแนวแกน Z:
            Layer 1 → สแกนจากศูนย์กลางออกด้านนอก (radius = r)
            Layer 2 → สแกนจากด้านนอกเข้าศูนย์กลาง (radius = r * zigzag_ratio)
            Layer 3 → ออกด้านนอกอีกครั้ง ...
        """
        use_zigzag = getattr(hole, 'zigzag_inspection', False)

        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        # อัตราส่วนรัศมี zigzag (inner sweep ใช้ 60% ของรัศมีหลัก)
        ZIGZAG_INNER_RATIO = 0.60

        layers = []
        for layer_idx, t in enumerate(t_vals):
            pt = o + t * (d - o)
            dx, dy, depth = projector.project_point_to_view(*pt, view_name)
            r_layer = hole.radius_at(t)

            if use_zigzag:
                # Layer คู่ (0, 2, 4, …) → ขอบนอก (radius เต็ม)
                # Layer คี่ (1, 3, 5, …) → ด้านใน (radius ลดลง) → zig-zag
                if layer_idx % 2 == 0:
                    r_display = r_layer            # ขอบนอก
                    zigzag_phase = 'outer'
                else:
                    r_display = r_layer * ZIGZAG_INNER_RATIO   # ด้านใน
                    zigzag_phase = 'inner'
            else:
                r_display = r_layer
                zigzag_phase = 'normal'

            layers.append({
                'z_display':   depth,
                'x_display':   dx,
                'y_display':   dy,
                'radius':      r_display,
                'zigzag_phase': zigzag_phase,   # ข้อมูลเสริมสำหรับ visualizer ที่ต้องการ
            })
        return layers
