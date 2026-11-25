"""Thresholds, scales and timing for the ORNA driver dashboard.

Everything the team may want to tune lives here, so the logic and the UI
never contain magic numbers. Values marked "ASSUMED" must be confirmed with
the team before the race.
"""

# --- Screen -----------------------------------------------------------------
SCREEN_W, SCREEN_H = 800, 480          # 7" driver display
UPDATE_HZ = 20                         # UI refresh / logic rate
LOG_HZ = 10                            # raw-data logging rate

# --- Gauge ------------------------------------------------------------------
SPEED_MAX_KMH = 120                    # ASSUMED: car top speed (gauge scale)
SPEED_REDLINE_KMH = 110                # ticks drawn red from here
TARGET_TOLERANCE_KMH = 1.0             # inside +/- this: no speed-up/slow-down band

# --- Power bar --------------------------------------------------------------
POWER_MAX_KW = 5.0                     # ASSUMED: full scale for drive power
REGEN_MAX_KW = 2.5                     # ASSUMED: full scale for regen

# --- Warning thresholds -----------------------------------------------------
MOTOR_HOT_C = 95                       # ASSUMED
CTRL_HOT_C = 85                        # ASSUMED
MOTOR_TEMP_SCALE_C = 130               # bar full scale
CTRL_TEMP_SCALE_C = 120
SOC_AMBER_PCT = 30                     # SOC/range turn amber below this
SOC_RED_PCT = 15                       # ... and red below this

# --- Data health ------------------------------------------------------------
CAN_TIMEOUT_S = 2.0                    # no CAN data for this long -> CAN LOSS
RECOVERING_S = 3.0                     # show RECOVERING after data comes back
PIT_LINK_TIMEOUT_S = 5.0               # no pit heartbeat for this long -> NO LINK

# --- Pit messages / pit light ----------------------------------------------
MESSAGE_TIMEOUT_S = 30                 # pop-up disappears after this
MESSAGE_MAX_CHARS = 40                 # keeps the text big enough to read
PIT_LOCK_S = 45                        # pit light can't be cancelled during this

# --- Turn signals (regulation 2.24.12: 90 +/- 30 flashes per minute) --------
BLINK_PERIOD_S = 60 / 90

# --- Bench / Simulator Toolbar ----------------------------------------------
AUTO_CYCLE_S = 3.0                     # seconds per state in Auto-Cycle mode
