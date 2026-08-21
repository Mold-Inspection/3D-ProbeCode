# ==============================================================================
# ui/tabs/evaluation_tab.py — แท็บ "Evaluation" (เทียบผลตรวจจริงจาก .log กับรูที่คาดหวัง)
# ==============================================================================
# VERSION: 01
# หน้าที่: วาด overview 2D (mesh background + hole markers) ของแท็บ Evaluation
# — ตรวจว่าแต่ละรูที่ถูกโพรบจริง (จากไฟล์ .log ของ OpenBuilds Control) ตรงกับ
# ตำแหน่งที่คำนวณไว้จาก STEP (ผ่าน core/gcode_generator.py::build_point_map())
# ภายใน tolerance ที่ผู้ใช้กำหนดหรือไม่ — สีของแต่ละรูบอกผลรวมของรูนั้น
# (เขียว = ผ่านทุกจุด, แดง = มีจุดไม่ผ่าน, เทา = ยังไม่มีผลตรวจ/รูถูกข้าม)
#
# NOTE (สำคัญ — ไฟล์นี้ถูกสร้างก่อนไฟล์อื่นตามคำขอ):
# ไฟล์นี้ยังไม่ทำงานได้ครบวงจรจนกว่าจะมีไฟล์ต่อไปนี้ตามแผน
# (PLAN_evaluation-tab-openbuilds-log-comparison_v02.md):
#   - core/log_parser.py            (parse .log -> actual points)
#   - core/evaluation_engine.py     (evaluate_points, สร้าง app.evaluation_result)
#   - core/gcode_generator.py v05   (build_point_map() แยกออกมาให้ใช้ร่วมกัน)
#   - ui/evaluation_left_panel.py   (ปุ่มโหลด .log, เปอร์เซ็นต์ความถูกต้องรวม)
#   - ui/evaluation_sidebar_panel.py (tolerance input + รายละเอียดราย layer/point)
#   - ui/main_window.py v12         (เพิ่มแท็บ "Evaluation" ใน nav + สลับ sidebar)
# ไฟล์นี้จึง "gate" ทุก state ไว้กันพัง แม้ app.evaluation_result จะยังไม่มีอยู่จริง
#
# EXPECTED CONTRACT — app.evaluation_result (สร้างโดย evaluation_engine ในอนาคต)
# เป็น dict ว่าง None ถ้ายังไม่ได้โหลด .log, หรือมีรูปแบบดังนี้เมื่อโหลดแล้ว:
#   {
#     'tolerance_mm':      float,   # ค่า tolerance ที่ใช้ประเมินผลรอบล่าสุด
#     'log_filename':      str,     # ชื่อไฟล์ .log ที่โหลด
#     'overall_accuracy':  float,   # % จุดที่ผ่าน (0-100) รวมทุกรูที่ประเมินได้
#     'total_points':      int,
#     'passed_points':     int,
#     'settings_mismatch': [hole_display_id, ...],  # รูที่ค่า setting ไม่ตรงกับตอน export
#     'holes': {
#         <global_idx into app.current_holes>: {
#             'display_id':    str/int,
#             'passed':        bool,   # True เฉพาะเมื่อทุกจุดของรูนี้ผ่าน
#             'total_points':  int,
#             'passed_points': int,
#             'max_deviation': float,  # mm, ระยะเบี่ยงเบนสูงสุดของรูนี้
#             'segments': [            # 1 รายการถ้าเป็นรูปกติ (segment เดียว)
#                 {
#                     'seg_idx': int,
#                     'layers': [
#                         {
#                             'layer_idx':      int,
#                             'passed':         bool,
#                             'max_deviation':  float,
#                             'points': [
#                                 {
#                                     'point_idx':  int,
#                                     'expected':   (x, y, z),
#                                     'actual':     (x, y, z),
#                                     'delta':      (dx, dy, dz),
#                                     'distance_mm': float,
#                                     'passed':      bool,
#                                 }, ...
#                             ],
#                         }, ...
#                     ],
#                 }, ...
#             ],
#         }, ...
#     },
#   }
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _PASS_FACE / _PASS_EDGE   = สี marker ของรูที่ "ผ่าน" ทั้งหมด
#   _FAIL_FACE / _FAIL_EDGE   = สี marker ของรูที่ "ไม่ผ่าน" (มีอย่างน้อย 1 จุด)
#   _NODATA_FACE / _NODATA_EDGE = สี marker ของรูที่ยังไม่มีผลตรวจจับคู่ได้
# ==============================================================================
import numpy as np
import matplotlib.pyplot as plt

_PASS_FACE    = '#66bb6a'
_PASS_EDGE    = '#43a047'
_FAIL_FACE    = '#e53935'
_FAIL_EDGE    = '#ff8a80'
_NODATA_FACE  = '#555555'
_NODATA_EDGE  = '#888888'
_HILITE_EDGE  = '#ffee58'


class EvaluationTab:
    def __init__(self, app):
        self.app = app
        self._overview_scatter   = None
        self._overview_index_map = {}   # {global_idx (into app.current_holes): local scatter index}
        self._overview_base_face = []
        self._overview_base_edge = []
        self._highlighted_gidx   = None

    # ------------------------------------------------------------------
    def draw_evaluation(self):
        """Entry point เรียกจาก ui/main_window.py::on_nav_change() เมื่อสลับมาแท็บ
        Evaluation (ยังไม่ได้ต่อสายในไฟล์นี้ — ดู VERSION note ด้านบน)"""
        app = self.app
        app.fig.clf()
        app.ax = app.fig.add_subplot(111, facecolor='#1e1e1e')
        app.fig.subplots_adjust(left=0.08, right=0.97, bottom=0.08, top=0.90)

        self._overview_scatter   = None
        self._overview_index_map = {}
        self._overview_base_face = []
        self._overview_base_edge = []
        self._highlighted_gidx   = None

        if app.geo.mesh is None or app.geo.step_data is None:
            self._draw_placeholder(
                "📐",
                "Please upload a STEP model first.\n"
                "Evaluation compares real probe results against STEP geometry, "
                "so a STEP file is required before this tab can be used.")
            return

        if not getattr(app, 'holes_detected', False) or not app.current_holes:
            self._draw_placeholder(
                "🔍",
                "Please generate holes first (left sidebar → Generate Holes).")
            return

        has_view_data = (getattr(app, 'current_x', None) is not None and
                          getattr(app, 'current_triangles', None) is not None and
                          getattr(app, 'current_face_data', None) is not None)
        if not has_view_data:
            self._draw_placeholder(
                "🗺️",
                "Select a view (Selection tab) first so the model background "
                "can be drawn here.")
            return

        evaluation_result = getattr(app, 'evaluation_result', None)
        if not evaluation_result:
            self._draw_placeholder(
                "🧪",
                "No evaluation results yet.\n"
                "Load an OpenBuilds Control .log file from the left panel to "
                "compare it against the expected probe points.")
            return

        self._draw_overview(evaluation_result)

    # ------------------------------------------------------------------
    def _draw_placeholder(self, icon: str, message: str):
        app = self.app
        app.ax.set_xlim(0, 1)
        app.ax.set_ylim(0, 1)
        app.ax.set_axis_off()

        app.ax.add_patch(plt.Rectangle((0.05, 0.1), 0.9, 0.8,
                          linewidth=1.5, edgecolor='#1f538d',
                          facecolor='#0d1117', zorder=1))

        app.ax.text(0.5, 0.58, icon, fontsize=42, ha='center', va='center',
                    transform=app.ax.transAxes, zorder=2)
        app.ax.text(0.5, 0.46, message, fontsize=12, color='#aaaaaa',
                    ha='center', va='center', wrap=True,
                    transform=app.ax.transAxes, zorder=2)

        app.canvas.draw()

    # ------------------------------------------------------------------
    def _draw_overview(self, evaluation_result: dict):
        """วาด mesh background + hole markers สีตามผลตรวจ (เขียว/แดง/เทา)
        พร้อมเส้นทางเดินเครื่อง (แบบเดียวกับ Path Mapper) เพื่ออ้างอิงลำดับ
        การโพรบจริง — ใช้แค่แสดงผล ไม่ใช้คำนวณ"""
        app = self.app
        ax  = app.ax

        gidx_of = {id(h): gi for gi, h in enumerate(app.current_holes)}

        selected_holes = [h for h in app.current_holes
                          if getattr(h, 'selected_for_inspection', False)
                          and h.x is not None and h.y is not None]

        if not selected_holes:
            self._draw_placeholder(
                "📍", "No holes are currently selected for inspection.")
            return

        holes_result = evaluation_result.get('holes', {})

        x, y, tris, fdata = app.current_x, app.current_y, app.current_triangles, app.current_face_data
        vmin, vmax = np.min(fdata), np.max(fdata)
        if vmin == vmax:
            vmax = vmin + 0.1

        ax.set_axis_on()
        ax.tripcolor(x, y, tris, facecolors=fdata, cmap=app.cmap,
                    edgecolors='none', vmin=vmin, vmax=vmax, alpha=0.55, zorder=1)

        # ลำดับการเดินเครื่อง (อ้างอิงเท่านั้น ใช้โมดูลเดียวกับ G-code จริง)
        try:
            from core.hole_ordering import order_holes_nearest_neighbor, split_step_ready
            ready, _skipped = split_step_ready(selected_holes)
            ordered = order_holes_nearest_neighbor(ready)
        except Exception:
            ordered = selected_holes

        if ordered:
            hx = [h.x for h in ordered]
            hy = [h.y for h in ordered]
            ax.plot(hx, hy, color='#546e7a', linestyle='--', linewidth=1.2,
                   alpha=0.6, zorder=3, marker=None)

        face_colors, edge_colors = [], []
        pass_count = fail_count = nodata_count = 0

        for h in selected_holes:
            gi   = gidx_of.get(id(h))
            info = holes_result.get(gi) if gi is not None else None
            if info is None:
                face_colors.append(_NODATA_FACE)
                edge_colors.append(_NODATA_EDGE)
                nodata_count += 1
            elif info.get('passed', False):
                face_colors.append(_PASS_FACE)
                edge_colors.append(_PASS_EDGE)
                pass_count += 1
            else:
                face_colors.append(_FAIL_FACE)
                edge_colors.append(_FAIL_EDGE)
                fail_count += 1

        hx_all = [h.x for h in selected_holes]
        hy_all = [h.y for h in selected_holes]

        scatter = ax.scatter(hx_all, hy_all, facecolors=face_colors, edgecolors=edge_colors,
                  marker='o', s=150, linewidths=2.2, zorder=5)

        for h in selected_holes:
            gi   = gidx_of.get(id(h))
            info = holes_result.get(gi) if gi is not None else None
            label = str(h.display_id)
            ax.text(h.x, h.y, label, color='black', fontsize=8,
                   weight='bold', ha='center', va='center', zorder=6)
            if info is not None and not info.get('passed', False):
                sub = f"{info.get('passed_points', 0)}/{info.get('total_points', 0)} pts"
                ax.text(h.x, h.y - 4, sub, color=_FAIL_FACE, fontsize=7,
                        ha='center', va='top', zorder=6)

        self._overview_scatter   = scatter
        self._overview_base_face = list(face_colors)
        self._overview_base_edge = list(edge_colors)
        self._overview_index_map = {gidx_of[id(h)]: i for i, h in enumerate(selected_holes)}

        accuracy = evaluation_result.get('overall_accuracy')
        acc_tag  = f"  |  Overall Accuracy: {accuracy:.1f}%" if accuracy is not None else ""
        ax.set_title(
            f"Evaluation — {pass_count} passed, {fail_count} failed, "
            f"{nodata_count} no data{acc_tag}",
            fontsize=13, color="white")
        ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        ax.set_xlabel("X-Axis (mm)", fontsize=11, color="white")
        ax.set_ylabel("Y-Axis (mm)", fontsize=11, color="white")

        if getattr(app, 'max_physical_dim', None) is not None and len(x) > 0:
            cx        = (np.min(x) + np.max(x)) / 2.0
            cy        = (np.min(y) + np.max(y)) / 2.0
            half_span = (app.max_physical_dim / 2.0) * 1.15
            ax.set_xlim([cx - half_span, cx + half_span])
            ax.set_ylim([cy - half_span, cy + half_span])
        ax.set_aspect('equal')

        mismatch = evaluation_result.get('settings_mismatch') or []
        if mismatch:
            names = ", ".join(str(m) for m in mismatch)
            ax.text(0.01, 0.99,
                   f"⚠ Settings changed since export for: {names} — results may not "
                   f"reflect the actual machine run.",
                   transform=ax.transAxes, fontsize=8, color='#ffca28',
                   va='top', ha='left', zorder=15,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1400',
                             edgecolor='#ffca28', alpha=0.85))

        ax.text(0.01, 0.01,
               "Green = all points within tolerance. Red = one or more points failed. "
               "Gray = no matching log data for this hole.",
               transform=ax.transAxes, fontsize=8, color='#888888',
               va='bottom', ha='left', zorder=15)

        app.canvas.draw()

    # ------------------------------------------------------------------
    def highlight_hole(self, global_idx):
        """เรียกจาก ui/main_window.py ตอน hover/click รูใน sidebar ขณะอยู่แท็บ
        Evaluation — ไฮไลต์ marker บน overview เดิม ไม่สลับหน้า (แบบเดียวกับ
        path_mapper_tab.py)"""
        if self._overview_scatter is None:
            return
        local_idx = self._overview_index_map.get(global_idx)
        if local_idx is None:
            return

        self._highlighted_gidx = global_idx
        edge = list(self._overview_base_edge)
        edge[local_idx] = _HILITE_EDGE
        self._overview_scatter.set_edgecolors(edge)
        self.app.canvas.draw_idle()

    def clear_hole_highlight(self):
        if self._overview_scatter is None or self._highlighted_gidx is None:
            return
        self._highlighted_gidx = None
        self._overview_scatter.set_edgecolors(self._overview_base_edge)
        self.app.canvas.draw_idle()
