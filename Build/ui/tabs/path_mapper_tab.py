# ==============================================================================
# ui/tabs/path_mapper_tab.py — แท็บ "Path Mapper"
# ==============================================================================
# หน้าที่: วาดหน้าจอ placeholder ของแท็บ Path Mapper (ฟีเจอร์นี้ยังไม่พัฒนา)
# แสดงไอคอน 🚧 + หัวข้อ + รายการฟีเจอร์ที่จะทำในอนาคต
#
# ตัวแปรที่ปรับจูนได้:
#   future_items  = รายการข้อความฟีเจอร์ที่จะขึ้นแสดงใต้หัวข้อ (แก้ไข/เพิ่มได้)
# ==============================================================================
import matplotlib.pyplot as plt

class PathMapperTab:
    def __init__(self, app):
        self.app = app

    def draw_path_mapper(self):
        app = self.app
        app.fig.clf()
        app.ax = app.fig.add_subplot(111, facecolor='#1a1a2e')
        app.fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        app.ax.set_xlim(0, 1)
        app.ax.set_ylim(0, 1)
        app.ax.set_axis_off()

        app.ax.add_patch(plt.Rectangle((0.05, 0.1), 0.9, 0.8,
                          linewidth=1.5, edgecolor='#1f538d',
                          facecolor='#0d1117', zorder=1))

        app.ax.text(0.5, 0.72, '🚧', fontsize=42, ha='center', va='center', transform=app.ax.transAxes, zorder=2)
        app.ax.text(0.5, 0.58, 'Path Mapper', fontsize=22, fontweight='bold', color='white', ha='center', va='center', transform=app.ax.transAxes, zorder=2)
        app.ax.text(0.5, 0.48, 'Under Development', fontsize=13, color='#1f538d', ha='center', va='center', transform=app.ax.transAxes, zorder=2)

        app.ax.plot([0.15, 0.85], [0.43, 0.43], color='#1f538d', linewidth=0.8, alpha=0.6, transform=app.ax.transAxes)

        # รายการฟีเจอร์ที่วางแผนไว้ในอนาคต — แก้ไขข้อความ/เพิ่ม-ลบรายการได้ที่นี่
        future_items = [
            "📂  Import G38.2 Log File from OpenBuilds",
            "📐  Apply Probe Radius Compensation",
            "⭕  Least Squares Circle Fitting per Layer",
            "📊  Deviation Report vs CAD Reference",
        ]
        for i, item in enumerate(future_items):
            app.ax.text(0.5, 0.36 - i * 0.065, item, fontsize=10, color='#aaaaaa', ha='center', va='center', transform=app.ax.transAxes, zorder=2)

        app.canvas.draw()
