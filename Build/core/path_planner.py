# core/path_planner.py
import numpy as np

class PathPlanner:
    """คำนวณ Path Planning สำหรับการสแกนความลึกรู (Probing)"""

    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str,
                               zigzag_inspection: bool = False, zigzag_degree: float = 45.0) -> list:
        """
        คืนค่า list ของ layer dict สำหรับวาด probe path

        พารามิเตอร์ zigzag_inspection / zigzag_degree ต้องถูกส่งเข้ามาตรงๆ จากผู้เรียก
        (ไม่ใช่อ่านจาก getattr(hole, ...) อีกต่อไป) เพราะ `hole` ในฟังก์ชันนี้อาจเป็น
        StepHole (core/models03.py) ซึ่งไม่มี attribute zigzag_inspection/zigzag_degree เลย —
        ค่าทั้งสองนี้ถูกเก็บอยู่บน HoleFeature (ฝั่ง UI) เท่านั้น
        ก่อนหน้านี้ฟังก์ชันนี้เคยใช้ getattr(hole, 'zigzag_inspection', False) ซึ่งถ้า `hole`
        ที่ส่งเข้ามาเป็น StepHole จะ fallback เป็น False เสมอ ทำให้ Zigzag ไม่ทำงานเลย
        สำหรับรูที่มาจากไฟล์ STEP (ดู geometry_engine.get_probe_path_layers /
        customization_tab03.draw_cross_section ที่เรียกใช้ฟังก์ชันนี้ด้วย hole._step_hole)

        โหมด Zigzag (zigzag_inspection == True):
            แต่ละ layer หมุนสะสมจาก layer ก่อนหน้า ตามองศาที่กำหนดใน zigzag_degree
            Layer 0 → offset = 0°
            Layer 1 → offset = 1 × degree
            Layer 2 → offset = 2 × degree
            Layer N → offset = N × degree
        """
        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        layers = []
        for layer_idx, t in enumerate(t_vals):
            pt = o + t * (d - o)
            dx, dy, depth = projector.project_point_to_view(*pt, view_name)
            r_layer = hole.radius_at(t)

            if zigzag_inspection:
                # หมุนสะสม: layer N = N × step_deg
                angle_offset = np.radians(layer_idx * zigzag_degree)
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
