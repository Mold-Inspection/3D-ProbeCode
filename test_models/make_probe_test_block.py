# สร้างชิ้นงานทดสอบสำหรับวัดจริงบนเครื่อง (PTB-01): รูกลม 3 ขนาด + รู counterbore + ช่องสี่เหลี่ยม
# ใช้ตรวจความแม่นยำ/ความซ้ำของระบบ เทียบกับค่าที่วัดด้วยเครื่องมืออ้างอิง (bore gauge / pin gauge / CMM)
# จุดอ้างอิง: มุมซ้าย-หน้า-ล่างของชิ้นงาน = (0,0,0), ผิวบน Z = T
import cadquery as cq

L, W, T = 100.0, 80.0, 25.0

# (ชื่อ, X กลาง, Y กลาง, ⌀, ความลึก)
HOLES = [
    ("H1", 25.0, 55.0, 20.0, 15.0),   # รูหลัก — ขนาดเดียวกับ ring gauge ⌀20
    ("H2", 60.0, 60.0, 12.0, 15.0),
    ("H3", 85.0, 60.0,  8.0, 12.0),   # รูเล็ก — ทดสอบระยะว่างหัวโพรบ
]
# (ชื่อ, X, Y, ⌀ บน, ลึกบน, ⌀ ล่าง, ลึกรวม)
CBORE = ("H4", 25.0, 20.0, 18.0, 6.0, 10.0, 18.0)
# (ชื่อ, X, Y, ยาว X, กว้าง Y, รัศมีมุม, ความลึก)
POCKET = ("P1", 67.0, 22.0, 34.0, 18.0, 4.0, 10.0)


def cut_down(body, x, y, sketch, depth):
    return body.cut(sketch(cq.Workplane("XY").workplane(offset=T - depth).center(x, y)).extrude(depth))


body = cq.Workplane("XY").box(L, W, T, centered=False)
for _, x, y, d, depth in HOLES:
    body = cut_down(body, x, y, lambda w, d=d: w.circle(d / 2), depth)

_, x, y, d_top, depth_top, d_bot, depth_all = CBORE
body = cut_down(body, x, y, lambda w: w.circle(d_top / 2), depth_top)
body = cut_down(body, x, y, lambda w: w.circle(d_bot / 2), depth_all)

_, x, y, lx, wy, r, depth = POCKET
cutter = cq.Workplane("XY").workplane(offset=T - depth).center(x, y).rect(lx, wy).extrude(depth)
body = body.cut(cutter.edges("|Z").fillet(r))

if __name__ == "__main__":
    cq.exporters.export(body, "probe_test_block_PTB01.step")
    print("faces:", len(body.val().Faces()), "volume:", round(body.val().Volume(), 1))
