import numpy as np
import trimesh
from trimesh.transformations import euler_matrix

class CustomizationTab:
    def __init__(self, app):
        self.app = app

    def draw_cross_section(self):
        app = self.app
        app.fig.clf()
        app.cax = None 

        has_mesh = app.geo.mesh is not None
        has_hole = app.selected_hole_idx is not None and len(app.current_holes) > 0

        if not has_mesh:
            app.ax = app.fig.add_subplot(111, facecolor='#1e1e1e')
            app.ax.set_title("Please upload a model and generate holes first.", color="white", fontsize=15)
            app.ax.set_axis_off()
            app.canvas.draw()
            return

        app.fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
        ax3d = app.fig.add_subplot(111, projection='3d', facecolor='#1e1e1e')
        app.ax = ax3d

        _view_rotations = {
            'Top':    (180,  0,   0),   
            'Bottom': (0,    0,   0),   
            'Front':  (-90,  0,   0),
            'Back':   (90,   0, 180),
            'Left':   (-90,  0,  90),
            'Right':  (-90,  0, -90),
        }
        rx_deg, ry_deg, rz_deg = _view_rotations.get(app.current_view, (0, 0, 0))
        _matrix = euler_matrix(np.radians(rx_deg), np.radians(ry_deg), np.radians(rz_deg))
        _rotated = trimesh.transformations.transform_points(app.geo.mesh.vertices, _matrix)

        faces = app.geo.mesh.faces
        x3 = _rotated[:, 0]
        y3 = _rotated[:, 1]
        z3 = _rotated[:, 2]
        tris = faces

        x3 = x3 - (float(np.min(x3)) + float(np.max(x3))) / 2.0
        y3 = y3 - (float(np.min(y3)) + float(np.max(y3))) / 2.0

        n_tri = len(tris)
        MAX_TRIS = 16000                          
        step = max(1, n_tri // MAX_TRIS)
        sampled = tris[::step]

        SURF_Z_GLOBAL = float(np.min(z3))   

        tx = x3[sampled]   
        ty = y3[sampled]
        tz = z3[sampled] - SURF_Z_GLOBAL    
        nan_col = np.full((len(sampled), 1), np.nan)
        seg_x = np.hstack([tx[:, [0,1,2,0]], nan_col]).ravel()
        seg_y = np.hstack([ty[:, [0,1,2,0]], nan_col]).ravel()
        seg_z = np.hstack([tz[:, [0,1,2,0]], nan_col]).ravel()

        ax3d.plot(seg_x, seg_y, seg_z, color="#1f538d", linewidth=0.8, alpha=0.6)

        tri_cx = x3[tris].mean(axis=1)
        tri_cy = y3[tris].mean(axis=1)
        tri_cz = z3[tris].mean(axis=1)   

        xmin, xmax = float(np.min(x3)), float(np.max(x3))
        ymin, ymax = float(np.min(y3)), float(np.max(y3))
        zmin_d = 0.0                                    
        zmax_d = float(np.max(z3)) - SURF_Z_GLOBAL     
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        cz = (zmin_d + zmax_d) / 2.0
        half = max(xmax - xmin, ymax - ymin, zmax_d - zmin_d) / 2.0 * 1.1

        for i, h in enumerate(app.current_holes):
            r_z = getattr(h, 'hole_top_z', h.surface_z)
            is_sel = (i == app.selected_hole_idx)

            ax3d.text(h.x, h.y, (r_z - SURF_Z_GLOBAL) + half * 0.02,
                      str(h.id), color='white', fontsize=7,
                      ha='center', va='bottom')

            dist_h = np.hypot(tri_cx - h.x, tri_cy - h.y)
            surf_z_g = SURF_Z_GLOBAL
            z_lo_h = min(h.bottom_z, r_z)
            z_hi_h = max(h.bottom_z, r_z) + 0.5

            mask_wall = ((dist_h <= h.radius * 1.2) & (tri_cz >= z_lo_h - 0.3) & (tri_cz <= z_hi_h))
            mask_rim  = ((dist_h <= h.radius * 1.3) & (tri_cz >= surf_z_g - 0.5) & (tri_cz <  z_lo_h + 0.3))
            hmask = mask_wall | mask_rim
            htris = tris[hmask]

            if len(htris) > 0:
                htx = x3[htris]; hty = y3[htris]
                htz = z3[htris] - SURF_Z_GLOBAL    
                nan_h = np.full((len(htris), 1), np.nan)
                hxs = np.hstack([htx[:,[0,1,2,0]], nan_h]).ravel()
                hys = np.hstack([hty[:,[0,1,2,0]], nan_h]).ravel()
                hzs = np.hstack([htz[:,[0,1,2,0]], nan_h]).ravel()
                if is_sel:
                    ax3d.plot(hxs, hys, hzs, color="white", linewidth=1.6, alpha=0.95, label='Selected Hole Mesh')
                else:
                    ax3d.plot(hxs, hys, hzs, color='#1f538d', linewidth=0.9, alpha=0.5)

        if has_hole:
            hole   = app.current_holes[app.selected_hole_idx]
            layers = hole.layers
            points = hole.points_per_layer
            use_zigzag = getattr(hole, 'zigzag_inspection', False)

            rim_z = getattr(hole, 'hole_top_z', hole.surface_z)   
            bot_z = hole.bottom_z                                   

            raw_rim_z = rim_z + SURF_Z_GLOBAL   
            raw_bot_z = bot_z + SURF_Z_GLOBAL   

            dist_v = np.hypot(x3 - hole.x, y3 - hole.y)
            z_lo_v = min(raw_rim_z, raw_bot_z) - 2.0
            z_hi_v = max(raw_rim_z, raw_bot_z) + 2.0
            vmask = (dist_v <= hole.radius * 1.6) & (z3 >= z_lo_v) & (z3 <= z_hi_v)
            vx = x3[vmask]; vy = y3[vmask]; vz = z3[vmask]

            has_step_hole = (hasattr(hole, '_step_hole') and hole._step_hole is not None
                             and hasattr(app.geo, 'step_data') and app.geo.step_data is not None)

            def dz(z_raw):
                return z_raw - SURF_Z_GLOBAL

            if has_step_hole:
                sh = hole._step_hole
                z_start = sh.depth_top     
                star_z  = sh.depth_bot     
                star_x  = hole.x
                star_y  = hole.y
                z_end   = star_z

                step_layers = app.geo.get_probe_path_layers(sh, layers, app.current_view)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                tx_list, ty_list, tz_list = [], [], []

                for lyr in step_layers:
                    z_disp      = lyr['z_display']
                    r_at_z      = lyr['radius'] * 0.92
                    cx_lyr      = lyr['x_display']
                    cy_lyr      = lyr['y_display']
                    ang_offset  = lyr.get('angle_offset', 0.0)   # ← zigzag offset
                    zz_phase    = lyr.get('zigzag_phase', 'normal')

                    px_list.append(cx_lyr); py_list.append(cy_lyr); pz_list.append(z_disp)

                    # สีจุดแตกต่างกันระหว่าง base / rotated layer เมื่อ zigzag เปิด
                    if use_zigzag and zz_phase == 'rotated':
                        pt_color = '#ff9900'   # สีส้ม = layer ที่หมุน 45°
                    else:
                        pt_color = 'red'

                    for ang in np.linspace(0, 2 * np.pi, points, endpoint=False):
                        a = ang + ang_offset           # ← บวก offset ที่นี่
                        ppx = cx_lyr + r_at_z * np.cos(a)
                        ppy = cy_lyr + r_at_z * np.sin(a)
                        tx_list.append(ppx); ty_list.append(ppy); tz_list.append(z_disp)
                        px_list += [ppx, cx_lyr]
                        py_list += [ppy, cy_lyr]
                        pz_list += [z_disp, z_disp]

            else:
                depth_span = abs(rim_z - bot_z)
                vz_disp = vz - SURF_Z_GLOBAL

                if len(vz_disp) >= 6:
                    n_bins = max(20, layers * 4)
                    z_bins = np.linspace(float(np.min(vz_disp)), float(np.max(vz_disp)), n_bins + 1)
                    z_profile = []
                    r_profile = []
                    for bi in range(n_bins):
                        b_mask = (vz_disp >= z_bins[bi]) & (vz_disp < z_bins[bi+1])
                        if b_mask.sum() >= 2:
                            r_vals = np.hypot(vx[b_mask]-hole.x, vy[b_mask]-hole.y)
                            z_profile.append(float((z_bins[bi] + z_bins[bi+1]) / 2))
                            r_profile.append(float(np.percentile(r_vals, 72)))
                    z_profile = np.array(z_profile)
                    r_profile = np.array(r_profile)

                    def mesh_radius_at_z(target_z_disp):
                        if len(z_profile) < 2: return hole.radius
                        return float(np.interp(target_z_disp, z_profile, r_profile, left=r_profile[0], right=r_profile[-1]))
                else:
                    def mesh_radius_at_z(target_z_disp): return hole.radius

                NEAR_CENTER_RATIO = 0.3
                if len(vz) == 0:
                    TRUE_TOP_Z = raw_rim_z
                    TRUE_BOT_Z = raw_bot_z
                else:
                    TRUE_TOP_Z = float(np.min(vz))
                    dist_vmask = dist_v[vmask]
                    near_center_vmask = dist_vmask < (hole.radius * NEAR_CENTER_RATIO)
                    if near_center_vmask.sum() < 1:
                        near_center_vmask = np.ones(len(vz), dtype=bool)
                    TRUE_BOT_Z = float(np.max(vz[near_center_vmask]))

                z_start = dz(TRUE_TOP_Z)
                star_z  = min(z_start + hole.depth, dz(TRUE_BOT_Z))
                star_x  = hole.x
                star_y  = hole.y
                z_end   = star_z
                z_levels_path = np.linspace(z_start, z_end, layers)

                # STL โหมดไม่มี step_layers dict → สร้าง angle_offset เอง
                zigzag_offset_rad = np.radians(45.0)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                tx_list, ty_list, tz_list = [], [], []

                for layer_idx, z_disp in enumerate(z_levels_path):
                    r_at_z = mesh_radius_at_z(z_disp) * 0.92

                    if use_zigzag and (layer_idx % 2 == 1):
                        ang_offset = zigzag_offset_rad
                        pt_color   = '#ff9900'
                    else:
                        ang_offset = 0.0
                        pt_color   = 'red'

                    px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_disp)

                    for ang in np.linspace(0, 2 * np.pi, points, endpoint=False):
                        a = ang + ang_offset           # ← บวก offset ที่นี่
                        ppx = hole.x + r_at_z * np.cos(a)
                        ppy = hole.y + r_at_z * np.sin(a)
                        tx_list.append(ppx); ty_list.append(ppy); tz_list.append(z_disp)
                        px_list += [ppx, hole.x]
                        py_list += [ppy, hole.y]
                        pz_list += [z_disp, z_disp]

            px_list.append(star_x); py_list.append(star_y); pz_list.append(star_z)
            tx_list.append(star_x); ty_list.append(star_y); tz_list.append(star_z)
            px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_start)

            ax3d.plot(px_list, py_list, pz_list,
                      color='yellow', linestyle='--', linewidth=1.2,
                      label='Tool Path', alpha=0.85)

            # --- วาดจุดแยกสี base (red) vs rotated (orange) ---
            if use_zigzag and has_step_hole:
                # แยกจุดตาม phase ที่เก็บใน step_layers
                base_pts    = [(tx, ty, tz) for tx, ty, tz, lyr in
                               zip(tx_list, ty_list, tz_list,
                                   [l for l in step_layers for _ in range(points)] + [step_layers[-1]])
                               if lyr.get('zigzag_phase', 'base') != 'rotated']
                rotated_pts = [(tx, ty, tz) for tx, ty, tz, lyr in
                               zip(tx_list, ty_list, tz_list,
                                   [l for l in step_layers for _ in range(points)] + [step_layers[-1]])
                               if lyr.get('zigzag_phase', 'base') == 'rotated']

                if base_pts:
                    bx, by, bz = zip(*base_pts)
                    ax3d.scatter(bx, by, bz, color='red',     s=22, depthshade=False, label=f'Base Layer pts')
                if rotated_pts:
                    rx_, ry_, rz_ = zip(*rotated_pts)
                    ax3d.scatter(rx_, ry_, rz_, color='#ff9900', s=22, depthshade=False, label='Zigzag +45° pts')
            else:
                wall_n = len(tx_list) - 1
                ax3d.scatter(tx_list[:wall_n], ty_list[:wall_n], tz_list[:wall_n],
                             color='red', s=22, depthshade=False,
                             label=f'Wall Contact ({layers}L×{points}P)')

            ax3d.scatter([tx_list[-1]], [ty_list[-1]], [tz_list[-1]],
                         color='#ffea00', s=90, marker='*', depthshade=False,
                         label='Bottom Depth Point', zorder=10)

            text_color = '#ff3333' if has_step_hole else '#ffea00'
            source_tag = ' [STEP]' if has_step_hole else ' [Mesh]'
            ax3d.text(star_x, star_y, star_z,
                      f" ★{source_tag} X={star_x:.2f}, Y={star_y:.2f}\n   Depth={hole.depth:.2f} mm",
                      color=text_color, fontsize=7, zorder=11)

            zigzag_tag = ' ↕Zigzag' if use_zigzag else ''
            title_str = (
                f"Customization — Hole {hole.id}  |  R={hole.radius:.1f} mm  "
                f"Depth={hole.depth:.2f} mm  |  {layers}L × {points}P = {layers*points} pts"
                + (' [STEP]' if has_step_hole else ' [Mesh]')
                + zigzag_tag
            )
            ax3d.view_init(elev=-135, azim=30)
        else:
            title_str = "Customization — Select a hole to show probing path"
            ax3d.view_init(elev=-135, azim=30)   

        ax3d.set_xlim([cx - half, cx + half])
        ax3d.set_ylim([cy - half, cy + half])
        ax3d.set_zlim([cz - half, cz + half])

        ax3d.set_title(title_str, color='white', fontsize=11, pad=10)
        for spine in [ax3d.xaxis, ax3d.yaxis, ax3d.zaxis]:
            spine.set_pane_color((0.10, 0.10, 0.10, 1.0))
            spine.line.set_color('gray')
        ax3d.tick_params(colors='white', labelsize=7)
        ax3d.set_xlabel("X (mm)", color='white', fontsize=9, labelpad=2)
        ax3d.set_ylabel("Y (mm)", color='white', fontsize=9, labelpad=2)
        ax3d.set_zlabel("Z (mm)", color='white', fontsize=9, labelpad=2)
        if has_hole:
            ax3d.legend(facecolor='#1e1e1e', edgecolor='gray', labelcolor='white',
                        loc='upper right', fontsize=7)

        app.canvas.draw()
