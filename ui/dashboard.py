"""The driver dashboard widget: draws a DisplayState exactly like the design.

Everything is drawn in a fixed 800x480 coordinate system and scaled to the
window, so it looks the same on the Pi's 7" screen and on a laptop.
"""
import math

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPolygonF)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

import config
from model import DisplayState
from ui.icons import svg

# --- palette (from the design) ----------------------------------------------
BG, PANEL, CARD, LINE = "#06080B", "#0A0D11", "#0F1216", "#232A31"
TEXT, MUTED, GREY, DIM = "#E8EDF2", "#8C98A5", "#4A545E", "#1E242B"
GREEN, BLUE, TEAL = "#32D17C", "#3FB8FF", "#2EC4B6"
NEEDLE = "#FF5A3C"
BAND_BELOW, MARK_BELOW = "#7956BC", "#C941FF"      # speed up
BAND_ABOVE, MARK_ABOVE = "#BC5757", "#FF4242"      # slow down

GHOST = dict(fg="#262D35", bd=None, bg=QColor("#0E1115"), glow=None)
RED = dict(fg="#FF7A7A", bd="#FF5A5A", bg=QColor(255, 77, 77, 36), glow=QColor(255, 90, 90))
AMBER = dict(fg="#FFB020", bd="#FFB020", bg=QColor(255, 176, 32, 33), glow=QColor(255, 176, 32))
ORANGE = dict(fg="#FF9A1F", bd="#FF9A1F", bg=QColor(255, 154, 31, 33), glow=QColor(255, 154, 31))

# --- gauge geometry (design viewBox 275x225, drawn at 280x229) -------------
GX, GY, K = 294.0, 105.5, 280 / 275
CX, CY, R = GX + 137.5 * K, GY + 130.4 * K, 105.35 * K
A0, SWEEP = 135.0, 270.0


def format_stint_time(stint_s: int) -> str:
    """Stint time as HH:MM. No seconds: a digit changing every second pulls the eye,
    and one format avoids reading 01:42 as minutes in one stint and hours in the next."""
    h, m = divmod(max(0, int(stint_s)) // 60, 60)
    return f"{h:02d}:{m:02d}"


def _fonts():
    fams = set(QFontDatabase.families())
    mono = "JetBrains Mono" if "JetBrains Mono" in fams else "DejaVu Sans Mono"
    sans = "Inter" if "Inter" in fams else "DejaVu Sans"
    return sans, mono


class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.state = DisplayState()
        self.sans, self.mono = _fonts()
        self._svg_cache = {}
        self.setMinimumSize(400, 240)
        self.setFocusPolicy(Qt.StrongFocus)

    def show_state(self, state: DisplayState) -> None:
        self.state = state
        self.update()

    # --- small drawing helpers ---------------------------------------------
    def font(self, mono: bool, px: float, weight: int, spacing: float = 0.0) -> QFont:
        f = QFont(self.mono if mono else self.sans)
        f.setPixelSize(int(round(px)))
        f.setWeight(QFont.Weight(weight))
        if spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        return f

    @staticmethod
    def rrect(p, x, y, w, h, r, fill=None, border=None, bw=1.0):
        p.setPen(QPen(QColor(border), bw) if border else Qt.NoPen)
        p.setBrush(QBrush(QColor(fill) if isinstance(fill, str) else fill) if fill is not None else Qt.NoBrush)
        o = bw / 2 if border else 0
        p.drawRoundedRect(QRectF(x + o, y + o, w - 2 * o, h - 2 * o), r, r)

    @staticmethod
    def glow(p, x, y, w, h, r, color: QColor, strength=0.4):
        p.setBrush(Qt.NoBrush)
        for i in range(1, 8):
            c = QColor(color)
            c.setAlphaF(strength * 0.22 * (1 - i / 8))
            p.setPen(QPen(c, 2))
            p.drawRoundedRect(QRectF(x - i, y - i, w + 2 * i, h + 2 * i), r + i, r + i)

    def text(self, p, x, y, w, h, s, font, color, align=Qt.AlignLeft | Qt.AlignVCenter):
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, w, h), int(align), s)

    def tw(self, s, font) -> float:
        return QFontMetricsF(font).horizontalAdvance(s)

    def icon(self, p, name, color, x, y, size):
        key = (name, color)
        if key not in self._svg_cache:
            self._svg_cache[key] = QSvgRenderer(QByteArray(svg(name, color)))
        self._svg_cache[key].render(p, QRectF(x, y, size, size))

    # --- paint ----------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(self.rect(), QColor(BG))
        s = min(self.width() / config.SCREEN_W, self.height() / config.SCREEN_H)
        p.translate((self.width() - config.SCREEN_W * s) / 2, (self.height() - config.SCREEN_H * s) / 2)
        p.scale(s, s)

        st = self.state
        self.draw_top_bar(p, st)
        self.draw_power(p, st)
        self.rrect(p, 84, 60, 700, 334, 6, PANEL, LINE)
        self.draw_left_lights(p, st)
        self.draw_right_lights(p, st)
        self.draw_pit_light(p, st)
        self.draw_gauge(p, st)
        self.draw_gear(p, st)
        self.draw_bottom(p, st)
        if st.message is not None:
            self.draw_message(p, st)
        p.end()

    # --- top bar: LAP / STINT -------------------------------------------------
    def draw_top_bar(self, p, st):
        label = self.font(False, 13, 800, 0.8)
        value = self.font(True, 26, 800)
        x = 16
        stint_str = format_stint_time(st.stint_s)
        for name, val, col in (("LAP", str(st.lap), BLUE), ("STINT", stint_str, TEXT)):
            w = 14 + self.tw(name, label) + 10 + self.tw(val, value) + 14
            self.rrect(p, x, 12, w, 34, 4, CARD, LINE)
            self.text(p, x + 14, 12, 100, 34, name, label, MUTED)
            self.text(p, x + 14 + self.tw(name, label) + 10, 12, 200, 34, val, value, col)
            x += w + 6
        p.setPen(QPen(QColor(LINE), 1))
        p.drawLine(QPointF(16, 51.5), QPointF(784, 51.5))

    # --- vertical power / regen bar --------------------------------------------
    def draw_power(self, p, st):
        v = st.vehicle
        self.rrect(p, 16, 60, 58, 334, 4, CARD, LINE)
        regen = v.power_kw < -0.05
        num = "0.0" if abs(v.power_kw) < 0.05 else f"{v.power_kw:+.1f}".replace("-", "−")
        num_col = GREY if st.stale else (TEAL if regen else BLUE)
        self.text(p, 16, 68, 58, 14, "PWR", self.font(False, 11, 900, 0.6), MUTED, Qt.AlignCenter)
        self.text(p, 16, 83, 58, 18, num, self.font(True, 16, 800), num_col, Qt.AlignCenter)
        self.text(p, 16, 101, 58, 12, "kW", self.font(False, 10, 700), MUTED, Qt.AlignCenter)

        tx, ty, tw, th = 33, 120, 24, 246
        self.rrect(p, tx, ty, tw, th, 3, "#161B21", "#2A323B")
        mid = ty + th / 2
        p.save()
        p.setOpacity(0.35 if st.stale else 1.0)
        if regen:
            frac = min(1.0, -v.power_kw / config.REGEN_MAX_KW)
            hgt = frac * (th / 2 - 2)
            g = QLinearGradient(0, mid, 0, mid + hgt)
            g.setColorAt(0, QColor("#FF7A3C")); g.setColorAt(0.4, QColor("#F7D046")); g.setColorAt(1, QColor(TEAL))
            p.fillRect(QRectF(tx + 2, mid, tw - 4, hgt), QBrush(g))
        elif v.power_kw > 0.05:
            frac = min(1.0, v.power_kw / config.POWER_MAX_KW)
            hgt = frac * (th / 2 - 2)
            g = QLinearGradient(0, mid, 0, mid - hgt)
            g.setColorAt(0, QColor(TEAL)); g.setColorAt(0.6, QColor("#F7D046")); g.setColorAt(1, QColor("#FF7A3C"))
            p.fillRect(QRectF(tx + 2, mid - hgt, tw - 4, hgt), QBrush(g))
        p.restore()
        p.fillRect(QRectF(tx + 1, mid - 1, tw - 2, 3), QColor(NEEDLE))
        self.text(p, 16, 372, 58, 14, "REGEN", self.font(False, 11, 900, 0.2), TEAL, Qt.AlignCenter)

    # --- warning lights -------------------------------------------------------
    def light(self, p, x, y, title, icon, tone):
        w, h = 190, 46
        if tone["glow"] is not None:
            self.glow(p, x, y, w, h, 3, tone["glow"])
        self.rrect(p, x, y, w, h, 3, tone["bg"], tone["bd"])
        self.icon(p, icon, tone["fg"], x + 10, y + 12, 22)
        self.text(p, x + 42, y, w - 46, h, title, self.font(False, 16, 900, 0.3), tone["fg"])

    def draw_left_lights(self, p, st):
        v = st.vehicle
        items = [("BMS FAULT", "bms", RED if v.bms_fault else GHOST),
                 ("IMD FAULT", "imd", RED if v.imd_fault else GHOST),
                 ("SAFE STATE", "safe", RED if v.safe_state else GHOST),
                 ("HAZARD", "hazard", AMBER if v.hazard else GHOST)]
        y = 68 + (318 - (4 * 46 + 3 * 8)) / 2
        for title, icon, tone in items:
            self.light(p, 92, y, title, icon, tone)
            y += 54

    def draw_right_lights(self, p, st):
        v = st.vehicle
        data = {"lost": ("CAN LOSS", RED), "recovering": ("RECOVERING", ORANGE)}.get(st.data_status, ("DATA", GHOST))
        items = [("MOTOR HOT", "motor", RED if st.motor_hot else GHOST),
                 ("CTRL HOT", "ctrl", RED if st.ctrl_hot else GHOST),
                 ("LOW TIRE", "tire", AMBER if v.low_tire else GHOST),
                 ("NO LINK", "link", RED if st.no_link else GHOST),
                 (data[0], "data", data[1])]
        y = 68 + (318 - (5 * 46 + 4 * 8)) / 2
        for title, icon, tone in items:
            self.light(p, 586, y, title, icon, tone)
            y += 54

    def draw_pit_light(self, p, st):
        if not st.pit_active:
            return
        f = self.font(False, 15, 900, 0.6)
        label = f"PIT — LOCKED {st.pit_lock_left}s" if st.pit_lock_left > 0 else "PIT"
        w = self.tw(label, f) + 32
        x = 434 - w / 2
        self.glow(p, x, 68, w, 30, 3, QColor(245, 158, 11), 0.5)
        self.rrect(p, x, 68, w, 30, 3, "#F59E0B", "#FCD34D", 2)
        self.text(p, x, 68, w, 30, label, f, "#020617", Qt.AlignCenter)

    # --- speedometer --------------------------------------------------------
    @staticmethod
    def pt(r, a):
        t = math.radians(a)
        return QPointF(CX + r * math.cos(t), CY + r * math.sin(t))

    def ang(self, kmh):
        return A0 + SWEEP * max(0.0, min(1.0, kmh / config.SPEED_MAX_KMH))

    def arc(self, p, a0, a1, color, width):
        if a1 - a0 < 0.3:
            return
        path = QPainterPath(self.pt(R, a0))
        n = max(2, int((a1 - a0) / 2))
        for i in range(1, n + 1):
            path.lineTo(self.pt(R, a0 + (a1 - a0) * i / n))
        p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def draw_gauge(self, p, st):
        v = st.vehicle
        sa = self.ang(v.speed_kmh)
        p.save()
        p.setOpacity(0.35 if st.stale else 1.0)
        self.arc(p, A0, A0 + SWEEP, LINE, 10 * K)
        self.arc(p, A0, sa, BLUE, 10 * K)

        if st.target_kmh is not None:
            ta = self.ang(st.target_kmh)
            band, mark = (BAND_ABOVE, MARK_ABOVE) if st.target_mode == "above" else (BAND_BELOW, MARK_BELOW)
            if st.target_mode == "below":
                self.arc(p, sa, ta, band, 14 * K)
            elif st.target_mode == "above":
                self.arc(p, ta, sa, band, 14 * K)
            half = math.degrees(5 / (105.35 + 20))
            tri = QPolygonF([self.pt(R + 2 * K, ta), self.pt(R + 20 * K, ta - half), self.pt(R + 20 * K, ta + half)])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(mark))
            p.drawPolygon(tri)

        for kmh in range(0, config.SPEED_MAX_KMH + 1, 10):
            major = kmh % 20 == 0
            a = self.ang(kmh)
            col = NEEDLE if kmh >= config.SPEED_REDLINE_KMH else ("#C3CCD5" if major else GREY)
            p.setPen(QPen(QColor(col), (2.5 if major else 1.5) * K, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(self.pt(R - 6 * K, a), self.pt(R - (17 if major else 11) * K, a))

        t = math.radians(sa)
        u, nrm = QPointF(math.cos(t), math.sin(t)), QPointF(-math.sin(t), math.cos(t))
        c = QPointF(CX, CY)
        q = lambda d, w: c + u * (d * K) + nrm * (w * K)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(NEEDLE))
        p.drawPolygon(QPolygonF([q(-12, -2.5), q(105.35 - 14, -1), q(105.35 - 14, 1), q(-12, 2.5)]))
        p.setBrush(QColor("#334155")); p.drawEllipse(c, 7 * K, 7 * K)
        p.setBrush(QColor(NEEDLE)); p.drawEllipse(c, 3.5 * K, 3.5 * K)
        p.restore()

        label_font = self.font(True, 13, 700)
        for kmh in range(0, config.SPEED_MAX_KMH + 1, 20):
            pos = self.pt(R - 29 * K, self.ang(kmh))
            self.text(p, pos.x() - 18, pos.y() - 9, 36, 18, str(kmh), label_font,
                      GREY if st.stale else "#C3CCD5", Qt.AlignCenter)

        self.text(p, GX, GY + 146, 280, 62, str(int(round(v.speed_kmh))), self.font(True, 56, 800),
                  GREY if st.stale else TEXT, Qt.AlignHCenter | Qt.AlignTop)
        self.text(p, GX, GY + 212, 280, 16, "KM/H", self.font(False, 12, 800, 1.0), MUTED, Qt.AlignCenter)

        left_on = (v.turn_left or v.hazard) and st.blink_on
        right_on = (v.turn_right or v.hazard) and st.blink_on
        self.arrow(p, GX, GY + 229 - 6 - 26, left=True, color=GREEN if left_on else DIM)
        self.arrow(p, GX + 280 - 34, GY + 229 - 6 - 26, left=False, color=GREEN if right_on else DIM)

    def arrow(self, p, x, y, left, color):
        pts = [(11, 5), (3, 12), (11, 19), (11, 15), (21, 15), (21, 9), (11, 9)] if left else \
              [(13, 5), (21, 12), (13, 19), (13, 15), (3, 15), (3, 9), (13, 9)]
        sx, sy = 34 / 24, 26 / 24
        sc = min(sx, sy)
        ox, oy = x + (34 - 24 * sc) / 2, y + (26 - 24 * sc) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(ox + a * sc, oy + b * sc) for a, b in pts]))

    # --- D / R ----------------------------------------------------------------
    def draw_gear(self, p, st):
        p.setPen(QPen(QColor(LINE), 1))
        p.drawLine(QPointF(290, 342.5), QPointF(578, 342.5))
        x, y = 434 - 42.5, 348
        self.rrect(p, x, y, 85, 36, 3, CARD, LINE)
        f = self.font(True, 18, 800)
        rev = st.vehicle.gear == "R"
        # D
        if not rev:
            self.rrect(p, x + 4, y + 4, 38, 28, 2, TEXT)
        self.text(p, x + 4, y + 4, 38, 28, "D", f, GREY if rev else "#0B0D10", Qt.AlignCenter)
        # R
        if rev:
            self.glow(p, x + 44, y + 4, 38, 28, 2, QColor(229, 72, 77), 0.6)
            self.rrect(p, x + 44, y + 4, 38, 28, 2, "#E5484D")
        self.text(p, x + 44, y + 4, 38, 28, "R", f, "#FFFFFF" if rev else GREY, Qt.AlignCenter)

    # --- bottom row: SOC / RANGE / MOTOR / CTRL --------------------------------
    def draw_bottom(self, p, st):
        v = st.vehicle
        p.setPen(QPen(QColor(LINE), 1))
        p.drawLine(QPointF(16, 402.5), QPointF(784, 402.5))
        cw = (768 - 30) / 4
        xs = [16 + i * (cw + 10) for i in range(4)]
        y, h = 408, 60
        for x in xs:
            self.rrect(p, x, y, cw, h, 4, CARD, LINE)
        label = self.font(False, 13, 800)
        val = self.font(True, 26, 800)

        soc_col = GREY if st.stale else {"ok": GREEN, "amber": "#FFB020", "red": "#FF5A5A"}[st.soc_level]
        # SOC: battery icon + label + value + bar
        x = xs[0]
        bx, by = x + 12, y + 12
        self.rrect(p, bx, by + 5, 30, 15, 2, None, MUTED, 1.5)
        p.fillRect(QRectF(bx + 30, by + 9, 3, 7), QColor(MUTED))
        p.fillRect(QRectF(bx + 3.5, by + 8.5, 23 * v.soc_pct / 100, 8), QColor(soc_col))
        self.text(p, bx + 41, by, 60, 26, "SOC", label, MUTED)
        self.text(p, x, by, cw - 12, 26, f"{v.soc_pct:.0f}%", val, soc_col, Qt.AlignRight | Qt.AlignVCenter)
        self.bar(p, x + 12, y + 44, cw - 24, v.soc_pct / 100, soc_col)

        # RANGE (same colour as the battery)
        x = xs[1]
        self.text(p, x + 12, y, 80, h, "RANGE", label, MUTED)
        unit = self.font(True, 14, 800)
        uw = self.tw(" km", unit)
        self.text(p, x, y + 4, cw - 12, h, " km", unit, MUTED, Qt.AlignRight | Qt.AlignVCenter)
        self.text(p, x, y, cw - 12 - uw, h, f"{v.range_km:.0f}", val, soc_col, Qt.AlignRight | Qt.AlignVCenter)

        # MOTOR / CTRL temperatures
        for x, name, temp, hot, scale in ((xs[2], "MOTOR", v.motor_temp_c, st.motor_hot, config.MOTOR_TEMP_SCALE_C),
                                          (xs[3], "CTRL", v.ctrl_temp_c, st.ctrl_hot, config.CTRL_TEMP_SCALE_C)):
            col = GREY if st.stale else ("#FF7A7A" if hot else GREEN)
            bar_col = GREY if st.stale else ("#FF5A5A" if hot else GREEN)
            self.text(p, x + 12, y + 12, 80, 26, name, label, MUTED)
            self.text(p, x, y + 12, cw - 12, 26, f"{temp:.0f}°C", val, col, Qt.AlignRight | Qt.AlignVCenter)
            self.bar(p, x + 12, y + 44, cw - 24, temp / scale, bar_col)

    def bar(self, p, x, y, w, frac, color):
        self.rrect(p, x, y, w, 7, 1, LINE)
        p.fillRect(QRectF(x, y, w * max(0.0, min(1.0, frac)), 7), QColor(color))

    # --- pit message pop-up -----------------------------------------------------
    def draw_message(self, p, st):
        x, y, w, h = 12, 8, 776, 92
        p.setPen(Qt.NoPen)
        for i in range(1, 9):
            c = QColor(0, 0, 0); c.setAlphaF(0.07)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x - i, y + 4 + i, w + 2 * i, h + i), 6, 6)
        self.rrect(p, x, y, w, h, 4, QColor(69, 26, 3, 247), "#FBBF24", 2)

        bf = self.font(False, 12, 900, 0.5)
        bw = self.tw("PIT MESSAGE", bf) + 16
        self.rrect(p, 24, 20, bw, 22, 2, "#F59E0B")
        self.text(p, 24, 20, bw, 22, "PIT MESSAGE", bf, "#020617", Qt.AlignCenter)
        if st.queued:
            qf = self.font(True, 12, 700)
            q = f"+{st.queued} QUEUED"
            qw = self.tw(q, qf) + 16
            self.rrect(p, 24 + bw + 8, 20, qw, 22, 2, "#1E242B")
            self.text(p, 24 + bw + 8, 20, qw, 22, q, qf, "#FCD34D", Qt.AlignCenter)

        of = self.font(False, 13, 900)
        ow = self.tw("OK ON WHEEL", of) + 20
        ox = 776 - ow
        self.rrect(p, ox, 20, ow, 22, 2, "#10B981")
        self.text(p, ox, 20, ow, 22, "OK ON WHEEL", of, "#020617", Qt.AlignCenter)
        cf = self.font(True, 15, 800)
        cnt = f"{st.message_left_s}s"
        self.text(p, ox - 10 - self.tw(cnt, cf), 20, self.tw(cnt, cf) + 2, 22, cnt, cf, "#FCD34D")

        self.text(p, 24, 48, 740, 30, st.message.text, self.font(False, 26, 900), "#FFFBEB")
        self.rrect(p, 24, 84, 752, 4, 0, "#1E242B")
        p.fillRect(QRectF(24, 84, 752 * st.message_left_s / config.MESSAGE_TIMEOUT_S, 4), QColor("#FBBF24"))
