# ==============================================================================
# ui/hardware_setting_dialog.py — "Hardware Setting" floating dialog (Probe
# Stylus + Machine Working Area), built on ui/settings_dialog_base.py
# ==============================================================================
# VERSION: 01
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
# เดียวกัน: X/Y/Z travel ต้อง > 0 ทุกค่าถึงจะ apply)
# ==============================================================================
import customtkinter as ctk
import tkinter.messagebox as _mb

from ui.settings_dialog_base import SettingsDialogBase
from core.machine_profile import MachineProfile


class HardwareSettingDialog:
    def __init__(self, app):
        self.app = app
        self.dialog = SettingsDialogBase(app.root, title="Hardware Setting")
        self.dialog.add_category("probe",   "Probe Stylus",         self._build_probe_fields)
        self.dialog.add_category("machine", "Machine Working Area", self._build_machine_fields)

        self._probe_length_entry = None
        self._probe_tip_entry    = None
        self._lbl_probe_summary  = None

        self._machine_x_entry     = None
        self._machine_y_entry     = None
        self._machine_z_entry     = None
        self._lbl_machine_summary = None

    # ------------------------------------------------------------------
    def show(self):
        self.dialog.show()

    # ==================================================================
    # Probe Stylus category (moved from ui/main_window.py::
    # _setup_probe_profile_panel() — same fields/behavior, new container)
    # ==================================================================
    def _build_probe_fields(self, parent):
        app = self.app

        len_row = ctk.CTkFrame(parent, fg_color="transparent")
        len_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(len_row, text="Stylus Length (mm):", font=ctk.CTkFont(size=13),
                    text_color="#b0bec5").pack(anchor="w")
        len_entry_row = ctk.CTkFrame(len_row, fg_color="transparent")
        len_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_length_entry = ctk.CTkEntry(len_entry_row, width=110, height=30,
                                                 placeholder_text="50.0", font=ctk.CTkFont(size=13))
        self._probe_length_entry.insert(0, str(app.probe_profile.stylus_length))
        self._probe_length_entry.pack(side="left")
        ctk.CTkLabel(len_entry_row, text="mm", font=ctk.CTkFont(size=11),
                    text_color="#78909c").pack(side="left", padx=(6, 0))

        tip_row = ctk.CTkFrame(parent, fg_color="transparent")
        tip_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(tip_row, text="Tip Diameter ⌀ (mm):", font=ctk.CTkFont(size=13),
                    text_color="#b0bec5").pack(anchor="w")
        tip_entry_row = ctk.CTkFrame(tip_row, fg_color="transparent")
        tip_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_tip_entry = ctk.CTkEntry(tip_entry_row, width=110, height=30,
                                             placeholder_text="2.0", font=ctk.CTkFont(size=13))
        self._probe_tip_entry.insert(0, str(app.probe_profile.tip_diameter))
        self._probe_tip_entry.pack(side="left")
        ctk.CTkLabel(tip_entry_row, text="mm", font=ctk.CTkFont(size=11),
                    text_color="#78909c").pack(side="left", padx=(6, 0))

        ctk.CTkFrame(parent, height=1, fg_color="#2a2a4e").pack(fill="x", pady=(6, 14))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="✔ Apply Profile", fg_color="#1565c0", hover_color="#1976d2",
                     font=ctk.CTkFont(size=12, weight="bold"), height=32,
                     command=self._apply_probe_profile).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="↺ Reset to Default", fg_color="#37474f", hover_color="#546e7a",
                     font=ctk.CTkFont(size=12), height=32,
                     command=self._reset_probe_profile).pack(side="left")

        self._lbl_probe_summary = ctk.CTkLabel(
            parent, text=self._probe_summary_text(), font=ctk.CTkFont(size=11),
            text_color="#546e7a", justify="left")
        self._lbl_probe_summary.pack(anchor="w", pady=(14, 0))

    def _probe_summary_text(self) -> str:
        p = self.app.probe_profile
        return (f"Length : {p.stylus_length:.1f} mm\n"
                f"Tip ⌀  : {p.tip_diameter:.1f} mm  (r = {p.tip_radius:.2f} mm)")

    def _apply_probe_profile(self):
        app = self.app
        try:
            new_length = float(self._probe_length_entry.get().strip())
            if new_length <= 0: raise ValueError("ความยาวต้องมากกว่า 0")
            new_tip_d = float(self._probe_tip_entry.get().strip())
            if new_tip_d <= 0: raise ValueError("เส้นผ่าศูนย์กลางต้องมากกว่า 0")
        except ValueError as e:
            _mb.showerror("Invalid Input", f"Profile ไม่ถูกต้อง:\n{e}")
            return

        app.probe_profile.stylus_length = new_length
        app.probe_profile.tip_diameter  = new_tip_d
        if self._lbl_probe_summary is not None:
            self._lbl_probe_summary.configure(text=self._probe_summary_text())
        if app.holes_detected and app.current_holes:
            app.update_treeview(app.current_holes)

    def _reset_probe_profile(self):
        app = self.app
        app.probe_profile.stylus_length = app.probe_profile.DEFAULT_LENGTH
        app.probe_profile.tip_diameter  = app.probe_profile.DEFAULT_TIP_D
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

    # ==================================================================
    # Machine Working Area category (NEW — wires up core/machine_profile.py,
    # which existed but had no UI consumer before this dialog)
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
                        text_color="#b0bec5").pack(anchor="w")
            entry_row = ctk.CTkFrame(row, fg_color="transparent")
            entry_row.pack(fill="x", pady=(4, 0))
            entry = ctk.CTkEntry(entry_row, width=110, height=30, font=ctk.CTkFont(size=13))
            entry.insert(0, str(getattr(app.machine_profile, attr)))
            entry.pack(side="left")
            ctk.CTkLabel(entry_row, text="mm", font=ctk.CTkFont(size=11),
                        text_color="#78909c").pack(side="left", padx=(6, 0))
            setattr(self, entry_attr, entry)

        ctk.CTkFrame(parent, height=1, fg_color="#2a2a4e").pack(fill="x", pady=(6, 14))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="✔ Apply", fg_color="#1565c0", hover_color="#1976d2",
                     font=ctk.CTkFont(size=12, weight="bold"), height=32,
                     command=self._apply_machine_profile).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="↺ Reset to Default", fg_color="#37474f", hover_color="#546e7a",
                     font=ctk.CTkFont(size=12), height=32,
                     command=self._reset_machine_profile).pack(side="left")

        self._lbl_machine_summary = ctk.CTkLabel(
            parent, text=self._machine_summary_text(), font=ctk.CTkFont(size=11),
            text_color="#546e7a", justify="left")
        self._lbl_machine_summary.pack(anchor="w", pady=(14, 0))

        ctk.CTkLabel(
            parent, text="Reference only for now — not yet used to block or\n"
                         "warn about out-of-range probe moves.",
            font=ctk.CTkFont(size=10), text_color="#5a6570", justify="left"
        ).pack(anchor="w", pady=(10, 0))

    def _machine_summary_text(self) -> str:
        m = self.app.machine_profile
        return f"X : {m.x_travel:.1f} mm   Y : {m.y_travel:.1f} mm   Z : {m.z_travel:.1f} mm"

    def _apply_machine_profile(self):
        app = self.app
        try:
            new_x = float(self._machine_x_entry.get().strip())
            if new_x <= 0: raise ValueError("X travel ต้องมากกว่า 0")
            new_y = float(self._machine_y_entry.get().strip())
            if new_y <= 0: raise ValueError("Y travel ต้องมากกว่า 0")
            new_z = float(self._machine_z_entry.get().strip())
            if new_z <= 0: raise ValueError("Z travel ต้องมากกว่า 0")
        except ValueError as e:
            _mb.showerror("Invalid Input", f"Machine profile ไม่ถูกต้อง:\n{e}")
            return

        app.machine_profile.x_travel = new_x
        app.machine_profile.y_travel = new_y
        app.machine_profile.z_travel = new_z
        if self._lbl_machine_summary is not None:
            self._lbl_machine_summary.configure(text=self._machine_summary_text())

    def _reset_machine_profile(self):
        app = self.app
        app.machine_profile.x_travel = app.machine_profile.DEFAULT_X
        app.machine_profile.y_travel = app.machine_profile.DEFAULT_Y
        app.machine_profile.z_travel = app.machine_profile.DEFAULT_Z
        if self._machine_x_entry is not None:
            self._machine_x_entry.delete(0, "end"); self._machine_x_entry.insert(0, str(app.machine_profile.x_travel))
        if self._machine_y_entry is not None:
            self._machine_y_entry.delete(0, "end"); self._machine_y_entry.insert(0, str(app.machine_profile.y_travel))
        if self._machine_z_entry is not None:
            self._machine_z_entry.delete(0, "end"); self._machine_z_entry.insert(0, str(app.machine_profile.z_travel))
        if self._lbl_machine_summary is not None:
            self._lbl_machine_summary.configure(text=self._machine_summary_text())