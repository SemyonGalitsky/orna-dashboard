"""Unit tests for the dashboard logic, presets, and threaded CAN source (no screen needed):
    python -m pytest tests
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from logic import DashboardLogic
from model import PitData, VehicleData
from presets import PRESET_LIST, PRESETS_BY_ID, STATES


def run(logic, t, vehicle, target=65.0, heartbeat=None):
    pit = PitData(target_kmh=target, last_heartbeat=t if heartbeat is None else heartbeat)
    return logic.update(t, vehicle, pit)


def test_recovering_at_boot_then_ok():
    lg = DashboardLogic(0.0)
    assert run(lg, 0.1, None).data_status == "recovering"
    assert run(lg, config.RECOVERING_S + 0.1, VehicleData()).data_status == "ok"


def test_can_loss_greys_out_and_recovers():
    lg = DashboardLogic(0.0)
    run(lg, 5.0, VehicleData(speed_kmh=60))
    s = run(lg, 5.0 + config.CAN_TIMEOUT_S + 0.1, None)
    assert s.data_status == "lost" and s.stale and s.vehicle.speed_kmh == 60   # frozen, not invented
    s = run(lg, 10.0, VehicleData(speed_kmh=61))
    assert s.data_status == "recovering" and not s.stale


def test_target_modes():
    lg = DashboardLogic(0.0)
    assert run(lg, 5, VehicleData(speed_kmh=50)).target_mode == "below"
    assert run(lg, 5, VehicleData(speed_kmh=70)).target_mode == "above"
    assert run(lg, 5, VehicleData(speed_kmh=65.5)).target_mode == "on"
    assert run(lg, 5, VehicleData(speed_kmh=3, gear="R")).target_mode == "none"


def test_thresholds():
    lg = DashboardLogic(0.0)
    s = run(lg, 5, VehicleData(motor_temp_c=config.MOTOR_HOT_C, ctrl_temp_c=config.CTRL_HOT_C - 1, soc_pct=10))
    assert s.motor_hot and not s.ctrl_hot and s.soc_level == "red"


def test_no_link_after_timeout():
    lg = DashboardLogic(0.0)
    assert run(lg, 20, VehicleData(), heartbeat=20 - config.PIT_LINK_TIMEOUT_S - 1).no_link


def test_pit_lock_blocks_cancel():
    lg = DashboardLogic(0.0)
    assert lg.pit_pressed(10)
    assert not lg.pit_pressed(10 + config.PIT_LOCK_S - 1)          # locked: ignored
    assert run(lg, 11, VehicleData()).pit_active
    assert lg.pit_pressed(10 + config.PIT_LOCK_S + 1)              # after the lock: cancels
    assert not run(lg, 60, VehicleData()).pit_active


def test_message_queue_ok_and_timeout():
    lg = DashboardLogic(0.0)
    lg.push_message("BOX THIS LAP", 1)
    lg.push_message("SAVE ENERGY", 1)
    s = run(lg, 2, VehicleData())
    assert s.message.text == "BOX THIS LAP" and s.queued == 1
    assert lg.ok_pressed(3) == "BOX THIS LAP"
    s = run(lg, 3, VehicleData())
    assert s.message.text == "SAVE ENERGY"
    s = run(lg, 3 + config.MESSAGE_TIMEOUT_S + 0.1, VehicleData())
    assert s.message is None


def test_all_19_presets_catalog():
    assert len(PRESET_LIST) == 19
    assert len(STATES) == 19
    assert PRESETS_BY_ID[1][2].vehicle.speed_kmh == 62
    assert PRESETS_BY_ID[2][2].target_mode == "above"
    assert PRESETS_BY_ID[14][2].stale is True and PRESETS_BY_ID[14][2].data_status == "lost"
    assert PRESETS_BY_ID[18][2].vehicle.gear == "R"


TEST_DBC = """VERSION ""

BU_: MC

BO_ 256 MC_Status: 8 MC
 SG_ MC_VehicleSpeed : 0|16@1+ (0.1,0) [0|200] "km/h" Vector__XXX
 SG_ MC_BusPower : 16|16@1- (1,0) [-5000|5000] "W" Vector__XXX
 SG_ MC_MotorTemp : 32|8@1+ (1,0) [0|200] "C" Vector__XXX
"""


def test_can_source_decodes_dbc_frames(tmp_path):
    cantools = pytest.importorskip("cantools")
    from sources.can_source import CanSource

    dbc = tmp_path / "test.dbc"
    dbc.write_text(TEST_DBC)
    src = CanSource(str(dbc), channels=(), start=False)
    msg = cantools.database.load_file(str(dbc)).get_message_by_name("MC_Status")
    assert src.poll(1.0) is None
    src.inject_test_frame(msg.frame_id, msg.encode({"MC_VehicleSpeed": 62.3, "MC_BusPower": -900, "MC_MotorTemp": 104}))
    v = src.poll(1.05)
    assert abs(v.speed_kmh - 62.3) < 1e-6 and abs(v.power_kw + 0.9) < 1e-6 and v.motor_temp_c == 104
    assert src.poll(1.10) is None                  # no new frames -> None, so CAN LOSS can trigger


def test_can_source_survives_bad_frames(tmp_path):
    pytest.importorskip("cantools")
    from sources.can_source import CanSource

    dbc = tmp_path / "test.dbc"
    dbc.write_text(TEST_DBC)
    src = CanSource(str(dbc), channels=(), start=False)
    src.inject_test_frame(256, b"\x01")          # too short for the DBC message
    src.inject_test_frame(0x7FF, b"\x00" * 8)     # ID not in the DBC
    assert src.poll(1.0) is None                   # ignored, and nothing crashed
