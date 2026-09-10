# ==============================================================================
# ui/evaluation_left_panel.py — Left sidebar แทนที่ sidebar ปกติ ขณะอยู่แท็บ
# "Evaluation" (§5 ของ PLAN_evaluation-tab-openbuilds-log-comparison_v02.md)
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FEATURE (PLAN_evaluation-expected-points-json-and-offset-only_v01.md
#   §4.2): new button "📂 Load Expected Points (.json)" +
#   _on_load_expected_points_json(). When loaded, points are stored on
#   app.loaded_expected_points (list) / app.loaded_expected_points_source
#   (filename) / app.loaded_expected_points_view (view_name from the
#   file's metadata, informational). _on_load_log() now PREFERS
#   app.loaded_expected_points over calling build_point_map() from the
#   live app.current_holes — fully backward compatible: if nothing has
#   been loaded, behavior is identical to v02 (live recompute).
#   The §6 stale-settings guard is skipped entirely when using a loaded
#   JSON (it IS the frozen source of truth already — see plan §4.2).
#   FEATURE (Requirement 4 — remove Accuracy, show Offset/Failed instead):
#   "Overall Accuracy" section replaced with "Results" section showing
#   "<failed> / <total> points failed" (green if 0 failed, red
#   otherwise) — no percentage anywhere. Reads the new
#   result['failed_points'] field from core/evaluation_engine.py v02.
#   No change to _remap_holes_by_gi() or _on_load_snapshot() (still only
#   relevant to the live-recompute / stale-settings-guard path).
# หน้าที่: แสดงข้อมูลไฟล์ STEP ที่โหลดอยู่ตอนนี้ + ขนาดจริง (X/Y/Z, mm แบบดิบ
# ไม่สลับตามมุมมองเหมือนแท็บ Selection) + ปุ่มโหลด Expected Points (.json,
# ใหม่ v03) + ปุ่ม "📥 Load OpenBuilds .log" + สรุปจำนวนจุดที่ไม่ผ่าน
# threshold (v03 — เดิมเป็น % accuracy)
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
import json
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
    ui/evaluation_left_panel.py (after a fresh .log load) and
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

        # --- Expected Points (.json) — v03 -----------------------------
        self.btn_load_points = ctk.CTkButton(
            parent, text="📂 Load Expected Points (.json)",
            fg_color="#37474f", hover_color="#546e7a",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_load_expected_points_json)
        self.btn_load_points.pack(pady=(0, 5), padx=20, fill="x")

        self.lbl_points_info = ctk.CTkLabel(
            parent, text="Using live hole config (no JSON loaded)", text_color="gray",
            font=ctk.CTkFont(size=11), wraplength=220, justify="left")
        self.lbl_points_info.pack(pady=(0, 3), padx=20, anchor="w")

        self.btn_clear_points = ctk.CTkButton(
            parent, text="↺ Use live hole config instead",
            fg_color="transparent", hover_color="#2a2a4e",
            text_color="#90caf9", font=ctk.CTkFont(size=11),
            command=self._on_clear_expected_points_json)
        self.btn_clear_points.pack(pady=(0, 15), padx=20, fill="x")

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

        # --- Results (v03: was "Overall Accuracy" — % removed entirely) ----
        self.results_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=5)
        self.results_frame.pack(pady=(0, 15), padx=20, fill="x")
        ctk.CTkLabel(self.results_frame, text="Results", text_color="gray",
                    font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_failed = ctk.CTkLabel(self.results_frame, text="—",
                                       font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_failed.pack(anchor="w", padx=10, pady=(0, 2))
        self.lbl_hole_rate = ctk.CTkLabel(self.results_frame, text="",
                                          text_color="#9aa4b2", font=ctk.CTkFont(size=11))
        self.lbl_hole_rate.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Optional cross-session snapshot load (§6 stale-settings guard) -
        self.btn_load_snapshot = ctk.CTkButton(
            parent, text="🔗 Load export snapshot (.json)",
            fg_color="transparent", hover_color="#2a2a4e",
            text_color="#90caf9", font=ctk.CTkFont(size=11),
            command=self._on_load_snapshot)
        self.btn_load_snapshot.pack(pady=(0, 10), padx=20, fill="x")

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

        # --- v03: Expected Points source readout ---------------------------
        loaded_points = getattr(app, 'loaded_expected_points', None)
        if loaded_points:
            source   = getattr(app, 'loaded_expected_points_source', None) or "?"
            view_tag = getattr(app, 'loaded_expected_points_view', None)
            view_tag = f" (view: {view_tag})" if view_tag else ""
            self.lbl_points_info.configure(
                text=f"Loaded: {source}\n{len(loaded_points)} points{view_tag}",
                text_color="#b0bec5")
        else:
            self.lbl_points_info.configure(
                text="Using live hole config (no JSON loaded)", text_color="gray")

        ready = (app.geo.mesh is not None and app.geo.step_data is not None
                and getattr(app, 'holes_detected', False) and app.current_holes)
        self.btn_load_log.configure(state="normal" if ready else "disabled")

        result = getattr(app, 'evaluation_result', None)
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
    # v03: Expected Points (.json) load / clear
    # ------------------------------------------------------------------
    def _on_load_expected_points_json(self):
        app = self.app
        filepath = ctk.filedialog.askopenfilename(
            title="Select Expected Points (.json)",
            filetypes=[("Expected Points JSON", "*.json"), ("All Files", "*.*")])
        if not filepath:
            return

        try:
            from core.expected_points_io import load_expected_points_json_full
        except ImportError as e:
            self.app.notify.show(
                f"ยังไม่มี core/expected_points_io.py ({e})",
                severity="info", duration_ms=6000)
            return

        try:
            data = load_expected_points_json_full(filepath)
        except Exception as e:
            _mb.showerror("Load Failed", f"โหลดไฟล์ Expected Points ไม่สำเร็จ:\n{e!r}")
            return

        points = data.get('points') or []
        if not points:
            _mb.showwarning("Empty File", "ไฟล์นี้ไม่มี points อยู่เลย")
            return

        app.loaded_expected_points        = points
        app.loaded_expected_points_source = os.path.basename(filepath)
        app.loaded_expected_points_view   = data.get('view_name')

        self.refresh()
        self.app.notify.show(
            f"โหลด Expected Points แล้ว: {len(points)} points", severity="success")

    def _on_clear_expected_points_json(self):
        app = self.app
        app.loaded_expected_points        = None
        app.loaded_expected_points_source = None
        app.loaded_expected_points_view   = None
        self.refresh()

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
            from core.evaluation_engine import (
                evaluate_points, build_settings_snapshot, diff_snapshots)
            from core.gcode_generator import build_point_map
        except ImportError as e:
            self.app.notify.show(
                "ยังไม่มีไฟล์คำนวณผล Evaluation ครบ (ต้องมี core/log_parser.py, "
                "core/evaluation_engine.py, และ core/gcode_generator.py::"
                f"build_point_map() ก่อน)\n\nรายละเอียด: {e}",
                severity="info", duration_ms=6000)
            return

        try:
            actual_points = parse_openbuilds_log(filepath)
        except Exception as e:
            _mb.showerror("Parse Failed", f"อ่านไฟล์ .log ไม่สำเร็จ:\n{e!r}")
            return

        selected  = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
        view_name = getattr(app, 'current_view', 'Top')

        # v03: prefer a loaded Expected Points JSON over live-recomputing
        # from app.current_holes — see plan §4.2. Fully backward
        # compatible: if nothing was loaded, this is identical to v02.
        using_json = bool(getattr(app, 'loaded_expected_points', None))
        if using_json:
            expected_points = app.loaded_expected_points
        else:
            try:
                expected_points = build_point_map(selected, view_name)
            except Exception as e:
                _mb.showerror("Expected Point Build Failed", f"คำนวณจุดที่คาดหวังไม่สำเร็จ:\n{e!r}")
                return

        tolerance = getattr(app, 'evaluation_tolerance_mm', 0.5)

        try:
            result = evaluate_points(expected_points, actual_points, tolerance)
        except Exception as e:
            _mb.showerror("Evaluation Failed", f"ประเมินผลไม่สำเร็จ:\n{e!r}")
            return

        result['log_filename']     = os.path.basename(filepath)
        result['tolerance_mm']     = tolerance
        result['expected_source']  = 'json' if using_json else 'live'   # v03
        result['expected_source_name'] = getattr(app, 'loaded_expected_points_source', None) if using_json else None
        # keep the raw point lists so the right-sidebar "Apply" tolerance
        # button can re-run evaluate_points() without reloading the file
        result['_expected_points'] = expected_points
        result['_actual_points']   = actual_points

        # evaluate_points() keys 'holes' by hole_id (display_id string) —
        # remap to global index into app.current_holes, which is what
        # ui/tabs/evaluation_tab.py's contract actually expects.
        _remap_holes_by_gi(result, app.current_holes)

        # --- §6 stale-settings guard ------------------------------------
        # v03: only meaningful for the LIVE-recompute path — a loaded
        # Expected Points JSON is already the frozen source of truth, so
        # the "did settings drift since export" question doesn't apply.
        if using_json:
            result.setdefault('settings_mismatch', [])
        else:
            try:
                current_snapshot = build_settings_snapshot(selected, view_name)
                last_snapshot = getattr(app, 'last_export_snapshot', None)
                if last_snapshot is not None:
                    result['settings_mismatch'] = diff_snapshots(last_snapshot, current_snapshot)
                else:
                    result.setdefault('settings_mismatch', [])
            except Exception:
                result.setdefault('settings_mismatch', [])

        app.evaluation_result = result
        self.refresh()
        if hasattr(app, 'evaluation_sidebar_panel'):
            app.evaluation_sidebar_panel.refresh()
        if app.current_tab == "Evaluation":
            app.evaluation_tab.draw_evaluation()

    # ------------------------------------------------------------------
    def _on_load_snapshot(self):
        """§6 optional secondary path: user points at the sidecar
        <name>.snapshot.json (written by core/gcode_export_panel.py) to
        restore the stale-settings guard across an app restart, when no
        in-session app.last_export_snapshot exists. Only relevant to the
        live-recompute path — has no effect when using a loaded Expected
        Points JSON (see _on_load_log()'s using_json branch)."""
        app = self.app
        filepath = ctk.filedialog.askopenfilename(
            title="Select export snapshot (.snapshot.json)",
            filetypes=[("Snapshot JSON", "*.json"), ("All Files", "*.*")])
        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                app.last_export_snapshot = json.load(f)
        except Exception as e:
            _mb.showerror("Load Failed", f"โหลด snapshot ไม่สำเร็จ:\n{e!r}")
            return

        result = getattr(app, 'evaluation_result', None)
        if result is not None and result.get('expected_source') != 'json':
            try:
                from core.evaluation_engine import build_settings_snapshot, diff_snapshots
                selected = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
                current_snapshot = build_settings_snapshot(selected, getattr(app, 'current_view', 'Top'))
                result['settings_mismatch'] = diff_snapshots(app.last_export_snapshot, current_snapshot)
                self.refresh()
                if hasattr(app, 'evaluation_sidebar_panel'):
                    app.evaluation_sidebar_panel.refresh()
                if app.current_tab == "Evaluation":
                    app.evaluation_tab.draw_evaluation()
            except ImportError:
                pass   # evaluation_engine not built yet — snapshot still stored for later

        self.app.notify.show(f"โหลด snapshot แล้ว: {os.path.basename(filepath)}", severity="success")
