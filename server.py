"""
server.py
---------
TCP + UDP Chat Server.

The server opens TWO sockets at the same time, on two different ports:
    - a TCP socket  (socket.SOCK_STREAM)  -> reliable, connection-oriented
    - a UDP socket  (socket.SOCK_DGRAM)   -> unreliable, connectionless

Each socket type runs its own accept/receive loop in its own background
thread, so the server can talk TCP and UDP simultaneously without one
blocking the other. Every message the server receives is echoed back
to the sender as an "ACK:<message>" so the client can tell whether a
message actually made it to the server and back.

Run this FIRST, then start one or more client.py instances and point
them at this machine's IP address and the ports shown in this window.
"""

import socket
import threading
import queue
import datetime

import customtkinter as ctk

import theme

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DEFAULT_HOST = "0.0.0.0"      # listen on all local network interfaces
DEFAULT_TCP_PORT = 5050
DEFAULT_UDP_PORT = 5001
BUFFER_SIZE = 4096


def now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class ChatServer(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TCP / UDP Chat Server")
        self.geometry("760x620")
        self.minsize(620, 480)
        self.configure(fg_color=theme.BG_MAIN)

        # ---- networking state ----
        self.tcp_socket: socket.socket | None = None
        self.udp_socket: socket.socket | None = None
        self.running = False
        self.tcp_clients: list[socket.socket] = []   # for future broadcast use
        self.tcp_count = 0
        self.udp_count = 0

        # Thread -> GUI communication. Tkinter is NOT thread-safe, so
        # worker threads never touch widgets directly; they push
        # events onto this queue and the GUI thread drains it with
        # `after()`, which is the standard safe pattern for Tkinter.
        self.event_queue: "queue.Queue[tuple]" = queue.Queue()

        self._build_ui()
        self.after(100, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        # ---- top control bar: host / ports / start-stop ----
        bar = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=0)
        bar.pack(side="top", fill="x")

        pad = {"padx": 8, "pady": 10}

        ctk.CTkLabel(bar, text="Host", text_color=theme.TEXT_MUTED).grid(row=0, column=0, **pad)
        self.host_entry = ctk.CTkEntry(bar, width=110)
        self.host_entry.insert(0, DEFAULT_HOST)
        self.host_entry.grid(row=0, column=1, **pad)

        ctk.CTkLabel(bar, text="TCP Port", text_color=theme.TEXT_MUTED).grid(row=0, column=2, **pad)
        self.tcp_port_entry = ctk.CTkEntry(bar, width=80)
        self.tcp_port_entry.insert(0, str(DEFAULT_TCP_PORT))
        self.tcp_port_entry.grid(row=0, column=3, **pad)

        ctk.CTkLabel(bar, text="UDP Port", text_color=theme.TEXT_MUTED).grid(row=0, column=4, **pad)
        self.udp_port_entry = ctk.CTkEntry(bar, width=80)
        self.udp_port_entry.insert(0, str(DEFAULT_UDP_PORT))
        self.udp_port_entry.grid(row=0, column=5, **pad)

        self.start_btn = ctk.CTkButton(
            bar, text="Start Server", fg_color=theme.GREEN_OK, hover_color="#16a34a",
            command=self.toggle_server, width=130
        )
        self.start_btn.grid(row=0, column=6, **pad)

        self.status_dot = ctk.CTkLabel(bar, text="●", text_color=theme.RED_ERR, font=(theme.FONT_FAMILY, 18))
        self.status_dot.grid(row=0, column=7, padx=(20, 4))
        self.status_label = ctk.CTkLabel(bar, text="Stopped", text_color=theme.TEXT_MUTED)
        self.status_label.grid(row=0, column=8, padx=(0, 10))

        # ---- stats strip ----
        stats = ctk.CTkFrame(self, fg_color=theme.BG_MAIN, corner_radius=0)
        stats.pack(side="top", fill="x", padx=16, pady=(10, 0))

        self.tcp_stat = self._stat_card(stats, "TCP messages", theme.TCP_COLOR)
        self.tcp_stat.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.udp_stat = self._stat_card(stats, "UDP messages", theme.UDP_COLOR)
        self.udp_stat.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        stats.grid_columnconfigure(0, weight=1)
        stats.grid_columnconfigure(1, weight=1)

        # ---- scrollable message log ----
        self.log_frame = ctk.CTkScrollableFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        self.log_frame.pack(side="top", fill="both", expand=True, padx=16, pady=16)

    def _stat_card(self, parent, label, color):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=12)
        ctk.CTkLabel(card, text=label, text_color=theme.TEXT_MUTED).pack(anchor="w", padx=14, pady=(10, 0))
        value_label = ctk.CTkLabel(card, text="0", text_color=color, font=(theme.FONT_FAMILY, 26, "bold"))
        value_label.pack(anchor="w", padx=14, pady=(0, 10))
        card.value_label = value_label  # stash for later updates
        return card

    def _log(self, text, color=theme.BUBBLE_SYSTEM_TEXT):
        row = ctk.CTkLabel(
            self.log_frame, text=text, text_color=color, anchor="w", justify="left",
            font=(theme.FONT_MONO, 13)
        )
        row.pack(fill="x", anchor="w", padx=10, pady=2)
        # auto-scroll to the newest entry
        self.log_frame.update_idletasks()
        self.log_frame._parent_canvas.yview_moveto(1.0)

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
            self._log("[!] Ports must be numbers.", theme.RED_ERR)
            return

        self.running = True
        threading.Thread(target=self._run_tcp_server, args=(host, tcp_port), daemon=True).start()
        threading.Thread(target=self._run_udp_server, args=(host, udp_port), daemon=True).start()

        self.start_btn.configure(text="Stop Server", fg_color=theme.RED_ERR, hover_color="#b91c1c")
        self.status_dot.configure(text_color=theme.GREEN_OK)
        self.status_label.configure(text=f"Listening — TCP:{tcp_port}  UDP:{udp_port}")
        self._log(f"[{now()}] Server started on {host}  (TCP {tcp_port} / UDP {udp_port})")

    def stop_server(self):
        self.running = False
        for sock in (self.tcp_socket, self.udp_socket):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        self.start_btn.configure(text="Start Server", fg_color=theme.GREEN_OK, hover_color="#16a34a")
        self.status_dot.configure(text_color=theme.RED_ERR)
        self.status_label.configure(text="Stopped")
        self._log(f"[{now()}] Server stopped.")

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
            self.event_queue.put(("system", f"[TCP] {addr[0]}:{addr[1]} connected"))
            threading.Thread(target=self._handle_tcp_client, args=(conn, addr), daemon=True).start()

    def _handle_tcp_client(self, conn: socket.socket, addr):
        """One thread per connected TCP client -- this is what makes
        TCP 'connection-oriented': the socket stays open for the whole
        conversation instead of being recreated per message."""
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
        self.event_queue.put(("system", f"[TCP] {addr[0]}:{addr[1]} disconnected"))
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
        # so a single loop with recvfrom() handles every sender.
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
    # GUI-thread queue drain (the only place that touches widgets
    # based on data from background threads)
    # ------------------------------------------------------------------
    def _drain_queue(self):
        while not self.event_queue.empty():
            kind, *payload = self.event_queue.get()
            if kind == "system":
                self._log(f"[{now()}] {payload[0]}")
            elif kind == "error":
                self._log(f"[{now()}] ERROR: {payload[0]}", theme.RED_ERR)
            elif kind == "tcp_recv":
                addr, text = payload
                self._log(f"[{now()}] TCP  {addr[0]}:{addr[1]} -> {text}", theme.TCP_COLOR)
                self.tcp_stat.value_label.configure(text=str(self.tcp_count))
            elif kind == "udp_recv":
                addr, text = payload
                self._log(f"[{now()}] UDP  {addr[0]}:{addr[1]} -> {text}", theme.UDP_COLOR)
                self.udp_stat.value_label.configure(text=str(self.udp_count))
        self.after(100, self._drain_queue)


if __name__ == "__main__":
    app = ChatServer()
    app.mainloop()
