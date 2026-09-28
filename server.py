"""
server.py  --  COMMAND CENTER
-----------------------------
The Command Center receives field reports from rescue teams over
TCP *and* UDP at the same time.

The server opens TWO sockets on two different ports:
    - a TCP socket  (socket.SOCK_STREAM)  -> reliable, connection-oriented
    - a UDP socket  (socket.SOCK_DGRAM)   -> unreliable, connectionless

Each socket type runs its own receive loop in its own background thread,
so neither blocks the other. Every report received is echoed back to the
sender as "ACK:<report>" so the field unit knows it was delivered.

Run this FIRST, then start one or more client.py Field Units.
"""

import socket
import threading
import queue
import datetime

import customtkinter as ctk

import messages
import theme

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

DEFAULT_HOST = "0.0.0.0"      # listen on all local network interfaces
DEFAULT_TCP_PORT = 5050
DEFAULT_UDP_PORT = 5001
BUFFER_SIZE = 4096

F = theme.FONT_FAMILY


def now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class CommandCenter(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Command Center — Disaster Response Communication")
        self.geometry("760x680")
        self.minsize(640, 520)
        self.configure(fg_color=theme.BG_MAIN)

        # ---- networking state ----
        self.tcp_socket: socket.socket | None = None
        self.udp_socket: socket.socket | None = None
        self.running = False
        self.tcp_clients: list[socket.socket] = []
        self.tcp_count = 0
        self.udp_count = 0

        # Thread -> GUI communication. Tkinter is NOT thread-safe, so
        # worker threads never touch widgets directly; they push events
        # onto this queue and the GUI thread drains it with `after()`.
        self.event_queue: "queue.Queue[tuple]" = queue.Queue()

        self._build_ui()
        self.after(100, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        # ---- header ----
        header = ctk.CTkFrame(self, fg_color=theme.BG_MAIN, corner_radius=0)
        header.pack(fill="x")
        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left", padx=24, pady=16)
        ctk.CTkLabel(title, text="COMMAND CENTER", font=(F, 11, "bold"),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        ctk.CTkLabel(title, text="Incoming Field Reports", font=(F, 20, "bold"),
                     text_color=theme.TEXT_PRIMARY).pack(anchor="w")

        status = ctk.CTkFrame(header, fg_color="transparent")
        status.pack(side="right", padx=24)
        self.status_dot = ctk.CTkLabel(status, text="●", text_color=theme.RED_ERR, font=(F, 16))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = ctk.CTkLabel(status, text="Offline", text_color=theme.TEXT_MUTED, font=(F, 12))
        self.status_label.pack(side="left")

        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x")

        # ---- control card: host / ports / start-stop ----
        card = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, border_width=1,
                            border_color=theme.BORDER, corner_radius=theme.CORNER_RADIUS)
        card.pack(fill="x", padx=24, pady=(16, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        def field(col, label, default, width):
            ctk.CTkLabel(inner, text=label, font=(F, 11), text_color=theme.TEXT_MUTED
                         ).grid(row=0, column=col, sticky="w", padx=(0, 12))
            entry = ctk.CTkEntry(inner, width=width, fg_color=theme.BG_MAIN, border_color=theme.BORDER,
                                 border_width=1, text_color=theme.TEXT_PRIMARY)
            entry.insert(0, default)
            entry.grid(row=1, column=col, sticky="w", padx=(0, 12), pady=(2, 0))
            return entry

        self.host_entry = field(0, "Host", DEFAULT_HOST, 130)
        self.tcp_port_entry = field(1, "TCP port", str(DEFAULT_TCP_PORT), 90)
        self.udp_port_entry = field(2, "UDP port", str(DEFAULT_UDP_PORT), 90)

        self.start_btn = ctk.CTkButton(
            inner, text="Start Server", width=130, fg_color=theme.BUTTON,
            hover_color=theme.BUTTON_HOVER, command=self.toggle_server
        )
        self.start_btn.grid(row=1, column=3, sticky="e", padx=(12, 0), pady=(2, 0))
        inner.grid_columnconfigure(3, weight=1)

        # ---- stats strip ----
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=24, pady=(12, 0))
        self.tcp_stat = self._stat_card(stats, "TCP reports", theme.TCP_COLOR)
        self.tcp_stat.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.udp_stat = self._stat_card(stats, "UDP reports", theme.UDP_COLOR)
        self.udp_stat.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        stats.grid_columnconfigure(0, weight=1)
        stats.grid_columnconfigure(1, weight=1)

        # ---- scrollable report feed ----
        self.feed = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_MAIN, border_width=1, border_color=theme.BORDER,
            corner_radius=theme.CORNER_RADIUS
        )
        self.feed.pack(fill="both", expand=True, padx=24, pady=16)

    def _stat_card(self, parent, label, color):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_MAIN, border_width=1,
                            border_color=theme.BORDER, corner_radius=theme.CORNER_RADIUS)
        ctk.CTkLabel(card, text=label, font=(F, 11), text_color=theme.TEXT_MUTED
                     ).pack(anchor="w", padx=14, pady=(10, 0))
        value_label = ctk.CTkLabel(card, text="0", text_color=color, font=(F, 24, "bold"))
        value_label.pack(anchor="w", padx=14, pady=(0, 10))
        card.value_label = value_label
        return card

    def _scroll_to_bottom(self):
        self.feed.update_idletasks()
        self.feed._parent_canvas.yview_moveto(1.0)

    def _log(self, text, color=theme.TEXT_MUTED):
        """A small centered system line (server started, client connected...)."""
        ctk.CTkLabel(self.feed, text=text, text_color=color, font=(F, 11, "italic")
                     ).pack(pady=4)
        self._scroll_to_bottom()

    def _report_card(self, proto, addr, raw):
        """One incoming field report shown as a clean bordered card."""
        callsign, priority, text = messages.decode_message(raw)
        color, soft, _ = theme.PROTOCOL_STYLE[proto]
        prio_color = theme.PRIORITY_COLORS[priority]
        border = prio_color if priority == "CRITICAL" else theme.BORDER

        card = ctk.CTkFrame(self.feed, fg_color=theme.BG_MAIN, border_width=1,
                            border_color=border, corner_radius=theme.CORNER_RADIUS)
        card.pack(fill="x", padx=6, pady=5)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(top, text=callsign, font=(F, 13, "bold"),
                     text_color=theme.TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(top, text=priority, font=(F, 10, "bold"),
                     text_color=prio_color).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(top, text=proto, fg_color=soft, text_color=color, corner_radius=8,
                     width=44, height=20, font=(F, 10, "bold")).pack(side="right")

        ctk.CTkLabel(card, text=text, wraplength=560, justify="left", font=(F, 13),
                     text_color=theme.TEXT_PRIMARY).pack(anchor="w", padx=14, pady=(4, 2))
        ctk.CTkLabel(card, text=f"{now()}  ·  {addr[0]}:{addr[1]}", font=(F, 10),
                     text_color=theme.TEXT_MUTED).pack(anchor="w", padx=14, pady=(0, 10))
        self._scroll_to_bottom()

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------
    def toggle_server(self):
        if not self.running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        host = self.host_entry.get().strip() or DEFAULT_HOST
        try:
            tcp_port = int(self.tcp_port_entry.get())
            udp_port = int(self.udp_port_entry.get())
        except ValueError:
            self._log("Ports must be numbers.", theme.RED_ERR)
            return

        self.running = True
        threading.Thread(target=self._run_tcp_server, args=(host, tcp_port), daemon=True).start()
        threading.Thread(target=self._run_udp_server, args=(host, udp_port), daemon=True).start()

        self.start_btn.configure(text="Stop Server", fg_color=theme.RED_ERR, hover_color="#b91c1c")
        self.status_dot.configure(text_color=theme.GREEN_OK)
        self.status_label.configure(text=f"Online — TCP {tcp_port} · UDP {udp_port}")
        self._log(f"{now()}  Command Center online on {host} (TCP {tcp_port} / UDP {udp_port})")

    def stop_server(self):
        self.running = False
        for sock in (self.tcp_socket, self.udp_socket):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        self.start_btn.configure(text="Start Server", fg_color=theme.BUTTON, hover_color=theme.BUTTON_HOVER)
        self.status_dot.configure(text_color=theme.RED_ERR)
        self.status_label.configure(text="Offline")
        self._log(f"{now()}  Command Center offline.")

    def _on_close(self):
        self.stop_server()
        self.destroy()

    # ------------------------------------------------------------------
    # TCP server loop  (runs on a background thread)
    # ------------------------------------------------------------------
    def _run_tcp_server(self, host, port):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((host, port))
            srv.listen(5)
        except OSError as exc:
            self.event_queue.put(("error", f"TCP bind failed: {exc}"))
            return
        self.tcp_socket = srv

        while self.running:
            try:
                conn, addr = srv.accept()
            except OSError:
                break  # socket was closed by stop_server()
            self.tcp_clients.append(conn)
            self.event_queue.put(("system", f"Field unit connected via TCP ({addr[0]}:{addr[1]})"))
            threading.Thread(target=self._handle_tcp_client, args=(conn, addr), daemon=True).start()

    def _handle_tcp_client(self, conn: socket.socket, addr):
        """One thread per connected TCP client -- the socket stays open for
        the whole conversation, which is what makes TCP 'connection-oriented'."""
        while self.running:
            try:
                data = conn.recv(BUFFER_SIZE)
            except OSError:
                break
            if not data:
                break  # client closed the connection cleanly
            text = data.decode("utf-8", errors="replace")
            self.tcp_count += 1
            self.event_queue.put(("tcp_recv", addr, text))
            try:
                conn.sendall(f"ACK:{text}".encode("utf-8"))
            except OSError:
                break
        if conn in self.tcp_clients:
            self.tcp_clients.remove(conn)
        self.event_queue.put(("system", f"Field unit disconnected ({addr[0]}:{addr[1]})"))
        conn.close()

    # ------------------------------------------------------------------
    # UDP server loop (runs on a background thread)
    # ------------------------------------------------------------------
    def _run_udp_server(self, host, port):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            srv.bind((host, port))
        except OSError as exc:
            self.event_queue.put(("error", f"UDP bind failed: {exc}"))
            return
        self.udp_socket = srv

        # UDP has no accept()/connection -- every packet is independent,
        # so one loop with recvfrom() handles every sender.
        while self.running:
            try:
                data, addr = srv.recvfrom(BUFFER_SIZE)
            except OSError:
                break
            text = data.decode("utf-8", errors="replace")
            self.udp_count += 1
            self.event_queue.put(("udp_recv", addr, text))
            try:
                srv.sendto(f"ACK:{text}".encode("utf-8"), addr)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # GUI-thread queue drain
    # ------------------------------------------------------------------
    def _drain_queue(self):
        while not self.event_queue.empty():
            kind, *payload = self.event_queue.get()
            if kind == "system":
                self._log(f"{now()}  {payload[0]}")
            elif kind == "error":
                self._log(f"{now()}  ERROR: {payload[0]}", theme.RED_ERR)
            elif kind == "tcp_recv":
                addr, text = payload
                self._report_card("TCP", addr, text)
                self.tcp_stat.value_label.configure(text=str(self.tcp_count))
            elif kind == "udp_recv":
                addr, text = payload
                self._report_card("UDP", addr, text)
                self.udp_stat.value_label.configure(text=str(self.udp_count))
        self.after(100, self._drain_queue)


if __name__ == "__main__":
    app = CommandCenter()
    app.mainloop()
