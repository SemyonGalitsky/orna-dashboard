"""Catalog of all 19 reference dashboard states for instant preset inspection,
automated PNG rendering (`tools/render_states.py`), and the GUI bench toolbar.
"""
from typing import Dict, List, Tuple

from model import DisplayState, Message, VehicleData


def _base(**kw) -> DisplayState:
    v = dict(
        speed_kmh=62,
        power_kw=1.8,
        soc_pct=74,
        range_km=186,
        motor_temp_c=68,
        ctrl_temp_c=59,
    )
    v.update(kw.pop("v", {}))
    s = dict(
        vehicle=VehicleData(**v),
        target_kmh=65,
        target_mode="below",
        lap=23,
        stint_s=6120,  # 01:42 (HH:MM)
    )
    s.update(kw)
    return DisplayState(**s)


# Ordered list of (state_id, slug, display_title, DisplayState)
PRESET_LIST: List[Tuple[int, str, str, DisplayState]] = [
    (1, "driving", "1 · Normal — below target", _base()),
    (2, "over", "2 · Over target — slow down", _base(v=dict(speed_kmh=72), target_mode="above")),
    (3, "ontarget", "3 · On target", _base(v=dict(speed_kmh=65), target_mode="on")),
    (4, "regen", "4 · Regen braking", _base(v=dict(speed_kmh=61, power_kw=-0.9), target_kmh=60, target_mode="on")),
    (5, "turnleft", "5 · Left turn signal", _base(v=dict(turn_left=True))),
    (6, "hazard", "6 · Hazard lights", _base(v=dict(hazard=True))),
    (7, "bms", "7 · BMS fault", _base(v=dict(bms_fault=True))),
    (8, "imd", "8 · IMD fault", _base(v=dict(imd_fault=True))),
    (9, "safestate", "9 · Safe state", _base(v=dict(safe_state=True, speed_kmh=0, power_kw=0), target_kmh=None, target_mode="none")),
    (10, "motorhot", "10 · Motor overheating", _base(v=dict(motor_temp_c=104), motor_hot=True)),
    (11, "ctrlhot", "11 · Controller overheating", _base(v=dict(ctrl_temp_c=92), ctrl_hot=True)),
    (12, "lowtire", "12 · Low tire pressure", _base(v=dict(low_tire=True))),
    (13, "nolink", "13 · No telemetry link", _base(no_link=True)),
    (14, "canloss", "14 · CAN loss — data frozen", _base(stale=True, data_status="lost")),
    (15, "recovering", "15 · System recovering", _base(data_status="recovering")),
    (16, "pit", "16 · Pit light active", _base(pit_active=True, pit_lock_left=45)),
    (17, "message", "17 · Pit message pop-up", _base(message=Message("BOX THIS LAP", 0), message_left_s=24, queued=1)),
    (18, "reverse", "18 · Reverse selected", _base(v=dict(gear="R", speed_kmh=4, power_kw=0.3), target_kmh=None, target_mode="none")),
    (19, "lowsoc", "19 · Low SOC (12%)", _base(v=dict(soc_pct=12, range_km=30), soc_level="red")),
]

STATES: Dict[str, DisplayState] = {slug: st for _, slug, _, st in PRESET_LIST}
PRESETS_BY_ID: Dict[int, Tuple[str, str, DisplayState]] = {
    sid: (slug, title, st) for sid, slug, title, st in PRESET_LIST
}
