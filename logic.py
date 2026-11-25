"""Turns raw vehicle + pit data into a DisplayState.

All "is this a warning?" decisions live here, so they can be unit-tested
without a screen and stay identical whether data comes from CAN or the
simulator.
"""
from collections import deque
from dataclasses import replace
from typing import Deque, Optional

import config
from model import DisplayState, Message, PitData, VehicleData


class DashboardLogic:
    def __init__(self, start_time: float):
        self.start = start_time
        self.last_vehicle: Optional[VehicleData] = None
        self.last_rx: Optional[float] = None
        self.lost_since: Optional[float] = None
        self.recovering_until = start_time + config.RECOVERING_S   # boot: show RECOVERING until data flows
        self.messages: Deque[Message] = deque()
        self.current: Optional[Message] = None
        self.pit_active = False
        self.pit_locked_until = 0.0
        self.lap = 1
        self.lap_started = start_time

    # --- driver / pit events ----------------------------------------------
    def push_message(self, text: str, now: float) -> None:
        self.messages.append(Message(text, now))

    def ok_pressed(self, now: float) -> Optional[str]:
        """Wheel OK: dismiss the current message. Returns the acked text."""
        if self.current is None:
            return None
        acked = self.current.text
        self._next_message(now)
        return acked

    def pit_pressed(self, now: float) -> bool:
        """Pit button from either side. Ignored while locked (anti double-press)."""
        if now < self.pit_locked_until:
            return False
        self.pit_active = not self.pit_active
        if self.pit_active:
            self.pit_locked_until = now + config.PIT_LOCK_S
        return True

    def new_lap(self, now: float) -> None:
        self.lap += 1
        self.lap_started = now

    def _next_message(self, now: float) -> None:
        self.current = None
        if self.messages:
            m = self.messages.popleft()
            self.current = Message(m.text, now)       # timer starts when it is shown

    # --- main update --------------------------------------------------------
    def update(self, now: float, vehicle: Optional[VehicleData], pit: PitData) -> DisplayState:
        if vehicle is not None:
            if self.lost_since is not None:          # data came back after a loss
                self.recovering_until = now + config.RECOVERING_S
                self.lost_since = None
            self.last_vehicle = vehicle
            self.last_rx = now
        elif self.last_rx is not None and now - self.last_rx > config.CAN_TIMEOUT_S and self.lost_since is None:
            self.lost_since = now

        if self.lost_since is not None or (self.last_rx is None and now >= self.recovering_until):
            data_status = "lost"
        elif now < self.recovering_until:
            data_status = "recovering"
        else:
            data_status = "ok"

        v = replace(self.last_vehicle) if self.last_vehicle else VehicleData()
        stale = data_status == "lost"

        # target speed: hidden in reverse / safe state / without a target
        target = pit.target_kmh
        if target is None or v.gear == "R" or v.safe_state:
            mode = "none"
        elif v.speed_kmh < target - config.TARGET_TOLERANCE_KMH:
            mode = "below"
        elif v.speed_kmh > target + config.TARGET_TOLERANCE_KMH:
            mode = "above"
        else:
            mode = "on"

        # messages: show the next queued one, expire after the timeout
        if self.current is None:
            self._next_message(now)
        elif now - self.current.received_at >= config.MESSAGE_TIMEOUT_S:
            self._next_message(now)
        msg_left = 0
        if self.current is not None:
            msg_left = max(0, int(round(config.MESSAGE_TIMEOUT_S - (now - self.current.received_at))))

        soc_level = "ok"
        if v.soc_pct < config.SOC_RED_PCT:
            soc_level = "red"
        elif v.soc_pct < config.SOC_AMBER_PCT:
            soc_level = "amber"

        blinking = v.turn_left or v.turn_right or v.hazard
        blink_on = (not blinking) or int((now - self.start) / (config.BLINK_PERIOD_S / 2)) % 2 == 0

        return DisplayState(
            vehicle=v,
            target_kmh=target if mode != "none" else None,
            target_mode=mode,
            stale=stale,
            data_status=data_status,
            no_link=(now - pit.last_heartbeat) > config.PIT_LINK_TIMEOUT_S,
            motor_hot=v.motor_temp_c >= config.MOTOR_HOT_C,
            ctrl_hot=v.ctrl_temp_c >= config.CTRL_HOT_C,
            soc_level=soc_level,
            blink_on=blink_on,
            pit_active=self.pit_active,
            pit_lock_left=max(0, int(round(self.pit_locked_until - now))) if self.pit_active else 0,
            message=self.current,
            message_left_s=msg_left,
            queued=len(self.messages),
            lap=self.lap,
            stint_s=int(now - self.start),
        )
