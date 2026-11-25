"""Data structures shared by the sources, the logic and the UI."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VehicleData:
    """Raw signals that come from the car (CAN bus or the simulator)."""
    speed_kmh: float = 0.0
    power_kw: float = 0.0          # + drive, - regen
    soc_pct: float = 100.0
    range_km: float = 0.0
    motor_temp_c: float = 25.0
    ctrl_temp_c: float = 25.0
    gear: str = "D"                # "D" or "R"
    turn_left: bool = False
    turn_right: bool = False
    hazard: bool = False
    bms_fault: bool = False
    imd_fault: bool = False
    safe_state: bool = False
    low_tire: bool = False


@dataclass
class PitData:
    """What arrives from the pit over the telemetry link."""
    target_kmh: Optional[float] = None
    link_up: bool = True
    last_heartbeat: float = 0.0


@dataclass
class Message:
    text: str
    received_at: float


@dataclass
class DisplayState:
    """Everything the UI needs, already decided by the logic layer.

    The UI only draws this; it never decides what is a fault.
    """
    vehicle: VehicleData = field(default_factory=VehicleData)
    target_kmh: Optional[float] = None
    target_mode: str = "none"      # "none" | "on" | "below" (speed up) | "above" (slow down)
    stale: bool = False            # CAN data frozen -> grey out values
    data_status: str = "ok"        # "ok" | "lost" | "recovering"
    no_link: bool = False
    motor_hot: bool = False
    ctrl_hot: bool = False
    soc_level: str = "ok"          # "ok" | "amber" | "red"
    blink_on: bool = True
    pit_active: bool = False
    pit_lock_left: int = 0
    message: Optional[Message] = None
    message_left_s: int = 0
    queued: int = 0
    lap: int = 0
    stint_s: int = 0
