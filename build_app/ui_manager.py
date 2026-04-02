import matplotlib.pyplot as plt
from matplotlib.widgets import Button
from matplotlib.colors import LinearSegmentedColormap
import tkinter as tk
from tkinter import filedialog
import numpy as np
import os

class UIManager:
    def __init__(self, geometry_engine):
        self.geo = geometry_engine
        self.marked_points = [] 
        self.current_view = 'Top'
        self.screen_rotation = 0 
        
        # --- NEW: ENABLE DARK MODE ---
        plt.style.use('dark_background')
        
        colors = ["white", "red"]
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)

        self.fig, self.ax = plt.subplots(figsize=(11, 9))
        
        # --- NEW: SET CUSTOM DARK GREY BACKGROUNDS ---
        self.fig.patch.set_facecolor('#181818') # Outer window background
        self.ax.set_facecolor('#242424')        # Inner plot background
        
        plt.subplots_adjust(bottom=0.2, right=0.85)
        self.cax = self.fig.add_axes([0.88, 0.25, 0.03, 0.5])
        
        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self._setup_buttons()
        self._setup_events()
        
        if self.geo.mesh is not None:
            self.show_view('Top')
        
    def _setup_buttons(self):
        bw, bh = 0.12, 0.05
        y1, y2 = 0.10, 0.03
        x1, x2, x3 = 0.10, 0.25, 0.40 
        
        ax_top = plt.axes([x1, y1, bw, bh])
        ax_under = plt.axes([x1, y2, bw, bh])
        ax_front = plt.axes([x2, y1, bw, bh])
        ax_back = plt.axes([x2, y2, bw, bh])
        ax_left = plt.axes([x3, y1, bw, bh])
        ax_right = plt.axes([x3, y2, bw, bh])
        
        # Dark Mode Upload Button (Dark Green)
        ax_upload = plt.axes([0.65, 0.10, 0.15, 0.05])
        self.btn_upload = Button(ax_upload, 'Upload STL', color='#2e7d32', hovercolor='#4caf50')
        self.btn_upload.on_clicked(self.open_file_dialog)

        # Dark Mode Rotate Button (Dark Blue)
        ax_rotate = plt.axes([0.65, 0.03, 0.15, 0.05])
        self.btn_rotate = Button(ax_rotate, '⟳ Rotate 90°', color='#0277bd', hovercolor='#039be5')
        self.btn_rotate.on_clicked(self.rotate_screen)

        # Dark Mode View Buttons (Dark Grey)
        btn_color = '#424242'
        btn_hover = '#616161'
        self.btn_top = Button(ax_top, 'Top', color=btn_color, hovercolor=btn_hover)
        self.btn_under = Button(ax_under, 'Bottom', color=btn_color, hovercolor=btn_hover)
        self.btn_front = Button(ax_front, 'Front', color=btn_color, hovercolor=btn_hover)
        self.btn_back = Button(ax_back, 'Back', color=btn_color, hovercolor=btn_hover)
        self.btn_left = Button(ax_left, 'Left', color=btn_color, hovercolor=btn_hover)
        self.btn_right = Button(ax_right, 'Right', color=btn_color, hovercolor=btn_hover)

        self.btn_top.on_clicked(lambda event: self.show_view('Top'))
        self.btn_under.on_clicked(lambda event: self.show_view('Bottom'))
        self.btn_front.on_clicked(lambda event: self.show_view('Front'))
        self.btn_back.on_clicked(lambda event: self.show_view('Back'))
        self.btn_left.on_clicked(lambda event: self.show_view('Left'))
        self.btn_right.on_clicked(lambda event: self.show_view('Right'))

    # --- NEW ROTATION LOGIC ---
    def rotate_screen(self, event):
        if self.geo.mesh is None: return
        # Add 90 degrees and wrap around at 360
        self.screen_rotation = (self.screen_rotation + 90) % 360
        # Clear custom marks because the coordinates just physically changed
        self.marked_points = [] 
        # Redraw the current view with the new rotation
        self.show_view(self.current_view)

    def open_file_dialog(self, event):
        root = tk.Tk()
        root.withdraw()
        filepath = filedialog.askopenfilename(title="Select 3D Model", filetypes=[("STL Files", "*.stl"), ("All Files", "*.*")])
        
        if filepath:
            filename = os.path.basename(filepath)
            print(f"Loading new file: {filename}")
            self.geo.load_file(filepath)
            self.marked_points = [] 
            self.screen_rotation = 0 # Reset rotation on new file
            self.show_view('Top')

    def update_plot(self, x, y, z_vert, z_faces, triangles, title, cmap):
        self.ax.clear()
        self.cax.clear()
        
        # --- SAVE RAW DATA FOR HOVER MATH ---
        self.current_x = x
        self.current_y = y
        self.current_z = z_vert
        
        vmin, vmax = np.min(z_faces), np.max(z_faces)
        if vmin == vmax: 
            vmax = vmin + 0.1 
            
        tpc = self.ax.tripcolor(x, y, triangles, facecolors=z_faces, cmap=cmap, edgecolors='none', vmin=vmin, vmax=vmax)
        
        rot_text = f" (Rotated {self.screen_rotation}°)" if self.screen_rotation > 0 else ""
        self.ax.set_title(title + rot_text, fontsize=16)
        self.ax.set_aspect('equal')
        
        self.ax.grid(True, linestyle='--', alpha=0.5, color='#444444')
        self.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold')
        self.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold')
        
        cbar = self.fig.colorbar(tpc, cax=self.cax)
        cbar.set_label('Depth / Z-Axis (mm)', fontsize=12)
        
        # --- CREATE INVISIBLE HOVER TOOLTIP ---
        self.hover_text = self.ax.annotate(
            "", 
            xy=(0, 0), 
            xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1),
            visible=False
        )
        self.hover_text.set_visible(False)
        
        if self.marked_points:
            mx, my = zip(*self.marked_points)
            self.ax.scatter(mx, my, color='red', s=80, marker='X', zorder=5)
            for i, (px, py) in enumerate(self.marked_points):
                self.ax.text(px + 2, py + 2, f"P{i+1}", color='red', fontsize=12, fontweight='bold', zorder=6)

        self.fig.canvas.draw_idle()

    def show_view(self, view_name):
        if self.geo.mesh is None:
            print("Please upload an STL file first.")
            return
            
        self.current_view = view_name
        
        # Unpack the 5 variables and pass them to update_plot
        if view_name == 'Top':
            x, y, z_v, z_f, tri = self.geo.get_top_view(self.screen_rotation)
            self.update_plot(x, y, z_v, z_f, tri, 'Top View', self.cmap)
        elif view_name == 'Bottom':
            x, y, z_v, z_f, tri = self.geo.get_bottom_view(self.screen_rotation)
            self.update_plot(x, y, z_v, z_f, tri, 'Bottom View', self.cmap)
        elif view_name == 'Front':
            x, y, z_v, z_f, tri = self.geo.get_front_view(self.screen_rotation)
            self.update_plot(x, y, z_v, z_f, tri, 'Front View', self.cmap)
        elif view_name == 'Back':
            x, y, z_v, z_f, tri = self.geo.get_back_view(self.screen_rotation)
            self.update_plot(x, y, z_v, z_f, tri, 'Back View', self.cmap)
        elif view_name == 'Left':
            x, y, z_v, z_f, tri = self.geo.get_left_view(self.screen_rotation)
            self.update_plot(x, y, z_v, z_f, tri, 'Left Side View', self.cmap)
        elif view_name == 'Right':
            x, y, z_v, z_f, tri = self.geo.get_right_view(self.screen_rotation)
            self.update_plot(x, y, z_v, z_f, tri, 'Right Side View', self.cmap)

    def _setup_events(self):
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def on_press(self, event):
        if event.inaxes != self.ax: return
        
        if event.button == 1:
            self.drag_state['is_dragging'] = True
            self.drag_state['x'], self.drag_state['y'] = event.x, event.y
            self.drag_state['xlim'], self.drag_state['ylim'] = self.ax.get_xlim(), self.ax.get_ylim()
            
        elif event.button == 3:
            if self.geo.mesh is None: return
            self.marked_points.append((event.xdata, event.ydata))
            print(f"Point Marked: X={event.xdata:.2f}mm, Y={event.ydata:.2f}mm")
            
            self.ax.scatter(event.xdata, event.ydata, color='red', s=80, marker='X', zorder=5)
            self.ax.text(event.xdata + 2, event.ydata + 2, f"P{len(self.marked_points)}", color='red', fontsize=12, fontweight='bold', zorder=6)
            self.fig.canvas.draw_idle()

    def on_release(self, event):
        if event.button == 1: self.drag_state['is_dragging'] = False

    def on_motion(self, event):
        if event.inaxes != self.ax: return
        
        # 1. IF DRAGGING THE SCREEN
        if self.drag_state['is_dragging']: 
            dx_pixel, dy_pixel = event.x - self.drag_state['x'], event.y - self.drag_state['y']
            inv = self.ax.transData.inverted()
            p0 = inv.transform((0, 0))
            p1 = inv.transform((dx_pixel, dy_pixel))
            dx_data, dy_data = p1[0] - p0[0], p1[1] - p0[1]
            self.ax.set_xlim(self.drag_state['xlim'][0] - dx_data, self.drag_state['xlim'][1] - dx_data)
            self.ax.set_ylim(self.drag_state['ylim'][0] - dy_data, self.drag_state['ylim'][1] - dy_data)
            self.fig.canvas.draw_idle()
            
        # 2. IF HOVERING (NOT DRAGGING)
        else:
            if not hasattr(self, 'current_x') or self.current_x is None: return
            
            dist = np.hypot(self.current_x - event.xdata, self.current_y - event.ydata)
            
            # Find ALL points within a 2mm radius of the mouse
            close_points = np.where(dist < 2.0)[0]
            
            if len(close_points) > 0:
                # --- NEW: DEPTH SORTING ---
                # Because the front and back of the mold share the same X,Y coordinates,
                # we force the tooltip to pick the one closest to the surface (Lowest Depth)
                best_idx = close_points[np.argmin(self.current_z[close_points])]
                depth = self.current_z[best_idx]
                
                self.hover_text.xy = (event.xdata, event.ydata)
                self.hover_text.set_text(f"Depth: {depth:.2f} mm")
                self.hover_text.set_visible(True)
            else:
                self.hover_text.set_visible(False)
                
            self.fig.canvas.draw_idle()

    def on_scroll(self, event):
        if event.inaxes != self.ax: return 
        base_scale = 1.2 
        scale_factor = 1 / base_scale if event.button == 'up' else base_scale
        xdata, ydata = event.xdata, event.ydata
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
        new_width = (xlim[1] - xlim[0]) * scale_factor
        new_height = (ylim[1] - ylim[0]) * scale_factor
        relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
        rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
        self.ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        self.ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.fig.canvas.draw_idle()

    def show(self):
        plt.show()