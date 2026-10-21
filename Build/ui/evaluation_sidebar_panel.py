# ==============================================================================
# ui/evaluation_sidebar_panel.py — Right sidebar แทนที่ "Detected Holes" ปกติ
# ขณะอยู่แท็บ "Evaluation" (§4 ของ PLAN_evaluation-tab-openbuilds-log-
# comparison_v02.md)
# ==============================================================================
# VERSION: 09
# CHANGE LOG (v08 -> v09):
#   Best-fit centre: การ์ดรูแสดงระยะที่เลื่อน (ตำแหน่งรูเยื้องจาก CAD) + Apply tolerance ส่ง best_fit
# CHANGE LOG (v07 -> v08):
#   เตือนจากเรขาคณิต: ชั้นที่ลึกกว่า probe_profile.shaft_contact_depth() → "ก้านอาจแตะขอบปากรูก่อน
#   หัวโพรบ" ที่หัวการ์ดรูและหัวชั้น (เตือนเท่านั้น ไม่ตัดจุด)
# CHANGE LOG (v06 -> v07):
#   จุดที่ก้านโพรบอาจแตะผนัง: สีผ่าน/ไม่ผ่านตามปกติ + ⚠ ท้ายแถว (เตือนเท่านั้น ไม่ตัดออก)
# CHANGE LOG (v05 -> v06):
#   จุดที่สงสัยก้านโพรบชน (core/evaluation_engine.py v09 — p['suspect']) แสดงสีเทา ⚠ ไม่นับผ่าน/
#   ไม่ผ่าน; หัวชั้นบอก "shaft contact?" + ผนังเลื่อนเทียบชั้นบน; การ์ดรูบอกจำนวนจุดที่ตัดออก
# CHANGE LOG (v04 -> v05):
#   FIX (layout): warning_frame ว่าง (CTkFrame สูง 200 px โดยปริยาย) ถูก pack ไว้เสมอ
#   ดันการ์ดรูลงไปกลางจอ — ตอนนี้ pack เฉพาะเมื่อมีข้อความ การ์ดแรกอยู่ใต้ Tolerance 5 px
#   FEATURE: เตือนให้กรอก Caliper depth — รูที่มีพื้นแต่โพรบไม่ได้แตะพื้นและยังไม่มีค่า:
#   แบนเนอร์สีส้มใต้ Tolerance (+ ปุ่ม 'Fill in ▸' เปิดการ์ดและโฟกัสช่องกรอก),
#   แท็ก '⚠ caliper depth' บนหัวการ์ด, กรอบช่องกรอกสีส้ม + '(required)' และสรุป
#   'Depth checked x / y holes' ที่แผงซ้าย — หายเองเมื่อกรอกครบ
# CHANGE LOG (v03 -> v04):
#   FEATURE: ส่วน "Depth" ในการ์ดรู — ความลึกสูงสุดตาม CAD (ถึงพื้น หรือรูทะลุ + ช่วงของ
#   แต่ละ segment), ความลึกพื้นที่โพรบวัดได้ (เมื่อเปิด Z trigger) และช่องกรอกค่าจาก
#   เวอร์เนียร์ (เทียบกับ CAD ด้วย tolerance เดียวกัน, จำค่าไว้ต่อไฟล์ STEP ใน
#   settings.json) — แสดงได้แม้ยังไม่ได้โหลด .log (การ์ดขึ้น "no data")
#   หัวการ์ดแสดงความลึก (↧) ด้วย
# CHANGE LOG (v02 -> v03):
#   FEATURE (PLAN_evaluation-expected-points-json-and-offset-only_v01.md
#   Requirement 5 — "แสดงผลลัพธ์...ให้อะไรที่ผ่าน threshold เป็นสีเขียว
#   ไม่ผ่านเป็นสีแดง โดยให้บอกค่าที่วัดได้ และค่าในอุดมคติ และบอกความต่าง"):
#     - Point table columns renamed: "Expected"->"Ideal", "Actual"->
#       "Measured", "Δ(mm)"->"Offset(mm)" (wording only — same underlying
#       fields, core/evaluation_engine.py's 'expected'/'actual'/
#       'distance_mm' are unchanged).
#     - Each point row now gets an explicit GREEN/RED background
#       (fg_color on the row frame), not just text color on the offset
#       column, so pass/fail reads at a glance per Requirement 5.
#     - "Max deviation" label renamed "Max Offset" for wording
#       consistency with the rest of the plan (same value/field).
#   NOTE (Requirement 6 — single failing point fails the whole hole):
#   already correct upstream in core/evaluation_engine.py (hole_entry
#   ['passed'] requires ALL points to pass) — this file only renders
#   what evaluate_points() already computed; see the comment on
#   _build_hole_card() below. No logic change needed here.
#   No other functional change — hole card badges, layer rows, and the
#   tolerance apply flow are unchanged from v02.
#
# หน้าที่: แสดงผลตรวจ (app.evaluation_result) แบบ read-only — การ์ดต่อรู
# (เฉพาะรูที่ selected_for_inspection) → ขยายดู segment → ขยายดู layer →
# ขยายดูตารางจุดวัดรายจุด (ideal / measured / offset / pass-fail) พร้อม
# ตัวเลือก "show failed only" (ค่าเริ่มต้น) / "show all points"
#
# ต่างจากการ์ดรูปกติใน ui/main_window.py ตรงที่:
#   - ไม่มี checkbox, ไม่มีปุ่ม "Apply Selection" (อ่านอย่างเดียว)
#   - แสดงเฉพาะรูที่ถูกเลือกไว้สำหรับ inspection (รูอื่นไม่เคยถูกโพรบจริง)
#   - ด้านบนสุดมีช่อง Tolerance (mm) + ปุ่ม Apply แยกต่างหาก
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _BADGE_PASS/_BADGE_FAIL/_BADGE_NODATA colors ของการ์ดหัวรู
#   _ROW_PASS/_ROW_FAIL colors ของพื้นหลังแถวจุดวัดรายจุด (v03)
# ==============================================================================
import customtkinter as ctk
import numpy as np
import tkinter.messagebox as _mb

from core import user_settings
from core.evaluation_engine import _hole_fingerprint
from core.models import hole_floor_depth
from ui.evaluation_left_panel import _remap_holes_by_gi
from ui import theme

_COLOR_PASS   = theme.OK_FILL
_COLOR_FAIL   = theme.ERR_FILL
_COLOR_NODATA = theme.BTN_SECONDARY

# v03 — per-point row background (Requirement 5: green pass / red fail)
_ROW_PASS = theme.OK_BG
_ROW_FAIL = theme.ERR_BG


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
        tol_frame = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS)
        tol_frame.pack(padx=20, pady=(0, 5), fill="x")   # v05: การ์ดแรกอยู่ใต้ Tolerance 5 px
        row = ctk.CTkFrame(tol_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(row, text="Tolerance (mm):", text_color=theme.TEXT_SECONDARY).pack(side="left")
        self.tol_entry = ctk.CTkEntry(row, width=70)
        self.tol_entry.insert(0, str(getattr(self.app, 'evaluation_tolerance_mm', 0.5)))
        self.tol_entry.pack(side="left", padx=(8, 8))
        ctk.CTkButton(row, text="Apply", width=70, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                     command=self._on_apply_tolerance).pack(side="left")

        # v05: pack เฉพาะเมื่อมีข้อความเตือน (_pack_warning_frame)
        self.warning_frame = ctk.CTkFrame(parent, fg_color="transparent", height=1)
        self._depth_banner = None

        # corner_radius=0: ขอบโค้งด้านในของ CTkScrollableFrame เว้นที่ว่างด้านบนอีก ~9 px
        self.list_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

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
        self._depth_banner = None
        self._hole_widgets = {}

        result = getattr(app, 'evaluation_result', None)
        if not result:
            # v04: ยังแสดงการ์ดรูได้ (ส่วน Depth + กรอกค่าเวอร์เนียร์) แม้ยังไม่มี .log
            ctk.CTkLabel(
                self.list_frame,
                text="No probe data yet — load or record a .log from the left panel.\n"
                     "Hole depths (CAD) and caliper entries are below.",
                text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=11), justify="left"
            ).pack(pady=(10, 6), padx=10, anchor="w")
        else:
            self._build_warning_banner(result)

        holes_result = (result or {}).get('holes', {}) or {}
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
                text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=12)
            ).pack(pady=20, padx=10)
        self._update_depth_prompts()   # v05: แบนเนอร์ความลึก + แสดง/ซ่อนพื้นที่เตือน

    def _build_warning_banner(self, result: dict):
        # v03: the §6 stale-settings guard has nothing to warn about when
        # expected points came from a loaded JSON (it IS the frozen
        # source of truth) — ui/evaluation_left_panel.py already forces
        # settings_mismatch = [] in that case, so this banner naturally
        # stays silent for JSON-sourced results without any extra check
        # needed here.
        mismatch = result.get('settings_mismatch') or []
        if mismatch:
            names = ", ".join(str(m) for m in mismatch)
            ctk.CTkLabel(
                self.warning_frame,
                text=f"⚠ Settings changed since export for: {names}\n"
                     f"Results may not reflect the actual machine run.",
                text_color=theme.WARN_TEXT, font=ctk.CTkFont(size=11, weight="bold"),
                wraplength=380, justify="left",
                fg_color=theme.WARN_BG, corner_radius=6
            ).pack(fill="x", pady=(0, 5), ipady=6)
        elif result.get('expected_source') != 'json' and getattr(self.app, 'last_export_snapshot', None) is None:
            ctk.CTkLabel(
                self.warning_frame,
                text="ℹ Settings could not be verified against the actual export — "
                     "results assume the current configuration matches what was run.",
                text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=10),
                wraplength=380, justify="left"
            ).pack(fill="x", pady=(0, 5))

    # ------------------------------------------------------------------
    def _bind_hover_recursive(self, widget, on_enter, on_leave):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        for child in widget.winfo_children():
            self._bind_hover_recursive(child, on_enter, on_leave)

    def _build_hole_card(self, parent, gi, hole, info):
        """v03 note (Requirement 6): 'info.get(\"passed\")' below comes
        straight from core/evaluation_engine.py's hole_entry['passed'],
        which is True only if EVERY point of this hole passed — a single
        failing point already flips this to False (and the badge to ❌)
        upstream. Nothing in this file needs to re-check that rule."""
        widgets = {'is_expanded': False, 'layer_state': {}}
        self._hole_widgets[gi] = widgets

        item_frame = ctk.CTkFrame(parent, fg_color="transparent")
        item_frame.pack(fill="x", padx=10, pady=(0, 8))   # v05: ชิดด้านบน

        if info is None:
            badge, color = "⚪ no data", _COLOR_NODATA
        elif info.get('passed'):
            badge, color = "✅", _COLOR_PASS
        else:
            badge = f"❌ ({info.get('passed_points', 0)}/{info.get('total_points', 0)} pts)"
            color = _COLOR_FAIL
        if info is not None and info.get('suspect_points'):   # v06: ก้านโพรบชน — ไม่นับ
            badge += f"  ⚠{info['suspect_points']} stylus?"

        # v08: ชั้นที่ลึกเกินจุดที่ก้านโพรบแตะขอบปากรู (คำนวณจากเรขาคณิต)
        crit = self.app.probe_profile.shaft_contact_depth()
        try:
            from core.gcode_generator import layer_depths
            depths = layer_depths(hole)
        except Exception as e:
            print(f"[evaluation_sidebar_panel] layer depths failed: {e!r}")
            depths = {}
        risky = sorted(i for i, d in depths.items() if crit is not None and d > crit)
        widgets.update(layer_depths=depths, shaft_crit=crit)
        if risky:
            badge += f"  ⚠ stylus L{','.join(str(i + 1) for i in risky)}"

        floor, length, _parts = self._depth_info(hole)   # v04: ความลึกบนหัวการ์ด
        depth_tag = (f"   ↧{floor:.2f}" if floor is not None else
                     f"   ↧{length:.2f} thru" if length is not None else "")
        btn = ctk.CTkButton(
            item_frame, text=f"Hole {hole.display_id}   {badge}{depth_tag}", anchor="w",
            fg_color=color, hover_color=color,
            command=lambda: self._toggle_hole(gi))
        btn.pack(fill="x")
        widgets['btn'] = btn
        widgets['btn_text'] = f"Hole {hole.display_id}   {badge}{depth_tag}"   # v05
        widgets.update(hole=hole, floor=floor, fp=_hole_fingerprint(hole),
                       probed_floor=bool((info or {}).get('floor')))

        def enter(e, g=gi):
            if self.app.current_tab == "Evaluation" and hasattr(self.app, 'evaluation_tab'):
                self.app.evaluation_tab.highlight_hole(g)

        def leave(e):
            if self.app.current_tab == "Evaluation" and hasattr(self.app, 'evaluation_tab'):
                self.app.evaluation_tab.clear_hole_highlight()

        self._bind_hover_recursive(item_frame, enter, leave)

        body = ctk.CTkFrame(item_frame, fg_color=theme.BG_INPUT, corner_radius=6)
        widgets['body'] = body
        self._build_depth_block(body, hole, info, gi)   # v04

        if info is None:
            ctk.CTkLabel(
                body, text=("No matching probe data found for this hole in the log."
                            if getattr(self.app, 'evaluation_result', None) else "No probe data yet."),
                text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=11),
                wraplength=280, justify="left"
            ).pack(padx=10, pady=8, anchor="w")
        else:
            ctk.CTkLabel(
                body, text=f"Max Offset: {info.get('max_deviation', 0):.3f} mm",   # v03: was "Max deviation"
                text_color=theme.TEXT_SECONDARY, font=ctk.CTkFont(size=11)
            ).pack(anchor="w", padx=10, pady=(8, 2))
            bf = info.get('best_fit_offset')   # v09: ตำแหน่งรูจริงเยื้องจาก CAD = −(การเลื่อน)
            if bf:
                d = (bf[0] ** 2 + bf[1] ** 2 + bf[2] ** 2) ** 0.5
                ctk.CTkLabel(
                    body, text=(f"Best-fit centre: hole is {d:.3f} mm from CAD position\n"
                                f"(ΔX {-bf[0]:+.3f}  ΔY {-bf[1]:+.3f}  ΔZ {-bf[2]:+.3f}) — not counted"),
                    text_color=theme.WARN_TEXT, font=ctk.CTkFont(size=11), justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 2))
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
        ctk.CTkLabel(frame, text=f"Segment {seg_idx + 1}", text_color=theme.TEXT_MUTED,
                    font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=4)
        for layer in seg.get('layers', []):
            self._build_layer_row(frame, gi, seg_idx, layer)

    def _build_layer_row(self, parent, gi, seg_idx, layer: dict):
        layer_idx = layer.get('layer_idx', 0)
        key = (gi, seg_idx, layer_idx)
        state = self._hole_widgets[gi]['layer_state'].setdefault(
            key, {'expanded': False, 'show_all': False})

        row = ctk.CTkFrame(parent, fg_color=theme.BG_CARD_HOVER, corner_radius=5)
        row.pack(fill="x", padx=4, pady=2)

        badge = "✅" if layer.get('passed') else "❌"
        text = f"{badge} Layer {layer_idx + 1}   max offset={layer.get('max_deviation', 0):.3f} mm"
        hw = self._hole_widgets[gi]
        depth = (hw.get('layer_depths') or {}).get(layer_idx)
        crit = hw.get('shaft_crit')
        if depth is not None:
            text += f"   depth {depth:.1f}"
        if depth is not None and crit is not None and depth > crit:   # v08: คำนวณจากเรขาคณิต
            text += (f"\n   ⚠ deeper than {crit:.1f} mm: the stylus shaft"
                     f"\n      may touch the hole edge before the ball tip"
                     f"\n      triggers — this layer may be off")
        if layer.get('shaft_suspect'):   # v06: ผนังเข้ามาใกล้กว่าชั้นบน — ก้านแตะก่อนลูกบอล
            text += (f"\n   ⚠ stylus shaft may touch the wall instead of the ball tip"
                     f"\n      (walls {layer.get('wall_shift', 0):+.2f} mm vs top layer) — values may be off")
        ctk.CTkButton(
            row, text=text, anchor="w",
            fg_color="transparent", hover_color=theme.SELECT_BG, text_color=theme.TEXT,
            font=ctk.CTkFont(size=11),
            command=lambda: self._toggle_layer(gi, seg_idx, layer_idx)
        ).pack(fill="x", padx=4, pady=4)

        circ = layer.get('circle')   # least-squares circle fit ของชั้นนี้ (เฉพาะรูกลม)
        if circ:
            rnd = circ.get('roundness')
            raw_d = circ.get('raw_center_diameter')
            lines = [
                f"⌀ {circ['measured_diameter']:.3f}  (CAD {circ['nominal_diameter']:.3f}, "
                f"{circ['diameter_error']:+.3f})",
                f"Centre offset {circ['center_offset']:.3f}   Roundness "
                + (f"{rnd:.3f}" if rnd is not None else "n/a (needs ≥ 4 pts)"),
            ]
            if raw_d is not None:
                lines.append(f"Ball-centre ⌀ {raw_d:.3f} (for tip calibration)")
            ctk.CTkLabel(
                row, text="\n".join(lines), anchor="w", justify="left",
                text_color=theme.OK_TEXT if circ.get('passed') else theme.ERR_TEXT,
                font=ctk.CTkFont(family=theme.FONT_MONO, size=10)
            ).pack(fill="x", padx=12, pady=(0, 6))

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
            fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER, font=ctk.CTkFont(size=10),
            command=lambda: self._toggle_show_all(gi, seg_idx, layer_idx)
        ).pack(anchor="w", pady=(2, 4))

        # v03: "Expected"/"Actual"/"Δ(mm)" -> "Ideal"/"Measured"/"Offset(mm)"
        # (Requirement 5 wording — same underlying fields, display only)
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x")
        for text, w in (("#", 22), ("Ideal", 130), ("Measured", 130), ("Offset(mm)", 68), ("", 24)):
            ctk.CTkLabel(header, text=text, text_color=theme.TEXT_MUTED,
                        font=ctk.CTkFont(size=9, weight="bold"), width=w).pack(side="left")

        for p in shown:
            exp  = p.get('expected', (0.0, 0.0, 0.0))
            act  = p.get('actual', (0.0, 0.0, 0.0))
            dist = p.get('distance_mm', 0.0)
            ok   = p.get('passed', False)
            sus  = bool(p.get('suspect'))   # v06: ก้านชน — ไม่นับ

            # v03: explicit green/red ROW background (Requirement 5),
            # not just text color on the offset column.
            row_color = _ROW_PASS if ok else _ROW_FAIL
            r = ctk.CTkFrame(parent, fg_color=row_color, corner_radius=3)
            r.pack(fill="x", pady=1)

            ctk.CTkLabel(r, text=str(p.get('point_idx', '?')), width=22,
                        font=ctk.CTkFont(size=9)).pack(side="left", pady=2)
            ctk.CTkLabel(r, text=f"{exp[0]:.2f},{exp[1]:.2f},{exp[2]:.2f}", width=130,
                        font=ctk.CTkFont(size=9)).pack(side="left", pady=2)
            ctk.CTkLabel(r, text=f"{act[0]:.2f},{act[1]:.2f},{act[2]:.2f}", width=130,
                        font=ctk.CTkFont(size=9)).pack(side="left", pady=2)
            ctk.CTkLabel(r, text=f"{dist:.3f}", width=68, font=ctk.CTkFont(size=9, weight="bold"),
                        text_color=(theme.OK_TEXT if ok else theme.ERR_TEXT)
                        ).pack(side="left", pady=2)
            ctk.CTkLabel(r, text=("✅" if ok else "❌") + ("⚠" if sus else ""), width=24,
                        font=ctk.CTkFont(size=9)).pack(side="left", pady=2)

        if not points:
            ctk.CTkLabel(parent, text="No points recorded for this layer.",
                        text_color=theme.TEXT_FAINT, font=ctk.CTkFont(size=10)).pack(anchor="w", pady=(4, 0))

    def _toggle_show_all(self, gi, seg_idx, layer_idx):
        key = (gi, seg_idx, layer_idx)
        state = self._hole_widgets[gi]['layer_state'][key]
        state['show_all'] = not state['show_all']
        self._render_point_table(state['table_frame'], gi, seg_idx, layer_idx)


    # ------------------------------------------------------------------
    # v04: ความลึกของรู — CAD / โพรบแตะพื้น (Z trigger) / เวอร์เนียร์ (กรอกเอง)
    # ------------------------------------------------------------------
    @staticmethod
    def _depth_info(hole):
        """(ความลึกพื้นตาม CAD หรือ None ถ้ารูทะลุ, ความยาวรูตาม CAD, ['⌀.. : a–b mm', ...])"""
        sh = getattr(hole, '_step_hole', None)
        if sh is None:
            return None, None, []
        o = np.asarray(sh.open_3d, dtype=float)
        parts = []
        segs = getattr(sh, 'segments', None) or []
        if len(segs) > 1:
            for seg in reversed(segs):   # segments เรียงลึกสุดก่อน — แสดงจากปากรูลงไป
                a = float(np.linalg.norm(np.asarray(seg.open_3d, dtype=float) - o))
                b = float(np.linalg.norm(np.asarray(seg.deep_3d, dtype=float) - o))
                parts.append(f"⌀{2 * max(seg.radius_open, seg.radius_deep):.2f}: "
                             f"{min(a, b):.2f} – {max(a, b):.2f} mm")
        return hole_floor_depth(sh), float(sh.depth), parts

    def _manual_depths(self) -> dict:
        """ค่าความลึกที่กรอกเอง (เวอร์เนียร์) ของไฟล์ STEP นี้ — จำไว้ใน settings.json"""
        all_ = user_settings.get("manual_depths", {}) or {}
        return all_.get(getattr(self.app, 'loaded_step_filename', None) or "?", {}) or {}

    def _save_manual_depth(self, fp: str, value):
        all_ = user_settings.get("manual_depths", {}) or {}
        key = getattr(self.app, 'loaded_step_filename', None) or "?"
        mine = all_.get(key, {}) or {}
        if value is None:
            mine.pop(fp, None)
        else:
            mine[fp] = value
        all_[key] = mine
        user_settings.save_section("manual_depths", all_)

    def _build_depth_block(self, parent, hole, info, gi=None):
        floor, length, parts = self._depth_info(hole)
        if length is None:
            return
        tol = float(getattr(self.app, 'evaluation_tolerance_mm', 0.5))
        box = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=5)
        box.pack(fill="x", padx=6, pady=(8, 2))
        lines = ([f"Depth (CAD): {floor:.3f} mm to the floor"] if floor is not None else
                 [f"Through hole — length {length:.3f} mm (no floor)"])
        lines += [f"  {p}" for p in parts]
        ctk.CTkLabel(box, text="\n".join(lines), anchor="w", justify="left",
                     font=ctk.CTkFont(family=theme.FONT_MONO, size=10),
                     text_color=theme.TEXT_SECONDARY).pack(fill="x", padx=8, pady=(6, 2))
        if floor is None:
            return

        fl = (info or {}).get('floor')
        if fl:
            err = fl.get('depth_error', 0.0)
            ok = fl.get('passed', False)
            ctk.CTkLabel(box, anchor="w", font=ctk.CTkFont(family=theme.FONT_MONO, size=10),
                         text=f"Probed floor: {floor + err:.3f} mm ({err:+.3f}) {'✅' if ok else '❌'}",
                         text_color=theme.OK_TEXT if ok else theme.ERR_TEXT).pack(fill="x", padx=8)
        else:
            probing = (getattr(self.app.probe_profile, 'z_trigger', False)
                       and getattr(hole, 'measure_floor', False))
            ctk.CTkLabel(box, anchor="w", font=ctk.CTkFont(size=10), text_color=theme.TEXT_MUTED,
                         text=("Floor not probed in this log — or measure it with a caliper:" if probing
                               else "Floor not probed — measure it with a caliper:")
                         ).pack(fill="x", padx=8)

        fp = _hole_fingerprint(hole)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(2, 6))
        lbl = ctk.CTkLabel(row, text="Caliper depth:", font=ctk.CTkFont(size=10),
                           text_color=theme.TEXT_SECONDARY)
        lbl.pack(side="left")
        ent = ctk.CTkEntry(row, width=70, height=24, font=ctk.CTkFont(size=11), placeholder_text="mm")
        ent.pack(side="left", padx=(6, 6))
        if gi is not None:   # v05: ให้ _update_depth_prompts() เน้นช่องนี้ได้
            w = self._hole_widgets[gi]
            w.update(caliper_entry=ent, caliper_label=lbl,
                     entry_border=ent.cget("border_color"), entry_border_w=ent.cget("border_width"))
        res = ctk.CTkLabel(row, text="", font=ctk.CTkFont(family=theme.FONT_MONO, size=10))
        res.pack(side="left")
        saved = self._manual_depths().get(fp)
        if saved is not None:
            ent.insert(0, f"{float(saved):g}")

        def show(value):
            if value is None:
                res.configure(text="")
                return
            err = value - floor
            ok = abs(err) <= tol
            res.configure(text=f"{err:+.3f} {'✅' if ok else '❌'}",
                          text_color=theme.OK_TEXT if ok else theme.ERR_TEXT)

        def commit(_e=None):
            text = ent.get().strip()
            if not text:
                self._save_manual_depth(fp, None)
                show(None)
            else:
                try:
                    value = float(text)
                except ValueError:
                    res.configure(text="number?", text_color=theme.WARN_TEXT)
                    return
                self._save_manual_depth(fp, value)
                show(value)
            self._update_depth_prompts()   # v05

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        show(None if saved is None else float(saved))


    # ------------------------------------------------------------------
    # v05: เตือนให้กรอกความลึกจากเวอร์เนียร์ — รูที่มีพื้นแต่โพรบไม่ได้แตะพื้น
    # ------------------------------------------------------------------
    def _needs_caliper(self, gi) -> bool:
        w = self._hole_widgets.get(gi) or {}
        if w.get('floor') is None or w.get('probed_floor'):
            return False
        return w.get('fp') not in self._manual_depths()

    def depth_status(self):
        """(จำนวนรูที่ตรวจความลึกแล้ว, จำนวนรูที่มีพื้นทั้งหมด) — ให้แผงซ้ายแสดงสรุป"""
        need = [gi for gi, w in self._hole_widgets.items() if w.get('floor') is not None]
        done = [gi for gi in need if not self._needs_caliper(gi)]
        return len(done), len(need)

    def _update_depth_prompts(self):
        """อัปเดตแบนเนอร์เตือน + แท็ก ⚠ บนหัวการ์ด + กรอบช่องกรอก ให้ตรงกับค่าปัจจุบัน"""
        missing = [gi for gi in self._hole_widgets if self._needs_caliper(gi)]
        for gi, w in self._hole_widgets.items():
            if 'btn' not in w:
                continue
            need = gi in missing
            w['btn'].configure(text=w['btn_text'] + ("   ⚠ caliper depth" if need else ""))
            ent = w.get('caliper_entry')
            if ent is not None:
                ent.configure(border_color=theme.WARN_TEXT if need else w['entry_border'],
                              border_width=2 if need else w['entry_border_w'])
                w['caliper_label'].configure(
                    text="Caliper depth (required):" if need else "Caliper depth:",
                    text_color=theme.WARN_TEXT if need else theme.TEXT_SECONDARY)

        if self._depth_banner is not None:
            self._depth_banner.destroy()
            self._depth_banner = None
        if missing:
            names = ", ".join(str(getattr(self._hole_widgets[gi]['hole'], 'display_id', '?'))
                              for gi in missing)
            banner = ctk.CTkFrame(self.warning_frame, fg_color=theme.WARN_BG, corner_radius=6)
            banner.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(
                banner, anchor="w", justify="left", wraplength=290,
                text_color=theme.WARN_TEXT, font=ctk.CTkFont(size=11, weight="bold"),
                text=(f"⚠ Depth not checked — hole {names}\n"
                      f"The probe does not touch the floor. Measure the depth with a caliper "
                      f"and type it into 'Caliper depth' in the hole card.")
            ).pack(side="left", fill="x", expand=True, padx=(10, 6), pady=6)
            ctk.CTkButton(banner, text="Fill in ▸", width=70, height=26,
                          fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                          font=ctk.CTkFont(size=11),
                          command=lambda: self._show_caliper_inputs(missing)
                          ).pack(side="right", padx=(0, 8), pady=6)
            self._depth_banner = banner
        self._pack_warning_frame()
        if hasattr(self.app, 'evaluation_left_panel'):
            self.app.evaluation_left_panel.refresh()

    def _show_caliper_inputs(self, gis):
        """ปุ่ม 'Fill in ▸' — เปิดการ์ดของรูที่ยังไม่ได้กรอก แล้วโฟกัสช่องแรก"""
        first = None
        for gi in gis:
            w = self._hole_widgets.get(gi) or {}
            if not w.get('is_expanded'):
                self._toggle_hole(gi)
            if first is None and w.get('caliper_entry') is not None:
                first = w['caliper_entry']
        if first is not None:
            first.focus_set()
            try:   # เลื่อนรายการให้เห็นการ์ดแรกที่ต้องกรอก
                self.list_frame._parent_canvas.yview_moveto(0.0)
            except Exception:
                pass

    def _pack_warning_frame(self):
        """แสดงพื้นที่เตือนเฉพาะเมื่อมีข้อความ — CTkFrame ว่างสูง 200 px โดยปริยาย
        (เคยดันรายการการ์ดรูลงไปกลางจอ)"""
        if self.warning_frame.winfo_children():
            # CTkScrollableFrame: ตัวที่ถูก pack จริงคือกรอบนอก _parent_frame
            anchor = getattr(self.list_frame, '_parent_frame', self.list_frame)
            self.warning_frame.pack(padx=20, fill="x", pady=(0, 0), before=anchor)
        else:
            self.warning_frame.pack_forget()

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
            self.refresh()   # v04: ผลเทียบค่าเวอร์เนียร์ใช้ tolerance นี้ด้วย
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
            new_result = evaluate_points(expected_points, actual_points, tol,
                                         tip_radius_mm=app.probe_profile.effective_tip_radius,
                                         best_fit=bool(getattr(app, 'evaluation_best_fit', False)))   # v09
        except Exception as e:
            _mb.showerror("Evaluation Failed", f"ประเมินผลใหม่ไม่สำเร็จ:\n{e!r}")
            return

        new_result['log_filename']           = result.get('log_filename')
        new_result['tolerance_mm']           = tol
        new_result['settings_mismatch']      = result.get('settings_mismatch', [])
        new_result['expected_source']        = result.get('expected_source')        # v03
        new_result['expected_source_name']   = result.get('expected_source_name')   # v03
        new_result['_expected_points']       = expected_points
        new_result['_actual_points']         = actual_points

        # same hole_id -> gi remap as evaluation_left_panel.py's initial load
        _remap_holes_by_gi(new_result, app.current_holes)

        app.evaluation_result = new_result

        self.refresh()
        if hasattr(app, 'evaluation_left_panel'):
            app.evaluation_left_panel.refresh()
        if app.current_tab == "Evaluation":
            app.evaluation_tab.draw_evaluation()
