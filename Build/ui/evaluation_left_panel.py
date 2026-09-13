# ==============================================================================
# ui/evaluation_left_panel.py — Left sidebar แทนที่ sidebar ปกติ ขณะอยู่แท็บ
# "Evaluation" (§5 ของ PLAN_evaluation-tab-openbuilds-log-comparison_v02.md)
# ==============================================================================
# VERSION: 08
# CHANGE LOG (v07 -> v08):
#   FIX (user report): app.evaluation_result was only ever (re)computed
#   from inside "📥 Load OpenBuilds .log" — so after loading a schema
#   (which changes hole selection / expected points) or clearing a
#   loaded schema, the Results panel and the Evaluation overview kept
#   showing the OLD result, computed against the config that existed
#   before the change, until the user re-picked the same .log file again.
#   FEATURE (hybrid, per discussion):
#     1) Extracted the "compute + apply a result" body of the old
#        _on_load_log() into a new shared _evaluate_and_apply(
#        actual_points, log_filename) — this is the ONLY place that
#        builds/updates app.evaluation_result now.
#     2) _on_load_log() re-parses the .log file (unchanged) and calls
#        _evaluate_and_apply() with the freshly parsed points.
#     3) NEW "🔄 Refresh Results" button next to the Results section —
#        re-runs _evaluate_and_apply() using the CACHED actual_points
#        from the last .log parse (evaluation_result['_actual_points']),
#        without re-opening a file dialog. Enabled only when a result
#        already exists (i.e. a .log has been loaded at least once this
#        session). Use this after tweaking hole settings anywhere else
#        in the app (e.g. Customization tab) and coming back to
#        Evaluation.
#     4) AUTO-REFRESH: _on_load_schema() and _on_clear_schema() now both
#        call a new _auto_refresh_if_result_exists() right after they
#        finish updating hole config — if a result already exists (cached
#        actual_points available), the result is recomputed automatically
#        against the new config. If no .log has been loaded yet this
#        session, there is nothing to refresh and nothing happens (the
#        Results panel still correctly shows "No .log file loaded").
#     Rationale for not also auto-refreshing on every single hole-setting
#     edit elsewhere in the app (checkbox/dropdown/zigzag degree, etc.):
#     those live in ui/main_window.py across many call sites, and
#     re-running evaluation on every keystroke/click would be excessive
#     and easy to get subtly wrong. Schema load/clear are the two
#     highest-value, lowest-risk auto-refresh points because they are
#     both funneled through this one file already; the manual "🔄 Refresh
#     Results" button covers everything else with one click.
#   No change to the §6 stale-settings banner logic, _remap_holes_by_gi(),
#   or anything in build()/refresh() other than the new button + wiring.
#
# หน้าที่: แสดงข้อมูลไฟล์ STEP ที่โหลดอยู่ตอนนี้ + ขนาดจริง (X/Y/Z, mm แบบดิบ
# ไม่สลับตามมุมมองเหมือนแท็บ Selection) + ปุ่มโหลด/clear Schema (.json —
# โหลดแล้วแทนที่การตั้งค่าปัจจุบันทันที + รีเฟรชผลลัพธ์อัตโนมัติถ้ามีผลอยู่แล้ว)
# + ปุ่ม "📥 Load OpenBuilds .log" + ปุ่ม "🔄 Refresh Results" (v08) +
# สรุปจำนวนจุดที่ไม่ผ่าน threshold
#
# ui/main_window.py::UIManager สร้าง instance นี้ตัวเดียวตอน __init__ แล้ว
# เรียก .build(self.evaluation_left_frame) ครั้งเดียว จากนั้นแค่เรียก
# .refresh() ทุกครั้งที่สลับเข้าแท็บ Evaluation หรือมีผลตรวจใหม่
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _COLOR_GOOD / _COLOR_BAD = สีของตัวเลข "Failed Points" (เขียว = 0 failed,
#                                แดง = มีจุดไม่ผ่าน)
# ==============================================================================
import os
import customtkinter as ctk
import tkinter.messagebox as _mb

_COLOR_GOOD = "#66bb6a"
_COLOR_BAD  = "#e53935"


def _remap_holes_by_gi(result: dict, current_holes: list) -> None:
    """core/evaluation_engine.py::evaluate_points() keys result['holes'] by
    hole_id (str of hole.display_id) — a core/*.py-level concept that
    knows nothing about app.current_holes. ui/tabs/evaluation_tab.py's
    contract expects 'holes' keyed by global index into app.current_holes
    instead (matching how every other tab's hover/click hooks already
    address holes — see gidx_of in evaluation_tab.py::_draw_overview()).
    Mutates result['holes'] in place. Shared by both
    ui/evaluation_left_panel.py (after a fresh .log load / refresh) and
    ui/evaluation_sidebar_panel.py (after re-running evaluate_points()
    with a new tolerance)."""
    holes_by_id = result.get('holes', {}) or {}
    holes_by_gi = {}
    for gi, h in enumerate(current_holes):
        hid = str(getattr(h, 'display_id', ''))
        if hid in holes_by_id:
            holes_by_gi[gi] = holes_by_id[hid]
    result['holes'] = holes_by_gi


class EvaluationLeftPanel:
    def __init__(self, app):
        self.app = app
        self._built = False

    # ------------------------------------------------------------------
    def build(self, parent):
        """สร้าง widget ทั้งหมดครั้งเดียวลงใน parent (app.evaluation_left_frame)
        เรียกจาก ui/main_window.py ตอน __init__ เท่านั้น"""
        self.parent = parent
        for w in parent.winfo_children():
            w.destroy()

        ctk.CTkLabel(parent, text="🧪 Evaluation", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))

        # --- STEP file info -------------------------------------------------
        self.file_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=5)
        self.file_frame.pack(pady=(0, 15), padx=20, fill="x")
        ctk.CTkLabel(self.file_frame, text="STEP File", text_color="gray",
                    font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_step_filename = ctk.CTkLabel(
            self.file_frame, text="—", font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=220, justify="left")
        self.lbl_step_filename.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Physical dimensions (raw X/Y/Z, no view-relabeling) ------------
        self.dim_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=5)
        self.dim_frame.pack(pady=(0, 15), padx=20, fill="x")
        ctk.CTkLabel(self.dim_frame, text="Physical Dimensions", text_color="gray",
                    font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_dim_x = ctk.CTkLabel(self.dim_frame, text="X: -- mm", font=ctk.CTkFont(size=12))
        self.lbl_dim_x.pack(anchor="w", padx=10)
        self.lbl_dim_y = ctk.CTkLabel(self.dim_frame, text="Y: -- mm", font=ctk.CTkFont(size=12))
        self.lbl_dim_y.pack(anchor="w", padx=10)
        self.lbl_dim_z = ctk.CTkLabel(self.dim_frame, text="Z: -- mm", font=ctk.CTkFont(size=12))
        self.lbl_dim_z.pack(anchor="w", padx=10, pady=(0, 8))

        ctk.CTkFrame(parent, height=1, fg_color="#333333").pack(fill="x", padx=20, pady=(5, 15))

        # --- Schema (.json) — load = direct replace, auto-refreshes
        # results if a .log has already been loaded (v08) ------------------
        self.btn_load_schema = ctk.CTkButton(
            parent, text="📂 Load Schema (.json)",
            fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_load_schema)
        self.btn_load_schema.pack(pady=(0, 5), padx=20, fill="x")

        self.lbl_schema_info = ctk.CTkLabel(
            parent, text="Using live hole config (no schema loaded)", text_color="gray",
            font=ctk.CTkFont(size=11), wraplength=220, justify="left")
        self.lbl_schema_info.pack(pady=(0, 8), padx=20, anchor="w")

        self.btn_clear_schema = ctk.CTkButton(
            parent, text="↺ Clear loaded schema",
            fg_color="transparent", hover_color="#2a2a4e",
            text_color="#90caf9", font=ctk.CTkFont(size=11),
            command=self._on_clear_schema)
        self.btn_clear_schema.pack(pady=(0, 15), padx=20, fill="x")

        ctk.CTkFrame(parent, height=1, fg_color="#333333").pack(fill="x", padx=20, pady=(0, 15))

        # --- Load .log ---------------------------------------------------
        self.btn_load_log = ctk.CTkButton(
            parent, text="📥 Load OpenBuilds .log",
            fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_load_log)
        self.btn_load_log.pack(pady=(0, 5), padx=20, fill="x")

        self.lbl_log_info = ctk.CTkLabel(
            parent, text="No .log file loaded", text_color="gray",
            font=ctk.CTkFont(size=11), wraplength=220, justify="left")
        self.lbl_log_info.pack(pady=(0, 15), padx=20, anchor="w")

        ctk.CTkFrame(parent, height=1, fg_color="#333333").pack(fill="x", padx=20, pady=(0, 15))

        # --- Results -----------------------------------------------------
        self.results_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=5)
        self.results_frame.pack(pady=(0, 15), padx=20, fill="x")

        results_header = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        results_header.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(results_header, text="Results", text_color="gray",
                    font=ctk.CTkFont(size=11)).pack(side="left")
        # v08: manual refresh — re-runs evaluation against whatever the
        # CURRENT hole config / schema is, reusing the last-loaded .log's
        # cached actual points (no file dialog).
        self.btn_refresh_results = ctk.CTkButton(
            results_header, text="🔄 Refresh Results", width=110, height=22,
            fg_color="#37474f", hover_color="#546e7a", font=ctk.CTkFont(size=10),
            state="disabled", command=self._on_refresh_results)
        self.btn_refresh_results.pack(side="right")

        self.lbl_failed = ctk.CTkLabel(self.results_frame, text="—",
                                       font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_failed.pack(anchor="w", padx=10, pady=(4, 2))
        self.lbl_hole_rate = ctk.CTkLabel(self.results_frame, text="",
                                          text_color="#9aa4b2", font=ctk.CTkFont(size=11))
        self.lbl_hole_rate.pack(anchor="w", padx=10, pady=(0, 8))

        self._built = True
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """อัปเดตทุก label ให้ตรงกับ state ปัจจุบันของ app — เรียกทุกครั้งที่
        สลับเข้าแท็บ Evaluation (_show_evaluation_sidebars) หรือหลังโหลด/
        ประเมินผล .log ใหม่ ไม่ rebuild widget"""
        if not self._built:
            return
        app = self.app

        filename = getattr(app, 'loaded_step_filename', None)
        self.lbl_step_filename.configure(text=filename or "—")

        if app.geo.mesh is not None:
            ext = app.geo.get_physical_dimensions()
            self.lbl_dim_x.configure(text=f"X: {ext[0]:.2f} mm", text_color="white")
            self.lbl_dim_y.configure(text=f"Y: {ext[1]:.2f} mm", text_color="white")
            self.lbl_dim_z.configure(text=f"Z: {ext[2]:.2f} mm", text_color="white")
        else:
            self.lbl_dim_x.configure(text="X: -- mm", text_color="gray")
            self.lbl_dim_y.configure(text="Y: -- mm", text_color="gray")
            self.lbl_dim_z.configure(text="Z: -- mm", text_color="gray")

        # --- Schema source readout ---------------------------------------
        schema        = getattr(app, 'loaded_schema', None)
        loaded_points = getattr(app, 'loaded_expected_points', None)
        if schema is not None and loaded_points:
            source   = getattr(app, 'loaded_expected_points_source', None) or "?"
            view_tag = getattr(app, 'loaded_expected_points_view', None)
            view_tag = f" (view: {view_tag})" if view_tag else ""
            self.lbl_schema_info.configure(
                text=f"Loaded: {source}\n{len(loaded_points)} points{view_tag}\n"
                     f"(hole selection + settings already applied)",
                text_color="#b0bec5")
        else:
            self.lbl_schema_info.configure(
                text="Using live hole config (no schema loaded)", text_color="gray")

        ready = (app.geo.mesh is not None and app.geo.step_data is not None
                and getattr(app, 'holes_detected', False) and app.current_holes)
        self.btn_load_log.configure(state="normal" if ready else "disabled")
        self.btn_load_schema.configure(state="normal" if ready else "disabled")

        result = getattr(app, 'evaluation_result', None)
        # v08: only useful once we actually have cached actual_points to
        # recompute against (i.e. a .log has been parsed at least once).
        can_refresh = bool(result and result.get('_actual_points'))
        self.btn_refresh_results.configure(state="normal" if can_refresh else "disabled")

        if result:
            log_name  = result.get('log_filename', '—')
            total_pts = result.get('total_points', 0)
            self.lbl_log_info.configure(
                text=f"Loaded: {log_name}\n{total_pts} points parsed",
                text_color="#b0bec5")

            failed = result.get('failed_points', 0)
            if total_pts:
                color = _COLOR_GOOD if failed == 0 else _COLOR_BAD
                self.lbl_failed.configure(
                    text=f"{failed} / {total_pts} points failed",
                    text_color=color)
            else:
                self.lbl_failed.configure(text="—", text_color="white")

            holes_r = result.get('holes', {}) or {}
            n_holes = len(holes_r)
            n_pass  = sum(1 for hv in holes_r.values() if hv.get('passed'))
            self.lbl_hole_rate.configure(
                text=f"{n_pass} / {n_holes} holes fully passed" if n_holes else "")
        else:
            self.lbl_log_info.configure(text="No .log file loaded", text_color="gray")
            self.lbl_failed.configure(text="—", text_color="white")
            self.lbl_hole_rate.configure(text="")

    # ------------------------------------------------------------------
    # Schema (.json) load (direct replace) / clear
    # ------------------------------------------------------------------
    def _on_load_schema(self):
        """loads the schema file AND immediately applies its
        settings_snapshot to app.current_holes (full replace — every
        hole's selection + layers/points/zigzag become exactly what's in
        the file; anything the file doesn't mention gets deselected).
        v08: also auto-refreshes app.evaluation_result if one already
        exists, so Results doesn't go stale after this change."""
        app = self.app

        if not getattr(app, 'holes_detected', False) or not app.current_holes:
            _mb.showwarning("No Holes", "กรุณากด 'Generate Holes' ก่อนโหลด Schema")
            return

        filepath = ctk.filedialog.askopenfilename(
            title="Select Schema (.json)",
            filetypes=[("Schema JSON", "*_schema.json *.json"), ("All Files", "*.*")])
        if not filepath:
            return

        try:
            from core.expected_points_io import load_schema_json
        except ImportError as e:
            self.app.notify.show(
                f"ยังไม่มี core/expected_points_io.py::load_schema_json() ({e})",
                severity="info", duration_ms=6000)
            return

        try:
            data = load_schema_json(filepath)
        except Exception as e:
            _mb.showerror("Load Failed", f"โหลด Schema ไม่สำเร็จ:\n{e!r}")
            return

        points = data.get('points') or []
        if not points:
            _mb.showwarning("Empty File", "ไฟล์นี้ไม่มี points อยู่เลย")
            return

        snapshot = data.get('settings_snapshot') or {}

        # --- apply the snapshot to app.current_holes RIGHT NOW — this is
        # the direct-replace the user asked for, no separate button ------
        report = {'matched': 0, 'deselected': 0, 'unmatched': 0, 'total_snapshot_holes': 0}
        if snapshot.get('holes'):
            try:
                from core.evaluation_engine import apply_settings_snapshot
            except ImportError as e:
                self.app.notify.show(
                    f"ยังไม่มี core/evaluation_engine.py::apply_settings_snapshot() ({e})",
                    severity="info", duration_ms=6000)
                return
            report = apply_settings_snapshot(app.current_holes, snapshot, full_replace=True)

        app.loaded_schema                 = data
        app.loaded_expected_points        = points
        app.loaded_expected_points_source = os.path.basename(filepath)
        app.loaded_expected_points_view   = data.get('view_name')

        # re-sync numbering / treeview / whichever tab is currently open —
        # reuses the exact same refresh path selection-checkbox toggles
        # already use (ui/main_window.py::_refresh_after_inspection_toggle())
        app._refresh_after_inspection_toggle()

        # v08: keep Results in sync with the config we just applied,
        # instead of leaving a stale result from before the load.
        refreshed = self._auto_refresh_if_result_exists()

        self.refresh()
        if hasattr(app, 'evaluation_sidebar_panel'):
            app.evaluation_sidebar_panel.refresh()
        if app.current_tab == "Evaluation":
            app.evaluation_tab.draw_evaluation()

        refresh_tag = "\nผลลัพธ์ถูกคำนวณใหม่แล้ว" if refreshed else ""
        if snapshot.get('holes'):
            self.app.notify.show(
                f"โหลด Schema แล้ว — แทนที่การตั้งค่าปัจจุบัน: "
                f"จับคู่ {report['matched']} รู, ปิดการเลือก {report['deselected']} รู "
                f"({len(points)} points){refresh_tag}",
                severity="success")
        else:
            self.app.notify.show(
                f"โหลด Schema แล้ว: {len(points)} points "
                f"(ไฟล์นี้ไม่มีข้อมูล settings ให้แทนที่ — ใช้ค่าตั้งค่าปัจจุบันต่อไป)"
                f"{refresh_tag}",
                severity="warn")

    def _on_clear_schema(self):
        """only clears which points source Evaluation compares the .log
        against (reverts to live-recomputing from app.current_holes as it
        currently stands). Does NOT undo the hole-settings replace that
        already happened on load — there is no undo for that, matching
        the requested direct-replace behavior. v08: also auto-refreshes
        app.evaluation_result if one already exists."""
        app = self.app
        app.loaded_schema                 = None
        app.loaded_expected_points        = None
        app.loaded_expected_points_source = None
        app.loaded_expected_points_view   = None

        refreshed = self._auto_refresh_if_result_exists()

        self.refresh()
        if hasattr(app, 'evaluation_sidebar_panel'):
            app.evaluation_sidebar_panel.refresh()
        if app.current_tab == "Evaluation":
            app.evaluation_tab.draw_evaluation()

        if refreshed:
            self.app.notify.show(
                "เลิกใช้ Schema แล้ว — กลับไปคำนวณ expected points จาก config "
                "ปัจจุบัน และคำนวณผลลัพธ์ใหม่แล้ว", severity="info")

    # ------------------------------------------------------------------
    # v08: shared recompute plumbing
    # ------------------------------------------------------------------
    def _auto_refresh_if_result_exists(self) -> bool:
        """เรียกหลัง schema load/clear — ถ้ามีผลตรวจอยู่แล้ว (คือเคยโหลด
        .log มาก่อนหน้านี้ในเซสชันนี้) ให้คำนวณผลใหม่ทันทีด้วย actual_points
        ที่ cache ไว้ (ไม่ถามไฟล์ซ้ำ) เทียบกับ expected points/config
        ปัจจุบัน — ถ้ายังไม่เคยโหลด .log เลย จะไม่ทำอะไร (ไม่มีอะไรให้รีเฟรช)

        Returns True ถ้ามีการคำนวณผลใหม่จริง (มี actual_points cache ให้ใช้)"""
        app = self.app
        result = getattr(app, 'evaluation_result', None)
        if not result or not result.get('_actual_points'):
            return False
        self._evaluate_and_apply(result['_actual_points'], result.get('log_filename', '—'))
        return True

    def _on_refresh_results(self):
        """ปุ่ม '🔄 Refresh Results' — คำนวณผลใหม่ด้วย actual_points ที่
        cache ไว้จากการโหลด .log ครั้งล่าสุด เทียบกับ expected points/
        config ปัจจุบัน โดยไม่ต้องเปิดไฟล์ .log ซ้ำ — ใช้เมื่อไปแก้ค่า
        layers/points/zigzag ของรูที่แท็บอื่น (เช่น Customization) แล้ว
        กลับมาดูผลที่แท็บนี้"""
        app = self.app
        result = getattr(app, 'evaluation_result', None)
        if not result or not result.get('_actual_points'):
            _mb.showinfo("No Log Loaded", "ยังไม่เคยโหลดไฟล์ .log ในเซสชันนี้ — กรุณากด 'Load OpenBuilds .log' ก่อน")
            return

        self._evaluate_and_apply(result['_actual_points'], result.get('log_filename', '—'))
        self.app.notify.show("คำนวณผลลัพธ์ใหม่แล้ว (ใช้ .log เดิม เทียบกับ config ปัจจุบัน)",
                             severity="success")

    def _evaluate_and_apply(self, actual_points: list, log_filename: str) -> bool:
        """แกนกลางที่แท้จริงของการ "ประเมินผลแล้วอัปเดต app.evaluation_result"
        — ใช้ actual_points ที่ได้มาแล้ว (parse ใหม่จาก .log หรือ cache ไว้
        ก็ได้) คำนวณ expected points ตามแหล่งปัจจุบัน (schema ที่โหลดไว้ หรือ
        live จาก app.current_holes), รัน evaluate_points(), ตรวจ settings
        mismatch, แล้ว set app.evaluation_result + รีเฟรช sidebar/แท็บที่
        เกี่ยวข้องทั้งหมด — เป็นจุดเดียวที่ set app.evaluation_result ในไฟล์
        นี้ เรียกจาก _on_load_log(), _on_refresh_results(), และ
        _auto_refresh_if_result_exists()

        Returns True ถ้าคำนวณและอัปเดตสำเร็จ, False ถ้าล้มเหลว (แสดง error
        dialog ให้แล้วภายในฟังก์ชันนี้)"""
        app = self.app

        try:
            from core.evaluation_engine import (
                evaluate_points, build_settings_snapshot, diff_snapshots)
            from core.gcode_generator import build_point_map
        except ImportError as e:
            self.app.notify.show(
                "ยังไม่มีไฟล์คำนวณผล Evaluation ครบ (ต้องมี core/evaluation_engine.py "
                f"และ core/gcode_generator.py::build_point_map() ก่อน)\n\nรายละเอียด: {e}",
                severity="info", duration_ms=6000)
            return False

        selected  = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
        view_name = getattr(app, 'current_view', 'Top')

        # prefer a loaded Schema's points over live-recomputing from
        # app.current_holes. Since loading a schema now immediately
        # replaces the live hole config to match it, the two are
        # normally in sync anyway — this just avoids recomputing when we
        # already have the exact points that were recorded at export time.
        schema     = getattr(app, 'loaded_schema', None)
        using_json = bool(getattr(app, 'loaded_expected_points', None))
        if using_json:
            expected_points = app.loaded_expected_points
        else:
            try:
                expected_points = build_point_map(selected, view_name)
            except Exception as e:
                _mb.showerror("Expected Point Build Failed", f"คำนวณจุดที่คาดหวังไม่สำเร็จ:\n{e!r}")
                return False

        tolerance = getattr(app, 'evaluation_tolerance_mm', 0.5)

        try:
            result = evaluate_points(expected_points, actual_points, tolerance)
        except Exception as e:
            _mb.showerror("Evaluation Failed", f"ประเมินผลไม่สำเร็จ:\n{e!r}")
            return False

        result['log_filename']         = log_filename
        result['tolerance_mm']         = tolerance
        result['expected_source']      = 'json' if using_json else 'live'
        result['expected_source_name'] = getattr(app, 'loaded_expected_points_source', None) if using_json else None
        result['_expected_points']     = expected_points
        result['_actual_points']       = actual_points

        # evaluate_points() keys 'holes' by hole_id (display_id string) —
        # remap to global index into app.current_holes, which is what
        # ui/tabs/evaluation_tab.py's contract actually expects.
        _remap_holes_by_gi(result, app.current_holes)

        # --- §6 stale-settings guard (READ-ONLY) -------------------------
        # Always builds a fresh LIVE snapshot for comparison. The
        # reference to compare against is the loaded schema's own
        # settings_snapshot when using one, or the in-memory
        # last_export_snapshot from a live G-code export otherwise.
        try:
            current_snapshot = build_settings_snapshot(app.current_holes, view_name)   # ALL holes
        except Exception:
            current_snapshot = None

        if using_json:
            reference_snapshot = (schema or {}).get('settings_snapshot')
        else:
            reference_snapshot = getattr(app, 'last_export_snapshot', None)

        if current_snapshot is not None and reference_snapshot:
            try:
                result['settings_mismatch'] = diff_snapshots(reference_snapshot, current_snapshot)
            except Exception:
                result.setdefault('settings_mismatch', [])
        else:
            result.setdefault('settings_mismatch', [])

        app.evaluation_result = result
        self.refresh()
        if hasattr(app, 'evaluation_sidebar_panel'):
            app.evaluation_sidebar_panel.refresh()
        if app.current_tab == "Evaluation":
            app.evaluation_tab.draw_evaluation()
        return True

    # ------------------------------------------------------------------
    def _on_load_log(self):
        app = self.app

        if app.geo.mesh is None or app.geo.step_data is None:
            _mb.showwarning("No STEP Model", "กรุณาโหลดไฟล์ STEP ก่อน")
            return
        if not getattr(app, 'holes_detected', False) or not app.current_holes:
            _mb.showwarning("No Holes", "กรุณากด 'Generate Holes' ก่อน")
            return

        filepath = ctk.filedialog.askopenfilename(
            title="Select OpenBuilds Control .log file",
            filetypes=[("Log Files", "*.log *.txt"), ("All Files", "*.*")])
        if not filepath:
            return

        try:
            from core.log_parser import parse_openbuilds_log
        except ImportError as e:
            self.app.notify.show(
                f"ยังไม่มี core/log_parser.py ({e})",
                severity="info", duration_ms=6000)
            return

        try:
            actual_points = parse_openbuilds_log(filepath)
        except Exception as e:
            _mb.showerror("Parse Failed", f"อ่านไฟล์ .log ไม่สำเร็จ:\n{e!r}")
            return

        self._evaluate_and_apply(actual_points, os.path.basename(filepath))