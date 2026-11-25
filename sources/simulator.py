"""A simple physics-ish simulator that stands in for the car's CAN bus."""
import math
from dataclasses import replace
from typing import Optional

import config
from model import VehicleData
from sources.base import VehicleSource

SIM_PACK_KWH = 5.0          # simulated battery size (not the real pack)
SIM_KWH_PER_KM = 0.02       # simulated consumption, used for the range estimate


class SimulatedSource(VehicleSource):
    def __init__(self, start_soc: float = 74.0):
        self.v = VehicleData(speed_kmh=55.0, soc_pct=start_soc, motor_temp_c=60, ctrl_temp_c=52)
        self.target: Optional[float] = 65.0
        self.t = 0.0
        self.last = None
        self.bus_silent = False          # toggled to simulate CAN loss
        self.motor_overheat = False
        self.ctrl_overheat = False

    # --- controls used by the keyboard in main.py --------------------------
    def toggle(self, name: str) -> None:
        if name in ("motor_overheat", "ctrl_overheat", "bus_silent"):
            setattr(self, name, not getattr(self, name))
        else:
            setattr(self.v, name, not getattr(self.v, name))

    def toggle_gear(self) -> None:
        self.v.gear = "R" if self.v.gear == "D" else "D"

    def set_target_hint(self, target_kmh: Optional[float]) -> None:
        if target_kmh is not None:
            self.target = target_kmh

    # --- VehicleSource -----------------------------------------------------
    def poll(self, now: float) -> Optional[VehicleData]:
        dt = 0.05 if self.last is None else min(0.5, now - self.last)
        self.last = now
        self.t += dt
        self._step(dt)
        return None if self.bus_silent else replace(self.v)

    def _step(self, dt: float) -> None:
        v = self.v
        if v.safe_state:
            desired = 0.0
        elif v.gear == "R":
            desired = 4.0
        else:
            wobble = 4.0 * math.sin(self.t / 7.0) + 2.0 * math.sin(self.t / 2.3)
            desired = (self.target or 60.0) + wobble

        prev = v.speed_kmh
        v.speed_kmh = max(0.0, prev + (desired - prev) * min(1.0, 0.6 * dt))
        accel = (v.speed_kmh - prev) / dt if dt else 0.0       # km/h per second

        if v.safe_state:
            v.power_kw = 0.0
        elif accel < -0.4:
            v.power_kw = max(-config.REGEN_MAX_KW, 0.6 * accel)  # regen braking
        else:
            v.power_kw = min(config.POWER_MAX_KW, 0.4 + 0.022 * v.speed_kmh + 0.5 * max(0.0, accel))

        v.soc_pct = max(0.0, v.soc_pct - v.power_kw * dt / 3600 / SIM_PACK_KWH * 100)
        v.range_km = v.soc_pct / 100 * SIM_PACK_KWH / SIM_KWH_PER_KM

        motor_goal = 45 + 9 * max(0.0, v.power_kw) + (50 if self.motor_overheat else 0)
        ctrl_goal = 40 + 6 * max(0.0, v.power_kw) + (45 if self.ctrl_overheat else 0)
        v.motor_temp_c += (motor_goal - v.motor_temp_c) * min(1.0, 0.25 * dt)
        v.ctrl_temp_c += (ctrl_goal - v.ctrl_temp_c) * min(1.0, 0.25 * dt)
