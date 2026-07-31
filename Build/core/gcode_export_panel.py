# ui/gcode_export_panel.py
# VERSION: 02
import customtkinter as ctk
import tkinter.messagebox as _mb

from core.gcode_generator import GCodeSettings, generate_gcode, suggest_safe_z


class GCodeExportPanel:
    def __init__(self, app):
        self.app = app
        self._expanded = False

    # ------------------------------------------------------------------
    def build(self, parent):
        header_frame = ctk.CTkFrame(parent, fg_color="#1a1a2e", corner_radius=6)
        header_frame.pack(pady=(10, 0), padx=12, fill="x")
        self._header_frame = header_frame   # v02: keep ref so dropdown can anchor after it

        self._toggle_btn = ctk.CTkButton(
            header_frame, text="🖨 G-code Export (GRBL)  ▸",
            fg_color="transparent", hover_color="#2a2a4e", anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#90caf9", command=self._toggle_panel,
        )
        self._toggle_btn.pack(fill="x", padx=4, pady=6)

        self._body = ctk.CTkFrame(parent, fg_color="#12122a", corner_radius=6)

        self._entries = {}
        fields = [
            ("safe_z",          "Safe Z (mm):",             ""),
            ("entry_clearance", "Entry Clearance (mm):",    "2.0"),
            ("probe_feedrate",  "Probe Feedrate (mm/min):", "100.0"),
            ("overtravel",      "Overtravel (mm):",         "0.8"),
            ("backoff",         "Back-off (mm):",           "1.2"),
        ]
        for key, label, default in fields:
            row = ctk.CTkFrame(self._body, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(8, 0))
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12),
                        text_color="#b0bec5").pack(anchor="w")
            entry_row = ctk.CTkFrame(row, fg_color="transparent")
            entry_row.pack(fill="x", pady=(4, 0))
            entry = ctk.CTkEntry(entry_row, width=110, height=28,
                                 placeholder_text=default or "e.g. 50.0",
                                 font=ctk.CTkFont(size=13))
            if default:
                entry.insert(0, default)
            entry.pack(side="left")
            self._entries[key] = entry

            if key == "safe_z":
                ctk.CTkButton(entry_row, text="↻ Suggest", width=80, height=28,
                             fg_color="#37474f", hover_color="#546e7a",
                             font=ctk.CTkFont(size=11),
                             command=self._suggest_safe_z).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(self._body, height=1, fg_color="#2a2a4e").pack(fill="x", padx=14, pady=(12, 6))

        self._btn_export = ctk.CTkButton(
            self._body, text="🖨 Export G-code", fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=12, weight="bold"), height=32, command=self._on_export)
        self._btn_export.pack(fill="x", padx=14, pady=(0, 12))

    # ------------------------------------------------------------------
    def _toggle_panel(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._body.pack(pady=(0, 10), padx=12, fill="x", after=self._header_frame)
            self._toggle_btn.configure(text="🖨 G-code Export (GRBL)  ▾")
        else:
            self._body.pack_forget()
            self._toggle_btn.configure(text="🖨 G-code Export (GRBL)  ▸")

    # ------------------------------------------------------------------
    def _suggest_safe_z(self):
        app = self.app
        if app.geo.mesh is None:
            _mb.showwarning("No Model", "กรุณาโหลดโมเดลก่อน")
            return
            
        # ดึงมุมมองปัจจุบันเพื่อส่งไปคำนวณ Safe Z ให้ล้อตามความหนาในด้านนั้นๆ
        view_name = "Top"
        if hasattr(app, 'current_view'):
            view_name = app.current_view
            
        # เรียกคำนวณค่า Z ที่ปลอดภัย โดยอิงจากการหมุนแกน
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

        # ดึงชื่อมุมมองปัจจุบันจาก UI เพื่อส่งไปจำลองการพลิกชิ้นงาน
        view_name = "Top"
        if hasattr(app, 'current_view'):
            view_name = app.current_view
        elif hasattr(app, 'view_name'):
            view_name = app.view_name
        elif hasattr(app, 'view_combobox'): 
            view_name = app.view_combobox.get()

        try:
            # เพิ่มการส่ง view_name เข้าไปในฟังก์ชัน
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

        _mb.showinfo("Export Complete", f"บันทึก G-code แล้ว:\n{filepath}")