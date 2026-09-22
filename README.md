# TCP / UDP Chat Application

A desktop chat app (Python + Tkinter/CustomTkinter) that lets you switch
between raw **TCP** and **UDP** sockets and see the reliability difference
between them live, including a simulated packet-loss demo for UDP.

## Files
- `server.py` — runs a TCP server and a UDP server at the same time (two ports, two threads)
- `client.py` — GUI client with a TCP/UDP switch, IP/port fields, chat bubbles, and a packet-loss slider
- `theme.py` — shared colors/fonts used by both windows
- `requirements.txt` — the one third-party dependency

## Setup
```bash
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```
Tkinter itself ships with standard Python on Windows/macOS. On Linux, if you
get an error about `_tkinter`, install it once with:
```bash
sudo apt-get install python3-tk
```

## Running the demo
1. **Start the server first:**
   ```bash
   python3 server.py
   ```
   Leave the host as `0.0.0.0`, ports as `5050` (TCP) / `5001` (UDP), and click **Start Server**.

2. **Start the client:**
   ```bash
   python3 client.py
   ```
   Set Server IP to `127.0.0.1` (if running on the same machine), pick **TCP** or **UDP**,
   click **Connect**, and start sending messages.

3. **Demonstrate the difference:**
   - In **TCP** mode, send 10–20 messages quickly — every single one arrives at the
     server and every ACK comes back to the client. Sent == Received, Dropped stays 0.
   - Switch to **UDP** mode, set the "Simulated packet loss" slider (e.g. 30%), and
     send the same messages — you'll see some bubbles marked **✕ dropped** in red,
     and the Dropped counter climbing, because those packets were never actually
     transmitted (simulating real-world UDP loss).
   - You can run a second `client.py` instance to chat from two clients into the
     same server at once.

## Ports
- TCP default: `5050`
- UDP default: `5001`
(The client auto-fills whichever default matches the protocol you select, but you can change them.)
