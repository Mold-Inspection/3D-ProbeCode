import numpy as np
from core.models import HoleFeature

class SelectionTab:
    def __init__(self, app):
        self.app = app 
        
    def setup_events(self):
        self.app.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.app.canvas.mpl_connect('button_press_event', self.on_press)
        self.app.canvas.mpl_connect('button_release_event', self.on_release)
        self.app.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def detect_holes_in_view(self, x, y, z, view_name):
        if len(z) == 0: return []

        if view_name in ['Front', 'Right']:
            surface_z = np.max(z)
            bottom_z  = np.min(z)
            valid_indices = np.where((z < surface_z - 1.0) & (z > bottom_z + 1.0))[0]
            is_positive_view = True
        else:
            surface_z = np.min(z)
            bottom_z  = np.max(z)
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
                if not remaining: break
                
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
                distances = np.hypot(cluster_x - center_x, cluster_y - center_y)
                radius = float(np.percentile(distances, 95))
                if radius < 1.0: radius = 2.0 
                
                NEAR_CENTER_RATIO = 0.3
                near_center_mask = distances < (radius * NEAR_CENTER_RATIO)
                if near_center_mask.sum() < 1:
                    near_center_mask = np.ones(len(cluster_z), dtype=bool) 

                if is_positive_view:
                    surf_z = surface_z
                    bot_z = float(np.min(cluster_z[near_center_mask]))
                    max_depth = float(surf_z - bot_z)
                    hole_top_z = float(np.max(cluster_z))
                else:
                    surf_z = surface_z
                    bot_z = float(np.max(cluster_z[near_center_mask]))
                    max_depth = float(bot_z - surf_z)
                    hole_top_z = float(np.min(cluster_z))
                
                hid = len(holes) + 1
                hf = HoleFeature(hid, center_x, center_y, surf_z, bot_z, max_depth, radius)
                hf.hole_top_z = hole_top_z
                holes.append(hf)
        
        holes.sort(key=lambda h: (-round(h.y / 5.0), h.x))
        for i, h in enumerate(holes):
            h.id = i + 1
            
        return holes

    def update_plot(self, x, y, z_vert, face_data, triangles, title, holes=None):
        app = self.app
        if app.current_tab != "Selection": return 
        
        app.ax.clear()
        if hasattr(app, 'cax') and app.cax is not None:
            app.cax.clear()
            app.cax.set_visible(True)
        app.ax.set_axis_on()
        
        app.current_x, app.current_y, app.current_z = x, y, z_vert
        app.current_triangles = triangles
        
        vmin, vmax = np.min(face_data), np.max(face_data)
        if vmin == vmax: vmax = vmin + 0.1 
            
        tpc = app.ax.tripcolor(x, y, triangles, facecolors=face_data, cmap=app.cmap, edgecolors='none', vmin=vmin, vmax=vmax)
        
        if holes:
            hole_x = [h.x for h in holes] 
            hole_y = [h.y for h in holes]
            app.current_holes_count = len(holes)
            initial_colors = ['white'] * app.current_holes_count
            
            if app.selected_hole_idx is not None and 0 <= app.selected_hole_idx < app.current_holes_count:
                initial_colors[app.selected_hole_idx] = 'yellow'
                
            app.scatter_holes = app.ax.scatter(hole_x, hole_y, facecolors=initial_colors, edgecolors="#3694ED", 
                                               marker='o', s=150, linewidths=2, zorder=5, clip_on=True)
            for i, h in enumerate(holes):
                app.ax.text(h.x, h.y, f"{h.id}", color='black', fontsize=8, weight='bold', 
                            ha='center', va='center', zorder=6, clip_on=True)
        else:
            app.scatter_holes = None
            app.current_holes_count = 0

        lock_text = " [LOCKED]" if app.holes_detected else "" 
        rot_text = f" (Rotated {app.screen_rotation}°)" if app.screen_rotation > 0 else ""
        app.ax.set_title(title + rot_text + lock_text, fontsize=16, color="white")
        
        app.ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        app.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        app.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        
        if app.max_physical_dim is not None and len(app.current_x) > 0:
            cx = (np.min(app.current_x) + np.max(app.current_x)) / 2.0
            cy = (np.min(app.current_y) + np.max(app.current_y)) / 2.0
            half_span = (app.max_physical_dim / 2.0) * 1.15  
            app.ax.set_xlim([cx - half_span, cx + half_span])
            app.ax.set_ylim([cy - half_span, cy + half_span])
            
        app.ax.set_aspect('equal')
        
        if hasattr(app, 'cax') and app.cax is not None:
            cbar = app.fig.colorbar(tpc, cax=app.cax)
            cbar.set_label("Depth / Z-Axis (mm)", fontsize=12, color="white")
            cbar.ax.yaxis.set_tick_params(color='white', labelcolor='white')
        
        app.canvas.draw()

    def on_press(self, event):
        if event.inaxes != self.app.ax: return
        if self.app.current_tab == "Path Mapper": return 
        
        if event.button == 1:
            self.app.drag_state['is_dragging'] = True
            self.app.drag_state['x'], self.app.drag_state['y'] = event.x, event.y
            self.app.drag_state['xlim'], self.app.drag_state['ylim'] = self.app.ax.get_xlim(), self.app.ax.get_ylim()

    def on_release(self, event):
        if event.button == 1: self.app.drag_state['is_dragging'] = False

    def on_motion(self, event):
        if event.inaxes != self.app.ax: return
        if self.app.current_tab == "Path Mapper": return 
        
        if self.app.drag_state['is_dragging']: 
            dx_pixel, dy_pixel = event.x - self.app.drag_state['x'], event.y - self.app.drag_state['y']
            inv = self.app.ax.transData.inverted()
            p0 = inv.transform((0, 0))
            p1 = inv.transform((dx_pixel, dy_pixel))
            dx_data, dy_data = p1[0] - p0[0], p1[1] - p0[1]
            self.app.ax.set_xlim(self.app.drag_state['xlim'][0] - dx_data, self.app.drag_state['xlim'][1] - dx_data)
            self.app.ax.set_ylim(self.app.drag_state['ylim'][0] - dy_data, self.app.drag_state['ylim'][1] - dy_data)
            self.app.canvas.draw()
        else:
            if self.app.current_tab != "Selection": 
                if hasattr(self.app, 'hover_text'): self.app.hover_text.set_visible(False)
                return
                
            if not hasattr(self.app, 'current_x') or self.app.current_x is None: return
            dist = np.hypot(self.app.current_x - event.xdata, self.app.current_y - event.ydata)
            close_points = np.where(dist < 2.0)[0]
            
            if len(close_points) > 0:
                if self.app.current_view in ['Front', 'Right']:
                    best_idx = close_points[np.argmin(self.app.current_z[close_points])]
                    surface_z = np.max(self.app.current_z)
                    depth = surface_z - self.app.current_z[best_idx]
                else:
                    best_idx = close_points[np.argmax(self.app.current_z[close_points])]
                    surface_z = np.min(self.app.current_z)
                    depth = self.app.current_z[best_idx] - surface_z
                
                if hasattr(self.app, 'hover_text'):
                    self.app.hover_text.set_text(f"Depth: {depth:.2f} mm")
                    self.app.hover_text.xy = (event.xdata, event.ydata)
                    self.app.hover_text.set_visible(True)
            else:
                if hasattr(self.app, 'hover_text'): self.app.hover_text.set_visible(False)
            self.app.canvas.draw()

    def on_scroll(self, event):
        if event.inaxes != self.app.ax: return 
        if self.app.current_tab == "Path Mapper": return 
        
        base_scale = 1.2 
        scale_factor = 1 / base_scale if event.button == 'up' else base_scale
        xdata, ydata = event.xdata, event.ydata
        xlim, ylim = self.app.ax.get_xlim(), self.app.ax.get_ylim()
        new_width = (xlim[1] - xlim[0]) * scale_factor
        new_height = (ylim[1] - ylim[0]) * scale_factor
        relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
        rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
        self.app.ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        self.app.ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.app.canvas.draw()