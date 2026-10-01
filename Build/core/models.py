# ==============================================================================
# core/models.py — โครงสร้างข้อมูล (data classes) ของรูและ segment
# ==============================================================================
# หน้าที่: เก็บโครงสร้างข้อมูลกลางที่ใช้ส่งต่อกันทั่วโปรแกรม
#   - HoleSegment        : เรขาคณิตดิบของรู 1 ช่วง (ก่อน merge เป็นรู counterbore)
#   - HoleSegmentSetting : ค่าตั้งค่าการตรวจสอบต่อ segment เดียว (รูหลายระดับเส้นผ่านศูนย์กลาง)
#   - HoleFeature        : ข้อมูลรูที่ตรวจพบ ใช้แสดงผลฝั่ง UI
#   - StepHole           : รูทรงกระบอกที่สกัดมาจาก B-Rep ของไฟล์ STEP
#   - StepPocket         : ช่องสี่เหลี่ยม (จัตุรัส/ผืนผ้า มุมคมหรือมุมโค้ง) — v04
#                          และช่องทรงแคปซูล/slot (corner_radius == half_v) — v05
#   - rect_wall_contacts(): กระจายจุดสัมผัสผนังของช่องสี่เหลี่ยม — v04
#   - validate_segment_reachability() : ตรวจสอบว่า segment ที่ลึกกว่าจะถูก
#     probe เข้าไปถึงได้จริงหรือไม่ เทียบกับคอขวดของ segment ที่ตื้นกว่า
#
# ตัวแปรสำคัญที่ปรับจูนได้ (ค่าเริ่มต้นการตรวจสอบต่อรู/segment):
#   layers            = จำนวนชั้น (layer) ที่จะตรวจสอบตามความลึกของรู
#   points_per_layer  = จำนวนจุดสัมผัสผนังรูต่อ 1 ชั้น
#   zigzag_inspection = เปิด/ปิดโหมดหมุนมุมโพรบทีละชั้น (ลดจุดบอดจากการสัมผัสซ้ำมุมเดิม)
#   zigzag_degree     = องศาสะสมที่หมุนต่อ 1 ชั้น เมื่อเปิดโหมด zigzag
#   selected_for_inspection (HoleSegmentSetting) = segment นี้ถูกรวมใน
#     probe path / G-code หรือไม่ (ผู้ใช้ปรับได้ผ่าน checkbox ใน sidebar
#     ขวา — ค่าเริ่มต้นคำนวณจาก validate_segment_reachability())
#
# NOTE (v03): hole.segments / sh.segments ถูกเรียงโดย
# core/step_extractor.py :: _order_segments_deepest_first() เสมอ ให้
# index 0 = segment ที่ลึกที่สุด และ index สุดท้าย = segment ที่ตื้นที่สุด
# (ปากรู) — validate_segment_reachability() ด้านล่างถูกปรับให้ตรงกับ
# ลำดับนี้แล้ว
#
# NOTE (v04): เพิ่มรูปทรง "ช่องสี่เหลี่ยม" (StepPocket, shape == 'rect') ที่
# ใช้ร่วมกับ pipeline เดิมทั้งหมด (view → path → G-code → evaluation) ได้
# เพราะสืบทอดจาก StepHole — radius ของ pocket = ครึ่งหนึ่งของด้านแคบ (วงกลม
# ที่ใหญ่ที่สุดที่ใส่ในช่องได้) จึงใช้กับการตรวจ probe fit เดิมได้ตรง ๆ
#
# NOTE (v05): ช่องทรงแคปซูล (slot) = StepPocket ที่ corner_radius == half_v
# ผนังปลายทั้งสองด้านจึงไม่มีช่วงตรง — rect_wall_contacts() วางจุดของผนัง
# ปลายบนส่วนโค้งครึ่งวงกลมแทน (กระจายตามมุม ±RECT_CONTACT_SPAN × 90°)
#
# ตัวแปรที่ปรับจูนได้ (v04):
#   RECT_CONTACT_SPAN = สัดส่วนช่วงความยาวด้านตรงที่วางจุดสัมผัสได้ (0..1)
#                       — กันหัวโพรบไม่ให้ไปโดนผนังข้างเคียงใกล้มุม
# ==============================================================================
import math

import numpy as np

RECT_CONTACT_SPAN = 0.7   # วางจุดภายใน ±70% ของครึ่งความยาวช่วงตรงของแต่ละด้าน — ปรับได้


class HoleSegment:
    """เรขาคณิตดิบของรู 1 ช่วง (segment) ก่อนถูก merge ใน step_extractor.py
    ใช้เป็นข้อมูลอ้างอิงสำหรับ path planning แบบแยกตามขั้น (แต่ละ segment มี
    รัศมีเป็นของตัวเอง ไม่ interpolate ข้ามขั้นไปยัง segment อื่น)"""
    def __init__(self, open_3d, deep_3d, radius_open, radius_deep):
        self.open_3d     = tuple(open_3d)
        self.deep_3d     = tuple(deep_3d)
        self.radius_open = float(radius_open)
        self.radius_deep = float(radius_deep)
        self.depth       = float(np.linalg.norm(np.array(deep_3d) - np.array(open_3d)))

    def radius_at(self, t: float) -> float:
        """รัศมี ณ ตำแหน่ง t (0.0=ปาก segment นี้ .. 1.0=ก้น segment นี้)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)


class HoleSegmentSetting:
    """การตั้งค่าการตรวจสอบ (inspection) ต่อ segment เดียวของรูหลายระดับ
    เส้นผ่านศูนย์กลาง — แสดงเป็น sub-tab ที่กางออกมาจากการ์ดรูหลักใน
    sidebar ขวา (การ์ดรู 1 ใบ = 1 display_id, กดขยายแล้วเห็น segment ย่อย)
    v03: seg_idx=0 ตอนนี้คือ segment ที่ลึกที่สุด (mouth = seg_idx สุดท้าย)"""
    def __init__(self, seg_idx: int, radius_open: float, radius_deep: float, depth: float):
        self.seg_idx      = seg_idx          # ลำดับ segment: 0 = ลึกที่สุด (v03)
        self.radius_open  = radius_open
        self.radius_deep  = radius_deep
        self.depth        = depth

        self.layers             = 3      # จำนวนชั้นตรวจสอบเริ่มต้น — ปรับได้
        self.points_per_layer   = 4      # จำนวนจุดสัมผัสผนังต่อชั้นเริ่มต้น — ปรับได้
        self.zigzag_inspection  = False  # เปิด/ปิดโหมด zigzag เริ่มต้น — ปรับได้
        self.zigzag_degree      = 45.0   # องศาสะสมต่อชั้นเมื่อเปิด zigzag — ปรับได้

        self.selected_for_inspection = True  # segment นี้ถูกรวมใน probe path / G-code หรือไม่
        self.size_warning            = ""    # ข้อความเตือนถ้า probe เข้าไม่ถึง segment นี้ (คอขวด)

        self.is_expanded = False             # UI state: sub-tab กางอยู่หรือไม่


def validate_segment_reachability(segments: list) -> None:
    """ตรวจสอบว่าแต่ละ segment จะถูก probe เข้าไปถึงได้จริงหรือไม่ เทียบกับ
    segment ที่ตื้นกว่าติดกัน"""
    
    # ค่าเผื่อความคลาดเคลื่อน (Tolerance) 1 ไมครอน ป้องกันปัญหา Floating-point precision
    # เวลารอยต่อของ Segment มีขนาดเท่ากันพอดี
    TOLERANCE = 0.001 

    for i in range(len(segments) - 1):
        deep    = segments[i]       # segment นี้กำลังถูกตรวจสอบว่าเข้าถึงได้ไหม
        shallow = segments[i + 1]   # เพื่อนบ้านที่ตื้นกว่า/ใกล้ปากรูกว่า (v03: i+1 ไม่ใช่ i-1)

        shallow_narrow = min(shallow.radius_open, shallow.radius_deep)
        deep_wide      = max(deep.radius_open, deep.radius_deep)

        # เพิ่ม TOLERANCE เข้าไปในการเปรียบเทียบ
        if (deep_wide - shallow_narrow) > TOLERANCE:
            deep.selected_for_inspection = False
            deep.size_warning = (
                f"⚠ Counterbore ด้านบน (Segment {i + 2}) มีขนาดเล็กกว่า — "
                f"probe เข้าไม่ถึง Segment {i + 1} นี้ (auto-unselected)")


class HoleFeature:
    """โครงสร้างข้อมูลสำหรับเก็บคุณลักษณะของรูที่ตรวจพบเพื่อใช้ในฝั่ง UI"""
    def __init__(self, hid, x, y, surface_z, bottom_z, depth, radius):
        self.id = hid
        self.x = x
        self.y = y
        self.surface_z = surface_z
        self.bottom_z = bottom_z
        self.depth = depth
        self.radius = radius
        self.layers = 3
        self.points_per_layer = 4
        self.hole_top_z = surface_z
        self._step_hole = None

        self.selected_for_inspection = False
        self.zigzag_inspection = False
        self.zigzag_degree = 45.0

        self.is_rejected = False
        self.reject_reason = ""
        self.position_unknown = False

        # segments ว่างเปล่า = รูปกติ (segment เดียว) ; มี 2+ = รูหลายระดับเส้นผ่านศูนย์กลาง
        # v03: segments[0] = segment ที่ลึกที่สุด
        self.segments: list = []


class StepHole:
    """โครงสร้างข้อมูลรูทรงกระบอกที่สกัดมาจาก B-Rep ของไฟล์ STEP
    v03: self.segments ถูกเรียงแบบ "ลึกสุดก่อน" เสมอโดย
    core/step_extractor.py :: _order_segments_deepest_first()"""
    def __init__(self, open_3d, deep_3d, radius_open, radius_deep, axis_vec, segments=None):
        self.open_3d     = tuple(open_3d)
        self.deep_3d     = tuple(deep_3d)
        self.radius_open = float(radius_open)
        self.radius_deep = float(radius_deep)
        self.radius      = float(radius_open)   # สำหรับใช้งานร่วมกับระบบเดิม
        self.axis        = axis_vec
        self.depth       = float(np.linalg.norm(np.array(deep_3d) - np.array(open_3d)))

        self.display_x = None
        self.display_y = None
        self.depth_top = None
        self.depth_bot = None

        self.segments = segments if segments is not None else [
            HoleSegment(self.open_3d, self.deep_3d, self.radius_open, self.radius_deep)
        ]

    shape = 'circle'

    def radius_at(self, t: float) -> float:
        """รัศมี ณ ตำแหน่งความลึก t สัดส่วนระหว่าง 0.0 (ปากรู) ถึง 1.0 (ก้นรู)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)

    @property
    def outer_radius(self) -> float:
        """รัศมีของวงกลมที่ครอบรูทั้งรู (ใช้กำหนดขอบเขตแสดงผล/hit-test)"""
        radii = [self.radius_open, self.radius_deep]
        for seg in self.segments:
            radii += [seg.radius_open, seg.radius_deep]
        return max(radii)

    def size_text(self) -> str:
        return f"⌀{self.radius_open * 2:.2f}"

    def outlines_3d(self, steps: int = 48) -> list:
        """เส้นขอบสำหรับวาดบนมุมมอง 2D: วงกลม 1 วงต่อ 1 ขนาดเส้นผ่านศูนย์กลาง
        (รู counterbore/เรียว จึงเห็นหลายวงซ้อนกัน) วาดที่ระนาบปากรู"""
        o = np.array(self.open_3d, dtype=float)
        axis = np.array(self.deep_3d, dtype=float) - o
        axis /= max(np.linalg.norm(axis), 1e-12)
        ref = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        u = np.cross(axis, ref); u /= np.linalg.norm(u)
        v = np.cross(axis, u)

        radii = {round(r, 3) for seg in self.segments
                 for r in (seg.radius_open, seg.radius_deep) if r > 1e-3}
        ang = np.linspace(0.0, 2 * np.pi, steps + 1)
        return [o + r * (np.outer(np.cos(ang), u) + np.outer(np.sin(ang), v))
                for r in sorted(radii, reverse=True)]


class StepPocket(StepHole):
    """ช่องสี่เหลี่ยม (pocket) ที่สกัดจาก B-Rep — จัตุรัสหรือผืนผ้า มุมคม
    (corner_radius == 0) หรือมุมโค้ง ผนังตั้งฉากกับระนาบปากช่อง (prismatic)

    half_u / half_v : ครึ่งความยาวด้านตามแกน u_dir / v (half_u >= half_v เสมอ)
    u_dir           : เวกเตอร์หน่วยตามด้านยาว ตั้งฉากกับ axis
    radius          : = half_v (ครึ่งด้านแคบ) ให้ระบบเดิม (probe fit, hole list)
                      ใช้ได้ตรง ๆ"""
    shape = 'rect'

    def __init__(self, open_3d, deep_3d, axis_vec, u_dir, half_u, half_v, corner_radius):
        r_in = min(half_u, half_v)
        super().__init__(open_3d, deep_3d, r_in, r_in, axis_vec)
        self.u_dir         = tuple(float(c) for c in u_dir)
        self.half_u        = float(half_u)
        self.half_v        = float(half_v)
        self.corner_radius = float(corner_radius)

    @property
    def outer_radius(self) -> float:
        if self.is_slot:
            return self.half_u
        return math.hypot(self.half_u, self.half_v)

    @property
    def is_slot(self) -> bool:
        """ช่องทรงแคปซูล: รัศมีมุมเท่าครึ่งความกว้าง (ปลายเป็นครึ่งวงกลม)"""
        return self.corner_radius >= self.half_v - 1e-3

    @property
    def kind_text(self) -> str:
        if self.is_slot:
            return "Slot (capsule)"
        return "Square" if abs(self.half_u - self.half_v) < 1e-3 else "Rectangle"

    def outline_3d(self, arc_steps: int = 6) -> np.ndarray:
        """จุดขอบปากช่อง (3D, วนปิด) สำหรับวาดเส้นขอบ — มุมโค้งแบ่ง arc_steps ช่วง"""
        o = np.array(self.open_3d, dtype=float)
        axis = np.array(self.deep_3d, dtype=float) - o
        axis /= max(np.linalg.norm(axis), 1e-12)
        u = np.array(self.u_dir, dtype=float)
        u = u - float(np.dot(u, axis)) * axis
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)

        r = self.corner_radius
        cu, cv = self.half_u - r, self.half_v - r
        steps = arc_steps if r > 1e-6 else 0
        pts = []
        for k, (su, sv) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
            a0 = k * np.pi / 2
            for a in np.linspace(a0, a0 + np.pi / 2, steps + 1):
                pts.append(o + (su * cu + r * np.cos(a)) * u + (sv * cv + r * np.sin(a)) * v)
        pts.append(pts[0])
        return np.array(pts)

    def outlines_3d(self, steps: int = 48) -> list:
        return [self.outline_3d()]

    def size_text(self) -> str:
        txt = f"{self.half_u * 2:.2f}×{self.half_v * 2:.2f}"
        if self.is_slot:
            return "slot " + txt
        return txt + (f" R{self.corner_radius:.1f}" if self.corner_radius > 1e-6 else "")


def rect_wall_contacts(half_u: float, half_v: float, corner_radius: float,
                       n_points: int, phase: float = 0.0) -> list:
    """กระจายจุดสัมผัสผนัง n_points จุดรอบช่องสี่เหลี่ยม (พิกัดในระนาบ u/v
    เทียบกับจุดศูนย์กลางช่อง)

    ทุกด้านได้อย่างน้อย 1 จุด จุดที่เหลือแจกเป็นคู่ (ด้านตรงข้ามกันได้เท่ากัน)
    ตามสัดส่วนความยาวด้าน วางจุดเฉพาะบน "ช่วงตรง" ของด้าน (ไม่ลงบนมุมโค้ง)
    และอยู่ภายใน ±RECT_CONTACT_SPAN ของช่วงนั้น เพื่อไม่ให้หัวโพรบไปโดนผนัง
    ข้างเคียงใกล้มุม

    phase (0..1) : เลื่อนตำแหน่งจุดตามแนวด้าน = สัดส่วนของระยะห่างระหว่างจุด
                   (ใช้แทน "การหมุนมุม" ของโหมด zigzag ในรูกลม)

    Returns list ของ (start_u, start_v, normal_u, normal_v, wall_dist):
      start  = จุดเริ่มเดิน probe (อยู่บนเส้นกึ่งกลางช่อง จึงอยู่ในช่องเสมอ)
      normal = ทิศพุ่งเข้าหาผนัง, wall_dist = ระยะจาก start ถึงผนัง
    เรียงทวนเข็มนาฬิกาเริ่มที่ผนัง +u (เหมือนมุม 0° ของรูกลม)"""
    n_points = max(4, int(n_points))
    extra_pairs, odd = divmod(n_points - 4, 2)

    # ด้านขนาน v (ผนัง ±u) ยาว 2*half_v ; ด้านขนาน u (ผนัง ±v) ยาว 2*half_u
    len_u_walls, len_v_walls = 2.0 * half_v, 2.0 * half_u
    share = extra_pairs * len_u_walls / (len_u_walls + len_v_walls)
    pairs_u = int(math.floor(share + 0.5 - 1e-9))   # ปัดครึ่งลง: เสมอกันให้ด้านยาว (ผนัง ±v)
    pairs_v = extra_pairs - pairs_u
    k_u = 1 + pairs_u   # จุดต่อผนัง +u / -u
    k_v = 1 + pairs_v   # จุดต่อผนัง +v / -v

    straight_u = max(0.0, half_u - corner_radius)   # ครึ่งช่วงตรงของผนัง ±v
    straight_v = max(0.0, half_v - corner_radius)   # ครึ่งช่วงตรงของผนัง ±u

    def offsets(k, straight_half):
        span = straight_half * RECT_CONTACT_SPAN
        return [-span + 2.0 * span * (((i + 0.5 + phase) % k) / k) for i in range(k)]

    # (normal_u, normal_v, จำนวนจุด, ครึ่งช่วงตรง, ระยะถึงผนัง)
    walls = [(1.0, 0.0, k_u, straight_v, half_u),
             (0.0, 1.0, k_v + odd, straight_u, half_v),   # จุดคี่ (ถ้ามี) ไปที่ผนังยาว
             (-1.0, 0.0, k_u, straight_v, half_u),
             (0.0, -1.0, k_v, straight_u, half_v)]

    contacts = []
    for nu, nv, k, straight_half, dist in walls:
        if straight_half < 1e-6 and corner_radius > 1e-6:
            # v05: ผนังนี้ไม่มีช่วงตรง (ปลายครึ่งวงกลมของ slot) — กระจายจุดบน
            # ส่วนโค้งตามมุมแทน โพรบเริ่มที่จุดศูนย์กลางส่วนโค้ง เดินออกตามรัศมี
            off = dist - corner_radius
            for f in offsets(k, 1.0):
                phi = f * math.pi / 2
                c, s_ = math.cos(phi), math.sin(phi)
                contacts.append((nu * off, nv * off,
                                 c * nu - s_ * nv, c * nv + s_ * nu, corner_radius))
            continue
        for s in offsets(k, straight_half):
            # จุดเริ่มเลื่อนตามแนวผนัง (ตั้งฉากกับ normal) — ทิศทวนเข็มฯ
            su, sv = -nv * s, nu * s
            contacts.append((su, sv, nu, nv, dist))
    return contacts