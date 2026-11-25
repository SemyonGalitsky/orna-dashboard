r"""ORNA driver dashboard — Combined Edition (v2).

Combines:
- 3-layer architecture (`VehicleSource` + `PitLink` -> `DashboardLogic` -> `Dashboard` UI)
- Per-channel background-threaded `CanSource` with 3-second auto-reconnect,
  DBC decoding via `cantools`; bad or unknown frames are skipped
- 1-second periodic CSV flush in `DataLogger` so power cuts lose at most ~1s
- Interactive bench-testing GUI toolbar (19 preset states dropdown, Prev/Next,
  Auto-Cycle, Live Physics, and Pit/Fault quick buttons) alongside all keyboard
  shortcuts (`F1`/`--demo`, `Tab`, `[`/`]`, `0`, `Space`, `P`, `M`, etc.)
- Animated turn-signal blinking even in static preset/demo inspection mode.

Usage:
    python main.py                               # Simulator + GUI bench toolbar
    python main.py --demo                        # Auto-cycle through all 19 design states
    python main.py --state 2                     # Start in Preset State 2 (Over target)
    python main.py --fullscreen                  # 800x480 fullscreen on Pi (hides toolbar)
    python main.py --source can --dbc orna.dbc   # Real CAN bus with DBC
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import os
import sys
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from datalog import DataLogger
from logic import DashboardLogic
from pitlink import SimulatedPitLink
from presets import PRESET_LIST, PRESETS_BY_ID
from sources.simulator import SimulatedSource
from ui.dashboard import Dashboard

HELP = """
Driver (wheel buttons):   Space = OK      P = PIT button
Car (simulator only):     Left/Right = turn signal   Z = hazard   R = D/R
                          B = BMS fault   I = IMD fault   S = safe state   T = low tire
                          H = motor overheat   J = controller overheat   C = cut CAN data
Pit side:                 M = send message   Shift+P = pit light   Up/Down = target +/-5
                          L = cut pit link   N = new lap
Demo & Presets:           F1 = toggle 3s Auto-Cycle demo   Tab or ] = next preset
                          [ = prev preset                  0 = return to Live Physics
Window:                   F11 = fullscreen   Esc = quit
"""


class AppWindow(QMainWindow):
    def __init__(
        self,
        source,
        pit: SimulatedPitLink,
        log: Optional[DataLogger],
        initial_preset_id: int = 0,
        auto_cycle: bool = False,
        show_toolbar: bool = True,
    ):
        super().__init__()
        self.source = source
        self.pit = pit
        self.log = log
        self.logic = DashboardLogic(time.monotonic())
        self.last_log = 0.0

        # Preset state mode: 0 = Live Physics/CAN, 1..19 = Reference Design State
        self.preset_id: int = initial_preset_id
        self.auto_cycle: bool = auto_cycle
        self.last_cycle_t: float = time.monotonic()

        self.setWindowTitle("ORNA Driver Dashboard · 800×480")
        self.setStyleSheet("background-color: #06080B; color: #E8EDF2;")

        central = QWidget()
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self.dashboard = Dashboard()
        vbox.addWidget(self.dashboard, 1)

        self.toolbar: Optional[QFrame] = None
        if show_toolbar and isinstance(self.source, SimulatedSource):
            self.toolbar = self._build_bench_toolbar()
            vbox.addWidget(self.toolbar)

        self.setCentralWidget(central)
        self.resize(config.SCREEN_W, config.SCREEN_H + (44 if self.toolbar else 0))

        if auto_cycle and initial_preset_id == 0:
            self.set_preset_mode(1)
        elif initial_preset_id > 0:
            self.set_preset_mode(initial_preset_id)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / config.UPDATE_HZ))

    # --- Interactive Bench Toolbar (hidden in --fullscreen) -----------------
    def _build_bench_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            "QFrame { background-color: #0F141C; border-top: 1px solid #232A31; }"
            "QPushButton { background-color: #1A222D; color: #E8EDF2; border: 1px solid #2E3846; "
            "border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold; }"
            "QPushButton:hover { background-color: #283344; }"
            "QComboBox { background-color: #0A0D11; color: #3FB8FF; border: 1px solid #2E3846; "
            "border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold; }"
            "QCheckBox { color: #CBD5E1; font-size: 11px; font-weight: bold; spacing: 5px; }"
        )
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(10, 4, 10, 4)
        hbox.setSpacing(6)

        btn_prev = QPushButton("◀ Prev")
        btn_next = QPushButton("Next ▶")
        btn_prev.setFocusPolicy(Qt.NoFocus)
        btn_next.setFocusPolicy(Qt.NoFocus)

        self.combo_preset = QComboBox()
        self.combo_preset.setFocusPolicy(Qt.NoFocus)
        self.combo_preset.addItem("0 · LIVE Physics Simulation", userData=0)
        for sid, _slug, title, _st in PRESET_LIST:
            self.combo_preset.addItem(title, userData=sid)

        self.chk_cycle = QCheckBox("Auto-Cycle (F1)")
        self.chk_cycle.setFocusPolicy(Qt.NoFocus)
        self.chk_cycle.setChecked(self.auto_cycle)

        btn_msg = QPushButton("Pit Msg (M)")
        btn_ok = QPushButton("Wheel OK (Space)")
        btn_pit = QPushButton("PIT (P)")
        btn_can = QPushButton("Cut CAN (C)")
        for b in (btn_msg, btn_ok, btn_pit, btn_can):
            b.setFocusPolicy(Qt.NoFocus)

        hbox.addWidget(btn_prev)
        hbox.addWidget(self.combo_preset, 1)
        hbox.addWidget(btn_next)
        hbox.addWidget(self.chk_cycle)
        hbox.addWidget(btn_msg)
        hbox.addWidget(btn_ok)
        hbox.addWidget(btn_pit)
        hbox.addWidget(btn_can)

        btn_prev.clicked.connect(self.prev_preset)
        btn_next.clicked.connect(self.next_preset)
        self.combo_preset.currentIndexChanged.connect(
            lambda idx: self.set_preset_mode(int(self.combo_preset.itemData(idx)))
        )
        self.chk_cycle.toggled.connect(self.set_auto_cycle)
        btn_msg.clicked.connect(self._trigger_pit_msg)
        btn_ok.clicked.connect(self._trigger_wheel_ok)
        btn_pit.clicked.connect(self._trigger_pit_btn)
        btn_can.clicked.connect(self._trigger_cut_can)

        return bar

    # --- Preset & Simulation Controls ---------------------------------------
    def set_preset_mode(self, preset_id: int) -> None:
        self.preset_id = max(0, min(len(PRESET_LIST), preset_id))
        self.last_cycle_t = time.monotonic()
        if self.preset_id == 0:
            self.setWindowTitle("ORNA Driver Dashboard · 800×480")
        elif self.preset_id in PRESETS_BY_ID:
            slug, title, _ = PRESETS_BY_ID[self.preset_id]
            self.setWindowTitle(f"ORNA Driver Dashboard — {title} ({slug})")
        if hasattr(self, "combo_preset"):
            self.combo_preset.blockSignals(True)
            self.combo_preset.setCurrentIndex(self.preset_id)
            self.combo_preset.blockSignals(False)

    def next_preset(self) -> None:
        nxt = (self.preset_id % len(PRESET_LIST)) + 1
        self.set_preset_mode(nxt)

    def prev_preset(self) -> None:
        prv = ((self.preset_id - 2) % len(PRESET_LIST)) + 1 if self.preset_id > 0 else len(PRESET_LIST)
        self.set_preset_mode(prv)

    def set_auto_cycle(self, enabled: bool) -> None:
        self.auto_cycle = enabled
        self.last_cycle_t = time.monotonic()
        if hasattr(self, "chk_cycle"):
            self.chk_cycle.blockSignals(True)
            self.chk_cycle.setChecked(enabled)
            self.chk_cycle.blockSignals(False)
        if enabled and self.preset_id == 0:
            self.set_preset_mode(1)

    def _trigger_pit_msg(self) -> None:
        self.set_auto_cycle(False)
        self.set_preset_mode(0)
        self.pit.send_preset()

    def _trigger_wheel_ok(self) -> None:
        now = time.monotonic()
        acked = self.logic.ok_pressed(now)
        if acked:
            self.pit.send_to_pit(f"ACK {acked}")
            self.log_event("ok_ack", acked)

    def _trigger_pit_btn(self) -> None:
        self.set_auto_cycle(False)
        self.set_preset_mode(0)
        now = time.monotonic()
        if self.logic.pit_pressed(now):
            self.pit.send_to_pit("PIT")
            self.log_event("pit_light", "from driver")

    def _trigger_cut_can(self) -> None:
        self.set_auto_cycle(False)
        self.set_preset_mode(0)
        if isinstance(self.source, SimulatedSource):
            self.source.toggle("bus_silent")

    # --- 20 Hz Main Update Loop ---------------------------------------------
    def tick(self) -> None:
        now = time.monotonic()

        if self.auto_cycle and (now - self.last_cycle_t >= config.AUTO_CYCLE_S):
            self.last_cycle_t = now
            self.next_preset()

        # When inspecting a design preset (1..19), don't drain live simulator/pit queues
        if self.preset_id in PRESETS_BY_ID:
            _slug, _title, preset_state = PRESETS_BY_ID[self.preset_id]
            blinking = (
                preset_state.vehicle.turn_left
                or preset_state.vehicle.turn_right
                or preset_state.vehicle.hazard
            )
            blink_on = (not blinking) or (
                int((now - self.logic.start) / (config.BLINK_PERIOD_S / 2)) % 2 == 0
            )
            st = dataclasses.replace(preset_state, blink_on=blink_on)
            self.dashboard.show_state(st)
            return

        pit = self.pit.poll(now)
        self.source.set_target_hint(pit.target_kmh)
        vehicle = self.source.poll(now)
        for text in self.pit.take_messages():
            self.logic.push_message(text, now)
            self.log_event("message_received", text)
        if self.pit.take_pit_request() and self.logic.pit_pressed(now):
            self.log_event("pit_light", "from pit")
        state = self.logic.update(now, vehicle, pit)
        if self.log and vehicle is not None and now - self.last_log >= 1 / config.LOG_HZ:
            self.log.log(now, vehicle, state.data_status)
            self.last_log = now
        self.dashboard.show_state(state)

    def log_event(self, name: str, detail: str = "") -> None:
        if self.log:
            self.log.event(time.monotonic(), name, detail)

    def keyPressEvent(self, e) -> None:
        now, k, sim = time.monotonic(), e.key(), self.source
        shift = e.modifiers() & Qt.ShiftModifier
        if k == Qt.Key_Escape:
            self.close()
        elif k == Qt.Key_F1:
            if self.preset_id > 0 or self.auto_cycle:
                self.set_auto_cycle(False)
                self.set_preset_mode(0)
            else:
                self.set_auto_cycle(True)
        elif k in (Qt.Key_Tab, Qt.Key_BracketRight):
            self.next_preset()
        elif k == Qt.Key_BracketLeft:
            self.prev_preset()
        elif k == Qt.Key_0:
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
        elif k == Qt.Key_F11:
            if self.isFullScreen():
                if self.toolbar:
                    self.toolbar.show()
                self.showNormal()
            else:
                if self.toolbar:
                    self.toolbar.hide()
                self.showFullScreen()
        # driver buttons (on the car these come from the wheel, e.g. via GPIO)
        elif k == Qt.Key_Space:
            self._trigger_wheel_ok()
        elif k == Qt.Key_P and shift:
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
            self.pit.press_pit()
        elif k == Qt.Key_P:
            self._trigger_pit_btn()
        # pit side
        elif k == Qt.Key_M:
            self._trigger_pit_msg()
        elif k == Qt.Key_Up:
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
            self.pit.change_target(+5)
        elif k == Qt.Key_Down:
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
            self.pit.change_target(-5)
        elif k == Qt.Key_L:
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
            self.pit.toggle_link()
            self.log_event("pit_link", "up" if self.pit.data.link_up else "down")
        elif k == Qt.Key_N:
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
            self.logic.new_lap(now)
        # car (simulator only)
        elif isinstance(sim, SimulatedSource):
            self.set_auto_cycle(False)
            self.set_preset_mode(0)
            toggles = {
                Qt.Key_Z: "hazard",
                Qt.Key_B: "bms_fault",
                Qt.Key_I: "imd_fault",
                Qt.Key_S: "safe_state",
                Qt.Key_T: "low_tire",
                Qt.Key_H: "motor_overheat",
                Qt.Key_J: "ctrl_overheat",
                Qt.Key_C: "bus_silent",
            }
            if k in toggles:
                sim.toggle(toggles[k])
            elif k == Qt.Key_Left:
                sim.v.turn_right = False
                sim.toggle("turn_left")
            elif k == Qt.Key_Right:
                sim.v.turn_left = False
                sim.toggle("turn_right")
            elif k == Qt.Key_R:
                sim.toggle_gear()

    def closeEvent(self, e) -> None:
        self.timer.stop()
        self.source.close()
        if self.log:
            self.log.close()
            self.log = None
        super().closeEvent(e)


def main() -> None:
    ap = argparse.ArgumentParser(description="ORNA driver dashboard (Combined Edition v2)")
    ap.add_argument("--source", choices=["sim", "can"], default="sim")
    ap.add_argument("--dbc", default=None, help="DBC file of the car (required for --source can)")
    ap.add_argument("--channels", nargs="+", default=["can0", "can1"], help="CAN bus channels (default: can0 can1)")
    ap.add_argument("--interface", default="socketcan", help="python-can interface (default: socketcan)")
    ap.add_argument("--bitrate", type=int, default=500_000, help="CAN bitrate (default: 500000)")
    ap.add_argument("--state", type=int, default=0, help="Initial preset state (0=Live Physics, 1..19=Reference State)")
    ap.add_argument("--demo", "--auto-cycle", dest="auto_cycle", action="store_true", help="Auto-cycle through all 19 design states")
    ap.add_argument("--fullscreen", action="store_true", help="Run fullscreen 800x480 (hides bench toolbar)")
    ap.add_argument("--no-toolbar", action="store_true", help="Hide bottom simulator bench toolbar")
    ap.add_argument("--no-log", action="store_true", help="Don't write CSV logs")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    here = os.path.dirname(os.path.abspath(__file__))
    for f in glob.glob(os.path.join(here, "fonts", "*.[ot]tf")):
        QFontDatabase.addApplicationFont(f)

    if args.source == "can":
        from sources.can_source import CanSource
        if not args.dbc:
            ap.error("--source can needs --dbc (the car's DBC file)")
        source = CanSource(
            dbc_path=args.dbc,
            channels=args.channels,
            bitrate=args.bitrate,
            interface=args.interface,
        )
    else:
        source = SimulatedSource()

    log = None if args.no_log else DataLogger(os.path.join(here, "logs"))
    win = AppWindow(
        source=source,
        pit=SimulatedPitLink(),
        log=log,
        initial_preset_id=args.state,
        auto_cycle=args.auto_cycle,
        show_toolbar=(not args.fullscreen and not args.no_toolbar),
    )
    win.showFullScreen() if args.fullscreen else win.show()
    print(HELP)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
