# สร้างชิ้นงานทดสอบ: ช่องสี่เหลี่ยมจัตุรัส/ผืนผ้า ทั้งมุมคมและมุมโค้ง + ช่องแคปซูล (slot) + รูกลม 1 รู
# (ทั้งแบบทะลุและแบบไม่ทะลุ) สำหรับทดสอบการตรวจจับ/วางเส้นทางโพรบ/ประเมินผล
import cadquery as cq

L, W, T = 200.0, 120.0, 20.0

# (X กลาง, Y กลาง, ยาว X, กว้าง Y, รัศมีมุม, ความลึก — None = ทะลุ)
POCKETS = [
    (30.0,  30.0, 20.0, 20.0, 0.0,  None),   # สี่เหลี่ยมจัตุรัส มุมคม ทะลุ
    (80.0,  30.0, 36.0, 20.0, 0.0,  10.0),   # สี่เหลี่ยมผืนผ้า มุมคม ลึก 10
    (30.0,  85.0, 20.0, 20.0, 4.0,  12.0),   # สี่เหลี่ยมจัตุรัส มุมโค้ง R4 ลึก 12
    (90.0,  85.0, 40.0, 24.0, 5.0,  None),   # สี่เหลี่ยมผืนผ้า มุมโค้ง R5 ทะลุ
]
ROUND = (160.0, 60.0, 10.0, None)            # รูกลม Ø10 ทะลุ (ไว้เทียบว่ายังทำงานปกติ)

# ช่องแคปซูล (slot): (X กลาง, Y กลาง, ความยาวรวม, ความกว้าง, ความลึก — None = ทะลุ)
SLOTS = [
    (160.0, 25.0, 30.0, 10.0, None),         # slot ทะลุ แนว X
    (160.0, 95.0, 24.0,  8.0, 6.0),          # slot ลึก 6
]

body = cq.Workplane("XY").box(L, W, T, centered=False)
for x, y, lx, wy, r, depth in POCKETS:
    d = T if depth is None else depth
    cutter = cq.Workplane("XY").workplane(offset=T - d).center(x, y).rect(lx, wy).extrude(d)
    if r > 0:
        cutter = cutter.edges("|Z").fillet(r)
    body = body.cut(cutter)

x, y, dia, depth = ROUND
d = T if depth is None else depth
body = body.cut(cq.Workplane("XY").workplane(offset=T - d).center(x, y).circle(dia / 2).extrude(d))

for x, y, length, width, depth in SLOTS:
    d = T if depth is None else depth
    body = body.cut(cq.Workplane("XY").workplane(offset=T - d).center(x, y)
                    .slot2D(length, width).extrude(d))

cq.exporters.export(body, "pocket_test.step")
print("faces:", len(body.val().Faces()), "volume:", round(body.val().Volume(), 1))
