# core/gcode_export_panel.py
# VERSION: 09
# CHANGE LOG (v08 -> v09):
#   FEATURE (user request, follow-up to
#   PLAN_merged-export-record-non-destructive_v01.md): renamed the
#   written sidecar from "<name>.export.json" to "<name>_schema.json"
#   (matches core/expected_points_io.py v03's export_schema_json() /
#   load_schema_json() rename), and the standalone button now suggests
#   that filename as its default save name too.
#   FIX (bug report — see core/evaluation_engine.py v04's changelog):
#   the settings snapshot written into the schema file must capture ALL
#   current holes (selected AND unselected), not just the ones currently
#   selected for inspection — otherwise a loaded schema can never
#   restore "which holes were selected at export time" at all, since
#   unselected holes never appeared in the snapshot in the first place.
#   _build_snapshot_or_none() now takes the holes to snapshot as an
#   explicit parameter and both call sites (_capture_export_record(),
#   _on_export_points_only()) now pass `app.current_holes` (ALL holes)
#   instead of the `selected` list used for the G-code/points
#   calculation — those two lists serve different purposes and are now
#   kept explicitly separate: `selected` still drives build_point_map()/
#   generate_gcode() (only selected holes are ever machined/probed), while
#   `app.current_holes` drives the settings snapshot (needs the full
#   picture so a later full-replace restore is possible).
#   Renamed export_combined_record_json import -> export_schema_json to
#   match core/expected_points_io.py v03. Wording updated from "Export
#   Record" to "Schema" throughout button labels/dialogs/messages.
import os
import customtkinter as ctk
import tkinter.messagebox as _mb

from core.gcode_generator import GCodeSettings, generate_gcode, suggest_safe_z, suggest_padding_height
from core.expected_points_io import export_schema_json
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

        # v09: standalone action — still no GCodeSettings needed at all
        # (only needs a loaded model + selected holes + current view),
        # deliberately placed outside the field-validation flow above.
        # Writes the "<name>_schema.json" combined format (points + full
        # settings snapshot) — see file changelog.
        ctk.CTkButton(
            parent, text="📄 Export Schema Only (.json)",
            fg_color="#37474f", hover_color="#546e7a",
            font=ctk.CTkFont(size=12), height=30,
            command=self._on_export_points_only).pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(
            parent, text="A Schema (.json) — points + full settings — is\n"
                         "also written automatically next to every G-code\n"
                         "export, as \"<name>_schema.json\". Use the button\n"
                         "above only if you want the schema WITHOUT\n"
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

    def _default_schema_filename(self) -> str:
        """v09: suggested filename for the standalone save dialog —
        "<step basename>_schema.json" when a STEP file is loaded,
        otherwise just "schema.json"."""
        app = self.app
        base = getattr(app, 'loaded_step_filename', None)
        if base:
            base = os.path.splitext(base)[0]
            return f"{base}_schema.json"
        return "schema.json"

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

        self._capture_export_record(selected, view_name, filepath)   # v09

        app.notify.show(f"บันทึก G-code แล้ว: {filepath}", severity="success")

    # ------------------------------------------------------------------
    def _on_export_points_only(self):
        """v09: standalone action — writes ONLY the Schema (.json),
        without validating/requiring any G-code Export Settings field and
        without writing a .gcode file at all. Writes the combined format
        (points + FULL settings snapshot, built from ALL current holes —
        see file changelog) as "<name>_schema.json"."""
        app = self.app
        selected = self._get_selected_holes_or_warn()
        if selected is None:
            return

        view_name = self._resolve_view_name()

        filepath = ctk.filedialog.asksaveasfilename(
            title="Save Schema", defaultextension=".json",
            initialfile=self._default_schema_filename(),
            filetypes=[("Schema JSON", "*.json")])
        if not filepath:
            return

        # v09: snapshot ALL current holes (selected + unselected), not
        # just `selected` — the schema must be able to fully replace the
        # current configuration on load, including which holes are
        # selected at all.
        settings_snapshot = self._build_snapshot_or_none(app.current_holes, view_name)

        try:
            export_schema_json(
                selected, view_name, filepath,
                settings_snapshot=settings_snapshot or {'view_name': view_name, 'holes': {}},
                source_step_filename=getattr(app, 'loaded_step_filename', None),
                tolerance_mm_at_export=getattr(app, 'evaluation_tolerance_mm', None))
        except Exception as e:
            _mb.showerror("Export Failed", f"เขียนไฟล์ Schema ไม่สำเร็จ:\n{e!r}")
            return

        app.notify.show(f"บันทึก Schema แล้ว: {filepath}", severity="success")

    # ------------------------------------------------------------------
    def _build_snapshot_or_none(self, holes_to_snapshot, view_name):
        """v09: best-effort build of the settings snapshot — returns None
        (never raises) if core/evaluation_engine.py isn't importable yet
        or the build itself fails, so a schema can still be written with
        a placeholder empty snapshot rather than failing the whole
        export. `holes_to_snapshot` should be ALL of app.current_holes
        (not just the selected ones) so the written snapshot is a
        complete picture — see file changelog. Shared by both the
        automatic sidecar path (_capture_export_record) and the
        standalone button (_on_export_points_only)."""
        try:
            from core.evaluation_engine import build_settings_snapshot
        except ImportError as e:
            print(f"[gcode_export_panel] settings_snapshot skipped — "
                  f"core/evaluation_engine.py not available yet ({e!r})")
            return None
        try:
            return build_settings_snapshot(holes_to_snapshot, view_name)
        except Exception as e:
            print(f"[gcode_export_panel] settings_snapshot build failed (non-blocking): {e!r}")
            return None

    # ------------------------------------------------------------------
    def _capture_export_record(self, selected_holes, view_name, gcode_filepath):
        """v09: หลัง export G-code สำเร็จ — สร้าง settings snapshot จาก
        รูทั้งหมด (app.current_holes ไม่ใช่แค่ selected_holes) ครั้งเดียว
        แล้วเขียนไฟล์ Schema "<name>_schema.json" ไฟล์เดียว (แทนที่
        "<name>.export.json" เดิม) — best-effort, ความล้มเหลวที่นี่ต้อง
        ไม่กระทบการ export G-code ที่สำเร็จไปแล้ว"""
        app = self.app
        snapshot = self._build_snapshot_or_none(app.current_holes, view_name)   # v09: ALL holes
        if snapshot is not None:
            app.last_export_snapshot = snapshot   # kept in-memory for this session's stale-settings guard

        try:
            sidecar_path = os.path.splitext(gcode_filepath)[0] + "_schema.json"   # v09: renamed
            export_schema_json(
                selected_holes, view_name, sidecar_path,
                settings_snapshot=snapshot or {'view_name': view_name, 'holes': {}},
                source_step_filename=getattr(app, 'loaded_step_filename', None),
                tolerance_mm_at_export=getattr(app, 'evaluation_tolerance_mm', None))
            print(f"[gcode_export_panel] schema written to {sidecar_path}")
        except Exception as e:
            print(f"[gcode_export_panel] schema write failed (non-blocking): {e!r}")
