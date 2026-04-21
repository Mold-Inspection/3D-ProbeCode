import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import customtkinter as ctk
from tkinter import ttk 
import numpy as np
import os

ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue")  

class UIManager:
    def __init__(self, geometry_engine):
        self.geo = geometry_engine
        self.marked_points = [] 
        self.current_view = 'Top'
        self.screen_rotation = 0 
        self.scatter_holes = None
        self.current_holes_count = 0
        self.current_holes = []
        
        self.root = ctk.CTk()
        self.root.title("3D Laser Scanner Simulator")
        self.root.geometry("1400x800") 
        
        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#2b2b2b",
                        foreground="white",
                        rowheight=30,
                        fieldbackground="#2b2b2b",
                        borderwidth=0,
                        font=('Arial', 10))
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading",
                        background="#1f1f1f",
                        foreground="white",
                        relief="flat")
        style.map("Treeview.Heading", background=[('active', '#333333')])

        self.sidebar_left = ctk.CTkFrame(self.root, width=250, corner_radius=0)
        self.sidebar_left.pack(side="left", fill="y")
        
        self.sidebar_right = ctk.CTkFrame(self.root, width=350, corner_radius=0, fg_color="#181818")
        self.sidebar_right.pack_propagate(False) 
        self.sidebar_right.pack(side="right", fill="y")
        
        self.center_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="#242424")
        self.center_frame.pack(side="left", fill="both", expand=True)

        self.top_bar = ctk.CTkFrame(self.center_frame, fg_color="transparent", height=50)
        self.top_bar.pack(side="top", fill="x", padx=20, pady=(10, 0))
        
        self.nav_selector = ctk.CTkSegmentedButton(
            self.top_bar, 
            values=["Selection", "Customization", "Path Mapper"],
            command=self.on_nav_change,
            height=35,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.nav_selector.set("Selection")
        self.nav_selector.pack(side="top", pady=5) 

        plt.style.use('dark_background')
        colors = ["white", "red"]
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)

        self.fig = Figure(figsize=(10, 8), facecolor='#242424')
        self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
        self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
        self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7]) 
        
        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.center_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1),
            visible=False
        )

        self._setup_left_sidebar()
        self._setup_right_sidebar()
        self._setup_events()
        
        if self.geo.mesh is not None:
            self.show_view('Top')

    def _setup_left_sidebar(self):
        ctk.CTkLabel(self.sidebar_left, text="3D CNC Control", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        
        self.btn_upload = ctk.CTkButton(self.sidebar_left, text="Upload STL", fg_color="#2e7d32", hover_color="#4caf50", command=self.open_file_dialog)
        self.btn_upload.pack(pady=10, padx=20, fill="x")
        
        self.info_frame = ctk.CTkFrame(self.sidebar_left, fg_color="#1e1e1e", corner_radius=5)
        self.info_frame.pack(pady=(0, 15), padx=20, fill="x")
        
        self.lbl_width = ctk.CTkLabel(self.info_frame, text="Width (X): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_width.pack(pady=(5, 0), padx=10, anchor="w")
        
        self.lbl_length = ctk.CTkLabel(self.info_frame, text="Length (Y): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_length.pack(pady=0, padx=10, anchor="w")
        
        self.lbl_thick = ctk.CTkLabel(self.info_frame, text="Thickness (Z): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_thick.pack(pady=(0, 5), padx=10, anchor="w")

        ctk.CTkLabel(self.sidebar_left, text="--- View Controls ---", text_color="gray").pack(pady=(20, 5))
        
        self.btn_rotate = ctk.CTkButton(self.sidebar_left, text="⟳ Rotate 90°", fg_color="#0277bd", hover_color="#039be5", command=self.rotate_screen)
        self.btn_rotate.pack(pady=10, padx=20, fill="x")

        self.btn_reset = ctk.CTkButton(self.sidebar_left, text="⌂ Reset Position", fg_color="#d84315", hover_color="#bf360c", command=self.reset_position)
        self.btn_reset.pack(pady=(0, 10), padx=20, fill="x")

        view_frame = ctk.CTkFrame(self.sidebar_left, fg_color="transparent")
        view_frame.pack(pady=10, padx=20, fill="x")
        
        views = [('Top', 0, 0), ('Bottom', 0, 1), 
                 ('Front', 1, 0), ('Back', 1, 1), 
                 ('Left', 2, 0), ('Right', 2, 1)]
                 
        for name, row, col in views:
            btn = ctk.CTkButton(view_frame, text=name, width=85, fg_color="#424242", hover_color="#616161",
                                command=lambda v=name: self.show_view(v))
            btn.grid(row=row, column=col, padx=5, pady=5)

    def _setup_right_sidebar(self):
        self.right_header = ctk.CTkLabel(self.sidebar_right, text="Detected Holes", font=ctk.CTkFont(size=16, weight="bold"))
        self.right_header.pack(pady=(20, 10), padx=20, anchor="w")

        self.tree_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True, padx=20, pady=20)

        columns = ("id", "type")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="tree", selectmode="browse")
        
        self.tree.column("#0", width=300, minwidth=200, stretch=ctk.YES) 
        self.tree.column("id", width=0, stretch=ctk.NO) 
        self.tree.column("type", width=0, stretch=ctk.NO)

        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # [NEW] Bind selection event to trigger the marker highlight
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        # Bind the left mouse click to the Treeview
        self.tree.bind("<Button-1>", self.on_tree_click)

    def _detect_holes_in_view(self, x, y, z, view_name):
        if len(z) == 0: return []
        
        if view_name in ['Top', 'Front', 'Right']:
            surface_z = np.max(z)
            bottom_z = np.min(z)
            valid_indices = np.where((z < surface_z - 1.0) & (z > bottom_z + 1.0))[0]
            is_positive_view = True
        else:
            surface_z = np.min(z)
            bottom_z = np.max(z)
            valid_indices = np.where((z > surface_z + 1.0) & (z < bottom_z - 1.0))[0]
            is_positive_view = False
            
        if len(valid_indices) == 0: return []

        holes = []
        cluster_radius = 15.0  
        remaining = set(valid_indices)

        while remaining:
            idx = remaining.pop()
            cluster = [idx]
            queue = [idx]
            
            while queue:
                current = queue.pop(0)
                curr_x, curr_y = x[current], y[current]
                
                if not remaining: 
                    break
                
                rem_arr = np.array(list(remaining))
                dists = np.hypot(x[rem_arr] - curr_x, y[rem_arr] - curr_y)
                
                neighbors = rem_arr[dists < cluster_radius]
                for n in neighbors:
                    remaining.remove(n)
                    cluster.append(n)
                    queue.append(n)
            
            if len(cluster) > 5:
                cluster_x = x[cluster]
                cluster_y = y[cluster]
                cluster_z = z[cluster]
                
                center_x = float(np.mean(cluster_x))
                center_y = float(np.mean(cluster_y))
                
                if is_positive_view:
                    max_depth = float(surface_z - np.min(cluster_z))
                else:
                    max_depth = float(np.max(cluster_z) - surface_z)
                
                holes.append({
                    'x': center_x, 
                    'y': center_y, 
                    'depth': max_depth
                })
        
        holes.sort(key=lambda h: (-round(h['y'] / 5.0), h['x']))
        return holes

    def update_treeview(self, holes):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not holes:
            self.tree.insert("", "end", text="   -- No holes detected --")
            return
            
        for i, hole in enumerate(holes):
            node_text = f" 🎯 Hole {i+1} [X: {hole['x']:.2f}, Y: {hole['y']:.2f}] Depth: {hole['depth']:.2f} mm"
            # We store "H{i}" so we can easily map the selection back to the marker index
            self.tree.insert("", "end", text=node_text, values=(f"H{i}", "Parent"), open=True)

    # [NEW] Event handler for Treeview selection
    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        
        if not self.scatter_holes:
            return

        # Default all markers back to white
        colors = ['white'] * self.current_holes_count

        if selected_items:
            item = selected_items[0]
            values = self.tree.item(item, "values")
            
            if values and str(values[0]).startswith("H"):
                try:
                    # Extract index from 'H0', 'H1', etc.
                    idx = int(values[0][1:])
                    if 0 <= idx < self.current_holes_count:
                        colors[idx] = 'yellow' # Highlight color
                except ValueError:
                    pass

        # Apply the new colors to the scatter markers and redraw the canvas
        self.scatter_holes.set_facecolors(colors)
        self.canvas.draw_idle()
    
    def on_tree_click(self, event):
        # Find exactly which row the mouse is hovering over
        item = self.tree.identify_row(event.y)
        
        # If the item exists and is already currently selected...
        if item and item in self.tree.selection():
            # ...remove it from the selection
            self.tree.selection_remove(item)
            
            # Manually trigger our color update so the marker turns white again
            self.on_tree_select(None)
            
            # Tell Tkinter to stop processing the click (so it doesn't immediately re-select it)
            return "break"

    def on_nav_change(self, selected_tab):
        if selected_tab == "Selection":
            self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)
        else:
            self.sidebar_right.pack_forget()
            
    def rotate_screen(self):
        if self.geo.mesh is None: return
        self.screen_rotation = (self.screen_rotation + 90) % 360
        self.show_view(self.current_view)

    def reset_position(self):
        if self.geo.mesh is not None:
            self.show_view(self.current_view)

    def open_file_dialog(self):
        filepath = ctk.filedialog.askopenfilename(title="Select 3D Model", filetypes=[("STL Files", "*.stl"), ("All Files", "*.*")])
        if filepath:
            filename = os.path.basename(filepath)
            self.geo.load_file(filepath)
            self.screen_rotation = 0
            if self.geo.mesh is not None:
                extents = self.geo.get_physical_dimensions() 
                self.lbl_width.configure(text=f"Width (X): {extents[0]:.2f} mm", text_color="white")
                self.lbl_length.configure(text=f"Length (Y): {extents[1]:.2f} mm", text_color="white")
                self.lbl_thick.configure(text=f"Thickness (Z): {extents[2]:.2f} mm", text_color="white")
            self.show_view('Top')

    def update_plot(self, x, y, z_vert, face_data, triangles, title, holes=None):
        self.ax.clear()
        self.cax.clear()
        
        self.current_x, self.current_y, self.current_z = x, y, z_vert
        self.current_triangles = triangles
        
        vmin, vmax = np.min(face_data), np.max(face_data)
        if vmin == vmax: vmax = vmin + 0.1 
            
        tpc = self.ax.tripcolor(x, y, triangles, facecolors=face_data, cmap=self.cmap, edgecolors='none', vmin=vmin, vmax=vmax)
        
        if holes:
            hole_x = [h['x'] for h in holes]
            hole_y = [h['y'] for h in holes]
            
            # [MODIFIED] Store reference to the scatter plot and track total hole count
            self.current_holes_count = len(holes)
            initial_colors = ['white'] * self.current_holes_count
            
            self.scatter_holes = self.ax.scatter(hole_x, hole_y, facecolors=initial_colors, edgecolors="#3694ED", 
                                                 marker='o', s=150, linewidths=2, zorder=5, clip_on=True)
            
            for i, h in enumerate(holes):
                self.ax.text(h['x'], h['y'], f"{i+1}", color='black', fontsize=8, weight='bold', 
                             ha='center', va='center', zorder=6, clip_on=True)
        else:
            self.scatter_holes = None
            self.current_holes_count = 0

        rot_text = f" (Rotated {self.screen_rotation}°)" if self.screen_rotation > 0 else ""
        self.ax.set_title(title + rot_text, fontsize=16, color="white")
        self.ax.set_aspect('equal')
        
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        self.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        self.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        
        cbar = self.fig.colorbar(tpc, cax=self.cax)
        cbar.set_label("Depth / Z-Axis (mm)", fontsize=12, color="white")
        cbar.ax.yaxis.set_tick_params(color='white', labelcolor='white')
        
        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1), visible=False
        )

        self.canvas.draw()
        
    def show_view(self, view_name):
        if self.geo.mesh is None: return
        self.current_view = view_name
        
        if view_name == 'Top':
            x, y, z_v, z_f, tri = self.geo.get_top_view(self.screen_rotation)
        elif view_name == 'Bottom':
            x, y, z_v, z_f, tri = self.geo.get_bottom_view(self.screen_rotation)
        elif view_name == 'Front':
            x, y, z_v, z_f, tri = self.geo.get_front_view(self.screen_rotation)
        elif view_name == 'Back':
            x, y, z_v, z_f, tri = self.geo.get_back_view(self.screen_rotation)
        elif view_name == 'Left':
            x, y, z_v, z_f, tri = self.geo.get_left_view(self.screen_rotation)
        elif view_name == 'Right':
            x, y, z_v, z_f, tri = self.geo.get_right_view(self.screen_rotation)

        self.current_holes = self._detect_holes_in_view(x, y, z_v, view_name)
        
        title = f"{view_name} View"
        self.update_plot(x, y, z_v, z_f, tri, title, holes=self.current_holes)
        self.update_treeview(self.current_holes)

    def _setup_events(self):
        self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def on_press(self, event):
        if event.inaxes != self.ax: return
        if event.button == 1:
            self.drag_state['is_dragging'] = True
            self.drag_state['x'], self.drag_state['y'] = event.x, event.y
            self.drag_state['xlim'], self.drag_state['ylim'] = self.ax.get_xlim(), self.ax.get_ylim()

    def on_release(self, event):
        if event.button == 1: self.drag_state['is_dragging'] = False

    def on_motion(self, event):
        if event.inaxes != self.ax: return
        
        if self.drag_state['is_dragging']: 
            dx_pixel, dy_pixel = event.x - self.drag_state['x'], event.y - self.drag_state['y']
            inv = self.ax.transData.inverted()
            p0 = inv.transform((0, 0))
            p1 = inv.transform((dx_pixel, dy_pixel))
            dx_data, dy_data = p1[0] - p0[0], p1[1] - p0[1]
            self.ax.set_xlim(self.drag_state['xlim'][0] - dx_data, self.drag_state['xlim'][1] - dx_data)
            self.ax.set_ylim(self.drag_state['ylim'][0] - dy_data, self.drag_state['ylim'][1] - dy_data)
            self.canvas.draw()
        else:
            if not hasattr(self, 'current_x') or self.current_x is None: return
            dist = np.hypot(self.current_x - event.xdata, self.current_y - event.ydata)
            close_points = np.where(dist < 2.0)[0]
            
            if len(close_points) > 0:
                if self.current_view in ['Top', 'Front', 'Right']:
                    best_idx = close_points[np.argmin(self.current_z[close_points])]
                    surface_z = np.max(self.current_z)
                    depth = surface_z - self.current_z[best_idx]
                else:
                    best_idx = close_points[np.argmax(self.current_z[close_points])]
                    surface_z = np.min(self.current_z)
                    depth = self.current_z[best_idx] - surface_z
                
                self.hover_text.set_text(f"Depth: {depth:.2f} mm")
                self.hover_text.xy = (event.xdata, event.ydata)
                self.hover_text.set_visible(True)
            else:
                self.hover_text.set_visible(False)
            self.canvas.draw()

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
        self.canvas.draw()
    
    def show(self):
        self.root.mainloop()