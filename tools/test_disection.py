import customtkinter as ctk
import tkinter as tk
import math

class InteractiveInspectionCanvas(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="#1e1e1e", corner_radius=10)
        
        # --- ตั้งค่า UI ด้านบน (Canvas) ---
        self.canvas_width = 500
        self.canvas_height = 350
        
        # ใช้ tk.Canvas ธรรมดาเพื่อการวาดเส้น 2D ที่ง่ายขึ้น
        self.canvas = tk.Canvas(self, width=self.canvas_width, height=self.canvas_height, 
                                bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(pady=(20, 10), padx=20)
        
        # --- ตั้งค่าพารามิเตอร์ของรูปทรงแม่พิมพ์ (อิงอุดมคติเป็นทรงรี/โค้ง) ---
        self.cx = 250       # จุดศูนย์กลางแนวแกน X
        self.cy_top = 80    # ระดับความสูงผิวหน้าแม่พิมพ์ (Top Surface)
        self.r_x = 120      # รัศมีความกว้างปากหลุม
        self.r_y = 200      # ความลึกสูงสุดของหลุม
        
        self.y_top_rim = self.cy_top + (self.r_y * 0.15)  # บังคับขอบบน (ลงมา 15%)
        self.y_bot_rim = self.cy_top + (self.r_y * 0.85)  # บังคับขอบล่าง (ลงมา 85%)
        self.y_apex = self.cy_top + self.r_y              # บังคับก้นหลุม (100%)

        # วาดส่วนที่คงที่ (แม่พิมพ์และจุดบังคับ)
        self._draw_static_mold()
        
        # --- ตั้งค่า UI ด้านล่าง (Controls) ---
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=10)
        
        # เลเบลแสดงผล
        self.lbl_info = ctk.CTkLabel(control_frame, text="Middle Layers: 3  |  Total Points: 41", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_info.pack(pady=(0, 10))
        
        # Slider สำหรับปรับชั้น
        slider_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        slider_frame.pack(fill="x")
        
        ctk.CTkLabel(slider_frame, text="2 ชั้น").pack(side="left")
        self.layer_slider = ctk.CTkSlider(slider_frame, from_=2, to=9, number_of_steps=7, 
                                          command=self._on_slider_change)
        self.layer_slider.set(3) # ค่าเริ่มต้น
        self.layer_slider.pack(side="left", fill="x", expand=True, padx=15)
        ctk.CTkLabel(slider_frame, text="9 ชั้น").pack(side="right")
        
        # วาดชั้นกลางครั้งแรก
        self._on_slider_change(3)

    def _get_x_on_curve(self, y):
        """ คำนวณหาตำแหน่ง X บนเส้นโค้ง โดยอิงจากสมการวงรี (Ellipse Equation) """
        # (x - cx)^2 / rx^2 + (y - cy)^2 / ry^2 = 1
        # ถอดสมการหาค่า X (บวกและลบ)
        if y >= self.y_apex:
            return self.cx, self.cx
            
        y_norm = (y - self.cy_top) / self.r_y
        x_offset = self.r_x * math.sqrt(1 - y_norm**2)
        return self.cx - x_offset, self.cx + x_offset

    def _draw_static_mold(self):
        """ วาดกราฟิกส่วนที่ไม่มีการเปลี่ยนแปลง (รูปร่างแม่พิมพ์ และ จุด Mandatory) """
        # วาดพื้นผิวแม่พิมพ์
        self.canvas.create_line(50, self.cy_top, self.cx - self.r_x, self.cy_top, fill="orange", width=4)
        self.canvas.create_line(self.cx + self.r_x, self.cy_top, 450, self.cy_top, fill="orange", width=4)
        
        # วาดเส้นโค้งหลุม (Cavity) ใช้ arc
        # bounding box ของวงรีคือ: cx-rx, cy-ry, cx+rx, cy+ry
        self.canvas.create_arc(self.cx - self.r_x, self.cy_top - self.r_y, 
                               self.cx + self.r_x, self.cy_top + self.r_y, 
                               start=180, extent=180, style=tk.ARC, outline="orange", width=3)
        
        # วาดเส้นแกน Z ตรงกลาง
        self.canvas.create_line(self.cx, 40, self.cx, 320, fill="#555555", dash=(4, 4))
        
        # --- วาดจุด Mandatory (สีแดง) ---
        self._draw_layer(self.y_top_rim, color="#e74c3c", tag="static", label="Top Rim (Fixed)")
        self._draw_layer(self.y_bot_rim, color="#e74c3c", tag="static", label="Bot Rim (Fixed)")
        
        # จุด Apex (1 จุดตรงกลาง)
        r = 5
        self.canvas.create_oval(self.cx - r, self.y_apex - r, self.cx + r, self.y_apex + r, 
                                fill="#e74c3c", outline="white", tags="static")
        self.canvas.create_text(self.cx + 15, self.y_apex, text="Apex", fill="#e74c3c", anchor="w", tags="static")

    def _draw_layer(self, y, color, tag, label=None):
        """ ฟังก์ชันผู้ช่วยสำหรับวาดเส้นแนวนอนและจุดตัดซ้าย-ขวา """
        x1, x2 = self._get_x_on_curve(y)
        
        # เส้นระดับ
        self.canvas.create_line(x1, y, x2, y, fill=color, tags=tag)
        
        # จุดซ้ายขวา
        r = 4
        self.canvas.create_oval(x1 - r, y - r, x1 + r, y + r, fill=color, outline="white", tags=tag)
        self.canvas.create_oval(x2 - r, y - r, x2 + r, y + r, fill=color, outline="white", tags=tag)
        
        if label:
            self.canvas.create_text(x2 + 10, y, text=label, fill=color, anchor="w", tags=tag)

    def _on_slider_change(self, value):
        """ ฟังก์ชันทำงานเมื่อดึง Slider (คำนวณและวาดจุดใหม่ Real-time) """
        num_layers = int(float(value))
        
        # อัปเดตข้อความ Total Points (บน+ล่าง อย่างละ 8, กลางชั้นละ 8, Apex 1)
        total_points = 8 + 8 + 1 + (num_layers * 8)
        self.lbl_info.configure(text=f"Middle Layers: {num_layers}  |  Total Points: {total_points}")
        
        # ลบเฉพาะกราฟิกเก่าที่เป็นชั้นแบบปรับแต่งได้ (tags="dynamic")
        self.canvas.delete("dynamic")
        
        # คำนวณช่วงห่างระหว่างขอบบนและขอบล่าง
        span_y = self.y_bot_rim - self.y_top_rim
        step_y = span_y / (num_layers + 1)
        
        # วาดชั้นกลางใหม่ทั้งหมด
        for i in range(1, num_layers + 1):
            target_y = self.y_top_rim + (step_y * i)
            # วาดชั้นเป็นสีฟ้า เพื่อแยกความต่างจากจุด Mandatory (สีแดง)
            self._draw_layer(target_y, color="#3498db", tag="dynamic")


if __name__ == "__main__":
    # ทดสอบรันหน้าต่างจำลอง
    ctk.set_appearance_mode("Dark")
    app = ctk.CTk()
    app.geometry("550x500")
    app.title("2D Path Virtualization")
    
    frame = InteractiveInspectionCanvas(app)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    app.mainloop()