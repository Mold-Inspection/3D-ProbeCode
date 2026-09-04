# core/gcode_export_panel.py
# VERSION: 05
# CHANGE LOG (v04 -> v05):
#   FEATURE (PLAN_toolbar-and-settings-dialogs_v01.md): rebuilt as a
#   floating VS Code-style dialog (ui/settings_dialog_base.py) instead of
#   an inline collapsible panel in the left sidebar — opened from the new
#   top toolbar's "G-code Export" icon (ui/tool_bar.py) via
#   ui/main_window.py v14, rather than built directly into
#   self._left_scroll. Single category ("Export Settings") since there's
#   only one group of fields here — kept a category list anyway for
#   visual consistency with the Hardware Setting dialog (PLAN §3, open
#   question 3, resolved: dual category list).
#   NO CHANGE to _read_settings()/_on_export()/_suggest_safe_z()/
#   _capture_export_snapshot() logic — same validation, same
#   generate_gcode()/suggest_safe_z() calls, same snapshot capture. Only
#   the container changed: _build_fields(parent) now populates a
#   SettingsDialogBase category frame instead of a self._body collapsible
#   CTkFrame. _toggle_panel()/self._expanded/self._header_frame/the
#   icon-swapped collapse header from v04 are removed (dialogs open/close
#   instead of expand/collapse — no header icon needed here anymore).
import os
import json
import customtkinter as ctk
import tkinter.messagebox as _mb

from core.gcode_generator import GCodeSettings, generate_gcode, suggest_safe_z
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

        ctk.CTkFrame(parent, height=1, fg_color="#2a2a4e").pack(fill="x", pady=(6, 14))

        ctk.CTkButton(
            parent, text="🖨 Export G-code", fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=13, weight="bold"), height=34,
            command=self._on_export).pack(fill="x")

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
    def _read_settings(self):
        try:
            safe_z          = float(self._entries["safe_z"].get().strip())
            entry_clearance = float(self._entries["entry_clearance"].get().strip())
            probe_feedrate  = float(self._entries["probe_feedrate"].get().strip())
            overtravel      = float(self._entries["overtravel"].get().strip())
            backoff         = float(self._entries["backoff"].get().strip())
        except ValueError:
            _mb.showerror("Invalid Input", "กรุณากรอกตัวเลขให้ครบทุกช่อง")
            return None

        if entry_clearance <= 0 or probe_feedrate <= 0 or overtravel < 0 or backoff <= 0:
            _mb.showerror("Invalid Input", "ค่าต้องมากกว่า 0 (Overtravel อนุญาต 0 ได้)")
            return None

        return GCodeSettings(
            safe_z=safe_z, entry_clearance=entry_clearance,
            probe_feedrate=probe_feedrate, overtravel=overtravel, backoff=backoff)

    # ------------------------------------------------------------------
    def _on_export(self):
        app = self.app
        if app.geo.mesh is None:
            _mb.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return

        selected = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
        if not selected:
            _mb.showwarning("No Holes Selected", "ไม่มีรูที่เลือกไว้สำหรับ inspection")
            return

        settings = self._read_settings()
        if settings is None:
            return

        view_name = "Top"
        if hasattr(app, 'current_view'):
            view_name = app.current_view
        elif hasattr(app, 'view_name'):
            view_name = app.view_name
        elif hasattr(app, 'view_combobox'):
            view_name = app.view_combobox.get()

        try:
            gcode_text, skipped, point_map = generate_gcode(selected, app.probe_profile, settings, view_name)
        except Exception as e:
            _mb.showerror("Generation Failed", f"สร้าง G-code ไม่สำเร็จ:\n{e!r}")
            return

        if skipped:
            names = ", ".join(str(getattr(h, 'display_id', '?')) for h in skipped)
            _mb.showwarning(
                "Some Holes Skipped",
                f"ข้ามรู {len(skipped)} รูที่ไม่มีข้อมูล STEP (mesh-only): {names}")

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

        _mb.showinfo("Export Complete", f"บันทึก G-code แล้ว:\n{filepath}")

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