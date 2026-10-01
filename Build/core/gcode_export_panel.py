# core/gcode_export_panel.py
# VERSION: 12
# CHANGE LOG (v11 -> v12):
#   FIX: ส่งการหมุนจอ (app.screen_rotation) เข้า generate_gcode() /
#   export_schema_json() / build_settings_snapshot() — X/Y ของ G-code และ
#   Schema ตรงกับที่เห็นบนจอหลังกด Rotate (ดู gcode_generator.py v08)
# CHANGE LOG (v10 -> v11):
#   FEATURE: หมวด "Axis Test (X/Y)" ในหน้าต่าง G-code Export — สร้างไฟล์
#   G-code ทดสอบแกนจาก core/axis_test.py: เข็มเริ่มที่มุมซ้ายบนของชิ้นงาน
#   (Set Zero ไว้แล้ว) เดินไปครบ 4 มุมแล้วกลับจุด zero ไว้เช็คทิศ/ระยะแกน
#   X/Y ใน OpenBuilds Control ก่อนรันโปรแกรมโพรบจริง — ขนาดชิ้นงานดึงจาก
#   โมเดลในมุมมองปัจจุบันบนจอ (แก้เองได้) ไม่ต้องมีรูที่เลือกไว้
#
# CHANGE LOG (v09 -> v10):
#   FEATURE (user request — "after exporting G-code, auto-set the Schema
#   as the active one, without the user picking it by hand"): both
#   sidecar-writing paths now push the schema they just wrote straight
#   into the app's "active schema" state — the exact same state
#   ui/evaluation_left_panel.py v08's "📂 Load Schema (.json)" button
#   sets, just without a file dialog:
#     - _capture_export_record() (the automatic sidecar after
#       "🖨 Export G-code")
#     - _on_export_points_only() (the standalone "📄 Export Schema Only"
#       button)
#   New shared helper _auto_load_schema(payload, filepath) does this:
#   sets app.loaded_schema / loaded_expected_points / _source / _view
#   from the `payload` dict that core/expected_points_io.py v04's
#   export_schema_json() now RETURNS (no re-reading the file back from
#   disk, no recomputing build_point_map() a second time). Does NOT call
#   apply_settings_snapshot() — unnecessary here, since the
#   settings_snapshot was built from app.current_holes at the exact
#   moment of export, i.e. it already IS the current configuration,
#   nothing to replace. Also calls
#   app.evaluation_left_panel._auto_refresh_if_result_exists() (added in
#   v08) so an already-loaded .log's results are recomputed immediately
#   too, and refreshes the evaluation left/right sidebars + redraws the
#   Evaluation tab if it's the one currently visible — all best-effort
#   (wrapped so a UI refresh failure never affects the export that
#   already succeeded).
#   Both success toasts now mention that the schema was set active (and
#   whether results were refreshed), so the user doesn't have to guess.
#
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

from core.gcode_generator import (GCodeSettings, generate_gcode, suggest_safe_z, suggest_padding_height,
                                  probe_safety_report, gcode_extents)
from core.expected_points_io import export_schema_json
from core.axis_test import (AxisTestSettings, generate_axis_test_gcode,
                            hole_centers_from_view, generate_hole_center_test_gcode)
from core.work_zero import (DEFAULT_WORK_ZERO, label_of, describe, work_zero_origin,
                            zero_offset_from_upper_left, test_zero_name, zero_view_text)
from ui.settings_dialog_base import SettingsDialogBase
from core import user_settings
from ui import theme


class GCodeExportPanel:
    def __init__(self, app):
        self.app = app
        self.dialog = SettingsDialogBase(app.root, title="G-code Export (GRBL)")
        self.dialog.add_category("export", "Export Settings", self._build_fields)
        self.dialog.add_category("axis_test", "Axis Test (X/Y)", self._build_axis_test_fields)
        self._entries = {}
        self._axis_entries = {}
        self.dialog.on_close = self._remember_fields   # จำค่าที่กรอกไว้ทุกครั้งที่ปิด dialog

    # ------------------------------------------------------------------
    def show(self):
        self.dialog.show()

    # ------------------------------------------------------------------
    # Work zero (X0 Y0 Z0) — core/work_zero.py
    # ------------------------------------------------------------------
    def _work_zero(self) -> str:
        return getattr(self.app, 'work_zero', DEFAULT_WORK_ZERO)

    def _zero_origin(self, view_name):
        """ตำแหน่งจุด zero ในพิกัดเครื่อง — ลบออกจากทุกพิกัดของ G-code / Schema"""
        app = self.app
        return work_zero_origin(app.geo.mesh, view_name,
                                getattr(app, 'screen_rotation', 0), self._work_zero())

    def _zero_note(self):
        """ข้อความหัวไฟล์ G-code — None = ใช้บรรทัดเดิม (mesh centroid)"""
        mode = self._work_zero()
        return None if mode == DEFAULT_WORK_ZERO else describe(mode)

    # ------------------------------------------------------------------
    # จำค่าที่กรอกไว้ข้ามการเปิดโปรแกรม (core/user_settings.py)
    # Safe Z และขนาดชิ้นงานของ Axis Test ไม่จำ — ขึ้นกับชิ้นงานแต่ละชิ้น
    # ------------------------------------------------------------------
    _REMEMBER_EXPORT = ("padding_height", "entry_clearance", "probe_feedrate", "overtravel", "backoff")
    _REMEMBER_AXIS   = ("z_lift", "feedrate", "dwell_s")

    def _remember_fields(self):
        for section, entries, keys in (("export", self._entries, self._REMEMBER_EXPORT),
                                       ("axis_test", self._axis_entries, self._REMEMBER_AXIS)):
            values = {}
            for key in keys:
                entry = entries.get(key)
                try:
                    if entry is not None and entry.winfo_exists():
                        values[key] = float(entry.get().strip())
                except (ValueError, Exception):
                    continue
            if values:
                saved = user_settings.get(section, {}) or {}
                saved.update(values)
                user_settings.save_section(section, saved)

    def _build_fields(self, parent):
        # --- Work zero (X0 Y0 Z0) — ตั้งค่าที่ Hardware Setting → Work Zero ----
        ctk.CTkLabel(parent, text="Work zero (X0 Y0 Z0):", font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360, font=ctk.CTkFont(size=13, weight="bold"),
            text=f"{label_of(self._work_zero())}  ({zero_view_text(self.app)})").pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360, font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED,
            text="Change it in Hardware Setting → Work Zero. Safe Z \u21bb Suggest uses this zero."
        ).pack(fill="x", pady=(0, 6))
        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(fill="x", pady=(4, 12))

        saved = user_settings.get("export", {}) or {}
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
                        text_color=theme.TEXT_SECONDARY).pack(anchor="w")
            entry_row = ctk.CTkFrame(row, fg_color="transparent")
            entry_row.pack(fill="x", pady=(4, 0))
            entry = ctk.CTkEntry(entry_row, width=120, height=30,
                                 placeholder_text=default or "e.g. 50.0",
                                 font=ctk.CTkFont(size=13))
            if key in self._REMEMBER_EXPORT and key in saved:
                default = f"{float(saved[key]):g}"   # ค่าที่ใช้ครั้งก่อน
            if default:
                entry.insert(0, default)
            entry.pack(side="left")
            self._entries[key] = entry

            if key == "safe_z":
                ctk.CTkButton(entry_row, text="↻ Suggest", width=90, height=30,
                             fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
                             font=ctk.CTkFont(size=11),
                             command=self._suggest_safe_z).pack(side="left", padx=(8, 0))
            elif key == "padding_height":
                ctk.CTkButton(entry_row, text="↻ Suggest", width=90, height=30,
                             fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
                             font=ctk.CTkFont(size=11),
                             command=self._suggest_padding_height).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(fill="x", pady=(6, 14))

        ctk.CTkButton(
            parent, text="🖨 Export G-code", fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"), height=34,
            command=self._on_export).pack(fill="x")

        # v09: standalone action — still no GCodeSettings needed at all
        # (only needs a loaded model + selected holes + current view),
        # deliberately placed outside the field-validation flow above.
        # Writes the "<name>_schema.json" combined format (points + full
        # settings snapshot) — see file changelog.
        ctk.CTkButton(
            parent, text="📄 Export Schema Only (.json)",
            fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
            font=ctk.CTkFont(size=12), height=30,
            command=self._on_export_points_only).pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(
            parent, text="A Schema (.json) — points + full settings — is\n"
                         "also written automatically next to every G-code\n"
                         "export, as \"<name>_schema.json\". Use the button\n"
                         "above only if you want the schema WITHOUT\n"
                         "exporting a G-code file.",
            font=ctk.CTkFont(size=10), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # v11: Axis Test — corner trace G-code
    # ------------------------------------------------------------------
    def _axis_intro_text(self) -> str:
        return ("Checks that the X/Y axes move the right way and the right "
                f"distance. Put the needle on the {test_zero_name(self._work_zero())} "
                "of the object (as it looks on screen) and Set Zero X/Y/Z there in "
                "OpenBuilds — the zero point is set in Hardware Setting → Work Zero. "
                "The program visits every corner, pauses at each one, then "
                "returns to the zero point.")

    def _test_zero(self, width_x: float, length_y: float):
        """(offset จากมุมซ้ายบน, ชื่อจุด zero) สำหรับ G-code ทดสอบ"""
        mode = self._work_zero()
        return zero_offset_from_upper_left(mode, width_x, length_y), test_zero_name(mode)

    def _build_axis_test_fields(self, parent):
        self._lbl_axis_intro = ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360,
            font=ctk.CTkFont(size=12), text_color=theme.TEXT_SECONDARY,
            text=self._axis_intro_text())
        self._lbl_axis_intro.pack(fill="x", pady=(0, 12))

        saved = user_settings.get("axis_test", {}) or {}
        fields = [
            ("width_x",  "Object width — X (mm):",  ""),
            ("length_y", "Object length — Y (mm):", ""),
            ("z_lift",   "Z Lift while moving (mm, 0 = none):", "5.0"),
            ("feedrate", "Feedrate (mm/min):",       "500.0"),
            ("dwell_s",  "Pause at each corner (s):", "2.0"),
        ]
        for key, label, default in fields:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13),
                        text_color=theme.TEXT_SECONDARY).pack(anchor="w")
            entry_row = ctk.CTkFrame(row, fg_color="transparent")
            entry_row.pack(fill="x", pady=(4, 0))
            entry = ctk.CTkEntry(entry_row, width=120, height=30,
                                 placeholder_text=default or "e.g. 300.0",
                                 font=ctk.CTkFont(size=13))
            if key in self._REMEMBER_AXIS and key in saved:
                default = f"{float(saved[key]):g}"   # ค่าที่ใช้ครั้งก่อน
            if default:
                entry.insert(0, default)
            entry.pack(side="left")
            self._axis_entries[key] = entry
            if key == "width_x":
                ctk.CTkButton(entry_row, text="↻ From model", width=110, height=30,
                             fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
                             font=ctk.CTkFont(size=11),
                             command=self._fill_axis_test_size).pack(side="left", padx=(8, 0))

        self._fill_axis_test_size(quiet=True)

        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(fill="x", pady=(6, 14))
        ctk.CTkButton(
            parent, text="🖨 Export Axis Test G-code", fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER, font=ctk.CTkFont(size=13, weight="bold"),
            height=34, command=self._on_export_axis_test).pack(fill="x")

        ctk.CTkButton(
            parent, text="🎯 Export Hole-Center Test G-code",
            fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
            font=ctk.CTkFont(size=12), height=30,
            command=self._on_export_hole_center_test).pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360,
            font=ctk.CTkFont(size=10), text_color=theme.TEXT_MUTED,
            text=("Hole-Center Test: same zero as the Axis Test and same "
                  "settings, but visits the center of every hole/pocket that is "
                  "selected for inspection, pausing over each one, then returns "
                  "to the zero point.")
        ).pack(anchor="w", pady=(4, 0))

        ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360,
            font=ctk.CTkFont(size=10), text_color=theme.TEXT_MUTED,
            text=("Path: upper-left → upper-right → lower-right → lower-left → "
                  "upper-left. Assumes X+ = right and Y+ = toward the back of "
                  "the machine (up on screen), so the lower corners are at "
                  "negative Y. If the needle goes the other way, that axis "
                  "direction is inverted on the machine. Lay the part on the "
                  "machine the same way it is shown on screen (use Rotate if "
                  "needed). Run with a hand on the stop button the first time.")
        ).pack(anchor="w", pady=(8, 0))

    def _fill_axis_test_size(self, quiet: bool = False):
        """ขนาดชิ้นงานตามแกน X/Y ของมุมมองบนจอปัจจุบัน (รวมการหมุนจอ)"""
        app = self.app
        xs, ys = getattr(app, 'current_x', None), getattr(app, 'current_y', None)
        if app.geo.mesh is None or xs is None or ys is None or len(xs) == 0:
            if not quiet:
                self.dialog.showwarning("No Model", "กรุณาโหลดโมเดลก่อน หรือกรอกขนาดเอง")
            return
        for key, vals in (("width_x", xs), ("length_y", ys)):
            entry = self._axis_entries[key]
            entry.delete(0, "end")
            entry.insert(0, f"{float(max(vals) - min(vals)):.3f}")

    def _read_axis_test_settings(self):
        try:
            settings = AxisTestSettings(**{k: float(e.get().strip())
                                           for k, e in self._axis_entries.items()})
        except ValueError:
            self.dialog.showerror("Invalid Input", "กรุณากรอกตัวเลขให้ครบทุกช่อง")
            return None
        err = settings.validate()
        if err:
            self.dialog.showerror("Invalid Input", err)
            return None
        return settings

    def _save_test_gcode(self, gcode_text, suffix, title, summary, zero_name="UPPER-LEFT corner"):
        base = os.path.splitext(getattr(self.app, 'loaded_step_filename', None) or "object")[0]
        filepath = self.dialog.run_native(
            ctk.filedialog.asksaveasfilename,
            title=title, defaultextension=".gcode",
            initialfile=f"{base}_{suffix}.gcode",
            filetypes=[("G-code Files", "*.gcode *.nc *.txt")])
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(gcode_text)
        except Exception as e:
            self.dialog.showerror("Save Failed", f"บันทึกไฟล์ไม่สำเร็จ:\n{e!r}")
            return
        self.dialog.showinfo(
            "Export complete",
            f"บันทึก {title.replace('Save ', '')} แล้ว:\n{filepath}\n\n{summary}\n"
            f"ตั้งเข็มที่ {zero_name} ของชิ้นงาน แล้ว Set Zero ก่อนรัน")

    def _on_export_axis_test(self):
        settings = self._read_axis_test_settings()
        if settings is None:
            return
        zero_offset, zero_name = self._test_zero(settings.width_x, settings.length_y)
        gcode_text = generate_axis_test_gcode(
            settings, self._resolve_view_name(), getattr(self.app, 'loaded_step_filename', None),
            zero_offset=zero_offset, zero_name=zero_name)
        self._save_test_gcode(
            gcode_text, "axis_test", "Save Axis Test G-code",
            f"ขนาด X {settings.width_x:.2f} × Y {settings.length_y:.2f} mm", zero_name)

    def _on_export_hole_center_test(self):
        """v11: เดินไปจุดศูนย์กลางของทุกรูที่เลือกไว้ตรวจ — zero เดียวกับ corner trace"""
        app = self.app
        if app.geo.mesh is None or getattr(app, 'current_x', None) is None:
            self.dialog.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return
        # ขนาดจริงของชิ้นงานบนจอ → ตำแหน่งจุด zero ที่เลือก เทียบมุมซ้ายบน
        zero_offset, zero_name = self._test_zero(float(max(app.current_x) - min(app.current_x)),
                                                 float(max(app.current_y) - min(app.current_y)))
        centers = hole_centers_from_view(app.current_holes, app.current_x, app.current_y,
                                         zero_offset=zero_offset)
        if not centers:
            self.dialog.showwarning("No Holes Selected",
                                    "ไม่มีรูที่เลือกไว้สำหรับ inspection — กด Generate Holes แล้วเลือกรูก่อน")
            return
        settings = self._read_axis_test_settings()
        if settings is None:
            return
        gcode_text = generate_hole_center_test_gcode(
            settings, centers, self._resolve_view_name(),
            getattr(app, 'loaded_step_filename', None), zero_name=zero_name)
        self._save_test_gcode(
            gcode_text, "hole_center_test", "Save Hole-Center Test G-code",
            f"{len(centers)} รู — เดินไปจุดศูนย์กลางทีละรูแล้วกลับจุด zero", zero_name)

    # ------------------------------------------------------------------
    def _suggest_safe_z(self):
        app = self.app
        if app.geo.mesh is None:
            self.dialog.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return

        view_name = "Top"
        if hasattr(app, 'current_view'):
            view_name = app.current_view

        z = suggest_safe_z(app.geo.mesh, margin=10.0, view_name=view_name,
                           zero_z=float(self._zero_origin(view_name)[2]))

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
            self.dialog.showerror("Invalid Input", "กรุณากรอกตัวเลขให้ครบทุกช่อง")
            return None

        if entry_clearance <= 0 or probe_feedrate <= 0 or overtravel < 0 or backoff <= 0:
            self.dialog.showerror("Invalid Input", "ค่าต้องมากกว่า 0 (Overtravel อนุญาต 0 ได้)")
            return None

        if padding_height < 0:
            self.dialog.showerror("Invalid Input", "Padding Height ต้องไม่ติดลบ")
            return None

        return GCodeSettings(
            safe_z=safe_z, entry_clearance=entry_clearance,
            probe_feedrate=probe_feedrate, overtravel=overtravel, backoff=backoff,
            padding_height=padding_height)

    # ------------------------------------------------------------------
    def _get_selected_holes_or_warn(self):
        app = self.app
        if app.geo.mesh is None:
            self.dialog.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return None
        selected = [h for h in app.current_holes if getattr(h, 'selected_for_inspection', False)]
        if not selected:
            self.dialog.showwarning("No Holes Selected", "ไม่มีรูที่เลือกไว้สำหรับ inspection")
            return None
        return selected

    # ------------------------------------------------------------------
    # Export guard + travel check — ใช้ค่าจาก Hardware Setting
    # ------------------------------------------------------------------
    def _guard_holes(self, selected, backoff: float):
        """ตัดรูที่โพรบไม่ได้อย่างปลอดภัยด้วยหัวโพรบปัจจุบัน (ถามผู้ใช้ก่อน)
        คืน (รูที่จะ export, ชื่อรูที่ถูกข้าม) หรือ (None, None) ถ้ายกเลิก"""
        problems = probe_safety_report(selected, self.app.probe_profile, backoff)
        if not problems:
            return selected, []
        lines = [f"\u2022 Hole {getattr(h, 'display_id', '?')}: " + "; ".join(reasons)
                 for h, reasons in problems[:12]]
        if len(problems) > 12:
            lines.append(f"\u2022 \u2026 and {len(problems) - 12} more")
        detail = "\n".join(lines)
        fix = "\n\nChange the stylus in Hardware Setting \u2192 Probe Stylus, or the hole settings."
        if len(problems) == len(selected):
            self.dialog.showerror(
                "Cannot probe safely",
                "None of the selected holes can be probed safely with the current probe:\n\n" + detail + fix)
            return None, None
        if not self.dialog.askyesno(
                "Some holes can't be probed safely",
                f"{len(problems)} of {len(selected)} selected holes can't be probed safely with "
                f"the current probe:\n\n{detail}{fix}\n\nSkip these holes and export the rest?"):
            return None, None
        bad = {id(h) for h, _ in problems}
        return ([h for h in selected if id(h) not in bad],
                [str(getattr(h, 'display_id', '?')) for h, _ in problems])

    def _travel_ok(self, gcode_text: str) -> bool:
        """เตือนถ้าโปรแกรมสั่งเดินไกลกว่าระยะเดินของเครื่อง (Hardware Setting → Machine
        Working Area) — เทียบ "ความยาวช่วง" ต่อแกน เพราะไม่รู้ว่าจุด zero อยู่ตรงไหนของโต๊ะ"""
        m = self.app.machine_profile
        ext = gcode_extents(gcode_text)
        over = []
        for ax, limit in (("X", m.x_travel), ("Y", m.y_travel), ("Z", m.z_travel)):
            if ax not in ext:
                continue
            lo, hi = ext[ax]
            if hi - lo > limit:
                over.append(f"\u2022 {ax}: moves over {hi - lo:.1f} mm ({lo:.1f} \u2192 {hi:.1f}), "
                            f"machine travel is {limit:.1f} mm")
        if not over:
            return True
        return self.dialog.askyesno(
            "Exceeds machine travel",
            "This program moves farther than the machine can travel "
            "(Hardware Setting \u2192 Machine Working Area):\n\n" + "\n".join(over) +
            "\n\nZ includes the climb to Safe Z. Export anyway?")

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
        self._remember_fields()

        selected, unsafe = self._guard_holes(selected, settings.backoff)
        if selected is None:
            return

        view_name = self._resolve_view_name()

        try:
            gcode_text, skipped, point_map = generate_gcode(selected, app.probe_profile, settings, view_name,
                                                            screen_rot=getattr(self.app, 'screen_rotation', 0),
                                                            origin=self._zero_origin(view_name),
                                                            zero_note=self._zero_note())
        except Exception as e:
            self.dialog.showerror("Generation Failed", f"สร้าง G-code ไม่สำเร็จ:\n{e!r}")
            return

        if not self._travel_ok(gcode_text):
            return

        filepath = self.dialog.run_native(
            ctk.filedialog.asksaveasfilename,
            title="Save G-code", defaultextension=".gcode",
            filetypes=[("G-code Files", "*.gcode *.nc *.txt")])
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(gcode_text)
        except Exception as e:
            self.dialog.showerror("Save Failed", f"บันทึกไฟล์ไม่สำเร็จ:\n{e!r}")
            return

        schema_report = self._capture_export_record(selected, view_name, filepath)   # v09/v10

        # popup ยืนยันว่า export เสร็จ — ใช้ messagebox ที่มี dialog นี้เป็นเจ้าของ
        # (toast ของ app.notify วางอยู่บนหน้าต่างหลัก จึงถูก dialog นี้บังไว้)
        msg = f"บันทึก G-code แล้ว:\n{filepath}"
        if schema_report.get('written'):
            msg += f"\n\nบันทึก Schema แล้ว:\n{schema_report.get('path')}"
            msg += "\n\nแท็บ Evaluation โหลด Schema นี้ให้แล้วอัตโนมัติ"
            if schema_report.get('refreshed'):
                msg += " และคำนวณผลลัพธ์ใหม่แล้ว"
        else:
            msg += "\n\n(เขียนไฟล์ Schema ไม่สำเร็จ — แท็บ Evaluation จะใช้ค่ารูปัจจุบันแทน)"
        if skipped:
            names = ", ".join(str(getattr(h, 'display_id', '?')) for h in skipped)
            msg += f"\n\nข้ามรู {len(skipped)} รูที่ไม่มีข้อมูล STEP (mesh-only): {names}"
        if unsafe:
            msg += f"\n\nข้ามรู {len(unsafe)} รูที่หัวโพรบปัจจุบันโพรบได้ไม่ปลอดภัย: {', '.join(unsafe)}"
        self.dialog.showinfo("Export complete", msg)

    # ------------------------------------------------------------------
    def _backoff_for_guard(self) -> float:
        try:
            return float(self._entries["backoff"].get().strip())
        except Exception:
            return float((user_settings.get("export", {}) or {}).get("backoff", 1.2))

    def _on_export_points_only(self):
        """standalone action — writes ONLY the Schema (.json), without
        validating/requiring any G-code Export Settings field and without
        writing a .gcode file at all. Writes the combined format (points
        + FULL settings snapshot, built from ALL current holes — see
        file changelog) as "<name>_schema.json", then (v10) immediately
        sets it as the app's active schema — see _auto_load_schema()."""
        app = self.app
        selected = self._get_selected_holes_or_warn()
        if selected is None:
            return
        # ชุดรูเดียวกับที่ Export G-code จะใช้ — schema กับ G-code จึงตรงกันเสมอ
        selected, _unsafe = self._guard_holes(selected, self._backoff_for_guard())
        if selected is None:
            return

        view_name = self._resolve_view_name()

        filepath = self.dialog.run_native(
            ctk.filedialog.asksaveasfilename,
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
            payload = export_schema_json(
                selected, view_name, filepath,
                settings_snapshot=settings_snapshot or {'view_name': view_name, 'holes': {}},
                source_step_filename=getattr(app, 'loaded_step_filename', None),
                tolerance_mm_at_export=getattr(app, 'evaluation_tolerance_mm', None),
                screen_rot=getattr(self.app, 'screen_rotation', 0),
                origin=self._zero_origin(view_name), work_zero=self._work_zero())
        except Exception as e:
            self.dialog.showerror("Export Failed", f"เขียนไฟล์ Schema ไม่สำเร็จ:\n{e!r}")
            return

        # v10: this schema was just built from the CURRENT app.current_holes
        # config — set it active immediately, same as picking it via
        # "Load Schema (.json)" would, minus the file dialog.
        refreshed = self._auto_load_schema(payload, filepath)

        msg = f"บันทึก Schema แล้ว:\n{filepath}\n\nแท็บ Evaluation โหลด Schema นี้ให้แล้วอัตโนมัติ"
        if refreshed:
            msg += " และคำนวณผลลัพธ์ใหม่แล้ว"
        self.dialog.showinfo("Export complete", msg)

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
            return build_settings_snapshot(holes_to_snapshot, view_name, getattr(self.app, 'screen_rotation', 0))
        except Exception as e:
            print(f"[gcode_export_panel] settings_snapshot build failed (non-blocking): {e!r}")
            return None

    # ------------------------------------------------------------------
    def _capture_export_record(self, selected_holes, view_name, gcode_filepath) -> dict:
        """หลัง export G-code สำเร็จ — สร้าง settings snapshot จากรูทั้งหมด
        (app.current_holes ไม่ใช่แค่ selected_holes) ครั้งเดียว แล้วเขียน
        ไฟล์ Schema "<name>_schema.json" ไฟล์เดียว — best-effort, ความ
        ล้มเหลวที่นี่ต้องไม่กระทบการ export G-code ที่สำเร็จไปแล้ว v10:
        ยังตั้ง schema ที่เพิ่งเขียนเป็น "schema ที่ใช้งานอยู่" ของแอปทันที
        ผ่าน _auto_load_schema() ด้วย

        Returns
        -------
        dict: {'written': bool, 'refreshed': bool} — ใช้โดย _on_export()
        เพื่อแต่งข้อความ toast เท่านั้น ไม่มีผลต่อการ export G-code
        """
        app = self.app
        snapshot = self._build_snapshot_or_none(app.current_holes, view_name)   # v09: ALL holes
        if snapshot is not None:
            app.last_export_snapshot = snapshot   # kept in-memory for this session's stale-settings guard

        try:
            sidecar_path = os.path.splitext(gcode_filepath)[0] + "_schema.json"   # v09: renamed
            payload = export_schema_json(
                selected_holes, view_name, sidecar_path,
                settings_snapshot=snapshot or {'view_name': view_name, 'holes': {}},
                source_step_filename=getattr(app, 'loaded_step_filename', None),
                tolerance_mm_at_export=getattr(app, 'evaluation_tolerance_mm', None),
                screen_rot=getattr(self.app, 'screen_rotation', 0),
                origin=self._zero_origin(view_name), work_zero=self._work_zero())
            print(f"[gcode_export_panel] schema written to {sidecar_path}")
        except Exception as e:
            print(f"[gcode_export_panel] schema write failed (non-blocking): {e!r}")
            return {'written': False, 'refreshed': False, 'path': None}

        refreshed = self._auto_load_schema(payload, sidecar_path)   # v10
        return {'written': True, 'refreshed': refreshed, 'path': sidecar_path}

    # ------------------------------------------------------------------
    def _auto_load_schema(self, payload: dict, filepath: str) -> bool:
        """v10: sets `payload` (the schema dict just written to `filepath`)
        as the app's active schema — the same app-state fields
        ui/evaluation_left_panel.py's "📂 Load Schema (.json)" sets, minus
        the file dialog and minus apply_settings_snapshot() (not needed
        here: `payload['settings_snapshot']` was built from
        app.current_holes at the exact moment of export, i.e. it already
        matches the current configuration exactly — there is nothing to
        replace). Best-effort: any failure here is logged and swallowed,
        never allowed to affect the export that already succeeded.

        Returns True if an already-loaded .log's results were also
        recomputed against this schema (via
        evaluation_left_panel._auto_refresh_if_result_exists()), False
        otherwise (including if that refresh mechanism isn't available
        yet, or there was nothing to refresh)."""
        app = self.app
        try:
            app.loaded_schema                 = payload
            app.loaded_expected_points        = payload.get('points') or []
            app.loaded_expected_points_source = os.path.basename(filepath)
            app.loaded_expected_points_view   = payload.get('view_name')

            refreshed = False
            left_panel = getattr(app, 'evaluation_left_panel', None)
            if left_panel is not None:
                if hasattr(left_panel, '_auto_refresh_if_result_exists'):
                    refreshed = left_panel._auto_refresh_if_result_exists()
                left_panel.refresh()
            if hasattr(app, 'evaluation_sidebar_panel'):
                app.evaluation_sidebar_panel.refresh()
            if getattr(app, 'current_tab', None) == "Evaluation" and hasattr(app, 'evaluation_tab'):
                app.evaluation_tab.draw_evaluation()
            return refreshed
        except Exception as e:
            print(f"[gcode_export_panel] auto-load schema into app state failed (non-blocking): {e!r}")
            return False