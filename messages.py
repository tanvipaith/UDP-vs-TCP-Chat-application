"""
messages.py
-----------
Defines the tiny wire format shared by the Field Unit and Command Center.

A field report travels over TCP or UDP as one plain UTF-8 string:

        CALLSIGN|PRIORITY|message text

e.g.    ALPHA-1|CRITICAL|Bridge collapsed, 3 people trapped

The server echoes it back unchanged with an "ACK:" prefix, which is how
the client knows the report was received. Because the format is just a
string, the socket code (TCP/UDP, send/recv, ACK) is exactly the same as
in a plain chat app.
"""

PRIORITIES = ("ROUTINE", "URGENT", "CRITICAL")
SEPARATOR = "|"


def encode_message(callsign: str, priority: str, text: str) -> str:
    callsign = (callsign or "UNIT").replace(SEPARATOR, "-").strip() or "UNIT"
    return SEPARATOR.join([callsign, priority, text])


def decode_message(raw: str) -> tuple[str, str, str]:
    """Return (callsign, priority, text). Falls back gracefully if a
    packet doesn't follow the format (e.g. from some other client)."""
    parts = raw.split(SEPARATOR, 2)
    if len(parts) == 3 and parts[1] in PRIORITIES:
        return parts[0], parts[1], parts[2]
    return "UNKNOWN", "ROUTINE", raw
