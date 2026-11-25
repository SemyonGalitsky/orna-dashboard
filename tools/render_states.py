"""Saves a PNG of the dashboard in each state (for documents / checking the UI).

    python tools/render_states.py out_folder
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from presets import STATES
from ui.dashboard import Dashboard

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "states"
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in glob.glob(os.path.join(here, "fonts", "*.[ot]tf")):
        QFontDatabase.addApplicationFont(f)
    w = Dashboard()
    w.resize(800, 480)
    for name, st in STATES.items():
        w.show_state(st)
        w.grab().save(os.path.join(out, f"{name}.png"))
        print("saved", name)
