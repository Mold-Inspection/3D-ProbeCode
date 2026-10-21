# ==============================================================================
# ui/wall_zero.py — หา X0 Y0 = กึ่งกลางชิ้นงาน (+ Z0 = ผิวบน) ด้วยการแตะผนังด้านนอก 4 ด้าน
# ==============================================================================
# VERSION: 05
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
#   _BACKOFF     = ถอยออกหลังแตะ (มม.)
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
_COORD_P = {"G54": 1, "G55": 2, "G56": 3, "G57": 4, "G58": 5, "G59": 6}


class CentreSettings:
    def __init__(self, width: float, length: float, tip_d: float, gap: float = 30.0, lift: float = 5.0,
                 depth: float = 4.0, feed: float = 100.0):
        # tip_d = ⌀ ลูกบอลที่ใช้หักออกจากระยะที่วัด (Effective Tip ⌀ ถ้า calibrate แล้ว)
        self.width, self.length, self.tip_d = float(width), float(length), float(tip_d)
        self.gap, self.lift, self.depth, self.feed = float(gap), float(lift), float(depth), float(feed)

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
        f"G0 {a}{sign * _BACKOFF:.3f}",
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
             lambda: f"$$\nG10 L20 P{p()} X0 Y0 Z0\nG90\nG0 Z{s.lift:.3f}", 0),
            ("X: left wall", lambda: side_gcode("X", -1, s), 1),
            ("X: right wall", lambda: side_gcode("X", +1, s), 1),
            # แตะผนังหน้า/หลังที่แนว X กึ่งกลางที่วัดได้ (พิกัดเครื่อง — ไม่ขึ้นกับ offset)
            ("Y: front wall", lambda: f"G90\nG0 Z{s.lift:.3f}\nG53 G0 X{self._mid('X'):.3f}\n"
                                      + side_gcode("Y", -1, s), 1),
            ("Y: back wall", lambda: side_gcode("Y", +1, s), 1),
            # 2) กลับจุดเริ่ม (Z ยังยกอยู่) — 3) ไปกึ่งกลางจริง — 4) ตั้ง X0 Y0 ตรงนั้น (Z0 คงเดิม)
            ("Back to the start point (Z lifted)", lambda: f"G90\nG0 Z{s.lift:.3f}\nG0 X0 Y0\nG4 P1", 0),
            ("Move to the measured centre",
             lambda: f"G53 G0 X{self._mid('X'):.3f} Y{self._mid('Y'):.3f}\nG4 P1", 0),
            ("Set X0 Y0 at the centre", lambda: f"G10 L20 P{p()} X0 Y0", 0),
        ]
        self.active, self.prb, self.result, self._i = True, [], {}, -1
        self.steps_mm = {}
        self._deadline = time.monotonic() + _TIMEOUT_S
        self.logger.on_event.append(self._on_event)
        self.logger.suppress_logs(_TIMEOUT_S + 30)
        self._next()
        self.app.root.after(500, self._watchdog)

    def stop(self):
        if self.active:
            try:
                self.logger.stop_machine()
            finally:
                self._end("Stopped — the machine was halted." + self._done_note(), ok=False)

    # ------------------------------------------------------------------
    def _mid(self, axis: str) -> float:
        """กึ่งกลางสองผนังของแกน (พิกัดเครื่อง) — X ใช้จุดแตะที่ 1–2, Y ใช้ 3–4"""
        i, k = {"X": (0, 0), "Y": (1, 2)}[axis]
        lo, hi = sorted((self.prb[k][i], self.prb[k + 1][i]))
        self.result[axis] = (lo, hi, (lo + hi) / 2.0, hi - lo)
        return (lo + hi) / 2.0

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
        lines = ["✔ X0 Y0 set at the measured centre — Z0 = top surface (set at the start).",
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
        self._end("\n".join(lines), ok=True)

    def _end(self, text, ok):
        self.active = False
        if self._on_event in self.logger.on_event:
            self.logger.on_event.remove(self._on_event)
        self.logger.suppress_logs(8)
        self.on_done(text, ok)
