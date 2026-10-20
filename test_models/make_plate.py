# สร้างแผ่น plate ทดสอบ (STEP + STL) ด้วย cadquery
# v04 (2026-10-15): ขนาดแผ่น 226.63 × 299.04 วัดด้วยโพรบ (แตะผนังสองฝั่ง หลังแก้ steps/mm แล้ว)
#   ตำแหน่งรู/ช่องกลับไปใช้ชุดวัดแรก (รวมระยะแนวกว้างได้ตรงกับความกว้างจริง)
# v03 (2026-10-15): ขนาดแผ่นและตำแหน่งรูกลม/ช่องสี่เหลี่ยมตามที่วัดจริงรอบสอง (ตลับเมตร + เวอร์เนียร์)
#   แผ่นจริงกว้าง 220.90 ยาว 294.20 (อ่านจากรูปไม้บรรทัด ±0.2; เดิมประมาณจากรูปถ่าย 226.5 × 300)
#   รูกลมอ้างอิงขอบซ้าย, ช่องสี่เหลี่ยมอ้างอิงขอบขวา (วัดจากขอบที่ใกล้ที่สุด)
# v02: วางแผ่น "แนวตั้ง" ตามที่ตั้งบนเครื่อง (ไม่ต้องกด Rotate ในโปรแกรม)
#   (slot 4 ช่องยังเป็นค่าประมาณจากรูปถ่ายเดิม — อ้างอิงขอบขวา/ขอบล่าง)
#
# ระบบพิกัด (มองจากด้านบน = มุมมอง Top ในโปรแกรม, Z ชี้ขึ้น):
#   origin = มุมซ้ายล่างของแผ่น, X = ไปทางขวา (ด้านกว้าง), Y = ขึ้นบน (ด้านยาว)
#   "ห่างจากขอบบน d" → Y = L - d,  "ห่างจากขอบซ้าย d" → X = d,  "ห่างจากขอบขวา d" → X = W - d
import cadquery as cq

W, L, T = 226.63, 299.04, 19.38        # กว้าง (X), ยาว (Y), หนา (Z) mm — วัดด้วยโพรบบนเครื่อง (หนายังไม่ได้วัดใหม่)

# --- ค่าที่วัดจริง ------------------------------------------------------------------------
HOLE_D        = 7.75     # รูกลมทะลุ ⌀
HOLE_LEFT     = 57.88    # ขอบซ้ายแผ่น → ขอบซ้ายของรู  (ชุดวัดแรก)
HOLE_TOP      = 66.00    # ขอบบนแผ่น → ขอบบนของรู  (ชุดวัดแรก — รอยืนยัน)

RECT_W        = 24.60    # ช่องสี่เหลี่ยมทะลุ: กว้าง (X)
RECT_L        = 37.80    #                  ยาว (Y)
RECT_R        = 7.75     #                  รัศมีมุม
RECT_LEFT     = 95.17    # ขอบซ้ายแผ่น → ขอบซ้ายของช่อง  (ชุดวัดแรก)
RECT_TOP      = 60.46    # ขอบบนแผ่น → ขอบบนของช่อง  (ชุดวัดแรก; ชุดที่สองวัดได้ 50.30 — รอยืนยัน)
# (ตรวจสอบ: ขอบขวาแผ่น → ขอบขวาของช่อง วัดได้ 106.44 — จากค่าข้างบนได้ 106.86)

# slot ยาว (ประมาณจากรูปถ่าย): (ห่างขอบขวา, Y กลางจากขอบล่าง, ความยาว, ความกว้าง) — แนวยาวขนานแกน Y
SLOTS = [
    (34.0,  9.0, 11.0, 5.0),
    (76.0,  9.0, 11.0, 5.0),
    (34.0, 66.0, 11.0, 5.0),
    (76.0, 66.0, 11.0, 5.0),
]

HOLE = (HOLE_LEFT + HOLE_D / 2, L - HOLE_TOP - HOLE_D / 2, HOLE_D)
RECT = (RECT_LEFT + RECT_W / 2, L - RECT_TOP - RECT_L / 2, RECT_W, RECT_L, RECT_R)

body = cq.Workplane("XY").box(W, L, T, centered=False)

for from_right, y, length, width in SLOTS:
    body = body.cut(
        cq.Workplane("XY").center(W - from_right, y).slot2D(length, width, angle=90).extrude(T)
    )

rx, ry, rw, rl, rr = RECT
body = body.cut(
    cq.Workplane("XY").center(rx, ry).rect(rw, rl).extrude(T).edges("|Z").fillet(rr)
)

hx, hy, hd = HOLE
body = body.cut(cq.Workplane("XY").center(hx, hy).circle(hd / 2).extrude(T))

if __name__ == "__main__":
    name = "plate_with_holes"
    cq.exporters.export(body, f"{name}.step")
    cq.exporters.export(body, f"{name}.stl")
    b = body.val().BoundingBox()
    print("bbox:", [round(v, 3) for v in (b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax)])
    print("hole centre:", [round(v, 3) for v in HOLE[:2]], " rect centre:", [round(v, 3) for v in RECT[:2]])
    print("gap hole right edge -> rect left edge:",
          round((RECT[0] - RECT_W / 2) - (HOLE[0] + HOLE_D / 2), 3))
    print("volume:", round(body.val().Volume(), 1))
