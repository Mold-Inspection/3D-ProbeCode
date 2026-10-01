# สร้างแผ่น plate ทดสอบ (STEP + STL) ด้วย cadquery
# ค่าตำแหน่งรูทั้งหมด "ประมาณจากรูปถ่าย" (~0.276 mm/px) — แก้เป็นค่าที่วัดจริงได้ตรงนี้
#
# ระบบพิกัด (มองจากด้านบน, Z ชี้ขึ้น):
#   origin = มุมซ้ายบนของแผ่นตามรูปถ่าย
#   X = ระยะจากขอบบนของรูป (ตามความยาว 300)
#   Y = ระยะจากขอบซ้ายของรูป (ตามความกว้าง 226.5)
import cadquery as cq

L, W, T = 300.0, 226.5, 19.38          # ยาว (X), กว้าง (Y), หนา (Z) mm

# slot ยาว: (X กลาง, Y กลาง, ความยาว, ความกว้าง) — แนวยาวของ slot ขนานแกน X
SLOTS = [
    (9.0,  34.0, 11.0, 5.0),
    (9.0,  76.0, 11.0, 5.0),
    (66.0, 34.0, 11.0, 5.0),
    (66.0, 76.0, 11.0, 5.0),
]

# ช่องสี่เหลี่ยมทะลุ: (X กลาง, Y กลาง, ยาว X, กว้าง Y, รัศมีมุม)
RECT = (218.0, 119.0, 36.0, 25.0, 4.0)

# รูกลมทะลุ: (X กลาง, Y กลาง, เส้นผ่านศูนย์กลาง)
HOLE = (227.0, 165.0, 8.0)

body = cq.Workplane("XY").box(L, W, T, centered=False)

for x, y, length, width in SLOTS:
    body = body.cut(
        cq.Workplane("XY").center(x, y).slot2D(length, width, angle=0).extrude(T)
    )

rx, ry, rl, rw, rr = RECT
body = body.cut(
    cq.Workplane("XY").center(rx, ry).rect(rl, rw).extrude(T).edges("|Z").fillet(rr)
)

hx, hy, hd = HOLE
body = body.cut(cq.Workplane("XY").center(hx, hy).circle(hd / 2).extrude(T))

name = "plate_with_holes"
cq.exporters.export(body, f"{name}.step")
cq.exporters.export(body, f"{name}.stl")
b = body.val().BoundingBox()
print("bbox:", [round(v, 3) for v in (b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax)])
print("volume:", round(body.val().Volume(), 1))
