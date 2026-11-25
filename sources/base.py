"""The interface every vehicle-data source implements.

The dashboard only talks to this interface, so the simulator and the real
CAN bus are interchangeable: pick one in main.py with --source sim|can.
"""
from abc import ABC, abstractmethod
from typing import Optional

from model import VehicleData


class VehicleSource(ABC):
    @abstractmethod
    def poll(self, now: float) -> Optional[VehicleData]:
        """Return the newest vehicle data, or None if nothing new arrived.

        Returning None for long enough is how the logic detects CAN LOSS,
        so a source must never invent data when the bus is silent.
        """

    def set_target_hint(self, target_kmh: Optional[float]) -> None:
        """Only the simulator uses this (to drive near the pit's target)."""

    def close(self) -> None:
        pass
