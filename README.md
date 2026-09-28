# Disaster Response Communication System

A desktop app where rescue **Field Units** send reports to a **Command Center**
over raw **TCP** or **UDP** sockets, with live acknowledgements, statistics and
a UDP packet-loss simulator that shows the reliability difference between the two.

## Files
- `server.py` : Command Center. Runs a TCP server and a UDP server at once (two ports, two threads) and shows incoming reports as cards.
- `client.py` : Field Unit. TCP/UDP switch, IP/port, callsign, priority, chat bubbles, packet-loss slider, Sent/Received/Dropped stats.
- `messages.py` : the small wire format shared by both (`CALLSIGN|PRIORITY|text`).
- `theme.py` : colors and fonts (white, minimal theme) for both windows.
- `requirements.txt` : one dependency (`customtkinter`).

## Setup
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
On Linux, if you get an error about `_tkinter`: `sudo apt-get install python3-tk`

## Run
1. `python3 server.py` then click **Start Server** (TCP 5000, UDP 5001).
2. `python3 client.py`, keep IP `127.0.0.1`, pick **TCP** or **UDP**, click **Connect**.
3. Choose a priority, type a report, press **Send**.

## Demo
- **TCP:** send 10 reports. Sent equals Received, Dropped stays 0.
- **UDP:** set the packet-loss slider to about 40% and send 10 reports. Some bubbles
  show "Packet lost — not delivered", the Dropped counter rises, and the Command
  Center only shows the reports that actually got through.
- Run a second `client.py` with a different callsign to simulate two rescue teams.
