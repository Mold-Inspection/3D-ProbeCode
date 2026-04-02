import matplotlib.pyplot as plt
from matplotlib.widgets import Button
from matplotlib.colors import LinearSegmentedColormap
import tkinter as tk
from tkinter import filedialog
import os

class UIManager:
    def __init__(self, geometry_engine):
        self.geo = geometry_engine
        self.marked_points = [] 
        
        # Setup colors (0/Lowest = Orange/Surface, High = Skyblue/Deep)
        colors = ["white", "red"]
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)
        # We can completely delete the self.cmap_r line!
        self.cmap_r = self.cmap.reversed()

        self.fig, self.ax = plt.subplots(figsize=(11, 9))
        plt.subplots_adjust(bottom=0.2, right=0.85)
        self.cax = self.fig.add_axes([0.88, 0.25, 0.03, 0.5])
        
        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self._setup_buttons()
        self._setup_events()
        
        if self.geo.mesh is not None:
            self.show_view('Top')
        
    def _setup_buttons(self):
        """Creates the 6 view buttons and the Upload button."""
        bw, bh = 0.12, 0.05
        y1, y2 = 0.10, 0.03
        x1, x2, x3 = 0.10, 0.25, 0.40 # X coordinates for the 3 columns
        
        # 6 View Buttons Grid
        ax_top = plt.axes([x1, y1, bw, bh])
        ax_under = plt.axes([x1, y2, bw, bh])
        
        ax_front = plt.axes([x2, y1, bw, bh])
        ax_back = plt.axes([x2, y2, bw, bh])
        
        ax_left = plt.axes([x3, y1, bw, bh])
        ax_right = plt.axes([x3, y2, bw, bh])
        
        # Upload Button on the right
        ax_upload = plt.axes([0.65, 0.10, 0.15, 0.05])
        self.btn_upload = Button(ax_upload, 'Upload STL', color='lightgreen', hovercolor='palegreen')
        self.btn_upload.on_clicked(self.open_file_dialog)

        # Initialize buttons
        self.btn_top = Button(ax_top, 'Top')
        self.btn_under = Button(ax_under, 'Bottom')
        self.btn_front = Button(ax_front, 'Front')
        self.btn_back = Button(ax_back, 'Back')
        self.btn_left = Button(ax_left, 'Left')
        self.btn_right = Button(ax_right, 'Right')

        # Link buttons to functions
        self.btn_top.on_clicked(lambda event: self.show_view('Top'))
        self.btn_under.on_clicked(lambda event: self.show_view('Bottom'))
        self.btn_front.on_clicked(lambda event: self.show_view('Front'))
        self.btn_back.on_clicked(lambda event: self.show_view('Back'))
        self.btn_left.on_clicked(lambda event: self.show_view('Left'))
        self.btn_right.on_clicked(lambda event: self.show_view('Right'))

    def open_file_dialog(self, event):
        root = tk.Tk()
        root.withdraw()
        
        filepath = filedialog.askopenfilename(
            title="Select 3D Model",
            filetypes=[("STL Files", "*.stl"), ("All Files", "*.*")]
        )
        
        if filepath:
            filename = os.path.basename(filepath)
            print(f"Loading new file: {filename}")
            
            self.geo.load_file(filepath)
            self.marked_points = [] # Reset marks when loading new file
            self.show_view('Top')

    def update_plot(self, x, y, z_faces, triangles, title, cmap):
        self.ax.clear()
        self.cax.clear()
        
        tpc = self.ax.tripcolor(x, y, triangles, facecolors=z_faces, cmap=cmap, edgecolors='none')
        self.ax.set_title(title, fontsize=16)
        self.ax.set_aspect('equal')
        
        # GRIDS AND SCALE
        self.ax.grid(True, linestyle='--', alpha=0.5, color='gray')
        self.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold')
        self.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold')
        
        cbar = self.fig.colorbar(tpc, cax=self.cax)
        cbar.set_label('Depth / Z-Axis (mm)', fontsize=12)
        
        # CUSTOM MARKINGS
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
            
        # Every view now uses self.cmap because the geometry engine 
        # automatically sets the closest surface to 0!
        if view_name == 'Top':
            x, y, z, tri = self.geo.get_top_view()
            self.update_plot(x, y, z, tri, 'Top View', self.cmap)
        elif view_name == 'Bottom':
            x, y, z, tri = self.geo.get_bottom_view()
            self.update_plot(x, y, z, tri, 'Bottom View', self.cmap)
        elif view_name == 'Front':
            x, y, z, tri = self.geo.get_front_view()
            self.update_plot(x, y, z, tri, 'Front View', self.cmap)
        elif view_name == 'Back':
            x, y, z, tri = self.geo.get_back_view()
            self.update_plot(x, y, z, tri, 'Back View', self.cmap)
        elif view_name == 'Left':
            x, y, z, tri = self.geo.get_left_view()
            self.update_plot(x, y, z, tri, 'Left Side View', self.cmap)
        elif view_name == 'Right':
            x, y, z, tri = self.geo.get_right_view()
            self.update_plot(x, y, z, tri, 'Right Side View', self.cmap)

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
        if not self.drag_state['is_dragging'] or event.inaxes != self.ax: return
        dx_pixel, dy_pixel = event.x - self.drag_state['x'], event.y - self.drag_state['y']
        inv = self.ax.transData.inverted()
        p0 = inv.transform((0, 0))
        p1 = inv.transform((dx_pixel, dy_pixel))
        dx_data, dy_data = p1[0] - p0[0], p1[1] - p0[1]
        self.ax.set_xlim(self.drag_state['xlim'][0] - dx_data, self.drag_state['xlim'][1] - dx_data)
        self.ax.set_ylim(self.drag_state['ylim'][0] - dy_data, self.drag_state['ylim'][1] - dy_data)
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