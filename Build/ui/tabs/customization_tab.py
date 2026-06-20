import numpy as np
import trimesh
from trimesh.transformations import euler_matrix

# สีประจำแต่ละ Layer สำหรับโหมด Zigzag — ขยายเป็น 24 สี
# เลือกมาให้ตัดกับสีเหลืองของ Tool Path / Bottom Depth Point (★) อย่างชัดเจน
# จึงหลีกเลี่ยงสีเหลือง/ทองทุกเฉด (เช่น #ffea00, #ffd700, #ffe066)
# วนซ้ำ (cycle) ถ้าจำนวน layer มากกว่าจำนวนสีในลิสต์
ZIGZAG_LAYER_COLORS = [
    '#00bcd4',  # 01 cyan
    '#ff4d6d',  # 02 rose red
    '#7c4dff',  # 03 violet
    '#69f0ae',  # 04 mint green
    '#ff9100',  # 05 amber orange
    '#40c4ff',  # 06 sky blue
    '#f06292',  # 07 pink
    '#aeea00',  # 08 lime
    '#ea80fc',  # 09 lavender purple
    '#ff6e40',  # 10 deep orange
    '#18ffff',  # 11 bright cyan
    '#b9f6ca',  # 12 pale mint
    '#ff4081',  # 13 hot pink
    '#b388ff',  # 14 soft violet
    '#00e676',  # 15 vivid green
    '#ff6d00',  # 16 burnt orange
    '#82b1ff',  # 17 periwinkle blue
    '#f48fb1',  # 18 dusty rose
    '#1de9b6',  # 19 teal
    '#ff8a65',  # 20 salmon
    '#ce93d8',  # 21 lilac
    '#80d8ff',  # 22 ice blue
    '#a5d6a7',  # 23 sage green
    '#ef9a9a',  # 24 blush red
]


def _layer_color(lidx: int) -> str:
    return ZIGZAG_LAYER_COLORS[lidx % len(ZIGZAG_LAYER_COLORS)]


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

        n_tri   = len(tris)
        MAX_TRIS = 16000
        step    = max(1, n_tri // MAX_TRIS)
        sampled = tris[::step]

        SURF_Z_GLOBAL = float(np.min(z3))

        tx_m = x3[sampled]
        ty_m = y3[sampled]
        tz_m = z3[sampled] - SURF_Z_GLOBAL
        nan_col = np.full((len(sampled), 1), np.nan)
        seg_x = np.hstack([tx_m[:, [0,1,2,0]], nan_col]).ravel()
        seg_y = np.hstack([ty_m[:, [0,1,2,0]], nan_col]).ravel()
        seg_z = np.hstack([tz_m[:, [0,1,2,0]], nan_col]).ravel()
        # ซ่อน wireframe โมเดลทั้งชิ้นเมื่อเลือกรูแล้ว (โหมด Focus)
        if not has_hole:
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
            r_z    = getattr(h, 'hole_top_z', h.surface_z)
            is_sel = (i == app.selected_hole_idx)

            ax3d.text(h.x, h.y, (r_z - SURF_Z_GLOBAL) + half * 0.02,
                      str(h.id), color='white', fontsize=7,
                      ha='center', va='bottom')

            # ── Focus mode: ถ้ามีรูถูกเลือกอยู่ (has_hole) ให้ซ่อน wall mesh
            # ของรูอื่นที่ไม่ได้ถูกเลือกทั้งหมด (ยังคงแสดงเลข ID ไว้ด้านบน
            # เพื่อให้กดเลือกรูอื่นจากแถบขวาได้ตามปกติ) ── ดู step 2 ──────────
            if has_hole and not is_sel:
                continue

            dist_h = np.hypot(tri_cx - h.x, tri_cy - h.y)
            z_lo_h = min(h.bottom_z, r_z)
            z_hi_h = max(h.bottom_z, r_z) + 0.5

            mask_wall = ((dist_h <= h.radius * 1.2) &
                         (tri_cz >= z_lo_h - 0.3) & (tri_cz <= z_hi_h))
            mask_rim  = ((dist_h <= h.radius * 1.3) &
                         (tri_cz >= SURF_Z_GLOBAL - 0.5) & (tri_cz < z_lo_h + 0.3))
            htris = tris[mask_wall | mask_rim]

            # วาดเฉพาะ mesh ของรูที่ถูกเลือก (is_sel == True) เท่านั้น
            # รูที่ไม่ได้เลือกให้ซ่อนทั้งหมด — ไม่ dim, ไม่วาดเลย
            if len(htris) > 0 and is_sel:
                htx = x3[htris]; hty = y3[htris]
                htz = z3[htris] - SURF_Z_GLOBAL
                nan_h = np.full((len(htris), 1), np.nan)
                hxs = np.hstack([htx[:,[0,1,2,0]], nan_h]).ravel()
                hys = np.hstack([hty[:,[0,1,2,0]], nan_h]).ravel()
                hzs = np.hstack([htz[:,[0,1,2,0]], nan_h]).ravel()
                ax3d.plot(hxs, hys, hzs, color="white", linewidth=1.6, alpha=0.76, label='Selected Hole Mesh')

        # ── ตรวจสอบ Probe Profile (ถ้ามี) ──────────────────────────────────────
        # probe_profile อยู่บน app (UIManager) ซึ่ง CustomizationTab เข้าถึงได้ผ่าน self.app
        probe_warn_lines = []   # list[str] สำหรับแสดงใน title / annotation
        probe_ok = True

        if has_hole:
            hole_for_check = app.current_holes[app.selected_hole_idx]
            if hasattr(app, 'probe_profile') and app.probe_profile is not None:
                chk = app.probe_profile.check_hole(
                    hole_for_check.depth, hole_for_check.radius)
                probe_ok = chk['ok']
                if chk['depth_warning']:
                    probe_warn_lines.append(chk['depth_warning'])
                if chk['fit_warning']:
                    probe_warn_lines.append(chk['fit_warning'])

        if has_hole:
            hole       = app.current_holes[app.selected_hole_idx]
            layers     = hole.layers
            points     = hole.points_per_layer
            use_zigzag = getattr(hole, 'zigzag_inspection', False)
            step_deg   = getattr(hole, 'zigzag_degree', 45.0)

            rim_z = getattr(hole, 'hole_top_z', hole.surface_z)
            bot_z = hole.bottom_z

            raw_rim_z = rim_z + SURF_Z_GLOBAL
            raw_bot_z = bot_z + SURF_Z_GLOBAL

            dist_v = np.hypot(x3 - hole.x, y3 - hole.y)
            z_lo_v = min(raw_rim_z, raw_bot_z) - 2.0
            z_hi_v = max(raw_rim_z, raw_bot_z) + 2.0
            vmask  = (dist_v <= hole.radius * 1.6) & (z3 >= z_lo_v) & (z3 <= z_hi_v)
            vx = x3[vmask]; vy = y3[vmask]; vz = z3[vmask]

            has_step_hole = (hasattr(hole, '_step_hole') and hole._step_hole is not None
                             and hasattr(app.geo, 'step_data') and app.geo.step_data is not None)

            def dz(z_raw): return z_raw - SURF_Z_GLOBAL

            # ------------------------------------------------------------------
            # px_list / py_list / pz_list  → ใช้วาดเส้น Tool Path (เส้นประเหลือง)
            # wall_pts                     → list[(x, y, z, layer_idx)] จุดบนผนัง
            # layer_centers                → dict[layer_idx] = (cx_lyr, cy_lyr, z_disp, angle_offset, radius)
            #                                 ใช้วาด "เข็มชี้มุมหมุน" ต่อ layer
            # star_x/y/z                   → จุดก้นรู (★) แยกต่างหาก ไม่รวมใน wall_pts
            # ------------------------------------------------------------------

            if has_step_hole:
                sh          = hole._step_hole
                z_start     = sh.depth_top
                star_z      = sh.depth_bot
                star_x      = hole.x
                star_y      = hole.y

                # สำคัญ: ต้องส่ง zigzag_inspection / zigzag_degree เข้าไปตรงๆ เพราะ `sh`
                # คือ StepHole ซึ่งไม่มี attribute เหล่านี้ — ถ้าไม่ส่งเข้าไป planner จะ
                # ใช้ค่า default (False / ไม่หมุน) เสมอ ทำให้ Zigzag ไม่ทำงานกับรูจาก STEP
                step_layers = app.geo.get_probe_path_layers(
                    sh, layers, app.current_view,
                    zigzag_inspection=use_zigzag, zigzag_degree=step_deg)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                wall_pts = []        # (x, y, z, layer_idx)
                layer_centers = {}   # layer_idx -> (cx_lyr, cy_lyr, z_disp, angle_offset, radius)

                for lyr in step_layers:
                    z_disp     = lyr['z_display']
                    r_at_z     = lyr['radius'] * 0.92
                    cx_lyr     = lyr['x_display']
                    cy_lyr     = lyr['y_display']
                    ang_offset = lyr.get('angle_offset', 0.0)
                    lidx       = lyr.get('layer_idx', 0)

                    layer_centers[lidx] = (cx_lyr, cy_lyr, z_disp, ang_offset, r_at_z)

                    px_list.append(cx_lyr); py_list.append(cy_lyr); pz_list.append(z_disp)

                    for ang in np.linspace(0, 2 * np.pi, points, endpoint=False):
                        a   = ang + ang_offset
                        ppx = cx_lyr + r_at_z * np.cos(a)
                        ppy = cy_lyr + r_at_z * np.sin(a)
                        wall_pts.append((ppx, ppy, z_disp, lidx))
                        px_list += [ppx, cx_lyr]
                        py_list += [ppy, cy_lyr]
                        pz_list += [z_disp, z_disp]

            else:
                vz_disp = vz - SURF_Z_GLOBAL

                if len(vz_disp) >= 6:
                    n_bins   = max(20, layers * 4)
                    z_bins   = np.linspace(float(np.min(vz_disp)), float(np.max(vz_disp)), n_bins + 1)
                    z_profile, r_profile = [], []
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
                        return float(np.interp(target_z_disp, z_profile, r_profile,
                                               left=r_profile[0], right=r_profile[-1]))
                else:
                    def mesh_radius_at_z(target_z_disp): return hole.radius

                NEAR_CENTER_RATIO = 0.3
                if len(vz) == 0:
                    TRUE_TOP_Z = raw_rim_z
                    TRUE_BOT_Z = raw_bot_z
                else:
                    TRUE_TOP_Z   = float(np.min(vz))
                    dist_vmask   = dist_v[vmask]
                    near_c_mask  = dist_vmask < (hole.radius * NEAR_CENTER_RATIO)
                    if near_c_mask.sum() < 1:
                        near_c_mask = np.ones(len(vz), dtype=bool)
                    TRUE_BOT_Z = float(np.max(vz[near_c_mask]))

                z_start       = dz(TRUE_TOP_Z)
                star_z        = min(z_start + hole.depth, dz(TRUE_BOT_Z))
                star_x        = hole.x
                star_y        = hole.y
                z_levels_path = np.linspace(z_start, star_z, layers)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                wall_pts = []
                layer_centers = {}

                for layer_idx, z_disp in enumerate(z_levels_path):
                    r_at_z     = mesh_radius_at_z(z_disp) * 0.92
                    ang_offset = np.radians(layer_idx * step_deg) if use_zigzag else 0.0

                    layer_centers[layer_idx] = (hole.x, hole.y, z_disp, ang_offset, r_at_z)

                    px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_disp)

                    for ang in np.linspace(0, 2 * np.pi, points, endpoint=False):
                        a   = ang + ang_offset
                        ppx = hole.x + r_at_z * np.cos(a)
                        ppy = hole.y + r_at_z * np.sin(a)
                        wall_pts.append((ppx, ppy, z_disp, layer_idx))
                        px_list += [ppx, hole.x]
                        py_list += [ppy, hole.y]
                        pz_list += [z_disp, z_disp]

            # ── เส้น Tool Path ────────────────────────────────────────────────
            # ปิดเส้นกลับ: เดินลงไปถึง star แล้ววกกลับ entry
            px_list.append(star_x); py_list.append(star_y); pz_list.append(star_z)
            px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_start)

            ax3d.plot(px_list, py_list, pz_list,
                      color='yellow', linestyle='--', linewidth=1.2,
                      label='Tool Path', alpha=0.85)

            # ── จุดบนผนัง (Wall Contact) ──────────────────────────────────────
            if wall_pts:
                if use_zigzag:
                    for lidx in range(layers):
                        pts_l = [(wx, wy, wz) for wx, wy, wz, li in wall_pts if li == lidx]
                        if not pts_l:
                            continue
                        wx_l, wy_l, wz_l = zip(*pts_l)
                        color_l = _layer_color(lidx)
                        deg_here = int(round(lidx * step_deg)) % 360
                        lbl = f'Layer {lidx+1} (+{deg_here}°)' if lidx > 0 else 'Layer 1 (0°)'
                        ax3d.scatter(wx_l, wy_l, wz_l,
                                     color=color_l, s=26, depthshade=False,
                                     edgecolors='white', linewidths=0.4, label=lbl)

                        # ── เข็มชี้มุมหมุน (rotation indicator spoke) ──────────
                        if lidx in layer_centers:
                            cx_lyr, cy_lyr, z_disp, ang_offset, r_at_z = layer_centers[lidx]
                            spoke_x = cx_lyr + r_at_z * np.cos(ang_offset)
                            spoke_y = cy_lyr + r_at_z * np.sin(ang_offset)
                            ax3d.plot([cx_lyr, spoke_x], [cy_lyr, spoke_y], [z_disp, z_disp],
                                      color=color_l, linewidth=2.4, alpha=0.95, zorder=12,
                                      solid_capstyle='round')
                else:
                    wx_a, wy_a, wz_a = zip(*[(wp[0], wp[1], wp[2]) for wp in wall_pts])
                    ax3d.scatter(wx_a, wy_a, wz_a,
                                 color='red', s=22, depthshade=False,
                                 label=f'Wall Contact ({layers}L×{points}P)')

            # ── จุดก้นรู ★ (วาดแยก — ไม่ใช่ dot สีแดง) ─────────────────────
            ax3d.scatter([star_x], [star_y], [star_z],
                         color='#ffea00', s=110, marker='*', depthshade=False,
                         label='Bottom Depth Point', zorder=10)

            text_color = '#ff3333' if has_step_hole else '#ffea00'
            source_tag = ' [STEP]' if has_step_hole else ' [Mesh]'
            ax3d.text(star_x, star_y, star_z,
                      f" ★{source_tag} X={star_x:.2f}, Y={star_y:.2f}\n   Depth={hole.depth:.2f} mm",
                      color=text_color, fontsize=7, zorder=11)

            # ── Probe Warning Annotation ในมุมมอง 3D ─────────────────────────
            # แสดงเมื่อ probe ไม่ผ่านการตรวจสอบ — วาดบน axes ใน 2D transform space
            # เพื่อให้ข้อความอยู่คงที่ไม่หมุนตามโมเดล
            if probe_warn_lines:
                warn_text = "\n".join(probe_warn_lines)
                ax3d.text2D(
                    0.01, 0.01,           # ตำแหน่ง axes fraction (ล่างซ้าย)
                    warn_text,
                    transform=ax3d.transAxes,
                    fontsize=9,
                    color='#ef5350',      # สีแดงชัดเจน
                    fontweight='bold',
                    va='bottom',
                    ha='left',
                    bbox=dict(
                        boxstyle='round,pad=0.4',
                        facecolor='#1a0000',
                        edgecolor='#ef5350',
                        alpha=0.88,
                    ),
                    zorder=20,
                )

            zigzag_tag = f' ↕Zigzag({step_deg}°/layer)' if use_zigzag else ''
            # ── เพิ่ม [⚠ PROBE] tag ใน title ถ้า probe ไม่ผ่าน ──────────────
            probe_tag  = '  ⚠ PROBE' if not probe_ok else ''
            title_str  = (
                f"Customization — Hole {hole.id}  |  R={hole.radius:.1f} mm  "
                f"Depth={hole.depth:.2f} mm  |  {layers}L × {points}P = {layers*points} pts"
                + (' [STEP]' if has_step_hole else ' [Mesh]')
                + zigzag_tag
                + probe_tag
            )
            ax3d.view_init(elev=-135, azim=30)

            # ── Zoom into the selected hole ──────────────────────────────────
            hole_z_mid = (z_start + star_z) / 2.0
            half_zoom  = max(hole.radius * 1.6, abs(star_z - z_start)) * 0.55
            half_zoom  = max(half_zoom, half * 0.05)

            ax3d.set_xlim([hole.x - half_zoom, hole.x + half_zoom])
            ax3d.set_ylim([hole.y - half_zoom, hole.y + half_zoom])
            ax3d.set_zlim([hole_z_mid - half_zoom, hole_z_mid + half_zoom])

        else:
            title_str = "Customization — Select a hole to show probing path"
            ax3d.view_init(elev=-135, azim=30)

            # ── Full-model view when nothing is selected ──────────────────────
            ax3d.set_xlim([cx - half, cx + half])
            ax3d.set_ylim([cy - half, cy + half])
            ax3d.set_zlim([cz - half, cz + half])

        ax3d.set_title(title_str, color='#ef5350' if not probe_ok else 'white',
                       fontsize=11, pad=10)
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
