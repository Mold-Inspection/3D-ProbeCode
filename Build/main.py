# main.py
from core.geometry_engine import MoldGeometry
from ui.main_window import UIManager

def main():
    print("Starting 3D ProbeCode...")
    
    # 1. สร้าง Engine คำนวณทางเรขาคณิต (Backend)
    geo = MoldGeometry()
    
    # 2. ส่งต่อ Engine เข้าไปทำงานร่วมกับหน้าต่าง UI หลัก (Frontend)
    ui = UIManager(geo)
    
    # 3. เปิดโปรแกรม
    ui.show()

if __name__ == "__main__":
    main()