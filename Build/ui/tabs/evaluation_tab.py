# ==============================================================================
# ui/tabs/evaluation_tab.py — แท็บ "Evaluation" (เทียบผลตรวจจริงจาก .log กับรูที่คาดหวัง)
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FEATURE (Feature 2): กราฟกลางเป็น 3D แทน heat map 2D — CAD wireframe (≤ MAX_TRIS_3D สามเหลี่ยม) + วงผนัง CAD
#   ทุกชั้นที่ตรวจ + จุดที่วัดได้ (เขียว/แดง) เลื่อนจากจุด CAD ตามระยะเบี่ยงจริง × k (ขยายให้เห็น บอกค่า k บนกราฟ)
#   + เส้นรอบรูปที่วัดได้ของแต่ละชั้น; ข้อความเหนือรู = Hole n PASS/FAIL x/y เท่านั้น; ถ้าวาด 3D ไม่ได้ → 2D เดิม
# CHANGE LOG (v01 -> v02):
#   FEATURE (PLAN_evaluation-expected-points-json-and-offset-only_v01.md
#   Requirement 4 — remove Accuracy, report Offset/Failed instead):
#   plot title no longer shows "Overall Accuracy: X%" (that field was
#   removed entirely from core/evaluation_engine.py v02's return dict —
#   see that file's changelog). Replaced with a plain
#   "<failed> / <total> points failed" count sourced from the new
#   'failed_points' / 'total_points' fields. Marker colors (green/red/
#   gray per hole) are unchanged — they were never accuracy-based.
#   No other change — overview drawing, highlight_hole()/
#   clear_hole_highlight(), and all placeholder states are identical
#   to v01.
#
# หน้าที่: วาด overview 2D (mesh background + hole markers) ของแท็บ Evaluation
# — ตรวจว่าแต่ละรูที่ถูกโพรบจริง (จากไฟล์ .log ของ OpenBuilds Control หรือ
# จากไฟล์ Expected Points .json ที่โหลดไว้ล่วงหน้า — ดู
# ui/evaluation_left_panel.py v03) ตรงกับตำแหน่งที่คำนวณไว้จาก STEP ภายใน
# tolerance ที่ผู้ใช้กำหนดหรือไม่ — สีของแต่ละรูบอกผลรวมของรูนั้น
# (เขียว = ผ่านทุกจุด, แดง = มีจุดไม่ผ่าน, เทา = ยังไม่มีผลตรวจ/รูถูกข้าม)
#
# EXPECTED CONTRACT — app.evaluation_result (สร้างโดย
# core/evaluation_engine.py::evaluate_points(), remapped by
# ui/evaluation_left_panel.py::_remap_holes_by_gi()) เป็น dict ว่าง None
# ถ้ายังไม่ได้โหลด .log, หรือมีรูปแบบดังนี้เมื่อโหลดแล้ว:
#   {
#     'tolerance_mm':      float,   # ค่า tolerance ที่ใช้ประเมินผลรอบล่าสุด
#     'log_filename':      str,     # ชื่อไฟล์ .log ที่โหลด
#     'total_points':      int,
#     'passed_points':     int,
#     'failed_points':     int,     # v02 — total_points - passed_points
#     'failed_point_refs': [ {hole_id, seg_idx, layer_idx, point_idx,
#                              offset_mm}, ... ],   # v02, flat list
#     'expected_source':   'live' | 'json',   # v02 (from left panel v03)
#     'settings_mismatch': [hole_display_id, ...],  # รูที่ค่า setting ไม่ตรงกับตอน export
#     'holes': {
#         <global_idx into app.current_holes>: {
#             'display_id':    str/int,
#             'passed':        bool,   # True เฉพาะเมื่อทุกจุดของรูนี้ผ่าน
#             'total_points':  int,
#             'passed_points': int,
#             'max_deviation': float,  # mm, ระยะเบี่ยงเบน/offset สูงสุดของรูนี้
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
#                                     'distance_mm': float,   # "Offset (mm)"
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
#   NOTE (v02): 'overall_accuracy' no longer exists anywhere in this
#   contract — removed per Requirement 4. Do not reintroduce a percentage
#   anywhere in this file.
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _PASS_FACE / _PASS_EDGE   = สี marker ของรูที่ "ผ่าน" ทั้งหมด
#   _FAIL_FACE / _FAIL_EDGE   = สี marker ของรูที่ "ไม่ผ่าน" (มีอย่างน้อย 1 จุด)
#   _NODATA_FACE / _NODATA_EDGE = สี marker ของรูที่ยังไม่มีผลตรวจจับคู่ได้
# ==============================================================================
import numpy as np
import matplotlib.pyplot as plt

from ui import theme

_PASS_FACE    = '#66bb6a'
_PASS_EDGE    = '#43a047'
_FAIL_FACE    = '#e53935'
_FAIL_EDGE    = '#ff8a80'
_NODATA_FACE  = '#555555'
_NODATA_EDGE  = '#888888'
_HILITE_EDGE  = '#ffee58'
MAX_TRIS_3D   = 2500   # v03: สามเหลี่ยม CAD สูงสุดในกราฟ 3D (มาก = ละเอียดแต่หมุนช้า)


class EvaluationTab:
    def __init__(self, app):
        self.app = app
        self._overview_scatter   = None
        self._overview_index_map = {}   # {global_idx (into app.current_holes): local scatter index}
        self._overview_base_face = []
        self._overview_base_edge = []
        self._highlighted_gidx   = None
        self._hole_artists       = {}   # v03: gi -> {'scatter': [...], 'text': Text}

    # ------------------------------------------------------------------
    def draw_evaluation(self):
        """Entry point เรียกจาก ui/main_window.py::on_nav_change() เมื่อสลับมาแท็บ
        Evaluation"""
        app = self.app
        app.fig.clf()
        app.ax = app.fig.add_subplot(111, facecolor=theme.c(theme.PLOT_AX))
        app.fig.subplots_adjust(left=0.08, right=0.97, bottom=0.08, top=0.90)

        self._overview_scatter   = None
        self._overview_index_map = {}
        self._overview_base_face = []
        self._overview_base_edge = []
        self._highlighted_gidx   = None
        self._hole_artists       = {}

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
                "Load an OpenBuilds Control .log file from the left panel to \n"
                "compare it against the expected probe points.")
            return

        try:
            self._draw_3d(evaluation_result)   # v03
        except Exception as e:
            print(f"[evaluation_tab] 3D view failed, using 2D: {e!r}")
            app.fig.clf()
            app.ax = app.fig.add_subplot(111, facecolor=theme.c(theme.PLOT_AX))
            self._hole_artists = {}
            self._draw_overview(evaluation_result)

    # ------------------------------------------------------------------
    def _draw_placeholder(self, icon: str, message: str):
        app = self.app
        app.ax.set_xlim(0, 1)
        app.ax.set_ylim(0, 1)
        app.ax.set_axis_off()

        app.ax.add_patch(plt.Rectangle((0.05, 0.1), 0.9, 0.8,
                          linewidth=1.5, edgecolor=theme.c(theme.ACCENT),
                          facecolor=theme.c(theme.BG_PANEL), zorder=1))

        app.ax.text(0.5, 0.58, icon, fontsize=42, ha='center', va='center',
                    transform=app.ax.transAxes, zorder=2)
        app.ax.text(0.5, 0.46, message, fontsize=12, color=theme.c(theme.TEXT_MUTED),
                    ha='center', va='center', wrap=True,
                    transform=app.ax.transAxes, zorder=2)

        app.canvas.draw()

    # ------------------------------------------------------------------
    def _work_mesh(self):
        """v03: (vertices, faces) ของ CAD ในพิกัดงาน (เดียวกับจุดใน Schema/log): หมุนตามมุมมอง − Work zero
        ลดจำนวนสามเหลี่ยมเหลือ ≤ MAX_TRIS_3D (หมุนกราฟได้ลื่น — วัดไว้ ~160 ms/ภาพที่ 2k)"""
        app = self.app
        from core.projector import view_rotation_matrix
        from core.work_zero import machining_origin
        rot = view_rotation_matrix(app.current_view, app.screen_rotation)
        org = machining_origin(app, app.current_view, app.screen_rotation)
        v = np.asarray(app.geo.mesh.vertices, dtype=float) @ rot.T - org
        f = np.asarray(app.geo.mesh.faces)
        step = max(1, len(f) // MAX_TRIS_3D)
        return v, f[::step]

    @staticmethod
    def _nice_scale(max_dev: float, size: float) -> int:
        """ตัวคูณขยายระยะเบี่ยงให้มองเห็น: max |dev| × k ≈ 25 % ของขนาดรู (ปัดเป็น 1/2/5/10/…)"""
        if not max_dev or max_dev <= 0:
            return 1
        want = 0.25 * size / max_dev
        for k in (1, 2, 5, 10, 20, 50, 100, 200):
            if k >= want * 0.7:
                return k
        return 200

    def _draw_3d(self, evaluation_result: dict):
        """v03: กราฟ 3D แทน heat map — CAD (wireframe จาง + วงผนัง CAD ทุกชั้นที่ตรวจ) + จุดที่วัดได้
        สีเขียว/แดงต่อจุด เลื่อนออกจากจุด CAD ตามระยะเบี่ยงจริง × k (ขยายให้เห็น) พร้อมเส้นเชื่อม
        และเส้นรอบรูปที่วัดได้ของแต่ละชั้น (× k) — ข้อความเหนือรูแสดงเฉพาะผลสำคัญ"""
        app = self.app
        app.fig.clf()
        app.fig.subplots_adjust(left=0.0, right=1.0, top=0.93, bottom=0.05)
        ax = app.fig.add_subplot(111, projection='3d', facecolor=theme.VIEW3D_BG)
        app.ax = ax
        holes_result = evaluation_result.get('holes', {}) or {}

        v, f = self._work_mesh()
        tri = v[f]
        nan = np.full((len(f), 1), np.nan)
        ax.plot(np.hstack([tri[:, [0, 1, 2, 0], 0], nan]).ravel(), np.hstack([tri[:, [0, 1, 2, 0], 1], nan]).ravel(),
                np.hstack([tri[:, [0, 1, 2, 0], 2], nan]).ravel(), color="#4f6d8f", linewidth=0.5, alpha=0.35)

        pts_all = [(gi, lyr, p) for gi, info in holes_result.items() for s in info.get('segments', [])
                   for lyr in s.get('layers', []) for p in lyr.get('points', [])]
        max_dev = max((abs(float(p.get('dev', p.get('distance_mm', 0.0)) or 0.0)) for _g, _l, p in pts_all), default=0.0)
        sizes = [lyr['circle']['nominal_diameter'] / 2 for _g, lyr, _p in pts_all if lyr.get('circle')] or [5.0]
        k = self._nice_scale(max_dev, float(np.median(sizes)))
        self._scale = k

        self._hole_artists = {}
        gidx = {gi: h for gi, h in enumerate(app.current_holes)}
        for gi, info in holes_result.items():
            ok_h = bool(info.get('passed'))
            arts = {'scatter': [], 'text': None}
            top = None
            for s in info.get('segments', []):
                for lyr in s.get('layers', []):
                    pts = lyr.get('points', [])
                    if not pts:
                        continue
                    E = np.array([p['expected'] for p in pts], dtype=float)
                    A = np.array([p['actual'] for p in pts], dtype=float)
                    M = E + k * (A - E)
                    c = lyr.get('circle')
                    if c:   # วงผนัง CAD ของชั้นนี้ (จาก fit จุด CAD — ตรงกับผิว CAD)
                        cc, r = np.asarray(c['nominal_center'], dtype=float), c['nominal_diameter'] / 2
                        t = np.linspace(0, 2 * np.pi, 73)
                        ax.plot(cc[0] + r * np.cos(t), cc[1] + r * np.sin(t), np.full_like(t, cc[2]),
                                color="#cfd8e3", linewidth=1.0, alpha=0.9)
                        cen = cc
                    else:
                        cen = E.mean(axis=0)
                        o = np.argsort(np.arctan2(E[:, 1] - cen[1], E[:, 0] - cen[0]))
                        ax.plot(*np.vstack([E[o], E[o[:1]]]).T, color="#cfd8e3", linewidth=1.0, alpha=0.9)
                    o = np.argsort(np.arctan2(M[:, 1] - cen[1], M[:, 0] - cen[0]))   # รูปร่างที่วัด (× k)
                    ax.plot(*np.vstack([M[o], M[o[:1]]]).T, color=_PASS_FACE if lyr.get('passed') else _FAIL_FACE,
                            linewidth=1.2, alpha=0.85, linestyle='--')
                    for e, m_ in zip(E, M):
                        ax.plot(*np.vstack([e, m_]).T, color="#e6e9ed", linewidth=0.8, alpha=0.7)
                    col = [_PASS_FACE if p.get('passed') else _FAIL_FACE for p in pts]
                    ax.scatter(*E.T, s=10, c="#cfd8e3", depthshade=False)
                    arts['scatter'].append(ax.scatter(*M.T, s=42, c=col, edgecolors="#111", linewidths=0.6,
                                                      depthshade=False))
                    top = max(top if top is not None else -1e9, float(E[:, 2].max()))
                    arts['xy'] = (float(cen[0]), float(cen[1]))
            if top is not None:
                x, y = arts['xy']
                _nf = info.get('total_points', 0) - info.get('passed_points', 0)
                lbl = (f"Hole {info.get('display_id', gidx.get(gi) and gidx[gi].display_id)}  "
                       + (f"PASS" if ok_h else
                          f"FAIL {_nf} pt{'s' if _nf != 1 else ''}"))
                arts['text'] = ax.text(x, y, 1.5, lbl, color=_PASS_FACE if ok_h else _FAIL_FACE, fontsize=10,
                                       weight='bold', ha='center', va='bottom', zorder=20)
                arts['base_color'] = _PASS_FACE if ok_h else _FAIL_FACE
            self._hole_artists[gi] = arts

        lo, hi = v.min(axis=0), v.max(axis=0)
        span = hi - lo
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], max(hi[2], 2.0))
        try:
            ax.set_box_aspect((span[0], span[1], max(span[2], 2.0)))
        except Exception:
            pass
        ax.view_init(elev=28, azim=-60)
        for a in (ax.xaxis, ax.yaxis, ax.zaxis):
            a.set_pane_color((0, 0, 0, 0))
            a.label.set_color(theme.VIEW3D_MUTED)
        ax.tick_params(colors=theme.VIEW3D_MUTED, labelsize=7)
        ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)"); ax.set_zlabel("Z (mm)")

        n_pass = sum(1 for i in holes_result.values() if i.get('passed'))
        n_fail = len(holes_result) - n_pass
        tot, pas = evaluation_result.get('total_points'), evaluation_result.get('passed_points')
        app.fig.suptitle(f"Evaluation 3D — {n_pass} hole(s) passed, {n_fail} failed  |  {(tot or 0) - (pas or 0)} of {tot} points failed"
                         f"  |  deviation shown ×{k}", fontsize=12, color=theme.VIEW3D_TEXT)
        app.fig.text(0.01, 0.01, f"Grey circle = CAD wall at each probed layer · dot = measured point moved away from its "
                     f"CAD point by the real deviation × {k} (green pass / red fail) · dashed = measured outline × {k}",
                     fontsize=8, color=theme.VIEW3D_MUTED, ha='left', va='bottom')
        mismatch = evaluation_result.get('settings_mismatch') or []
        if mismatch:
            app.fig.text(0.01, 0.96, f"⚠ Settings changed since export for: {', '.join(str(m) for m in mismatch)}",
                         fontsize=8, color='#ffca28', ha='left', va='top')
        app.canvas.draw()

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
                sub = f"{info.get('total_points', 0) - info.get('passed_points', 0)} fail"
                ax.text(h.x, h.y - 4, sub, color=_FAIL_FACE, fontsize=7,
                        ha='center', va='top', zorder=6)

        self._overview_scatter   = scatter
        self._overview_base_face = list(face_colors)
        self._overview_base_edge = list(edge_colors)
        self._overview_index_map = {gidx_of[id(h)]: i for i, h in enumerate(selected_holes)}

        # v02: no more "Overall Accuracy: X%" — replaced with a plain
        # failed/total points count sourced from evaluation_engine v02's
        # 'failed_points' field (Requirement 4).
        failed_pts = evaluation_result.get('failed_points')
        total_pts  = evaluation_result.get('total_points')
        passed_pts = evaluation_result.get('passed_points',
                                           (total_pts or 0) - (failed_pts or 0))
        pts_tag    = f"  |  {passed_pts} / {total_pts} points passed" if total_pts else ""
        ax.set_title(
            f"Evaluation — {pass_count} passed, {fail_count} failed, "
            f"{nodata_count} no data{pts_tag}",
            fontsize=13, color=theme.c(theme.TEXT))
        ax.grid(True, linestyle='--', alpha=0.3, color=theme.c(theme.PLOT_GRID))
        ax.set_xlabel("X-Axis (mm)", fontsize=11, color=theme.c(theme.TEXT))
        ax.set_ylabel("Y-Axis (mm)", fontsize=11, color=theme.c(theme.TEXT))

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
        arts = (self._hole_artists or {}).get(global_idx)   # v03: กราฟ 3D
        if arts is not None:
            self._highlighted_gidx = global_idx
            if arts.get('text') is not None:
                arts['text'].set_color(_HILITE_EDGE)
            for sc in arts['scatter']:
                sc.set_edgecolors(_HILITE_EDGE); sc.set_linewidths(1.6)
            self.app.canvas.draw_idle()
            return
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
        arts = (self._hole_artists or {}).get(self._highlighted_gidx)   # v03: กราฟ 3D
        if arts is not None:
            if arts.get('text') is not None:
                arts['text'].set_color(arts.get('base_color', _PASS_FACE))
            for sc in arts['scatter']:
                sc.set_edgecolors("#111"); sc.set_linewidths(0.6)
            self._highlighted_gidx = None
            self.app.canvas.draw_idle()
            return
        if self._overview_scatter is None or self._highlighted_gidx is None:
            return
        self._highlighted_gidx = None
        self._overview_scatter.set_edgecolors(self._overview_base_edge)
        self.app.canvas.draw_idle()
