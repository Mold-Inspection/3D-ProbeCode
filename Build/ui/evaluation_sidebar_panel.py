# ==============================================================================
# ui/evaluation_sidebar_panel.py — Right sidebar แทนที่ "Detected Holes" ปกติ
# ขณะอยู่แท็บ "Evaluation" (§4 ของ PLAN_evaluation-tab-openbuilds-log-
# comparison_v02.md)
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FIX: _on_apply_tolerance() re-runs core.evaluation_engine.evaluate_
#   points() with the new tolerance, whose returned 'holes' dict is keyed
#   by hole_id (display_id string) — same remap needed as ui/evaluation_
#   left_panel.py's v01->v02 fix (see that file's changelog for the full
#   explanation). Reuses the shared _remap_holes_by_gi() helper from
#   there rather than duplicating the logic.
# 
# หน้าที่: แสดงผลตรวจ (app.evaluation_result) แบบ read-only — การ์ดต่อรู
# (เฉพาะรูที่ selected_for_inspection) → ขยายดู segment → ขยายดู layer →
# ขยายดูตารางจุดวัดรายจุด (expected / actual / Δ / pass-fail) พร้อม
# ตัวเลือก "show failed only" (ค่าเริ่มต้น) / "show all points"
#
# ต่างจากการ์ดรูปกติใน ui/main_window.py ตรงที่:
#   - ไม่มี checkbox, ไม่มีปุ่ม "Apply Selection" (อ่านอย่างเดียว)
#   - แสดงเฉพาะรูที่ถูกเลือกไว้สำหรับ inspection (รูอื่นไม่เคยถูกโพรบจริง)
#   - ด้านบนสุดมีช่อง Tolerance (mm) + ปุ่ม Apply แยกต่างหาก
#
# NOTE: เช่นเดียวกับ ui/evaluation_left_panel.py — core/evaluation_engine.py
# ยังไม่ถูกสร้าง ปุ่ม "Apply" tolerance จึง import แบบ lazy และแจ้งเตือน
# อย่างสุภาพถ้ายังไม่มีไฟล์นั้น แทนที่จะทำให้แอปพัง
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _BADGE_PASS/_BADGE_FAIL/_BADGE_NODATA colors ของการ์ดหัวรู
# ==============================================================================
import customtkinter as ctk
import tkinter.messagebox as _mb

from ui.evaluation_left_panel import _remap_holes_by_gi

_COLOR_PASS   = "#1b3a1f"
_COLOR_FAIL   = "#3a1f1f"
_COLOR_NODATA = "#2a2a2a"


class EvaluationSidebarPanel:
    def __init__(self, app):
        self.app = app
        self._built = False
        self._hole_widgets = {}   # gi -> {'is_expanded':bool, 'layer_state': {(gi,seg,layer): {...}}}

    # ------------------------------------------------------------------
    def build(self, parent):
        self.parent = parent
        for w in parent.winfo_children():
            w.destroy()

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(pady=(20, 4), padx=20, fill="x")
        ctk.CTkLabel(header, text="Evaluation Results", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")

        # --- tolerance row ---------------------------------------------
        tol_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=5)
        tol_frame.pack(padx=20, pady=(0, 10), fill="x")
        row = ctk.CTkFrame(tol_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(row, text="Tolerance (mm):", text_color="#b0bec5").pack(side="left")
        self.tol_entry = ctk.CTkEntry(row, width=70)
        self.tol_entry.insert(0, str(getattr(self.app, 'evaluation_tolerance_mm', 0.5)))
        self.tol_entry.pack(side="left", padx=(8, 8))
        ctk.CTkButton(row, text="Apply", width=70, fg_color="#1565c0", hover_color="#1976d2",
                     command=self._on_apply_tolerance).pack(side="left")

        self.warning_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.warning_frame.pack(padx=20, fill="x")

        self.list_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._built = True
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """rebuild ทั้งรายการการ์ด — เรียกทุกครั้งที่เข้าแท็บ Evaluation,
        โหลด .log ใหม่ หรือกด Apply tolerance"""
        if not self._built:
            return
        app = self.app

        for w in self.list_frame.winfo_children():
            w.destroy()
        for w in self.warning_frame.winfo_children():
            w.destroy()
        self._hole_widgets = {}

        result = getattr(app, 'evaluation_result', None)
        if not result:
            ctk.CTkLabel(
                self.list_frame,
                text="No evaluation data yet.\nLoad a .log file from the left panel.",
                text_color="gray", font=ctk.CTkFont(size=12), justify="left"
            ).pack(pady=20, padx=10)
            return

        self._build_warning_banner(result)

        holes_result = result.get('holes', {}) or {}
        any_card = False
        for gi, h in enumerate(app.current_holes):
            if not getattr(h, 'selected_for_inspection', False):
                continue
            info = holes_result.get(gi)
            self._build_hole_card(self.list_frame, gi, h, info)
            any_card = True

        if not any_card:
            ctk.CTkLabel(
                self.list_frame, text="No holes are currently selected for inspection.",
                text_color="gray", font=ctk.CTkFont(size=12)
            ).pack(pady=20, padx=10)

    def _build_warning_banner(self, result: dict):
        mismatch = result.get('settings_mismatch') or []
        if mismatch:
            names = ", ".join(str(m) for m in mismatch)
            ctk.CTkLabel(
                self.warning_frame,
                text=f"⚠ Settings changed since export for: {names}\n"
                     f"Results may not reflect the actual machine run.",
                text_color="#ffca28", font=ctk.CTkFont(size=11, weight="bold"),
                wraplength=380, justify="left",
                fg_color="#1a1400", corner_radius=6
            ).pack(fill="x", pady=(0, 10), ipady=6)
        elif getattr(self.app, 'last_export_snapshot', None) is None:
            ctk.CTkLabel(
                self.warning_frame,
                text="ℹ Settings could not be verified against the actual export — "
                     "results assume the current configuration matches what was run.",
                text_color="#78909c", font=ctk.CTkFont(size=10),
                wraplength=380, justify="left"
            ).pack(fill="x", pady=(0, 10))

    # ------------------------------------------------------------------
    def _bind_hover_recursive(self, widget, on_enter, on_leave):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        for child in widget.winfo_children():
            self._bind_hover_recursive(child, on_enter, on_leave)

    def _build_hole_card(self, parent, gi, hole, info):
        widgets = {'is_expanded': False, 'layer_state': {}}
        self._hole_widgets[gi] = widgets

        item_frame = ctk.CTkFrame(parent, fg_color="transparent")
        item_frame.pack(fill="x", padx=10, pady=4)

        if info is None:
            badge, color = "⚪ no data", _COLOR_NODATA
        elif info.get('passed'):
            badge, color = "✅", _COLOR_PASS
        else:
            badge = f"❌ ({info.get('passed_points', 0)}/{info.get('total_points', 0)} pts)"
            color = _COLOR_FAIL

        btn = ctk.CTkButton(
            item_frame, text=f"Hole {hole.display_id}   {badge}", anchor="w",
            fg_color=color, hover_color=color,
            command=lambda: self._toggle_hole(gi))
        btn.pack(fill="x")
        widgets['btn'] = btn

        def enter(e, g=gi):
            if self.app.current_tab == "Evaluation" and hasattr(self.app, 'evaluation_tab'):
                self.app.evaluation_tab.highlight_hole(g)

        def leave(e):
            if self.app.current_tab == "Evaluation" and hasattr(self.app, 'evaluation_tab'):
                self.app.evaluation_tab.clear_hole_highlight()

        self._bind_hover_recursive(item_frame, enter, leave)

        body = ctk.CTkFrame(item_frame, fg_color="#141822", corner_radius=6)
        widgets['body'] = body

        if info is None:
            ctk.CTkLabel(
                body, text="No matching probe data found for this hole in the log.",
                text_color="#888888", font=ctk.CTkFont(size=11),
                wraplength=280, justify="left"
            ).pack(padx=10, pady=8, anchor="w")
        else:
            ctk.CTkLabel(
                body, text=f"Max deviation: {info.get('max_deviation', 0):.3f} mm",
                text_color="#b0bec5", font=ctk.CTkFont(size=11)
            ).pack(anchor="w", padx=10, pady=(8, 2))
            for seg in info.get('segments', []):
                self._build_segment_block(body, gi, seg)

        if widgets['is_expanded']:
            body.pack(fill="x", pady=(4, 0))

    def _toggle_hole(self, gi):
        widgets = self._hole_widgets.get(gi)
        if widgets is None:
            return
        widgets['is_expanded'] = not widgets['is_expanded']
        if widgets['is_expanded']:
            widgets['body'].pack(fill="x", pady=(4, 0))
        else:
            widgets['body'].pack_forget()

    # ------------------------------------------------------------------
    def _build_segment_block(self, parent, gi, seg: dict):
        seg_idx = seg.get('seg_idx', 0)
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=6, pady=(4, 0))
        ctk.CTkLabel(frame, text=f"Segment {seg_idx + 1}", text_color="#78909c",
                    font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=4)
        for layer in seg.get('layers', []):
            self._build_layer_row(frame, gi, seg_idx, layer)

    def _build_layer_row(self, parent, gi, seg_idx, layer: dict):
        layer_idx = layer.get('layer_idx', 0)
        key = (gi, seg_idx, layer_idx)
        state = self._hole_widgets[gi]['layer_state'].setdefault(
            key, {'expanded': False, 'show_all': False})

        row = ctk.CTkFrame(parent, fg_color="#1c212c", corner_radius=5)
        row.pack(fill="x", padx=4, pady=2)

        badge = "✅" if layer.get('passed') else "❌"
        text = f"{badge} Layer {layer_idx + 1}   max Δ={layer.get('max_deviation', 0):.3f} mm"
        ctk.CTkButton(
            row, text=text, anchor="w",
            fg_color="transparent", hover_color="#2c3348",
            font=ctk.CTkFont(size=11),
            command=lambda: self._toggle_layer(gi, seg_idx, layer_idx)
        ).pack(fill="x", padx=4, pady=4)

        table_frame = ctk.CTkFrame(row, fg_color="transparent")
        state['table_frame'] = table_frame
        state['layer'] = layer
        if state['expanded']:
            table_frame.pack(fill="x", padx=6, pady=(0, 6))
            self._render_point_table(table_frame, gi, seg_idx, layer_idx)

    def _toggle_layer(self, gi, seg_idx, layer_idx):
        key = (gi, seg_idx, layer_idx)
        state = self._hole_widgets[gi]['layer_state'][key]
        state['expanded'] = not state['expanded']
        if state['expanded']:
            state['table_frame'].pack(fill="x", padx=6, pady=(0, 6))
            self._render_point_table(state['table_frame'], gi, seg_idx, layer_idx)
        else:
            state['table_frame'].pack_forget()

    # ------------------------------------------------------------------
    def _render_point_table(self, parent, gi, seg_idx, layer_idx):
        key = (gi, seg_idx, layer_idx)
        state = self._hole_widgets[gi]['layer_state'][key]
        layer = state['layer']

        for w in parent.winfo_children():
            w.destroy()

        points = layer.get('points', [])
        if state['show_all']:
            shown = points
        else:
            shown = [p for p in points if not p.get('passed', True)]
            if not shown:
                # nothing failed in this layer — showing "failed only" would
                # just be an empty table, so fall back to showing everything
                shown = points

        toggle_text = "Show failed only" if state['show_all'] else "Show all points"
        ctk.CTkButton(
            parent, text=toggle_text, width=140, height=22,
            fg_color="#37474f", hover_color="#546e7a", font=ctk.CTkFont(size=10),
            command=lambda: self._toggle_show_all(gi, seg_idx, layer_idx)
        ).pack(anchor="w", pady=(2, 4))

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x")
        for text, w in (("#", 22), ("Expected", 130), ("Actual", 130), ("Δ(mm)", 55), ("", 24)):
            ctk.CTkLabel(header, text=text, text_color="#78909c",
                        font=ctk.CTkFont(size=9, weight="bold"), width=w).pack(side="left")

        for p in shown:
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x")
            exp  = p.get('expected', (0.0, 0.0, 0.0))
            act  = p.get('actual', (0.0, 0.0, 0.0))
            dist = p.get('distance_mm', 0.0)
            ok   = p.get('passed', False)

            ctk.CTkLabel(r, text=str(p.get('point_idx', '?')), width=22,
                        font=ctk.CTkFont(size=9)).pack(side="left")
            ctk.CTkLabel(r, text=f"{exp[0]:.2f},{exp[1]:.2f},{exp[2]:.2f}", width=130,
                        font=ctk.CTkFont(size=9)).pack(side="left")
            ctk.CTkLabel(r, text=f"{act[0]:.2f},{act[1]:.2f},{act[2]:.2f}", width=130,
                        font=ctk.CTkFont(size=9)).pack(side="left")
            ctk.CTkLabel(r, text=f"{dist:.3f}", width=55, font=ctk.CTkFont(size=9),
                        text_color=("#66bb6a" if ok else "#e53935")).pack(side="left")
            ctk.CTkLabel(r, text=("✅" if ok else "❌"), width=24,
                        font=ctk.CTkFont(size=9)).pack(side="left")

        if not points:
            ctk.CTkLabel(parent, text="No points recorded for this layer.",
                        text_color="#666666", font=ctk.CTkFont(size=10)).pack(anchor="w", pady=(4, 0))

    def _toggle_show_all(self, gi, seg_idx, layer_idx):
        key = (gi, seg_idx, layer_idx)
        state = self._hole_widgets[gi]['layer_state'][key]
        state['show_all'] = not state['show_all']
        self._render_point_table(state['table_frame'], gi, seg_idx, layer_idx)

    # ------------------------------------------------------------------
    def _on_apply_tolerance(self):
        app = self.app
        try:
            tol = float(self.tol_entry.get().strip())
            if tol <= 0:
                raise ValueError
        except ValueError:
            _mb.showerror("Invalid Tolerance", "กรุณากรอกค่า tolerance เป็นตัวเลขที่มากกว่า 0")
            return
        app.evaluation_tolerance_mm = tol

        result = getattr(app, 'evaluation_result', None)
        if result is None:
            # nothing to re-run yet — value is stored and will be used the
            # next time a .log is loaded from the left panel
            return

        try:
            from core.evaluation_engine import evaluate_points
        except ImportError as e:
            self.app.notify.show(
                f"core/evaluation_engine.py ยังไม่พร้อมใช้งาน — ค่า tolerance ถูก"
                f"บันทึกไว้แล้ว จะถูกใช้ตอนโหลด .log ครั้งถัดไป ({e})",
                severity="info", duration_ms=6000)
            return

        expected_points = result.get('_expected_points')
        actual_points   = result.get('_actual_points')
        if expected_points is None or actual_points is None:
            _mb.showwarning(
                "Cannot Re-evaluate",
                "ไม่มีข้อมูลจุดดิบให้คำนวณใหม่ กรุณาโหลดไฟล์ .log ใหม่อีกครั้ง")
            return

        try:
            new_result = evaluate_points(expected_points, actual_points, tol)
        except Exception as e:
            _mb.showerror("Evaluation Failed", f"ประเมินผลใหม่ไม่สำเร็จ:\n{e!r}")
            return

        new_result['log_filename']       = result.get('log_filename')
        new_result['tolerance_mm']       = tol
        new_result['settings_mismatch']  = result.get('settings_mismatch', [])
        new_result['_expected_points']   = expected_points
        new_result['_actual_points']     = actual_points

        # v02 FIX: same hole_id -> gi remap as evaluation_left_panel.py's
        # initial load — see that file's v02 changelog.
        _remap_holes_by_gi(new_result, app.current_holes)

        app.evaluation_result = new_result

        self.refresh()
        if hasattr(app, 'evaluation_left_panel'):
            app.evaluation_left_panel.refresh()
        if app.current_tab == "Evaluation":
            app.evaluation_tab.draw_evaluation()
