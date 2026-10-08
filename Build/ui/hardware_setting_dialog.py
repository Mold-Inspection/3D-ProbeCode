# ==============================================================================
# ui/hardware_setting_dialog.py — "Hardware Setting" floating dialog (Probe
# Stylus + Machine Working Area), built on ui/settings_dialog_base.py
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FEATURE: หมวด "Auto Log (OpenBuilds)" — เปิด/ปิดการบันทึก log อัตโนมัติ,
#   โฟลเดอร์ที่เก็บ log (Browse / พิมพ์เอง + Apply / Open folder) และรูปแบบชื่อไฟล์
#   (ชื่อ job + เวลา / เวลา / ชื่อ job) — ผูกกับ ui/openbuilds_logger.py มีผลทันที
# CHANGE LOG (v01 -> v02):
#   FEATURE (PLAN_machine-z-height-and-padding-calculation.md, Step 3):
#   two new fields added, one per category, both wired into their
#   existing all-or-nothing Apply/Reset validation pattern — no new
#   pattern introduced:
#     - Probe Stylus: "Stylus Holder Height (mm)" — new row bound to
#       core/probe_profile.py v02's `stylus_holder_height` field, placed
#       ABOVE the existing "Stylus Length" row (physically the holder
#       sits above the rod, closer to the Z-axis). Wired into
#       _apply_probe_profile() / _reset_probe_profile() /
#       _probe_summary_text().
#     - Machine Working Area: "Machine Z Height (mm)" — new 4th row,
#       placed AFTER the existing X/Y/Z Travel rows, bound to
#       core/machine_profile.py v02's `z_height` field. Wired into
#       _apply_machine_profile() / _reset_machine_profile() /
#       _machine_summary_text().
#   Both new fields use the exact same validation rule as their siblings
#   (must be > 0, all-or-nothing — if any field in the category is
#   invalid, NONE of that category's fields are applied).
#   Reworded the "Reference only for now..." helper label under Machine
#   Working Area: it is no longer fully accurate now that z_height feeds
#   a real calculation (core/gcode_generator.py v06's
#   suggest_padding_height(), wired up in Step 4/5 of the same plan) —
#   now explicitly says only X/Y/Z Travel remain reference-only.
# ==============================================================================
# หน้าที่: ย้าย Probe Stylus Profile panel (เดิมอยู่ใน sidebar ซ้าย ผ่าน
# ui/main_window.py::_setup_probe_profile_panel()) มาไว้เป็นหมวดหนึ่งใน
# dialog นี้ พร้อมเพิ่มหมวดใหม่ "Machine Working Area" ที่ผูกกับ
# core/machine_profile.py::MachineProfile (เดิมมีไฟล์อยู่แล้วแต่ไม่เคยมี UI
# consumer จริง — main_window.py ไม่เคยสร้าง instance หรือแสดงผลค่านี้เลย
# ก่อนหน้านี้ — ดู PLAN_toolbar-and-settings-dialogs_v01.md)
#
# ui/main_window.py v14 สร้าง instance นี้ตัวเดียวตอน __init__
# (self.hardware_setting_dialog) แล้วเรียก .show() จาก toolbar callback
# ทุกครั้งที่กดปุ่ม "Hardware Setting" — fields ถูกสร้างครั้งเดียวแบบ lazy
# โดย SettingsDialogBase (ดูไฟล์นั้น) ไม่ rebuild ทุกครั้งที่เปิด
#
# ตรรกะ Apply/Reset ของทั้งสองหมวด — Probe Stylus เหมือนของเดิมทุกประการ
# (all-or-nothing validation, ถ้าฟิลด์ใดพังทั้งคู่จะไม่ถูก apply) แค่ย้าย
# container; Machine Working Area เป็นของใหม่ทั้งหมด (มี validation แบบ
# เดียวกัน: X/Y/Z travel + Z Height ต้อง > 0 ทุกค่าถึงจะ apply — v02)
# ==============================================================================
import datetime
import os

import customtkinter as ctk

from ui.settings_dialog_base import SettingsDialogBase
from ui import theme
from core.machine_profile import MachineProfile
from core import user_settings
from core.work_zero import WORK_ZERO_CHOICES, label_of, mode_of_label, zero_hint_text
from core.openbuilds_link import LOG_NAME_CHOICES, log_file_name


class HardwareSettingDialog:
    def __init__(self, app):
        self.app = app
        self.dialog = SettingsDialogBase(app.root, title="Hardware Setting")
        self.dialog.add_category("probe",   "Probe Stylus",         self._build_probe_fields)
        self.dialog.add_category("machine", "Machine Working Area", self._build_machine_fields)
        self.dialog.add_category("work_zero", "Work Zero",            self._build_work_zero_fields)
        self.dialog.add_category("auto_log", "Auto Log (OpenBuilds)", self._build_auto_log_fields)

        self._probe_holder_entry = None   # v02 — Stylus Holder Height
        self._probe_length_entry = None
        self._probe_tip_entry    = None
        self._probe_clear_entry  = None   # ระยะว่างหัวโพรบ-ผนังขั้นต่ำ
        self._probe_eff_entry    = None   # ขนาดหัวโพรบที่ calibrate แล้ว (ชดเชยรัศมี)
        self._lbl_probe_summary  = None

        self._machine_x_entry     = None
        self._machine_y_entry     = None
        self._machine_z_entry     = None
        self._machine_zh_entry    = None   # v02 — Machine Z Height
        self._lbl_machine_summary = None

    # ------------------------------------------------------------------
    def show(self):
        self.dialog.show()

    # ==================================================================
    # v03: Auto Log category — ไฟล์ log ของทุก job ใน OpenBuilds Control
    # (ui/openbuilds_logger.py) มีผลทันที + จำข้ามการเปิดโปรแกรม
    # ==================================================================
    def _build_auto_log_fields(self, parent):
        logger = self.app.openbuilds_logger

        self._auto_log_var = ctk.BooleanVar(value=logger.auto_log)
        ctk.CTkCheckBox(parent, text="Auto-save a log for every OpenBuilds job",
                        variable=self._auto_log_var, font=ctk.CTkFont(size=13),
                        command=lambda: logger.set_auto_log(bool(self._auto_log_var.get()))
                        ).pack(anchor="w", pady=(0, 14))

        ctk.CTkLabel(parent, text="Save logs to:", font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        self._log_dir_entry = ctk.CTkEntry(parent, height=30, font=ctk.CTkFont(size=12))
        self._log_dir_entry.insert(0, logger.log_dir)
        self._log_dir_entry.pack(fill="x", pady=(4, 4))
        self._log_dir_entry.bind("<Return>", lambda _e: self._apply_log_dir())
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 14))
        for text, cmd in (("📁 Browse…", self._browse_log_dir), ("✔ Apply", self._apply_log_dir),
                          ("📂 Open folder", self._open_log_dir)):
            ctk.CTkButton(row, text=text, width=100, height=28,
                          fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
                          font=ctk.CTkFont(size=11), command=cmd).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(parent, text="File name:", font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        self._log_name_menu = ctk.CTkOptionMenu(
            parent, values=[text for _key, text in LOG_NAME_CHOICES], width=200, height=30,
            font=ctk.CTkFont(size=13), command=self._on_log_name_change)
        self._log_name_menu.set(dict(LOG_NAME_CHOICES).get(logger.log_name, LOG_NAME_CHOICES[0][1]))
        self._log_name_menu.pack(anchor="w", pady=(4, 4))
        self._lbl_log_example = ctk.CTkLabel(parent, text="", anchor="w", justify="left",
                                             font=ctk.CTkFont(size=11), text_color=theme.TEXT_MUTED)
        self._lbl_log_example.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360, font=ctk.CTkFont(size=10),
            text_color=theme.TEXT_MUTED,
            text=("Job name = the last G-code file exported from this program (OpenBuilds "
                  "does not report the name of the file it runs), or the STEP file name if "
                  "none was exported yet. A name that already exists gets _2, _3 … — old "
                  "logs are never overwritten.")
        ).pack(fill="x", pady=(0, 12))

        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(fill="x", pady=(0, 10))
        self._lbl_log_status = ctk.CTkLabel(parent, text=logger.status, anchor="w", justify="left",
                                            wraplength=360, font=ctk.CTkFont(size=11),
                                            text_color=theme.TEXT_MUTED)
        self._lbl_log_status.pack(fill="x")

        logger.on_status.append(self._on_log_status)
        logger.on_settings.append(self._sync_auto_log_fields)
        self._update_log_example()

    def _sync_auto_log_fields(self):
        """ค่าเปลี่ยนจากที่อื่น (เช่น checkbox ในแท็บ Evaluation) — อัปเดตหน้านี้ให้ตรง"""
        logger = self.app.openbuilds_logger
        try:
            self._auto_log_var.set(logger.auto_log)
            self._log_dir_entry.delete(0, "end")
            self._log_dir_entry.insert(0, logger.log_dir)
            self._update_log_example()
        except Exception:
            pass   # หน้านี้ยังไม่ถูกสร้าง / ถูกปิดไปแล้ว

    def _on_log_status(self, text: str):
        try:
            self._lbl_log_status.configure(text=text)
        except Exception:
            pass

    def _update_log_example(self):
        logger = self.app.openbuilds_logger
        example = log_file_name(logger.job_name(), datetime.datetime.now(), logger.log_name)
        self._lbl_log_example.configure(text=f"e.g.  {example}")

    def _on_log_name_change(self, label: str):
        key = next((k for k, text in LOG_NAME_CHOICES if text == label), "both")
        self.app.openbuilds_logger.set_log_name(key)

    def _browse_log_dir(self):
        folder = self.dialog.run_native(ctk.filedialog.askdirectory,
                                        title="Folder for OpenBuilds job logs",
                                        initialdir=self.app.openbuilds_logger.log_dir)
        if folder:
            self._log_dir_entry.delete(0, "end")
            self._log_dir_entry.insert(0, os.path.normpath(folder))
            self._apply_log_dir()

    def _apply_log_dir(self):
        folder = os.path.normpath(self._log_dir_entry.get().strip().strip('"'))
        if not folder or folder == ".":
            self.dialog.showerror("Invalid Folder", "กรุณาระบุโฟลเดอร์")
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            self.dialog.showerror("Invalid Folder", f"สร้าง/ใช้โฟลเดอร์นี้ไม่ได้:\n{e}")
            return
        self.app.openbuilds_logger.set_log_dir(folder)

    def _open_log_dir(self):
        folder = self.app.openbuilds_logger.log_dir
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except OSError as e:
            self.dialog.showerror("Open Failed", f"เปิดโฟลเดอร์ไม่ได้:\n{e}")

    # ==================================================================
    # Work Zero category — จุด X0 Y0 Z0 ของ G-code (core/work_zero.py)
    # มีผลทันทีที่เลือก (ไม่มีปุ่ม Apply) + จำข้ามการเปิดโปรแกรม
    # ==================================================================
    def _build_work_zero_fields(self, parent):
        ctk.CTkLabel(parent, text="Work zero (X0 Y0 Z0):", font=ctk.CTkFont(size=13),
                     text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        menu = ctk.CTkOptionMenu(
            parent, values=[text for _key, text in WORK_ZERO_CHOICES], width=230, height=30,
            font=ctk.CTkFont(size=13), command=self._on_work_zero_change)
        menu.set(label_of(getattr(self.app, 'work_zero', None)))
        menu.pack(anchor="w", pady=(4, 6))
        self._lbl_zero_hint = ctk.CTkLabel(
            parent, text=zero_hint_text(self.app), anchor="w", justify="left", wraplength=360,
            font=ctk.CTkFont(size=11), text_color=theme.TEXT_MUTED)
        self._lbl_zero_hint.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            parent, anchor="w", justify="left", wraplength=360, font=ctk.CTkFont(size=10),
            text_color=theme.TEXT_MUTED,
            text=("Left / right / upper / lower are as seen on screen in the current view "
                  "and rotation. Z0 is the top surface for every choice except the centroid. "
                  "After changing it, press \u21bb Suggest for Safe Z in G-code Export.")
        ).pack(fill="x", pady=(8, 0))

    def _on_work_zero_change(self, label: str):
        self.app.work_zero = mode_of_label(label)
        user_settings.save_section("work_zero", self.app.work_zero)
        self.app.refresh_work_zero_marker()
        try:
            self._lbl_zero_hint.configure(text=zero_hint_text(self.app))
        except Exception:
            pass

    # ==================================================================
    # Probe Stylus category (moved from ui/main_window.py::
    # _setup_probe_profile_panel() — same fields/behavior, new container)
    # ==================================================================
    def _build_probe_fields(self, parent):
        app = self.app

        # v02: Stylus Holder Height — placed above Stylus Length since the
        # holder physically sits between the Z-axis carriage and the rod.
        holder_row = ctk.CTkFrame(parent, fg_color="transparent")
        holder_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(holder_row, text="Stylus Holder Height (mm):", font=ctk.CTkFont(size=13),
                    text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        holder_entry_row = ctk.CTkFrame(holder_row, fg_color="transparent")
        holder_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_holder_entry = ctk.CTkEntry(holder_entry_row, width=110, height=30,
                                                 placeholder_text="20.0", font=ctk.CTkFont(size=13))
        self._probe_holder_entry.insert(0, str(app.probe_profile.stylus_holder_height))
        self._probe_holder_entry.pack(side="left")
        ctk.CTkLabel(holder_entry_row, text="mm", font=ctk.CTkFont(size=11),
                    text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))

        len_row = ctk.CTkFrame(parent, fg_color="transparent")
        len_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(len_row, text="Stylus Length (mm):", font=ctk.CTkFont(size=13),
                    text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        len_entry_row = ctk.CTkFrame(len_row, fg_color="transparent")
        len_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_length_entry = ctk.CTkEntry(len_entry_row, width=110, height=30,
                                                 placeholder_text="50.0", font=ctk.CTkFont(size=13))
        self._probe_length_entry.insert(0, str(app.probe_profile.stylus_length))
        self._probe_length_entry.pack(side="left")
        ctk.CTkLabel(len_entry_row, text="mm", font=ctk.CTkFont(size=11),
                    text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))

        tip_row = ctk.CTkFrame(parent, fg_color="transparent")
        tip_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(tip_row, text="Tip Diameter ⌀ (mm):", font=ctk.CTkFont(size=13),
                    text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        tip_entry_row = ctk.CTkFrame(tip_row, fg_color="transparent")
        tip_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_tip_entry = ctk.CTkEntry(tip_entry_row, width=110, height=30,
                                             placeholder_text="2.0", font=ctk.CTkFont(size=13))
        self._probe_tip_entry.insert(0, str(app.probe_profile.tip_diameter))
        self._probe_tip_entry.pack(side="left")
        ctk.CTkLabel(tip_entry_row, text="mm", font=ctk.CTkFont(size=11),
                    text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))

        clear_row = ctk.CTkFrame(parent, fg_color="transparent")
        clear_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(clear_row, text="Min. Wall Clearance (mm):", font=ctk.CTkFont(size=13),
                    text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        clear_entry_row = ctk.CTkFrame(clear_row, fg_color="transparent")
        clear_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_clear_entry = ctk.CTkEntry(clear_entry_row, width=110, height=30,
                                               placeholder_text="0.5", font=ctk.CTkFont(size=13))
        self._probe_clear_entry.insert(0, str(app.probe_profile.wall_clearance))
        self._probe_clear_entry.pack(side="left")
        ctk.CTkLabel(clear_entry_row, text="mm  free space between tip and wall",
                     font=ctk.CTkFont(size=11), text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))

        eff_row = ctk.CTkFrame(parent, fg_color="transparent")
        eff_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(eff_row, text="Effective Tip ⌀ — calibrated (mm):", font=ctk.CTkFont(size=13),
                    text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        eff_entry_row = ctk.CTkFrame(eff_row, fg_color="transparent")
        eff_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_eff_entry = ctk.CTkEntry(eff_entry_row, width=110, height=30,
                                             placeholder_text="0", font=ctk.CTkFont(size=13))
        self._probe_eff_entry.insert(0, str(app.probe_profile.effective_tip_diameter))
        self._probe_eff_entry.pack(side="left")
        ctk.CTkLabel(eff_entry_row, text="mm  0 = use Tip ⌀ for compensation",
                     font=ctk.CTkFont(size=11), text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(eff_row, text="From a ring gauge: Ring ⌀ − \"ball-centre ⌀\" shown in Evaluation",
                     font=ctk.CTkFont(size=11), text_color=theme.TEXT_MUTED).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(fill="x", pady=(6, 14))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="✔ Apply Profile", fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                     font=ctk.CTkFont(size=12, weight="bold"), height=32,
                     command=self._apply_probe_profile).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="↺ Reset to Default", fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
                     font=ctk.CTkFont(size=12), height=32,
                     command=self._reset_probe_profile).pack(side="left")

        self._lbl_probe_summary = ctk.CTkLabel(
            parent, text=self._probe_summary_text(), font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED, justify="left")
        self._lbl_probe_summary.pack(anchor="w", pady=(14, 0))

    def _probe_summary_text(self) -> str:
        p = self.app.probe_profile
        return (f"Holder : {p.stylus_holder_height:.1f} mm\n"   # v02
                f"Length : {p.stylus_length:.1f} mm\n"
                f"Tip ⌀  : {p.tip_diameter:.1f} mm  (r = {p.tip_radius:.2f} mm)\n"
                f"Clearance : {p.wall_clearance:.2f} mm\n"
                f"Compensation r : {p.effective_tip_radius:.3f} mm"
                f"{'  (calibrated)' if p.effective_tip_diameter > 0 else '  (from Tip ⌀)'}")

    def _apply_probe_profile(self):
        app = self.app
        try:
            new_holder = float(self._probe_holder_entry.get().strip())   # v02
            if new_holder <= 0: raise ValueError("ความสูงตัวจับต้องมากกว่า 0")
            new_length = float(self._probe_length_entry.get().strip())
            if new_length <= 0: raise ValueError("ความยาวต้องมากกว่า 0")
            new_tip_d = float(self._probe_tip_entry.get().strip())
            if new_tip_d <= 0: raise ValueError("เส้นผ่าศูนย์กลางต้องมากกว่า 0")
            new_clear = float(self._probe_clear_entry.get().strip())
            if new_clear < 0: raise ValueError("ระยะว่างต้องไม่ติดลบ")
            new_eff = float(self._probe_eff_entry.get().strip() or 0)
            if new_eff < 0: raise ValueError("ขนาดหัวโพรบที่ calibrate ต้องไม่ติดลบ (0 = ไม่ใช้)")
        except ValueError as e:
            self.dialog.showerror("Invalid Input", f"Profile ไม่ถูกต้อง:\n{e}")
            return

        app.probe_profile.stylus_holder_height = new_holder   # v02
        app.probe_profile.stylus_length = new_length
        app.probe_profile.tip_diameter  = new_tip_d
        app.probe_profile.wall_clearance = new_clear
        app.probe_profile.effective_tip_diameter = new_eff
        if self._lbl_probe_summary is not None:
            self._lbl_probe_summary.configure(text=self._probe_summary_text())
        if app.holes_detected and app.current_holes:
            app.update_treeview(app.current_holes)
        self._save_probe()

    def _save_probe(self):
        p = self.app.probe_profile
        user_settings.save_section("probe", {
            "stylus_holder_height": p.stylus_holder_height,
            "stylus_length": p.stylus_length, "tip_diameter": p.tip_diameter,
            "wall_clearance": p.wall_clearance,
            "effective_tip_diameter": p.effective_tip_diameter})

    def _save_machine(self):
        m = self.app.machine_profile
        user_settings.save_section("machine", {
            "x_travel": m.x_travel, "y_travel": m.y_travel,
            "z_travel": m.z_travel, "z_height": m.z_height})

    def _reset_probe_profile(self):
        app = self.app
        app.probe_profile.stylus_holder_height = app.probe_profile.DEFAULT_HOLDER_HEIGHT   # v02
        app.probe_profile.stylus_length = app.probe_profile.DEFAULT_LENGTH
        app.probe_profile.tip_diameter  = app.probe_profile.DEFAULT_TIP_D
        app.probe_profile.wall_clearance = app.probe_profile.DEFAULT_CLEARANCE
        app.probe_profile.effective_tip_diameter = app.probe_profile.DEFAULT_EFFECTIVE_TIP_D
        if self._probe_eff_entry is not None:
            self._probe_eff_entry.delete(0, "end")
            self._probe_eff_entry.insert(0, str(app.probe_profile.effective_tip_diameter))
        if self._probe_clear_entry is not None:
            self._probe_clear_entry.delete(0, "end")
            self._probe_clear_entry.insert(0, str(app.probe_profile.wall_clearance))
        if self._probe_holder_entry is not None:   # v02
            self._probe_holder_entry.delete(0, "end")
            self._probe_holder_entry.insert(0, str(app.probe_profile.stylus_holder_height))
        if self._probe_length_entry is not None:
            self._probe_length_entry.delete(0, "end")
            self._probe_length_entry.insert(0, str(app.probe_profile.stylus_length))
        if self._probe_tip_entry is not None:
            self._probe_tip_entry.delete(0, "end")
            self._probe_tip_entry.insert(0, str(app.probe_profile.tip_diameter))
        if self._lbl_probe_summary is not None:
            self._lbl_probe_summary.configure(text=self._probe_summary_text())
        if app.holes_detected and app.current_holes:
            app.update_treeview(app.current_holes)
        self._save_probe()

    # ==================================================================
    # Machine Working Area category (wires up core/machine_profile.py)
    # ==================================================================
    def _build_machine_fields(self, parent):
        app = self.app
        if not hasattr(app, 'machine_profile') or app.machine_profile is None:
            app.machine_profile = MachineProfile()   # safety net — main_window.py v14 also creates this in __init__

        for axis, attr, entry_attr in (("X", "x_travel", "_machine_x_entry"),
                                        ("Y", "y_travel", "_machine_y_entry"),
                                        ("Z", "z_travel", "_machine_z_entry")):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(row, text=f"{axis} Travel (mm):", font=ctk.CTkFont(size=13),
                        text_color=theme.TEXT_SECONDARY).pack(anchor="w")
            entry_row = ctk.CTkFrame(row, fg_color="transparent")
            entry_row.pack(fill="x", pady=(4, 0))
            entry = ctk.CTkEntry(entry_row, width=110, height=30, font=ctk.CTkFont(size=13))
            entry.insert(0, str(getattr(app.machine_profile, attr)))
            entry.pack(side="left")
            ctk.CTkLabel(entry_row, text="mm", font=ctk.CTkFont(size=11),
                        text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))
            setattr(self, entry_attr, entry)

        # v02: Machine Z Height — 4th row, after X/Y/Z Travel.
        zh_row = ctk.CTkFrame(parent, fg_color="transparent")
        zh_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(zh_row, text="Machine Z Height (mm):", font=ctk.CTkFont(size=13),
                    text_color=theme.TEXT_SECONDARY).pack(anchor="w")
        zh_entry_row = ctk.CTkFrame(zh_row, fg_color="transparent")
        zh_entry_row.pack(fill="x", pady=(4, 0))
        self._machine_zh_entry = ctk.CTkEntry(zh_entry_row, width=110, height=30, font=ctk.CTkFont(size=13))
        self._machine_zh_entry.insert(0, str(app.machine_profile.z_height))
        self._machine_zh_entry.pack(side="left")
        ctk.CTkLabel(zh_entry_row, text="mm", font=ctk.CTkFont(size=11),
                    text_color=theme.TEXT_MUTED).pack(side="left", padx=(6, 0))

        ctk.CTkFrame(parent, height=1, fg_color=theme.BORDER).pack(fill="x", pady=(6, 14))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="✔ Apply", fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                     font=ctk.CTkFont(size=12, weight="bold"), height=32,
                     command=self._apply_machine_profile).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="↺ Reset to Default", fg_color=theme.BTN_SECONDARY, hover_color=theme.BTN_SECONDARY_HOVER,
                     font=ctk.CTkFont(size=12), height=32,
                     command=self._reset_machine_profile).pack(side="left")

        self._lbl_machine_summary = ctk.CTkLabel(
            parent, text=self._machine_summary_text(), font=ctk.CTkFont(size=11),
            text_color=theme.TEXT_MUTED, justify="left")
        self._lbl_machine_summary.pack(anchor="w", pady=(14, 0))

        # v02: reworded — Machine Z Height now feeds
        # core/gcode_generator.py::suggest_padding_height(), so it is no
        # longer accurate to call the whole category "reference only".
        ctk.CTkLabel(
            parent, text="X/Y/Z Travel are checked when you export G-code:\n"
                         "you are warned if the program moves farther than the\n"
                         "machine can travel. Machine Z Height and Z Travel also\n"
                         "drive G-code Export's Padding Height suggestion.",
            font=ctk.CTkFont(size=10), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", pady=(10, 0))

    def _machine_summary_text(self) -> str:
        m = self.app.machine_profile
        return (f"X : {m.x_travel:.1f} mm   Y : {m.y_travel:.1f} mm   Z : {m.z_travel:.1f} mm\n"
                f"Z Height : {m.z_height:.1f} mm")   # v02

    def _apply_machine_profile(self):
        app = self.app
        try:
            new_x = float(self._machine_x_entry.get().strip())
            if new_x <= 0: raise ValueError("X travel ต้องมากกว่า 0")
            new_y = float(self._machine_y_entry.get().strip())
            if new_y <= 0: raise ValueError("Y travel ต้องมากกว่า 0")
            new_z = float(self._machine_z_entry.get().strip())
            if new_z <= 0: raise ValueError("Z travel ต้องมากกว่า 0")
            new_zh = float(self._machine_zh_entry.get().strip())   # v02
            if new_zh <= 0: raise ValueError("Machine Z Height ต้องมากกว่า 0")
        except ValueError as e:
            self.dialog.showerror("Invalid Input", f"Machine profile ไม่ถูกต้อง:\n{e}")
            return

        app.machine_profile.x_travel = new_x
        app.machine_profile.y_travel = new_y
        app.machine_profile.z_travel = new_z
        app.machine_profile.z_height = new_zh   # v02
        if self._lbl_machine_summary is not None:
            self._lbl_machine_summary.configure(text=self._machine_summary_text())
        self._save_machine()

    def _reset_machine_profile(self):
        app = self.app
        app.machine_profile.x_travel = app.machine_profile.DEFAULT_X
        app.machine_profile.y_travel = app.machine_profile.DEFAULT_Y
        app.machine_profile.z_travel = app.machine_profile.DEFAULT_Z
        app.machine_profile.z_height = app.machine_profile.DEFAULT_Z_HEIGHT   # v02
        if self._machine_x_entry is not None:
            self._machine_x_entry.delete(0, "end"); self._machine_x_entry.insert(0, str(app.machine_profile.x_travel))
        if self._machine_y_entry is not None:
            self._machine_y_entry.delete(0, "end"); self._machine_y_entry.insert(0, str(app.machine_profile.y_travel))
        if self._machine_z_entry is not None:
            self._machine_z_entry.delete(0, "end"); self._machine_z_entry.insert(0, str(app.machine_profile.z_travel))
        if self._machine_zh_entry is not None:   # v02
            self._machine_zh_entry.delete(0, "end"); self._machine_zh_entry.insert(0, str(app.machine_profile.z_height))
        if self._lbl_machine_summary is not None:
            self._lbl_machine_summary.configure(text=self._machine_summary_text())
        self._save_machine()