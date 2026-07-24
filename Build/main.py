# ==============================================================================
# main.py — จุดเริ่มต้นโปรแกรม 3D ProbeCode
# ==============================================================================
# หน้าที่ของไฟล์นี้: ประกอบ (bootstrap) โปรแกรมเข้าด้วยกัน
#   1) สร้าง MoldGeometry (core/geometry_engine.py) = Backend คำนวณเรขาคณิต
#   2) สร้าง UIManager (ui/main_window.py) = Frontend หน้าต่างโปรแกรม
#   3) เปิดโปรแกรม
#
# ไฟล์นี้ไม่มีตัวแปรที่ต้องปรับจูน — การตั้งค่าต่าง ๆ (ขนาดหน้าต่าง,
# ค่าเริ่มต้น probe ฯลฯ) อยู่ใน ui/main_window.py และ core/probe_profile.py
# ==============================================================================
from core.geometry_engine import MoldGeometry
from ui.main_window import UIManager


def main():
    print("Starting 3D ProbeCode...")

    geo = MoldGeometry()
    ui = UIManager(geo)
    ui.show()


if __name__ == "__main__":
    main()
