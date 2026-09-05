# ==============================================================================
# ui/evaluation_left_panel.py — Left sidebar แทนที่ sidebar ปกติ ขณะอยู่แท็บ
# "Evaluation" (§5 ของ PLAN_evaluation-tab-openbuilds-log-comparison_v02.md)
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FIX: core/evaluation_engine.py::evaluate_points() (now built) keys its
#   returned 'holes' dict by hole_id (str of hole.display_id) — that's a
#   core/*.py-level concept, deliberately decoupled from the UI's "global
#   index into app.current_holes" (gi) that ui/tabs/evaluation_tab.py's
#   contract actually expects 'holes' to be keyed by. _on_load_log() now
#   remaps display_id -> gi right after evaluate_points() returns (see
#   new _remap_holes_by_gi() below) before storing app.evaluation_result,
#   otherwise evaluation_tab.py's gidx_of lookups would silently find
#   nothing and every hole would render as "no data" (gray).
#   Also now actually imports core.log_parser / core.evaluation_engine /
#   core.gcode_generator.build_point_map for real (all three exist now)
#   — the lazy-import/graceful-fallback pattern from v01 is kept as-is
#   since it costs nothing and protects against a future partial
#   checkout / missing file.
# หน้าที่: แสดงข้อมูลไฟล์ STEP ที่โหลดอยู่ตอนนี้ + ขนาดจริง (X/Y/Z, mm แบบดิบ
# ไม่สลับตามมุมมองเหมือนแท็บ Selection) + ปุ่ม "📥 Load OpenBuilds .log" +
# สรุปความถูกต้องโดยรวม (overall accuracy) เมื่อมีผลตรวจแล้ว
#
# ui/main_window.py::UIManager สร้าง instance นี้ตัวเดียวตอน __init__ แล้ว
# เรียก .build(self.evaluation_left_frame) ครั้งเดียว จากนั้นแค่เรียก
# .refresh() ทุกครั้งที่สลับเข้าแท็บ Evaluation หรือมีผลตรวจใหม่ — ไม่ได้
# สร้าง widget ใหม่ทุกครั้งเหมือน update_treeview() ของแท็บอื่น เพราะเนื้อหา
# ส่วนใหญ่เป็น label ไม่กี่บรรทัด ไม่จำเป็นต้อง rebuild ทั้งชุด
#
# NOTE (สำคัญ): ไฟล์นี้ยังไม่มี core/log_parser.py และ core/evaluation_engine.py
# ให้ import จริง (ตามลำดับการสร้างไฟล์ใน PLAN §9 — ไฟล์ UI ถูกสร้างก่อน)
# จึง import โมดูลทั้งสองแบบ "lazy" (เฉพาะตอนกดปุ่มโหลด .log จริง ๆ) และ
# ดักด้วย try/except ImportError เพื่อแจ้งผู้ใช้อย่างสุภาพแทนที่จะทำให้
# ทั้งแอปพัง — รูปแบบเดียวกับที่ ui/tabs/evaluation_tab.py ใช้กับ
# core.hole_ordering (import ภายในฟังก์ชัน ไม่ import ที่หัวไฟล์)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _ACCURACY_GOOD_THRESHOLD / _ACCURACY_WARN_THRESHOLD (% ) และสีที่ใช้แสดง
#     ระดับความถูกต้องโดยรวม (เขียว/เหลือง/แดง)
# ==============================================================================
import os
import json
import customtkinter as ctk
import tkinter.messagebox as _mb

_ACCURACY_GOOD_THRESHOLD = 95.0   # % ขึ้นไป = สีเขียว — ปรับได้
_ACCURACY_WARN_THRESHOLD = 80.0   # % ขึ้นไป (แต่ต่ำกว่า GOOD) = สีเหลือง, ต่ำกว่านี้ = แดง — ปรับได้

_COLOR_GOOD = "#66bb6a"
_COLOR_WARN = "#ffca28"
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

        # --- Overall accuracy ----------------------------------------------
        self.accuracy_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=5)
        self.accuracy_frame.pack(pady=(0, 15), padx=20, fill="x")
        ctk.CTkLabel(self.accuracy_frame, text="Overall Accuracy", text_color="gray",
                    font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_accuracy = ctk.CTkLabel(self.accuracy_frame, text="—",
                                         font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_accuracy.pack(anchor="w", padx=10, pady=(0, 2))
        self.lbl_hole_rate = ctk.CTkLabel(self.accuracy_frame, text="",
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

            acc     = result.get('overall_accuracy')
            passed  = result.get('passed_points', 0)
            if acc is not None:
                self.lbl_accuracy.configure(
                    text=f"{acc:.1f}%  ({passed} / {total_pts} pts)",
                    text_color=self._accuracy_color(acc))
            else:
                self.lbl_accuracy.configure(text="—", text_color="white")

            holes_r = result.get('holes', {}) or {}
            n_holes = len(holes_r)
            n_pass  = sum(1 for hv in holes_r.values() if hv.get('passed'))
            self.lbl_hole_rate.configure(
                text=f"{n_pass} / {n_holes} holes fully passed" if n_holes else "")
        else:
            self.lbl_log_info.configure(text="No .log file loaded", text_color="gray")
            self.lbl_accuracy.configure(text="—", text_color="white")
            self.lbl_hole_rate.configure(text="")

    def _accuracy_color(self, acc: float) -> str:
        if acc >= _ACCURACY_GOOD_THRESHOLD:
            return _COLOR_GOOD
        if acc >= _ACCURACY_WARN_THRESHOLD:
            return _COLOR_WARN
        return _COLOR_BAD

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

        # --- lazy import: core/log_parser.py + core/evaluation_engine.py +
        # core/gcode_generator.py::build_point_map() are not created yet
        # (see PLAN §9, steps 1-3) — fail gracefully instead of crashing.
        try:
            from core.log_parser import parse_openbuilds_log
            from core.evaluation_engine import (
                evaluate_points, build_settings_snapshot, diff_snapshots)
            from core.gcode_generator import build_point_map
        except ImportError as e:
            self.app.notify.show(
                "ยังไม่มีไฟล์คำนวณผล Evaluation ครบ (ต้องมี core/log_parser.py, "
                "core/evaluation_engine.py, และ core/gcode_generator.py::"
                f"build_point_map() ตาม PLAN §7-§9 ก่อน)\n\nรายละเอียด: {e}",
                severity="info", duration_ms=6000)
            return

        try:
            actual_points = parse_openbuilds_log(filepath)
        except Exception as e:
            _mb.showerror("Parse Failed", f"อ่านไฟล์ .log ไม่สำเร็จ:\n{e!r}")
            return

        selected  = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
        view_name = getattr(app, 'current_view', 'Top')

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

        result['log_filename'] = os.path.basename(filepath)
        result['tolerance_mm'] = tolerance
        # keep the raw point lists so the right-sidebar "Apply" tolerance
        # button can re-run evaluate_points() without reloading the file
        result['_expected_points'] = expected_points
        result['_actual_points']   = actual_points

        # v02 FIX: evaluate_points() keys 'holes' by hole_id (display_id
        # string) — remap to global index into app.current_holes, which is
        # what ui/tabs/evaluation_tab.py's contract actually expects.
        _remap_holes_by_gi(result, app.current_holes)

        # --- §6 stale-settings guard ------------------------------------
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
        <name>.snapshot.json (written by core/gcode_export_panel.py in a
        future change) to restore the stale-settings guard across an app
        restart, when no in-session app.last_export_snapshot exists."""
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
        if result is not None:
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
