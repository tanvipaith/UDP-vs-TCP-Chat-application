"""
theme.py
--------
Shared visual constants for the Disaster Response Communication System.
Both the Command Center (server) and Field Unit (client) windows read
their colors and fonts from here, so the two apps always look consistent
and the whole look can be changed by editing only this file.

Design language: white background, slate text, thin light borders, and
one accent color per protocol (blue = TCP, orange = UDP).
"""

# ---- Base palette (white, minimal) ----
BG_MAIN = "#ffffff"
BG_PANEL = "#f8fafc"
BORDER = "#e2e8f0"

TEXT_PRIMARY = "#0f172a"
TEXT_MUTED = "#64748b"

BUTTON = "#0f172a"
BUTTON_HOVER = "#1e293b"

# ---- Protocol accents: (strong color, soft background, label) ----
TCP_COLOR = "#2563eb"
TCP_SOFT = "#eff6ff"
UDP_COLOR = "#ea580c"
UDP_SOFT = "#fff7ed"
PROTOCOL_STYLE = {
    "TCP": (TCP_COLOR, TCP_SOFT, "TCP · Reliable"),
    "UDP": (UDP_COLOR, UDP_SOFT, "UDP · Best effort"),
}

# ---- Status colors ----
GREEN_OK = "#16a34a"
RED_ERR = "#dc2626"
YELLOW_WARN = "#d97706"

# ---- Message priority colors ----
PRIORITY_COLORS = {
    "ROUTINE": "#64748b",
    "URGENT": "#d97706",
    "CRITICAL": "#dc2626",
}

# ---- Chat bubble colors ----
BUBBLE_SENT = "#eff6ff"
BUBBLE_SENT_BORDER = "#bfdbfe"
BUBBLE_RECEIVED = "#f1f5f9"
BUBBLE_RECEIVED_BORDER = "#e2e8f0"
BUBBLE_DROPPED = "#fef2f2"
BUBBLE_DROPPED_BORDER = "#fca5a5"
BUBBLE_DROPPED_TEXT = "#b91c1c"

FONT_FAMILY = "Segoe UI"     # falls back to a system sans-serif elsewhere
FONT_MONO = "Consolas"

CORNER_RADIUS = 12
