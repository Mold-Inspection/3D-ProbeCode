import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 1. ข้อมูลจำลองที่ประมวลผลด้วย Pandas (ได้มาจากการวัดจริง)
data = {
    'Point_ID': [1, 2, 3],
    'X_Coord': [15.0, -10.0, 5.0],  # พิกัดแกน X บนชิ้นงานที่เลเซอร์ยิง
    'Y_Coord': [20.0, -5.0, 10.0],  # พิกัดแกน Y บนชิ้นงานที่เลเซอร์ยิง
    'Deviation': [0.01, 0.08, -0.02], # ค่าความคลาดเคลื่อน (มิลลิเมตร)
}
df = pd.DataFrame(data)

# กำหนดเงื่อนไข Pass/Fail (สมมติ Tolerance = 0.05)
tolerance = 0.05
# สร้างคอลัมน์สี: เขียว = Pass, แดง = Fail
df['Color'] = df['Deviation'].abs().apply(lambda x: 'lime' if x <= tolerance else 'red')

# ---------------------------------------------------------
# 2. ส่วนของการวาดภาพ (นำโค้ดเดิมมาประยุกต์)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 6))

# (สมมติว่าตรงนี้คือโค้ด ax.tripcolor ที่วาดโมเดล STL ของคุณ)
# ax.tripcolor(x, y, triangles, facecolors=z_faces, cmap=custom_cmap)

# นำข้อมูลจาก Pandas มาพล็อตทับลงบนกราฟ!
# วาดจุด (Scatter) ตามพิกัด X, Y และใช้สีตามที่ Pandas คำนวณไว้
ax.scatter(df['X_Coord'], df['Y_Coord'], 
           color=df['Color'],     # ใช้สีเขียว/แดงจากตาราง
           s=100,                 # ขนาดของจุด
           edgecolors='black',    # ขอบของจุดสีดำให้ดูมีมิติ
           zorder=5,              # ให้อยู่เลเยอร์บนสุด จะได้ไม่ถูก STL บัง
           label='Measurement Points')

# ใส่ตัวเลขกำกับจุด (Point ID)
for i, row in df.iterrows():
    ax.annotate(f" P{row['Point_ID']}", (row['X_Coord'], row['Y_Coord']), 
                color='white', fontweight='bold', zorder=6)

ax.set_aspect('equal')
ax.set_title('Inspection Overlay (Top View)')
plt.show()