# สร้างโมเดล Ring Gauge สำหรับ calibrate ขนาดหัวโพรบ (Effective Tip ⌀) ในแท็บ Evaluation
# แก้ BORE_D / OUTER_D / HEIGHT ให้ตรงกับ ring gauge จริง (ดูใบ certificate) แล้วรันใหม่
import sys

import cadquery as cq

BORE_D  = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0   # ⌀ รูใน (ค่าตาม certificate)
OUTER_D = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0   # ⌀ นอก
HEIGHT  = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0   # ความหนา

ring = (cq.Workplane("XY").circle(OUTER_D / 2).extrude(HEIGHT)
        .cut(cq.Workplane("XY").circle(BORE_D / 2).extrude(HEIGHT)))

if __name__ == "__main__":
    out = f"ring_gauge_D{BORE_D:g}.step"
    cq.exporters.export(ring, out)
    print("saved", out)
