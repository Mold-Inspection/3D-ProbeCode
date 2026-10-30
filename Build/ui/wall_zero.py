# ==============================================================================
# ui/wall_zero.py — หา X0 Y0 = กึ่งกลางชิ้นงาน (+ Z0 = ผิวบน) ด้วยการแตะผนังด้านนอก 4 ด้าน
# ==============================================================================
# VERSION: 10
# CHANGE LOG (v09 -> v10):
#   ถอยออกหลังแตะแต่ละผนัง (ก่อนยก Z) ตั้งได้: CentreSettings.backoff (เดิมค่าคงที่ _BACKOFF = 2.0)
# CHANGE LOG (v08 -> v09):
#   repeatability: ผนังที่ขยับไปทางเดียวกับที่โพรบดันทุกครั้ง (drift > _REP_TOL) = ชิ้นงานเลื่อนเมื่อถูกดัน
#   (ไม่ได้ยึด / ฐานไม่เรียบ) แจ้งแยกจาก 'ไม่ซ้ำ' ทั่วไป — เก็บที่ rep[wall]['drift'] / ['slides']
# CHANGE LOG (v07 -> v08):
#   zero_mode: ขั้นสุดท้ายตั้ง X0 Y0 ที่จุด Work zero ที่เลือก (กึ่งกลาง หรือมุมของชิ้นงาน) — มุมคิดจาก
#   กึ่งกลางที่วัดได้ ± ครึ่งขนาด (ขนาดเวอร์เนียร์ถ้ากรอก ไม่งั้นขนาดที่วัดได้)
#   keep_zero: รันซ้ำโดยใช้ Z0 เดิม (ลูกบอลค้างอยู่เหนือกึ่งกลางที่ Z+lift จากรอบก่อน) — ตั้ง X0 Y0
#   ชั่วคราวที่ตำแหน่งปัจจุบันอย่างเดียว ไม่ต้อง jog ลงแตะผิวใหม่ (ใช้ยืนยัน Effective Tip ที่เพิ่งเปลี่ยน)
# CHANGE LOG (v06 -> v07):
#   Repeatability ในปุ่มเดียวกัน: ต่อผนัง หลังแตะหาครั้งแรก (feed ค้นหา) ถอย rep_back แล้วแตะซ้ำ
#   repeats ครั้งที่ rep_feed (feed ที่ใช้วัดจริง = แตะช้าของ double touch) → ต่อผนัง: ช่วง, SD,
#   ผลต่างแตะเร็ว−แตะช้า, ผ่าน/ไม่ผ่าน (_REP_TOL) — กึ่งกลางและ Effective Tip ⌀ ใช้ค่าเฉลี่ยแตะซ้ำ
#   บันทึกทุกจุดเป็น Find_centre_<เวลา>.csv ในโฟลเดอร์ log (ใช้ในบท 4.6 ได้)
# CHANGE LOG (v05 -> v06):
#   ขนาดจริงจากเวอร์เนียร์ (ไม่บังคับ) → คำนวณ Effective Tip ⌀ แยกแกนจากการแตะขอบนอก:
#   D_eff = span − W_จริง (span = ระยะระหว่างศูนย์กลางลูกบอลสองฝั่ง) เก็บที่ self.deff
#   (ถือว่า steps/mm ถูกแล้ว — สเกลแกนคลาด 0.1% บนชิ้น 200 มม. = D_eff คลาด 0.2 มม.)
# CHANGE LOG (v04 -> v05):
#   ลำดับใหม่ตามที่ผู้ใช้กำหนด: (1) แตะผนัง 4 ด้าน แล้วประเมินขนาด X/Y เทียบแบบ (2) กลับจุดเริ่ม
#   โดย Z ยังยกอยู่ (3) ไปกึ่งกลางที่วัดได้จริง (G53 — พิกัดเครื่อง) (4) ตั้ง X0 Y0 ตรงนั้น (Z0 คง
#   เป็นผิวบนจากขั้นแรก) (5) สรุปขนาด, ผลต่างจากแบบ และค่า steps/mm ที่แนะนำถ้าคลาดเกิน
#   0.2 มม./0.1% ($$ อ่านในขั้นแรก) — ไม่ลด Z ลงแตะผิวตอนจบแล้ว (ตัด lower_at_end)
# CHANGE LOG (v03 -> v04):
#   FIX (บนเครื่องจริง): เดิมตัดสินว่าขั้นจบเมื่อเห็น runStatus = Idle — แต่ OpenBuilds รอให้เครื่อง
#   Idle ก่อนส่ง G38.2 จึงเห็น Idle ก่อนเริ่มแตะ → ขึ้น "no wall" แล้วสั่ง Stop ขณะ G38.2 เพิ่งเริ่ม
#   (ALARM:3) ตอนนี้ต่อท้ายทุกขั้นด้วย "G4 P0" แล้วรอ ok ของบรรทัดนั้น (GRBL ตอบหลังการเคลื่อนที่
#   ก่อนหน้าเสร็จจริง) ค่อยตรวจจำนวนจุดแตะและไปขั้นต่อไป
# CHANGE LOG (v02 -> v03):
#   เปลี่ยนวิธีเป็น "เริ่มจากกลางชิ้นงาน" (แบบที่ทดสอบกับ plate_with_holes บนเครื่องจริง):
#   ผู้ใช้ jog ลูกบอลไปกลางชิ้นงาน (ประมาณ) ให้ก้นลูกบอลแตะผิวบนพอดี แล้วกด Find centre
#     1. ตั้ง X0 Y0 Z0 ชั่วคราวที่จุดนั้น (Z0 = ผิวบน — ก้นลูกบอลแตะผิว) แล้วยก Z ก่อนเสมอ
#     2. แกน X: ไปนอกผนังซ้าย (ครึ่งความกว้าง + gap) → ลง → แตะเข้าหาชิ้นงาน → ยก →
#        ไปนอกผนังขวา → ลง → แตะ → ยก → ตั้ง X0 = กึ่งกลางสองจุดที่แตะ (G10 L2) → ไป X0
#     3. แกน Y: แบบเดียวกัน (ผนังหน้า/หลัง) → ตั้ง Y0
#     4. ไปที่ X0 Y0 (ความสูงยก) แล้วลดลงช้า ๆ ให้ก้นลูกบอลแตะผิว (Z0) — เลือกปิดได้
#   ขนาดลูกบอลและระยะโก่งก่อนทริกหักล้างกันเองที่กึ่งกลาง จึงไม่ต้อง calibrate ก่อน
#   ทุกการลด Z เกิดนอกขอบชิ้นงาน gap มม. (ค่าเริ่มต้น 30) — กันกรณีวางไม่ตรงกลาง /
#   ขนาดชิ้นงานหรือ steps/mm คลาด (หัวโพรบส่วนใหญ่ไม่ทริกแนว Z: ลงบนผิว = ชน)
# CHANGE LOG (v01 -> v02): far-side gap (แบบเริ่มจากนอกผนัง — แทนที่แล้วใน v03)
#
# ความปลอดภัย: ทุกขั้นรอเครื่อง Idle ก่อนส่งขั้นต่อไป, ALARM / แตะไม่โดน / หมดเวลา →
# ส่ง Stop และหยุด (zero ที่ตั้งไปแล้วในขั้นก่อนหน้ายังอยู่ — แจ้งผู้ใช้), งานนี้ไม่ถูก
# บันทึกเป็นไฟล์ log งานวัด (OpenBuildsLogger.suppress_logs)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _TIMEOUT_S   = เวลาสูงสุดทั้งงาน (วินาที)
#   _SEARCH_PAD  = ระยะค้นหา = gap + ค่านี้ (เผื่อวางไม่ตรงกลาง/ขนาดคลาด)
#   _BACKOFF     = ค่าเริ่มต้นของการถอยออกหลังแตะ (มม.) — ตั้งได้ที่ Hardware Setting → Work Zero
# ==============================================================================
import re
import time

_PRB = re.compile(r"\[PRB:\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*:\s*(\d)\s*\]")
_TIMEOUT_S = 600.0
_SEARCH_PAD = 20.0
_BACKOFF = 2.0
# v04: ต่อท้ายทุกขั้น — GRBL ตอบ ok ของ dwell หลังการเคลื่อนที่ก่อนหน้าเสร็จทั้งหมด (planner sync)
_END_MARK = "G4 P0"
_SETTING = re.compile(r"\$(\d+)=([-\d.]+)")
# ขนาดที่วัดได้คลาดจากแบบเกินนี้ → แนะนำให้ตรวจ steps/mm (มม. หรือสัดส่วน ใช้ค่าที่มากกว่า)
_SIZE_TOL_MM, _SIZE_TOL_FRAC = 0.2, 0.001
_REP_TOL = 0.02   # v07: ช่วง (สูงสุด − ต่ำสุด) ของการแตะซ้ำต่อผนังที่ถือว่าผ่าน (มม.) — ปรับได้
_WALLS = (("X", -1, "left"), ("X", +1, "right"), ("Y", -1, "front"), ("Y", +1, "back"))
# v08: ตำแหน่งจุด zero เทียบกึ่งกลางชิ้นงาน เป็นสัดส่วนของ (กว้าง X, ยาว Y) — บน = Y+ เหมือนบนจอ
_ZERO_FROM_CENTRE = {"center": (0.0, 0.0), "upper_left": (-0.5, 0.5), "upper_right": (0.5, 0.5),
                     "lower_left": (-0.5, -0.5), "lower_right": (0.5, -0.5)}
_ZERO_TEXT = {"center": "the measured centre", "upper_left": "the upper-left corner",
              "upper_right": "the upper-right corner", "lower_left": "the lower-left corner",
              "lower_right": "the lower-right corner"}
_COORD_P = {"G54": 1, "G55": 2, "G56": 3, "G57": 4, "G58": 5, "G59": 6}


class CentreSettings:
    def __init__(self, width: float, length: float, tip_d: float, gap: float = 30.0, lift: float = 5.0,
                 depth: float = 4.0, feed: float = 100.0, true_x: float = None, true_y: float = None,
                 repeats: int = 0, rep_feed: float = 20.0, rep_back: float = 1.0,
                 zero_mode: str = "center", keep_zero: bool = False, backoff: float = _BACKOFF):
        # tip_d = ⌀ ลูกบอลที่ใช้หักออกจากระยะที่วัด (Effective Tip ⌀ ถ้า calibrate แล้ว)
        self.width, self.length, self.tip_d = float(width), float(length), float(tip_d)
        # v06: ขนาดจริงที่วัดด้วยเวอร์เนียร์ (None = ไม่ calibrate) — ใช้หา Effective Tip ⌀
        self.true = {"X": None if true_x is None else float(true_x),
                     "Y": None if true_y is None else float(true_y)}
        self.gap, self.lift, self.depth, self.feed = float(gap), float(lift), float(depth), float(feed)
        # v07: แตะซ้ำต่อผนัง (0 = ไม่ตรวจ repeatability) ที่ feed / ระยะถอย ของการแตะช้า
        self.repeats, self.rep_feed, self.rep_back = max(0, int(repeats)), float(rep_feed), float(rep_back)
        # v08: จุดที่จะตั้ง X0 Y0 ตอนจบ (core/work_zero.py) และรันซ้ำโดยใช้ Z0 เดิม
        self.zero_mode = zero_mode if zero_mode in _ZERO_FROM_CENTRE else "center"
        self.keep_zero = bool(keep_zero)
        self.backoff = float(backoff)   # v10: ถอยออกหลังแตะผนัง ก่อนยก Z

    @property
    def per_wall(self) -> int:
        """v07: จำนวนจุดแตะต่อผนัง (ค้นหา 1 + แตะซ้ำ)"""
        return 1 + self.repeats

    @property
    def search(self) -> float:
        return self.gap + _SEARCH_PAD

    def outside(self, axis: str) -> float:
        """ระยะจากจุดเริ่มถึงจุดลด Z นอกผนัง (ครึ่งขนาด + gap)"""
        return (self.width if axis == "X" else self.length) / 2.0 + self.gap

    def validate(self) -> str:
        if self.width <= 0 or self.length <= 0:
            return "ขนาดชิ้นงานต้องมากกว่า 0"
        if self.gap < 10.0:
            return "Gap ควรอย่างน้อย 10 มม. (เผื่อวางไม่ตรงกลาง)"
        if self.lift < 2.0 or self.depth <= 0 or self.feed <= 0:
            return "Z lift ≥ 2 มม., Probe depth และ Feed ต้องมากกว่า 0"
        if not 0 < self.backoff <= self.gap:
            return "Back-off ต้องมากกว่า 0 และไม่เกิน Gap"
        if self.repeats and (self.rep_feed <= 0 or self.rep_back <= 0):
            return "Repeat feed / back-off ต้องมากกว่า 0"
        return ""


def side_gcode(axis: str, sign: int, s: CentreSettings) -> str:
    """แตะผนังด้าน sign (−1 = ซ้าย/หน้า, +1 = ขวา/หลัง) — เริ่มและจบที่ความสูง Z+lift"""
    a = axis
    return "\n".join([
        "G90",
        f"G0 Z{s.lift:.3f}",
        f"G0 {a}{sign * s.outside(a):.3f}",            # ไปนอกผนัง (ที่ความสูงยก)
        f"G0 Z{-s.depth:.3f}",                          # ลดลงข้างผนัง
        f"G91 G38.2 {a}{-sign * s.search:.3f} F{s.feed:.0f}",   # แตะเข้าหาชิ้นงาน
        *[ln for _ in range(s.repeats) for ln in (                # v07: แตะซ้ำที่ feed วัดจริง
            f"G0 {a}{sign * s.rep_back:.3f}",
            f"G38.2 {a}{-sign * (s.rep_back + 2.0):.3f} F{s.rep_feed:.0f}")],
        f"G0 {a}{sign * s.backoff:.3f}",
        "G90",
        f"G0 Z{s.lift:.3f}",
    ])


class CentreRun:
    """หา X0 Y0 (กึ่งกลาง) + Z0 (ผิวบน) — เรียก start() แล้วรอ on_done(text, ok)"""

    def __init__(self, app, logger, settings: CentreSettings, on_status, on_done):
        self.app, self.logger, self.s = app, logger, settings
        self.on_status, self.on_done = on_status, on_done
        self.active = False
        self.coord = "G54"
        self.prb = []
        self.result = {}
        self.offset = {}
        self._steps = []
        self._i = -1
        self._need = 0
        self._sent_at = 0.0
        self._deadline = 0.0

    # ------------------------------------------------------------------
    def start(self):
        s = self.s
        p = lambda: _COORD_P.get(self.coord, 1)
        self._steps = [
            # 1) zero ชั่วคราวที่จุดเริ่ม (Z0 = ผิวบน) + อ่าน steps/mm ปัจจุบัน แล้วยกก่อนเสมอ
            ("Read $$, set zero at the start point, lift",
             lambda: f"$$\nG10 L20 P{p()} X0 Y0 Z0\nG90\nG0 Z{s.lift:.3f}", 0) if not s.keep_zero else
            # v08: รันซ้ำ — Z0 เดิม, X0 Y0 ชั่วคราวที่ตำแหน่งปัจจุบัน (เหนือกึ่งกลางจากรอบก่อน)
            ("Read $$, keep Z0, temporary X0 Y0 here, lift",
             lambda: f"$$\nG10 L20 P{p()} X0 Y0\nG90\nG0 Z{s.lift:.3f}", 0),
            ("X: left wall", lambda: side_gcode("X", -1, s), s.per_wall),
            ("X: right wall", lambda: side_gcode("X", +1, s), s.per_wall),
            # แตะผนังหน้า/หลังที่แนว X กึ่งกลางที่วัดได้ (พิกัดเครื่อง — ไม่ขึ้นกับ offset)
            ("Y: front wall", lambda: f"G90\nG0 Z{s.lift:.3f}\nG53 G0 X{self._mid('X'):.3f}\n"
                                      + side_gcode("Y", -1, s), s.per_wall),
            ("Y: back wall", lambda: side_gcode("Y", +1, s), s.per_wall),
            # 2) กลับจุดเริ่ม (Z ยังยกอยู่) — 3) ไปกึ่งกลางจริง — 4) ตั้ง X0 Y0 ตรงนั้น (Z0 คงเดิม)
            ("Back to the start point (Z lifted)", lambda: f"G90\nG0 Z{s.lift:.3f}\nG0 X0 Y0\nG4 P1", 0),
            ("Move to the measured centre",
             lambda: f"G53 G0 X{self._mid('X'):.3f} Y{self._mid('Y'):.3f}\nG4 P1", 0),
            ("Set X0 Y0 at the work zero", lambda: "G10 L20 P{} X{:.4f} Y{:.4f}".format(p(), *self._zero_xy()), 0),
        ]
        self.active, self.prb, self.result, self._i = True, [], {}, -1
        self.deff = {}   # v06
        self.steps_mm = {}
        self.rep = {}    # v07
        timeout = _TIMEOUT_S + 60.0 * s.repeats   # แตะซ้ำที่ feed ช้าใช้เวลาเพิ่ม
        self._deadline = time.monotonic() + timeout
        self.logger.on_event.append(self._on_event)
        self.logger.suppress_logs(timeout + 30)
        self._next()
        self.app.root.after(500, self._watchdog)

    def stop(self):
        if self.active:
            try:
                self.logger.stop_machine()
            finally:
                self._end("Stopped — the machine was halted." + self._done_note(), ok=False)

    # ------------------------------------------------------------------
    def _wall_touches(self, w: int) -> list:
        """v07: จุดแตะทั้งหมดของผนังลำดับ w (0..3 ตาม _WALLS) — [0] = แตะค้นหา, ที่เหลือ = แตะซ้ำ"""
        k = self.s.per_wall
        return self.prb[w * k:(w + 1) * k]

    def _wall_value(self, w: int, i: int) -> float:
        """v07: ตำแหน่งผนัง (แกน i, พิกัดเครื่อง) = ค่าเฉลี่ยแตะซ้ำ ถ้ามี ไม่งั้นแตะค้นหา"""
        pts = self._wall_touches(w)
        rep = pts[1:] or pts[:1]
        return sum(p[i] for p in rep) / len(rep)

    def _mid(self, axis: str) -> float:
        """กึ่งกลางสองผนังของแกน (พิกัดเครื่อง) — X ใช้ผนัง 0–1, Y ใช้ 2–3"""
        i, k = {"X": (0, 0), "Y": (1, 2)}[axis]
        lo, hi = sorted((self._wall_value(k, i), self._wall_value(k + 1, i)))
        self.result[axis] = (lo, hi, (lo + hi) / 2.0, hi - lo)
        return (lo + hi) / 2.0

    def _sizes(self):
        """v08: ขนาดชิ้นงานที่ใช้ตั้งมุม — เวอร์เนียร์ถ้ากรอก ไม่งั้น span − ⌀ลูกบอล"""
        return {a: (self.s.true.get(a) or (self.result[a][3] - self.s.tip_d)) for a in ("X", "Y")}

    def _zero_xy(self):
        """v08: พิกัดงานของกึ่งกลางชิ้นงาน (ตำแหน่งปัจจุบัน) เมื่อ X0 Y0 อยู่ที่จุด zero ที่เลือก"""
        size = self._sizes()
        fx, fy = _ZERO_FROM_CENTRE[self.s.zero_mode]
        self.zero_set = (self.s.zero_mode, -fx * size["X"], -fy * size["Y"])
        return -fx * size["X"], -fy * size["Y"]

    def _next(self):
        self._i += 1
        if self._i >= len(self._steps):
            self._finish()
            return
        label, make, need = self._steps[self._i]
        try:
            code = make() + "\n" + _END_MARK   # v04: ok ของบรรทัดนี้ = ขั้นนี้เคลื่อนที่เสร็จจริง
            self._need = len(self.prb) + need
            self.logger.send_gcode(code)
        except Exception as e:
            self._end(f"Could not send '{label}' to OpenBuilds: {e}" + self._done_note(), ok=False)
            return
        self._sent_at = time.monotonic()
        self.on_status(f"Step {self._i + 1}/{len(self._steps)}: {label}…")

    def _watchdog(self):
        if not self.active:
            return
        if time.monotonic() > self._deadline:
            self.stop()
            return
        self.app.root.after(500, self._watchdog)

    def _on_event(self, name, payload):
        if not self.active:
            return
        if name == "status" and isinstance(payload, dict):
            m = payload.get("machine") or {}
            self.coord = (m.get("modals") or {}).get("coordinatesys") or self.coord
            off = (m.get("position") or {}).get("offset")
            if isinstance(off, dict) and self._i >= 1 and not self.offset:
                self.offset = dict(off)   # offset ของจุดเริ่ม (หลังขั้นแรก) — จำครั้งเดียว
            comms = payload.get("comms") or {}
            if comms.get("alarm"):
                self._fail(f"ALARM {comms.get('alarm')}")
            # v04: ไม่ใช้ runStatus = Idle ตัดสินว่าขั้นจบ — OpenBuilds รอให้เครื่อง Idle ก่อนส่ง
            # G38.2 เสมอ ช่วงนั้นเครื่อง Idle ทั้งที่ยังเหลือคำสั่งในคิว (เคยทำให้สั่ง Stop ผิดจังหวะ)
        elif name == "data" and isinstance(payload, dict):
            resp = str(payload.get("response") or "")
            if "ALARM" in resp.upper():
                self._fail(resp.strip())
                return
            cmd = str(payload.get("command") or "").replace(" ", "").upper()
            if cmd == _END_MARK.replace(" ", "") and resp.strip().lower() == "ok":
                # ok ของ G4 P0 มาหลังการเคลื่อนที่ก่อนหน้าทั้งหมดเสร็จจริง = ขั้นนี้จบ
                if len(self.prb) >= self._need:
                    self._next()
                else:
                    self._fail("a probe move ended without touching a wall "
                               f"(no wall within {self.s.search:g} mm)")
                return
            mm = _SETTING.match(resp.strip())   # $100= / $101= จาก $$ ในขั้นแรก
            if mm:
                self.steps_mm[int(mm.group(1))] = float(mm.group(2))
            m = _PRB.search(resp)
            if m:
                if m.group(4) != "1":
                    self._fail("a probe move ended without touching a wall")
                    return
                self.prb.append(tuple(float(m.group(k)) for k in (1, 2, 3)))

    def _fail(self, why: str):
        try:
            self.logger.stop_machine()
        finally:
            self._end(f"{why} — stopped. Clear an alarm with $X, check the start position "
                      f"(near the centre, ball touching the top) and try again." + self._done_note(), ok=False)

    def _done_note(self) -> str:
        if self._i >= 7:
            return "\nX0 Y0 may already be at the centre — check the position before continuing."
        if self._i >= 1:
            return "\nZ0 (top surface) and a temporary X0 Y0 were set at the start point."
        return ""

    def _finish(self):
        s = self.s
        lines = [f"✔ X0 Y0 set at {_ZERO_TEXT[s.zero_mode]} — Z0 = top surface "
                 f"({'kept from before' if s.keep_zero else 'set at the start'}).",
                 f"   The ball is waiting at Z+{s.lift:g} above the centre."]
        for a, cad, key in (("X", s.width, 100), ("Y", s.length, 101)):
            lo, hi, mid, span = self.result[a]
            size = span - s.tip_d                       # ระยะระหว่างจุดศูนย์กลางลูกบอล − ⌀ลูกบอล
            diff = size - cad
            start = self.offset.get(a.lower())
            shift = f"{mid - float(start):+.3f}" if start is not None else "?"
            lines.append(f"{a}: {size:.3f} mm  (CAD {cad:.3f}, {diff:+.3f} mm, {100 * diff / cad:+.2f}%)  "
                         f"— centre {shift} mm from the start point")
            if abs(diff) <= max(_SIZE_TOL_MM, _SIZE_TOL_FRAC * cad):
                lines.append(f"   ✔ matches the CAD size — steps/mm (${key}) OK")
            else:
                cur = self.steps_mm.get(key)
                if cur:
                    new = cur * span / (cad + s.tip_d)
                    lines.append(f"   ⚠ if the CAD size is right, set ${key}={new:.3f} (now {cur:.3f}) — "
                                 f"check with a 200 mm jog first, then run Find centre again")
                else:
                    lines.append(f"   ⚠ differs from CAD — check ${key} (steps/mm) with a 200 mm jog")
        lines.append(f"(sizes use ball ⌀ {s.tip_d:g} mm)")
        lines += self._repeat_lines()   # v07
        # v06: Effective Tip ⌀ จากขอบนอก — span ยาวกว่าชิ้นงานจริงเท่า ⌀ ลูกบอลที่ใช้งานจริง
        self.deff = {}
        for a in ("X", "Y"):
            w = s.true.get(a)
            if w:
                span = self.result[a][3]
                self.deff[a] = span - w
        if self.deff:
            lines.append("Effective Tip ⌀ from the measured size (assumes steps/mm are right):")
            for a, d in self.deff.items():
                lines.append(f"   {a}: span {self.result[a][3]:.3f} − measured {s.true[a]:.3f} = {d:.3f} mm"
                             + ("   ⚠ outside 0–Tip ⌀ — check the measured size / steps/mm"
                                if not 0 <= d <= 2.5 else ""))
            if len(self.deff) == 2:
                lines.append(f"   X−Y difference {self.deff['X'] - self.deff['Y']:+.3f} mm "
                             f"(probe pre-travel differs per axis)")
        self._end("\n".join(lines), ok=True)

    def _repeat_lines(self) -> list:
        """v07: สรุป repeatability ต่อผนัง + เขียน CSV ทุกจุดแตะ"""
        s = self.s
        if not s.repeats:
            return []
        out = [f"Repeatability: {s.repeats} touches per wall at F{s.rep_feed:g} "
               f"(back-off {s.rep_back:g} mm), pass if range ≤ {_REP_TOL:g} mm"]
        ok_all, any_slide = True, False
        for w, (axis, sign, name) in enumerate(_WALLS):
            i = 0 if axis == "X" else 1
            pts = self._wall_touches(w)
            vals = [p[i] for p in pts[1:]]
            if not vals:
                continue
            mean = sum(vals) / len(vals)
            sd = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
            rng = max(vals) - min(vals)
            fast = (pts[0][i] - mean) * -sign   # แตะเร็วเลยแตะช้าไปตามทิศที่โพรบเดินเท่าไหร่ (+ = เลยไป)
            # v09: ผนังถอยไปตามทิศที่ดันทุกครั้ง = ชิ้นงานเลื่อน (ไม่ใช่หัวโพรบ)
            steps = [(b - a) * -sign for a, b in zip(vals, vals[1:])]
            drift = (vals[-1] - vals[0]) * -sign
            slides = drift > _REP_TOL and sum(1 for d in steps if d > -0.005) >= len(steps) - 1
            ok = rng <= _REP_TOL
            ok_all &= ok
            any_slide = any_slide or slides
            self.rep[f"{axis}{'+' if sign > 0 else '-'}"] = {'mean': mean, 'sd': sd, 'range': rng,
                                                             'fast_minus_slow': fast, 'ok': ok,
                                                             'drift': drift, 'slides': slides}
            out.append(f"   {name:5s} ({axis}{'+' if sign > 0 else '-'}): range {rng:.4f}  SD {sd:.4f}  "
                       f"fast overshoot {fast:+.4f}  " + ("✔" if ok else "⚠")
                       + (f"  ← wall moved {drift:+.3f} along the push: the PART SLIDES" if slides else ""))
        out.append("   ✔ probe + holder repeat well" if ok_all else
                   ("   ⚠ the part moves when pushed — clamp it / fix the base, then run again"
                    if any_slide else
                    "   ⚠ not repeatable — tighten the probe holder / clamp the part, then run again"))
        path = self._write_csv()
        if path:
            out.append(f"   touches saved: {path}")
        return out

    def _write_csv(self):
        """v07: ทุกจุดแตะของรอบนี้ (พิกัดเครื่อง) → Find_centre_<เวลา>.csv ในโฟลเดอร์ log"""
        import csv
        import datetime
        import os
        try:
            folder = getattr(self.logger, 'log_dir', None) or "."
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"Find_centre_{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.csv")
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                wr.writerow(["wall", "touch", "feed", "machine_x", "machine_y", "machine_z"])
                for w, (axis, sign, name) in enumerate(_WALLS):
                    for j, p in enumerate(self._wall_touches(w)):
                        wr.writerow([f"{axis}{'+' if sign > 0 else '-'} ({name})", j,
                                     self.s.feed if j == 0 else self.s.rep_feed] + [f"{c:.3f}" for c in p])
            return path
        except Exception as e:
            print(f"[wall_zero] repeatability CSV not written: {e!r}")
            return None

    def _end(self, text, ok):
        self.active = False
        if self._on_event in self.logger.on_event:
            self.logger.on_event.remove(self._on_event)
        self.logger.suppress_logs(8)
        self.on_done(text, ok)
