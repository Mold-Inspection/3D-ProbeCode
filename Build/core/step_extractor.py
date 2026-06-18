# core/step_extractor.py
import numpy as np
import math
import copy
from core.models03 import StepHole

class StepExtractor:
    """แกะข้อมูลทางเรขาคณิต (รู/ทรงกระบอก) ออกจากไฟล์ STEP"""
    def __init__(self):
        self._step_holes_cache = []

    def extract(self, step_data, mesh_centroid):
        if step_data is None: return []

        cx_off, cy_off, cz_off = mesh_centroid
        holes = []
        seen = {}

        for face in step_data.faces().vals():
            try:
                if face.geomType() not in ('CYLINDER', 'CONE'): continue

                # หมายเหตุสำคัญ: geomType() == 'CIRCLE' หมายถึง "เส้นโค้งอ้างอิงเป็นวงกลม"
                # เท่านั้น ไม่ได้แปลว่าเส้นขอบนั้นเป็นวงกลมเต็มวง (360°)
                # ขอบของ Fillet ที่มุม (เช่น มุมโค้งของบล็อกสี่เหลี่ยมมุมมน) ก็มี
                # geomType() == 'CIRCLE' เหมือนกัน (เพราะเป็นส่วนหนึ่งของวงกลม)
                # ทั้งที่จริงเป็นแค่ Arc เสี้ยววงกลม ไม่ใช่ปากรู
                # ต้องเช็ค IsClosed() เพิ่มเพื่อกรองเอาเฉพาะวงกลมที่ปิดสนิทจริงๆ
                # (ปากรู/ก้นรูจริงจะเป็นวงกลมเต็มวงเสมอ ส่วน Fillet มุมจะเป็นแค่ Arc)
                circle_edges = []
                for e in face.Edges():
                    if e.geomType() != 'CIRCLE': continue
                    try:
                        is_full_circle = bool(e.IsClosed())
                    except Exception:
                        # fallback: เทียบความยาวเส้นขอบกับเส้นรอบวงเต็มที่คำนวณจากรัศมี
                        # ถ้าสั้นกว่าอย่างมีนัยสำคัญ แสดงว่าเป็นแค่ Arc ไม่ใช่วงกลมเต็มวง
                        try:
                            r_chk = e.Length() / (2 * math.pi)
                            is_full_circle = r_chk > 0  # ไม่สามารถยืนยันได้ ปล่อยผ่านแบบระมัดระวัง
                        except Exception:
                            is_full_circle = False
                    if is_full_circle:
                        circle_edges.append(e)

                if len(circle_edges) < 2: continue

                circle_data = []
                for edge in circle_edges:
                    c = edge.Center()
                    ex, ey, ez = float(c.x) - cx_off, float(c.y) - cy_off, float(c.z) - cz_off
                    r = edge.Length() / (2 * math.pi)
                    circle_data.append((ex, ey, ez, r))

                if len(circle_data) < 2: continue

                c0 = np.array(circle_data[0][:3])
                c1 = np.array(circle_data[-1][:3])
                diff = c1 - c0
                dist = float(np.linalg.norm(diff))
                if dist < 0.05: continue
                
                axis_vec = diff / dist
                ax, ay, az = axis_vec
                circle_data.sort(key=lambda d: ax*d[0] + ay*d[1] + az*d[2])

                end_a, end_b = tuple(circle_data[0][:3]), tuple(circle_data[-1][:3])
                r_a, r_b = circle_data[0][3], circle_data[-1][3]

                if abs(az) < 0.70: continue

                face_depth = float(np.linalg.norm(np.array(end_b) - np.array(end_a)))
                if face_depth < 0.1: continue

                mid = (np.array(end_a) + np.array(end_b)) / 2.0
                key = (round(mid[0], 1), round(mid[1], 1), round(mid[2], 1), round(max(r_a, r_b), 2))

                if key in seen:
                    idx = seen[key]
                    if face_depth > holes[idx].depth:
                        holes[idx] = StepHole(end_a, end_b, r_a, r_b, (ax, ay, az))
                    continue

                seen[key] = len(holes)
                holes.append(StepHole(end_a, end_b, r_a, r_b, (ax, ay, az)))

            except Exception:
                continue

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    def get_step_holes_in_view(self, projector, view_name: str):
        if not self._step_holes_cache: return []
        
        p = projector.get_view_params(view_name)
        part_total_depth = p['total_depth']
        OPEN_THRESHOLD = max(part_total_depth * 0.03, 1.5)
        MIN_DEPTH = max(part_total_depth * 0.05, 0.5)

        result = []
        for h in self._step_holes_cache:
            dx_a, dy_a, d_a = projector.project_point_to_view(*h.open_3d, view_name)
            dx_b, dy_b, d_b = projector.project_point_to_view(*h.deep_3d, view_name)

            if d_a <= d_b:
                open_depth, deep_depth = d_a, d_b
                display_x, display_y = dx_a, dy_a
                r_open, r_deep = h.radius_open, h.radius_deep
                open_3d, deep_3d = h.open_3d, h.deep_3d
            else:
                open_depth, deep_depth = d_b, d_a
                display_x, display_y = dx_b, dy_b
                r_open, r_deep = h.radius_deep, h.radius_open
                open_3d, deep_3d = h.deep_3d, h.open_3d

            actual_depth = deep_depth - open_depth
            if open_depth > OPEN_THRESHOLD or actual_depth < MIN_DEPTH: continue

            hc = copy.copy(h)
            hc.open_3d, hc.deep_3d = open_3d, deep_3d
            hc.radius_open, hc.radius_deep, hc.radius = r_open, r_deep, r_open
            hc.display_x, hc.display_y = display_x, display_y
            hc.depth_top, hc.depth_bot, hc.depth = open_depth, deep_depth, actual_depth
            result.append(hc)

        result.sort(key=lambda h: (-round(h.display_y / 5.0), h.display_x))
        for i, h in enumerate(result):
            h._id = i + 1
        
        print(f"[geo] {view_name} view — visible holes: {len(result)}")
        return result
