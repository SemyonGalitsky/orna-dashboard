"""The pit <-> car link (target speed, messages, pit light, acknowledgements).

In the car this runs over cellular (today: Firebase / FastAPI). Here it is
simulated from the keyboard, behind the same small interface, so a real
network implementation can replace SimulatedPitLink later.
"""
from typing import List

import config
from model import PitData

PRESET_MESSAGES = [
    "BOX THIS LAP",
    "PUSH +5 KM/H",
    "SAVE ENERGY",
    "DRIVER CHANGE NEXT LAP",
    "CHECK MOTOR TEMP",
]


class SimulatedPitLink:
    def __init__(self, target_kmh: float = 65.0):
        self.data = PitData(target_kmh=target_kmh, link_up=True)
        self._inbox: List[str] = []
        self._next_preset = 0
        self.pit_request = False
        self.sent: List[str] = []           # what the car sent back (acks, pit presses)

    # --- pit side (keyboard) ----------------------------------------------
    def toggle_link(self) -> None:
        self.data.link_up = not self.data.link_up

    def change_target(self, delta: float) -> None:
        if self.data.link_up and self.data.target_kmh is not None:
            self.data.target_kmh = max(0.0, min(config.SPEED_MAX_KMH, self.data.target_kmh + delta))

    def send_preset(self) -> None:
        if self.data.link_up:
            self._inbox.append(PRESET_MESSAGES[self._next_preset % len(PRESET_MESSAGES)])
            self._next_preset += 1

    def press_pit(self) -> None:
        if self.data.link_up:
            self.pit_request = True

    # --- car side ---------------------------------------------------------
    def poll(self, now: float) -> PitData:
        if self.data.link_up:
            self.data.last_heartbeat = now
        return self.data

    def take_messages(self) -> List[str]:
        msgs, self._inbox = self._inbox, []
        return [m[: config.MESSAGE_MAX_CHARS] for m in msgs]

    def take_pit_request(self) -> bool:
        req, self.pit_request = self.pit_request, False
        return req

    def send_to_pit(self, event: str) -> None:
        """Acks and pit presses go back over the link (queued if it's down)."""
        self.sent.append(event)
