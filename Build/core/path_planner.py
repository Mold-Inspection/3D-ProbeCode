# ==============================================================================
# core/path_planner.py — คำนวณเส้นทางโพรบ (probe path) แบบทีละชั้น
# ==============================================================================
# หน้าที่: จากข้อมูลรู (open_3d → deep_3d) คำนวณตำแหน่งจุดสัมผัสผนังรูในแต่ละ
# "ชั้น" (layer) ตามความลึก เพื่อนำไปวาดเส้นทางโพรบและจุดวัด
#   - get_probe_path_layers()       ใช้กับรูปกติ (segment เดียว หรือรูเรียว/กรวยต่อเนื่อง)
#   - get_probe_path_layers_multi() ใช้กับรูหลายระดับเส้นผ่านศูนย์กลาง (counterbore)
#     คำนวณแยกทีละ segment ไม่ interpolate รัศมีข้ามขั้น
#
# ตัวแปรสำคัญที่ปรับจูนได้ (ส่งเข้ามาจาก UI ต่อรู/segment ไม่ใช่ค่าคงที่ในไฟล์นี้):
#   n_layers / cfg.layers            = จำนวนชั้นตรวจสอบ
#   zigzag_inspection / cfg.zigzag_inspection = เปิด/ปิดการหมุนมุมโพรบต่อชั้น
#   zigzag_degree / cfg.zigzag_degree = องศาสะสมที่หมุนต่อ 1 ชั้น
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FEATURE: ช่องสี่เหลี่ยม (StepPocket) — get_probe_path_layers() เติม key
#   'contacts_display' ให้แต่ละ layer: list ของ (start_xyz, wall_xyz) ใน
#   พิกัดจอ (project แล้ว) คำนวณจาก core/gcode_generator.py::
#   _layer_contacts() ตัวเดียวกับ G-code — จุดที่เห็นใน Customization tab จึง
#   ตรงกับจุดที่เครื่องจะโพรบจริง รูกลมไม่มี key นี้ (พฤติกรรมเดิม)
# CHANGE LOG (v01 -> v02):
#   FIX: get_probe_path_layers_multi() now SKIPS any segment whose
#   cfg.selected_for_inspection is False (see core/models.py
#   HoleSegmentSetting + validate_segment_reachability()) — a segment
#   the UI has marked unreachable/deselected no longer produces any
#   layer points, so it's excluded from both the on-screen preview
#   (Customization tab / Path Mapper) and — since G-code export walks
#   the same per-segment cfg list — from the exported program too.
#   layer_idx numbering only counts included (selected) layers, so
#   numbering stays contiguous for whatever actually gets probed.
import numpy as np


class PathPlanner:
    """คำนวณเส้นทางโพรบสำหรับตรวจสอบรูทีละชั้น (layer-by-layer)"""

    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str,
                               screen_rot: int = 0,
                               zigzag_inspection: bool = False,
                               zigzag_degree: float = 45.0,
                               points_per_layer: int = 4) -> list:
        """คืนรายการ dict ของแต่ละ layer สำหรับวาดเส้นทางโพรบ

        โหมด Zigzag: layer 0 → offset มุม 0°, layer N → offset = N × zigzag_degree

        หมายเหตุ: ฟังก์ชันนี้มองรูเป็นความเรียวต่อเนื่องเดียว (open_3d → deep_3d,
        ใช้ hole.radius_at) เหมาะกับรูปกติและรูเรียว/กรวยแท้ ถ้ารูมีขั้นเส้นผ่าน
        ศูนย์กลางจริง ให้ใช้ get_probe_path_layers_multi() แทน
        """
        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)
        # ช่องสี่เหลี่ยม / ร่องเปิด / รูที่มีร่องวิ่งเข้ามา: จุดไม่ได้เรียงเป็นวงกลมธรรมดา —
        # คำนวณด้วย _layer_contacts() ตัวเดียวกับ G-code ให้ preview ตรงกับเครื่องจริง
        is_rect = (getattr(hole, 'shape', 'circle') in ('rect', 'channel')
                   or bool(getattr(hole, 'blocked_dirs', None)))

        layers = []
        for layer_idx, t in enumerate(t_vals):
            pt              = o + t * (d - o)
            dx, dy, depth   = projector.project_point_to_view(
                *pt, view_name, screen_rot)
            r_layer         = hole.radius_at(t)
            angle_offset    = (np.radians(layer_idx * zigzag_degree)
                               if zigzag_inspection else 0.0)

            layer = {
                'z_display':    depth,
                'x_display':    dx,
                'y_display':    dy,
                'radius':       r_layer,
                'angle_offset': angle_offset,
                'layer_idx':    layer_idx,
            }
            if is_rect:
                layer['contacts_display'] = self._rect_contacts_display(
                    hole, pt, angle_offset, points_per_layer, projector,
                    view_name, screen_rot, t=t, radius=r_layer)
            layers.append(layer)
        return layers

    @staticmethod
    def _rect_contacts_display(hole, center, angle_offset, n_points,
                               projector, view_name, screen_rot, t=0.5, radius=None) -> list:
        """v03: จุดเริ่ม/จุดสัมผัสผนังของ 1 layer ในพิกัดจอ — ช่องสี่เหลี่ยม,
        ร่องเปิด (channel) และรูกลมที่มีมุมห้ามโพรบ (ปากร่องที่วิ่งเข้ามา)"""
        from core.gcode_generator import _layer_contacts, _orthonormal_basis, channel_layer_fields

        axis, u, v = _orthonormal_basis(np.array(hole.deep_3d) - np.array(hole.open_3d))
        shape = getattr(hole, 'shape', 'circle')
        if shape in ('rect', 'channel'):
            u = np.array(hole.u_dir, dtype=float)
            u = u - float(np.dot(u, axis)) * axis
            u /= np.linalg.norm(u)
            v = np.cross(axis, u)
        lyr = dict(center=np.array(center), u=u, v=v,
                   angle_offset=angle_offset, points_n=n_points,
                   radius=radius if radius is not None else hole.radius_at(t),
                   blocked=getattr(hole, 'blocked_dirs', None))
        if shape == 'rect':
            lyr.update(shape='rect', half_u=hole.half_u, half_v=hole.half_v,
                       corner_radius=hole.corner_radius)
        elif shape == 'channel':
            lyr.update(channel_layer_fields(hole, t))

        def proj(p):
            return projector.project_point_to_view(*p, view_name, screen_rot)

        return [(proj(start), proj(start + dist * normal))
                for start, normal, dist in _layer_contacts(lyr)]

    # ------------------------------------------------------------------
    def get_probe_path_layers_multi(self, hole, segment_settings: list,
                                     projector, view_name: str,
                                     screen_rot: int = 0) -> list:
        """เวอร์ชันแยกตาม segment ของ get_probe_path_layers() สำหรับรูหลายระดับ
        เส้นผ่านศูนย์กลาง (แบบ counterbore)

        Parameters
        ----------
        hole              : StepHole ที่มี .segments เป็นเรขาคณิตดิบ (เรียงจากปากรูก่อน)
        segment_settings  : list ของ core.models.HoleSegmentSetting ความยาว/ลำดับ
                            ตรงกับ hole.segments — เก็บค่า layers/points_per_layer/
                            zigzag/selected_for_inspection ต่อ segment
        projector, view_name, screen_rot : เหมือนกับ get_probe_path_layers()

        คืนค่า: list แบบเรียงราบ (ปากรู → ก้นรู) เฉพาะ segment ที่
        cfg.selected_for_inspection == True เท่านั้น แต่ละอันมี key เหมือน
        get_probe_path_layers() บวกเพิ่ม:
          - 'seg_idx'          : segment ที่ layer นี้อยู่
          - 'seg_local_idx'    : ลำดับ layer ภายใน segment นั้น (มุม zigzag จะเริ่ม
                                  นับ 0° ใหม่ทุก segment)
          - 'points_per_layer' : จำนวนจุดของ segment นั้น
        รัศมี interpolate เฉพาะภายใน radius_open/radius_deep ของ segment ตัวเอง
        เท่านั้น ไม่ข้ามขั้นไปยัง segment ถัดไป
        """
        if len(segment_settings) != len(hole.segments):
            raise ValueError(
                f"segment_settings length ({len(segment_settings)}) must match "
                f"hole.segments length ({len(hole.segments)})")

        layers = []
        global_idx = 0

        for seg_idx, (seg, cfg) in enumerate(zip(hole.segments, segment_settings)):
            if not getattr(cfg, 'selected_for_inspection', True):
                continue   # segment ถูกเลือกออก (unreachable/manual uncheck) — ข้ามทั้ง segment

            o = np.array(seg.open_3d)
            d = np.array(seg.deep_3d)
            t_vals = np.linspace(0.0, 1.0, cfg.layers + 2)[1:-1]

            for seg_local_idx, t in enumerate(t_vals):
                pt            = o + t * (d - o)
                dx, dy, depth = projector.project_point_to_view(
                    *pt, view_name, screen_rot)
                r_layer       = seg.radius_at(t)
                angle_offset  = (np.radians(seg_local_idx * cfg.zigzag_degree)
                                 if cfg.zigzag_inspection else 0.0)

                layer = {
                    'z_display':        depth,
                    'x_display':        dx,
                    'y_display':        dy,
                    'radius':           r_layer,
                    'angle_offset':     angle_offset,
                    'layer_idx':        global_idx,
                    'seg_idx':          seg_idx,
                    'seg_local_idx':    seg_local_idx,
                    'points_per_layer': cfg.points_per_layer,
                }
                if getattr(hole, 'blocked_dirs', None):   # รูที่มีร่องวิ่งเข้ามา
                    layer['contacts_display'] = self._rect_contacts_display(
                        hole, pt, angle_offset, cfg.points_per_layer, projector,
                        view_name, screen_rot, t=t, radius=r_layer)
                layers.append(layer)
                global_idx += 1

        return layers