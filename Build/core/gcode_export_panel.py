# core/gcode_export_panel.py
# VERSION: 07
# CHANGE LOG (v06 -> v07):
#   FEATURE (PLAN_evaluation-expected-points-json-and-offset-only_v01.md
#   §4.1/§6): two additions, both using the new core/expected_points_io.py:
#     1) After every successful full G-code export, _capture_expected_
#        points_sidecar() now also writes "<name>.points.json" next to
#        the existing "<name>.snapshot.json" — best-effort, non-blocking,
#        same pattern as _capture_export_snapshot().
#     2) New standalone button "📄 Export Expected Points Only (.json)"
#        in the Export Settings category — calls
#        core.expected_points_io.export_expected_points_json() directly.
#        Deliberately does NOT go through _read_settings() / GCodeSettings
#        validation (Safe Z, feedrate, etc.) at all, since none of that
#        affects expected point coordinates — satisfies Requirement 3
#        ("...โดยที่ไม่ต้องสร้าง G-code ใหม่") literally: a user can get
#        this file without ever touching the G-code Export fields.
#   No change to _read_settings(), the G-code text emission in
#   _on_export(), or _capture_export_snapshot() — both keep working
#   exactly as before, just with one extra sidecar write appended.
import os
import json
import customtkinter as ctk
import tkinter.messagebox as _mb

from core.gcode_generator import GCodeSettings, generate_gcode, suggest_safe_z, suggest_padding_height
from core.expected_points_io import export_expected_points_json
from ui.settings_dialog_base import SettingsDialogBase


class GCodeExportPanel:
    def __init__(self, app):
        self.app = app
        self.dialog = SettingsDialogBase(app.root, title="G-code Export (GRBL)")
        self.dialog.add_category("export", "Export Settings", self._build_fields)
        self._entries = {}

    # ------------------------------------------------------------------
    def show(self):
        self.dialog.show()

    # ------------------------------------------------------------------
    def _build_fields(self, parent):
        fields = [
            ("safe_z",          "Safe Z (mm):",             ""),
            ("padding_height",  "Padding Height (mm):",     "0.0"),
            ("entry_clearance", "Entry Clearance (mm):",    "2.0"),
            ("probe_feedrate",  "Probe Feedrate (mm/min):", "100.0"),
            ("overtravel",      "Overtravel (mm):",         "0.8"),
            ("backoff",         "Back-off (mm):",           "1.2"),
        ]
        for key, label, default in fields:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13),
                        text_color="#b0bec5").pack(anchor="w")
            entry_row = ctk.CTkFrame(row, fg_color="transparent")
            entry_row.pack(fill="x", pady=(4, 0))
            entry = ctk.CTkEntry(entry_row, width=120, height=30,
                                 placeholder_text=default or "e.g. 50.0",
                                 font=ctk.CTkFont(size=13))
            if default:
                entry.insert(0, default)
            entry.pack(side="left")
            self._entries[key] = entry

            if key == "safe_z":
                ctk.CTkButton(entry_row, text="↻ Suggest", width=90, height=30,
                             fg_color="#37474f", hover_color="#546e7a",
                             font=ctk.CTkFont(size=11),
                             command=self._suggest_safe_z).pack(side="left", padx=(8, 0))
            elif key == "padding_height":
                ctk.CTkButton(entry_row, text="↻ Suggest", width=90, height=30,
                             fg_color="#37474f", hover_color="#546e7a",
                             font=ctk.CTkFont(size=11),
                             command=self._suggest_padding_height).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(parent, height=1, fg_color="#2a2a4e").pack(fill="x", pady=(6, 14))

        ctk.CTkButton(
            parent, text="🖨 Export G-code", fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=13, weight="bold"), height=34,
            command=self._on_export).pack(fill="x")

        # v07: standalone action — no GCodeSettings needed at all (only
        # needs a loaded model + selected holes + current view), so it's
        # deliberately placed outside the field-validation flow above.
        ctk.CTkButton(
            parent, text="📄 Export Expected Points Only (.json)",
            fg_color="#37474f", hover_color="#546e7a",
            font=ctk.CTkFont(size=12), height=30,
            command=self._on_export_points_only).pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(
            parent, text="Expected Points (.json) is also written automatically\n"
                         "as a sidecar next to every G-code export — use the\n"
                         "button above only if you want the points WITHOUT\n"
                         "exporting a G-code file.",
            font=ctk.CTkFont(size=10), text_color="#5a6570", justify="left"
        ).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------
    def _suggest_safe_z(self):
        app = self.app
        if app.geo.mesh is None:
            _mb.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return

        view_name = "Top"
        if hasattr(app, 'current_view'):
            view_name = app.current_view

        z = suggest_safe_z(app.geo.mesh, margin=10.0, view_name=view_name)

        self._entries["safe_z"].delete(0, "end")
        self._entries["safe_z"].insert(0, f"{z:.2f}")

    # ------------------------------------------------------------------
    def _suggest_padding_height(self):
        """fill Padding Height from machine_profile.z_height +
        probe_profile.stylus_holder_height/stylus_length + machine_profile
        .z_travel — see core/gcode_generator.py::suggest_padding_height().
        Only needs the machine/probe profiles (always present), unlike
        Safe Z's suggest which needs a loaded mesh."""
        app = self.app
        padding = suggest_padding_height(app.machine_profile, app.probe_profile)

        self._entries["padding_height"].delete(0, "end")
        self._entries["padding_height"].insert(0, f"{padding:.2f}")

    # ------------------------------------------------------------------
    def _read_settings(self):
        try:
            safe_z          = float(self._entries["safe_z"].get().strip())
            entry_clearance = float(self._entries["entry_clearance"].get().strip())
            probe_feedrate  = float(self._entries["probe_feedrate"].get().strip())
            overtravel      = float(self._entries["overtravel"].get().strip())
            backoff         = float(self._entries["backoff"].get().strip())
            padding_str     = self._entries["padding_height"].get().strip()
            padding_height  = float(padding_str) if padding_str else 0.0
        except ValueError:
            _mb.showerror("Invalid Input", "กรุณากรอกตัวเลขให้ครบทุกช่อง")
            return None

        if entry_clearance <= 0 or probe_feedrate <= 0 or overtravel < 0 or backoff <= 0:
            _mb.showerror("Invalid Input", "ค่าต้องมากกว่า 0 (Overtravel อนุญาต 0 ได้)")
            return None

        if padding_height < 0:
            _mb.showerror("Invalid Input", "Padding Height ต้องไม่ติดลบ")
            return None

        return GCodeSettings(
            safe_z=safe_z, entry_clearance=entry_clearance,
            probe_feedrate=probe_feedrate, overtravel=overtravel, backoff=backoff,
            padding_height=padding_height)

    # ------------------------------------------------------------------
    def _get_selected_holes_or_warn(self):
        app = self.app
        if app.geo.mesh is None:
            _mb.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return None
        selected = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
        if not selected:
            _mb.showwarning("No Holes Selected", "ไม่มีรูที่เลือกไว้สำหรับ inspection")
            return None
        return selected

    def _resolve_view_name(self):
        app = self.app
        if hasattr(app, 'current_view'):
            return app.current_view
        if hasattr(app, 'view_name'):
            return app.view_name
        if hasattr(app, 'view_combobox'):
            return app.view_combobox.get()
        return "Top"

    # ------------------------------------------------------------------
    def _on_export(self):
        app = self.app
        selected = self._get_selected_holes_or_warn()
        if selected is None:
            return

        settings = self._read_settings()
        if settings is None:
            return

        view_name = self._resolve_view_name()

        try:
            gcode_text, skipped, point_map = generate_gcode(selected, app.probe_profile, settings, view_name)
        except Exception as e:
            _mb.showerror("Generation Failed", f"สร้าง G-code ไม่สำเร็จ:\n{e!r}")
            return

        if skipped:
            names = ", ".join(str(getattr(h, 'display_id', '?')) for h in skipped)
            app.notify.show(f"ข้ามรู {len(skipped)} รูที่ไม่มีข้อมูล STEP (mesh-only): {names}",
                    severity="warn")

        filepath = ctk.filedialog.asksaveasfilename(
            title="Save G-code", defaultextension=".gcode",
            filetypes=[("G-code Files", "*.gcode *.nc *.txt")])
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(gcode_text)
        except Exception as e:
            _mb.showerror("Save Failed", f"บันทึกไฟล์ไม่สำเร็จ:\n{e!r}")
            return

        self._capture_export_snapshot(selected, view_name, filepath)
        self._capture_expected_points_sidecar(selected, view_name, filepath)   # v07

        app.notify.show(f"บันทึก G-code แล้ว: {filepath}", severity="success")

    # ------------------------------------------------------------------
    def _on_export_points_only(self):
        """v07: standalone action — write ONLY the Expected Points (.json)
        artifact, without validating/requiring any G-code Export Settings
        field and without writing a .gcode file at all (Requirement §3).
        Needs just a loaded model + selected holes + the active view."""
        app = self.app
        selected = self._get_selected_holes_or_warn()
        if selected is None:
            return

        view_name = self._resolve_view_name()

        filepath = ctk.filedialog.asksaveasfilename(
            title="Save Expected Points", defaultextension=".json",
            filetypes=[("Expected Points JSON", "*.json")])
        if not filepath:
            return

        try:
            export_expected_points_json(
                selected, view_name, filepath,
                source_step_filename=getattr(app, 'loaded_step_filename', None),
                tolerance_mm_at_export=getattr(app, 'evaluation_tolerance_mm', None))
        except Exception as e:
            _mb.showerror("Export Failed", f"เขียนไฟล์ Expected Points ไม่สำเร็จ:\n{e!r}")
            return

        app.notify.show(f"บันทึก Expected Points แล้ว: {filepath}", severity="success")

    # ------------------------------------------------------------------
    def _capture_export_snapshot(self, selected_holes, view_name, gcode_filepath):
        """หลัง export สำเร็จ — จับภาพค่าตั้งค่าการตรวจสอบของรูที่เพิ่ง
        export ไป ทั้งแบบเก็บใน memory (app.last_export_snapshot) และเขียน
        เป็นไฟล์ sidecar "<ชื่อ .gcode>.snapshot.json" (best-effort) —
        ความล้มเหลวที่นี่ต้องไม่กระทบการ export ที่สำเร็จไปแล้ว"""
        app = self.app
        try:
            from core.evaluation_engine import build_settings_snapshot
        except ImportError as e:
            print(f"[gcode_export_panel] snapshot skipped — "
                  f"core/evaluation_engine.py not available yet ({e!r})")
            return

        try:
            snapshot = build_settings_snapshot(selected_holes, view_name)
        except Exception as e:
            print(f"[gcode_export_panel] snapshot build failed (non-blocking): {e!r}")
            return

        app.last_export_snapshot = snapshot

        try:
            sidecar_path = os.path.splitext(gcode_filepath)[0] + ".snapshot.json"
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            print(f"[gcode_export_panel] export snapshot written to {sidecar_path}")
        except Exception as e:
            print(f"[gcode_export_panel] sidecar snapshot write failed (non-blocking): {e!r}")

    # ------------------------------------------------------------------
    def _capture_expected_points_sidecar(self, selected_holes, view_name, gcode_filepath):
        """v07: after a successful full G-code export, also write the
        Expected Points (.json) sidecar "<name>.points.json" next to the
        .snapshot.json sidecar — satisfies "users who DO export G-code
        get it for free" (plan §4.1). Best-effort only, never blocks a
        successful export that already wrote the .gcode file."""
        app = self.app
        try:
            sidecar_path = os.path.splitext(gcode_filepath)[0] + ".points.json"
            export_expected_points_json(
                selected_holes, view_name, sidecar_path,
                source_step_filename=getattr(app, 'loaded_step_filename', None),
                tolerance_mm_at_export=getattr(app, 'evaluation_tolerance_mm', None))
            print(f"[gcode_export_panel] expected points sidecar written to {sidecar_path}")
        except Exception as e:
            print(f"[gcode_export_panel] expected points sidecar write failed (non-blocking): {e!r}")
