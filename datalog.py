"""Writes raw vehicle data and events to CSV, for the engineers in the pit."""
import csv
import os
import time
from dataclasses import asdict, fields

from model import VehicleData


class DataLogger:
    def __init__(self, folder: str = "logs"):
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._data_f = open(os.path.join(folder, f"telemetry_{stamp}.csv"), "w", newline="")
        self._event_f = open(os.path.join(folder, f"events_{stamp}.csv"), "w", newline="")
        self._data = csv.writer(self._data_f)
        self._events = csv.writer(self._event_f)
        self._data.writerow(["time", "data_status"] + [f.name for f in fields(VehicleData)])
        self._events.writerow(["time", "event", "detail"])
        self._rows = 0

    def log(self, now: float, v: VehicleData, data_status: str) -> None:
        row = asdict(v)
        self._data.writerow([f"{now:.2f}", data_status] + [
            f"{x:.2f}" if isinstance(x, float) else x for x in row.values()])
        self._rows += 1
        if self._rows % 10 == 0:          # flush ~once/sec at 10 Hz so power loss loses <= 1 s
            self._data_f.flush()

    def event(self, now: float, name: str, detail: str = "") -> None:
        self._events.writerow([f"{now:.2f}", name, detail])
        self._event_f.flush()

    def close(self) -> None:
        self._data_f.close()
        self._event_f.close()
