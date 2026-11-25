"""Real CAN bus source.

Swap the simulator for this with:  python main.py --source can --dbc orna.dbc

A background thread reads frames with python-can (so no frame is lost and the
UI never waits for the bus), decodes them with the team's DBC file (cantools)
and maps DBC signal names to VehicleData fields. If the CAN interface can't be
opened (cable, driver, HAT), the dashboard keeps running and shows CAN LOSS,
and the thread retries every few seconds.

The decoding was tested on a virtual CAN bus, NOT on the car. The signal
names below are placeholders: replace them with the names in the team's DBC.

Requires:  pip install python-can cantools
"""
import threading
import time
from dataclasses import replace
from typing import Callable, Dict, Optional, Tuple

from model import VehicleData
from sources.base import VehicleSource

# DBC signal name -> (VehicleData field, conversion)
SIGNAL_MAP: Dict[str, Tuple[str, Callable]] = {
    "MC_VehicleSpeed": ("speed_kmh", float),        # TODO: real names from the team's DBC
    "MC_BusPower":     ("power_kw", lambda w: float(w) / 1000.0),
    "MC_MotorTemp":    ("motor_temp_c", float),
    "MC_ControllerTemp": ("ctrl_temp_c", float),
    "MC_Direction":    ("gear", lambda d: "R" if int(d) == 1 else "D"),
    "BMS_SOC":         ("soc_pct", float),
    "BMS_FaultActive": ("bms_fault", bool),
    "IMD_Fault":       ("imd_fault", bool),
    "VCU_SafeState":   ("safe_state", bool),
    "VCU_TurnLeft":    ("turn_left", bool),
    "VCU_TurnRight":   ("turn_right", bool),
    "VCU_Hazard":      ("hazard", bool),
    "TPMS_LowPressure": ("low_tire", bool),
}

KWH_PER_KM = 0.02            # TODO: replace with the strategy team's consumption model
PACK_KWH = 5.0               # TODO: real pack capacity
RETRY_S = 3.0                # how often to retry opening a CAN interface


class _Frame:
    def __init__(self, arbitration_id: int, data: bytes):
        self.arbitration_id, self.data = arbitration_id, data


class CanSource(VehicleSource):
    def __init__(self, dbc_path: str, channels=("can0", "can1"), bitrate: int = 500_000,
                 interface: str = "socketcan", start: bool = True):
        import cantools   # imported here so the simulator runs without these packages

        self.db = cantools.database.load_file(dbc_path)
        self.channels, self.bitrate, self.interface = channels, bitrate, interface
        self.v = VehicleData()
        self._lock = threading.Lock()
        self._fresh = False
        self._running = True
        self._threads = [threading.Thread(target=self._reader, args=(ch,), daemon=True) for ch in channels]
        if start:
            for t in self._threads:
                t.start()

    def _reader(self, channel: str) -> None:
        import can
        while self._running:
            try:
                bus = can.interface.Bus(channel=channel, interface=self.interface, bitrate=self.bitrate)
            except Exception as exc:                     # interface missing: dashboard shows CAN LOSS
                print(f"[can] cannot open {channel}: {exc} (retrying in {RETRY_S:.0f}s)")
                self._sleep_interruptible(RETRY_S)
                continue
            try:
                while self._running:
                    msg = bus.recv(timeout=0.1)
                    if msg is not None:
                        self._decode(msg)
            except Exception as exc:                     # bus error mid-race: reopen
                print(f"[can] {channel} error: {exc} (reopening)")
            finally:
                bus.shutdown()

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(0.05)

    def _decode(self, msg) -> None:
        try:
            signals = self.db.decode_message(msg.arbitration_id, msg.data)
        except Exception:                                # unknown ID, wrong length, bad value:
            return                                       # skip the frame, never kill the reader
        with self._lock:
            for name, value in signals.items():
                if name in SIGNAL_MAP:
                    field, conv = SIGNAL_MAP[name]
                    setattr(self.v, field, conv(value))
            self._fresh = True

    def inject_test_frame(self, arb_id: int, data: bytes) -> None:
        """For unit tests: feed a raw frame without CAN hardware."""
        self._decode(_Frame(arb_id, bytes(data)))

    def poll(self, now: float) -> Optional[VehicleData]:
        with self._lock:
            if not self._fresh:
                return None
            self._fresh = False
            self.v.range_km = self.v.soc_pct / 100 * PACK_KWH / KWH_PER_KM
            return replace(self.v)

    def close(self) -> None:
        self._running = False
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=1.0)
