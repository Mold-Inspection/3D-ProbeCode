# ==============================================================================
# core/hole_ordering.py — จัดลำดับการเดินเครื่องระหว่างรู (nearest-neighbor)
# ==============================================================================
# VERSION: 01
# หน้าที่: คำนวณลำดับการเข้าตรวจสอบรูแบบ nearest-neighbor บนพิกัด 3D ดิบ
# (raw CAD-space, ไม่ใช่พิกัดที่ projected ตามมุมมองหน้าจอ) เพื่อให้ทั้ง
# G-code export (core/gcode_generator.py) และ Path Mapper preview
# (ui/tabs/path_mapper_tab.py) ใช้ลำดับเดียวกันเป๊ะ ๆ — ไม่มีสองแหล่งความจริง
#
# ใช้ได้เฉพาะรูที่มีข้อมูล STEP (h._step_hole ไม่ใช่ None) เพราะต้องมีพิกัด
# 3D ดิบ (open_3d) มาคำนวณระยะทางจริง — รูที่ไม่มี STEP (mesh-only) ให้แยก
# ออกด้วย split_step_ready() ก่อนส่งเข้า order_holes_nearest_neighbor()
#
# ตัวแปรที่ปรับจูนได้: ไม่มี — อัลกอริทึม greedy nearest-neighbor ล้วน ๆ
# เริ่มจากรูที่ใกล้ (0,0) ที่สุด แล้ววิ่งหารูถัดไปที่ใกล้สุดเรื่อย ๆ
# ==============================================================================
import numpy as np


def split_step_ready(holes: list) -> tuple:
    """แยกรายการรูออกเป็น (มี STEP data, ไม่มี STEP data)
    ใช้ทั้งฝั่ง G-code export และ Path Mapper preview เพื่อให้เกณฑ์การ
    คัดกรองตรงกันเป๊ะ (รูที่ export G-code ไม่ได้ ก็ไม่ควรถูกนับใน
    เส้นทางเดินบน Path Mapper เช่นกัน)"""
    ready   = [h for h in holes if getattr(h, '_step_hole', None) is not None]
    skipped = [h for h in holes if getattr(h, '_step_hole', None) is None]
    return ready, skipped


def order_holes_nearest_neighbor(holes: list) -> list:
    """ลำดับการเดินเครื่องแบบ greedy nearest-neighbor บนพิกัด XY ดิบ
    (h._step_hole.open_3d) เริ่มจากรูที่ใกล้ (0,0) ที่สุด — ใช้ร่วมกันโดย
    core/gcode_generator.py และ ui/tabs/path_mapper_tab.py

    Parameters
    ----------
    holes : list ของ HoleFeature ที่ต้องมี h._step_hole ไม่ใช่ None ทุกตัว
            (กรองด้วย split_step_ready() ก่อนเรียกฟังก์ชันนี้)
    """
    def open_xy(h):
        return np.array(h._step_hole.open_3d[:2])

    remaining = list(holes)
    remaining.sort(key=lambda h: float(np.linalg.norm(open_xy(h))))
    if not remaining:
        return []

    ordered = [remaining.pop(0)]
    while remaining:
        cur_xy = open_xy(ordered[-1])
        remaining.sort(key=lambda h: float(np.linalg.norm(open_xy(h) - cur_xy)))
        ordered.append(remaining.pop(0))
    return ordered