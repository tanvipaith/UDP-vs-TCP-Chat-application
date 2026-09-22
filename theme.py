"""
theme.py
--------
Shared visual constants for the TCP/UDP Chat Application.
Keeping colors/fonts in one place means the client and server
windows look consistent, and it's easy to re-theme the whole app
by editing only this file.
"""

# ---- Base palette (dark, modern) ----
BG_MAIN = "#12141c"          # window background
BG_PANEL = "#181b26"         # side/top panel background
BG_CARD = "#1f2330"          # cards / input backgrounds
BORDER = "#2a2f3f"

TEXT_PRIMARY = "#eef0f6"
TEXT_MUTED = "#8d93a8"

# ---- Protocol accent colors ----
TCP_COLOR = "#3b82f6"        # blue  -> reliable / ordered
UDP_COLOR = "#f97316"        # orange -> fast / unreliable

# ---- Status colors ----
GREEN_OK = "#22c55e"
RED_ERR = "#ef4444"
YELLOW_WARN = "#eab308"

# ---- Chat bubble colors ----
BUBBLE_SENT = "#3b82f6"          # my outgoing, delivered
BUBBLE_SENT_TEXT = "#ffffff"
BUBBLE_RECEIVED = "#2a2f3f"       # incoming from the other side
BUBBLE_RECEIVED_TEXT = "#eef0f6"
BUBBLE_DROPPED = "#3a1f22"        # simulated packet loss
BUBBLE_DROPPED_BORDER = "#ef4444"
BUBBLE_DROPPED_TEXT = "#f3b4b4"
BUBBLE_SYSTEM_TEXT = "#8d93a8"

FONT_FAMILY = "Segoe UI"      # falls back gracefully on Linux/Mac
FONT_MONO = "Consolas"

CORNER_RADIUS = 14
