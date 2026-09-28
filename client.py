"""
client.py  --  FIELD UNIT
-------------------------
A rescue team's app for sending field reports to the Command Center.

One window, two transports. Choose TCP or UDP with the protocol switch;
only one socket is active at a time, and switching protocols creates a
fresh socket of the new type.

    TCP mode:
        - socket.socket(AF_INET, SOCK_STREAM)
        - connect() once -> a persistent, ordered, reliable byte stream
        - every send() is guaranteed to arrive, in order, or the
          connection reports an error.

    UDP mode:
        - socket.socket(AF_INET, SOCK_DGRAM)
        - no connect() handshake -- each packet is fired independently
          with sendto(); nothing guarantees delivery or order.
        - a PACKET-LOSS SIMULATOR rolls a random number before sendto().
          If "unlucky", the packet is never sent and is shown as
          "not delivered". This stands in for the loss a real, flaky
          disaster-zone network would cause, so the TCP-vs-UDP
          difference can be demonstrated reliably on localhost.

Run server.py first, then run one or more copies of this client.
"""

import socket
import threading
import queue
import random
import datetime

import customtkinter as ctk

import messages
import theme

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BUFFER_SIZE = 4096
F = theme.FONT_FAMILY


def now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class FieldUnit(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Field Unit — Disaster Response Communication")
        self.geometry("560x760")
        self.minsize(480, 640)
        self.configure(fg_color=theme.BG_MAIN)

        # ---- networking state ----
        self.tcp_socket: socket.socket | None = None
        self.udp_socket: socket.socket | None = None
        self.udp_target: tuple[str, int] | None = None
        self.connected = False
        self.listen_thread: threading.Thread | None = None

        # ---- stats ----
        self.sent_count = 0
        self.received_count = 0
        self.dropped_count = 0

        # Cross-thread messaging (see server.py for why this exists)
        self.event_queue: "queue.Queue[tuple]" = queue.Queue()

        self._build_ui()
        self._apply_protocol_style("TCP")
        self.after(100, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _entry(self, parent, width, default=""):
        e = ctk.CTkEntry(parent, width=width, fg_color=theme.BG_MAIN, border_color=theme.BORDER,
                         border_width=1, text_color=theme.TEXT_PRIMARY)
        if default:
            e.insert(0, default)
        return e

    def _small_label(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=(F, 11), text_color=theme.TEXT_MUTED)

    def _segmented(self, parent, values, command):
        return ctk.CTkSegmentedButton(
            parent, values=values, command=command, fg_color=theme.BORDER,
            unselected_color=theme.BORDER, unselected_hover_color="#cbd5e1",
            text_color=theme.TEXT_PRIMARY, font=(F, 12, "bold"),
        )

    def _build_ui(self):
        # ---- header: title + protocol badge ----
        header = ctk.CTkFrame(self, fg_color=theme.BG_MAIN, corner_radius=0)
        header.pack(fill="x")
        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left", padx=24, pady=16)
        ctk.CTkLabel(title, text="FIELD UNIT", font=(F, 11, "bold"),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        ctk.CTkLabel(title, text="Disaster Response", font=(F, 20, "bold"),
                     text_color=theme.TEXT_PRIMARY).pack(anchor="w")

        # Big, always-visible indicator of the protocol currently in use
        self.protocol_badge = ctk.CTkLabel(
            header, text="TCP · Reliable", corner_radius=14, width=150, height=30,
            font=(F, 12, "bold")
        )
        self.protocol_badge.pack(side="right", padx=24)

        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x")

        # ---- connection card ----
        card = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, border_width=1,
                            border_color=theme.BORDER, corner_radius=theme.CORNER_RADIUS)
        card.pack(fill="x", padx=24, pady=(16, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        # row 0/1: Protocol | Server IP | Port | Connect
        self._small_label(inner, "Protocol").grid(row=0, column=0, sticky="w")
        self._small_label(inner, "Command Center IP").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self._small_label(inner, "Port").grid(row=0, column=2, sticky="w", padx=(12, 0))

        self.protocol_switch = self._segmented(inner, ["TCP", "UDP"], self._on_protocol_change)
        self.protocol_switch.set("TCP")
        self.protocol_switch.grid(row=1, column=0, sticky="w", pady=(2, 10))

        self.ip_entry = self._entry(inner, 140, "127.0.0.1")
        self.ip_entry.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(2, 10))
        self.port_entry = self._entry(inner, 70, "5050")
        self.port_entry.grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(2, 10))

        self.connect_btn = ctk.CTkButton(
            inner, text="Connect", width=100, fg_color=theme.BUTTON,
            hover_color=theme.BUTTON_HOVER, command=self.toggle_connection
        )
        self.connect_btn.grid(row=1, column=3, sticky="e", padx=(12, 0), pady=(2, 10))
        inner.grid_columnconfigure(3, weight=1)

        # row 2/3: Callsign | Packet-loss slider
        self._small_label(inner, "Callsign").grid(row=2, column=0, sticky="w")
        self.loss_label = self._small_label(inner, "Simulated packet loss (UDP only): 30%")
        self.loss_label.grid(row=2, column=1, columnspan=3, sticky="w", padx=(12, 0))

        self.callsign_entry = self._entry(inner, 100, "ALPHA-1")
        self.callsign_entry.grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.loss_slider = ctk.CTkSlider(inner, from_=0, to=90, number_of_steps=18,
                                         command=self._on_loss_change, width=260)
        self.loss_slider.set(30)
        self.loss_slider.grid(row=3, column=1, columnspan=3, sticky="w", padx=(12, 0), pady=(2, 0))

        # row 4: connection status
        status = ctk.CTkFrame(inner, fg_color="transparent")
        status.grid(row=4, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.status_dot = ctk.CTkLabel(status, text="●", text_color=theme.RED_ERR, font=(F, 14))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = ctk.CTkLabel(status, text="Disconnected", font=(F, 12),
                                         text_color=theme.TEXT_MUTED)
        self.status_label.pack(side="left")

        # ---- stats strip ----
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=24, pady=(12, 0))
        self.sent_card = self._stat_card(stats, "Sent", theme.TEXT_PRIMARY)
        self.sent_card.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.recv_card = self._stat_card(stats, "Received", theme.GREEN_OK)
        self.recv_card.grid(row=0, column=1, padx=6, sticky="ew")
        self.drop_card = self._stat_card(stats, "Dropped", theme.RED_ERR)
        self.drop_card.grid(row=0, column=2, padx=(6, 0), sticky="ew")
        for c in range(3):
            stats.grid_columnconfigure(c, weight=1)

        # ---- bottom composer (packed before the chat so it stays visible) ----
        composer = ctk.CTkFrame(self, fg_color="transparent")
        composer.pack(side="bottom", fill="x", padx=24, pady=(0, 20))

        prio_row = ctk.CTkFrame(composer, fg_color="transparent")
        prio_row.pack(fill="x", pady=(0, 8))
        self._small_label(prio_row, "Priority").pack(side="left", padx=(0, 10))
        self.priority_switch = self._segmented(prio_row, ["Routine", "Urgent", "Critical"],
                                               self._on_priority_change)
        self.priority_switch.set("Routine")
        self.priority_switch.pack(side="left")
        self._on_priority_change("Routine")

        entry_row = ctk.CTkFrame(composer, fg_color="transparent")
        entry_row.pack(fill="x")
        self.msg_entry = ctk.CTkEntry(
            entry_row, placeholder_text="Type a field report...", height=38,
            fg_color=theme.BG_MAIN, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT_PRIMARY
        )
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.msg_entry.bind("<Return>", lambda _e: self.send_message())
        self.send_btn = ctk.CTkButton(entry_row, text="Send", width=90, height=38,
                                      fg_color=theme.BUTTON, hover_color=theme.BUTTON_HOVER,
                                      command=self.send_message)
        self.send_btn.pack(side="left")

        # ---- chat bubble area ----
        self.chat_frame = ctk.CTkScrollableFrame(
            self, fg_color=theme.BG_MAIN, border_width=1, border_color=theme.BORDER,
            corner_radius=theme.CORNER_RADIUS
        )
        self.chat_frame.pack(side="top", fill="both", expand=True, padx=24, pady=12)

    def _stat_card(self, parent, label, color):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_MAIN, border_width=1,
                            border_color=theme.BORDER, corner_radius=theme.CORNER_RADIUS)
        ctk.CTkLabel(card, text=label, font=(F, 11), text_color=theme.TEXT_MUTED
                     ).pack(anchor="w", padx=14, pady=(8, 0))
        value_label = ctk.CTkLabel(card, text="0", text_color=color, font=(F, 22, "bold"))
        value_label.pack(anchor="w", padx=14, pady=(0, 8))
        card.value_label = value_label
        return card

    # ------------------------------------------------------------------
    # Chat bubbles
    # ------------------------------------------------------------------
    def _add_bubble(self, text, *, sent, dropped=False, system=False,
                    header=None, header_color=None, proto=None):
        row = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        row.pack(fill="x", pady=4, padx=6)

        if system:
            ctk.CTkLabel(row, text=text, text_color=theme.TEXT_MUTED,
                         font=(F, 11, "italic")).pack(anchor="center")
            self._scroll_to_bottom()
            return

        if dropped:
            fg, border, txt = theme.BUBBLE_DROPPED, theme.BUBBLE_DROPPED_BORDER, theme.BUBBLE_DROPPED_TEXT
        elif sent:
            fg, border, txt = theme.BUBBLE_SENT, theme.BUBBLE_SENT_BORDER, theme.TEXT_PRIMARY
        else:
            fg, border, txt = theme.BUBBLE_RECEIVED, theme.BUBBLE_RECEIVED_BORDER, theme.TEXT_PRIMARY

        bubble = ctk.CTkFrame(row, fg_color=fg, corner_radius=theme.CORNER_RADIUS,
                              border_width=1, border_color=border)
        bubble.pack(side="right" if sent else "left")

        if header:
            ctk.CTkLabel(bubble, text=header, font=(F, 10, "bold"),
                         text_color=header_color or theme.TEXT_MUTED
                         ).pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(bubble, text=text, text_color=txt, wraplength=300, justify="left",
                     font=(F, 13)).pack(anchor="w", padx=12, pady=(2, 0))
        if dropped:
            ctk.CTkLabel(bubble, text="✕  Packet lost — not delivered", font=(F, 10, "bold"),
                         text_color=theme.RED_ERR).pack(anchor="w", padx=12, pady=(2, 0))

        foot = ctk.CTkFrame(bubble, fg_color="transparent")
        foot.pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(foot, text=now(), font=(F, 9), text_color=theme.TEXT_MUTED).pack(side="left")
        if proto:
            ctk.CTkLabel(foot, text=proto, font=(F, 9, "bold"),
                         text_color=theme.PROTOCOL_STYLE[proto][0]).pack(side="right", padx=(16, 0))

        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self.chat_frame.update_idletasks()
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    # ------------------------------------------------------------------
    # Protocol switching / options
    # ------------------------------------------------------------------
    def _apply_protocol_style(self, value):
        """Recolor the badge, switch and slider for the chosen protocol."""
        color, soft, label = theme.PROTOCOL_STYLE[value]
        self.protocol_badge.configure(text=f"●  {label}", fg_color=soft, text_color=color)
        self.protocol_switch.configure(selected_color=color, selected_hover_color=color)
        # Packet-loss simulation only applies to UDP, so dim it for TCP.
        self.loss_slider.configure(
            state="normal" if value == "UDP" else "disabled",
            progress_color=color, button_color=color, button_hover_color=color,
        )

    def _on_protocol_change(self, value):
        if self.connected:
            # A live socket belongs to one protocol only -- switching
            # protocols mid-session means starting a fresh connection.
            self.disconnect()
        self._apply_protocol_style(value)
        if value == "TCP" and self.port_entry.get() == "5001":
            self.port_entry.delete(0, "end")
            self.port_entry.insert(0, "5050")
        elif value == "UDP" and self.port_entry.get() == "5050":
            self.port_entry.delete(0, "end")
            self.port_entry.insert(0, "5001")

    def _on_priority_change(self, value):
        color = theme.PRIORITY_COLORS[value.upper()]
        self.priority_switch.configure(selected_color=color, selected_hover_color=color)

    def _on_loss_change(self, value):
        self.loss_label.configure(text=f"Simulated packet loss (UDP only): {int(value)}%")

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------
    def toggle_connection(self):
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        host = self.ip_entry.get().strip()
        try:
            port = int(self.port_entry.get())
        except ValueError:
            self._add_bubble("Port must be a number.", sent=False, system=True)
            return

        protocol = self.protocol_switch.get()
        if protocol == "TCP":
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.tcp_socket.connect((host, port))
            except OSError as exc:
                self._add_bubble(f"TCP connection failed: {exc}", sent=False, system=True)
                self.tcp_socket = None
                return
            self.connected = True
            self.listen_thread = threading.Thread(target=self._tcp_listen, daemon=True)
            self.listen_thread.start()
            self.status_dot.configure(text_color=theme.GREEN_OK)
            self.status_label.configure(text=f"Connected via TCP to {host}:{port}")
            self._add_bubble(f"TCP connection established with {host}:{port}", sent=False, system=True)
        else:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(("0.0.0.0", 0))  # let the OS pick a free local port for replies
            self.udp_target = (host, port)
            self.connected = True
            self.listen_thread = threading.Thread(target=self._udp_listen, daemon=True)
            self.listen_thread.start()
            # UDP is connectionless -- "Ready" is the technically accurate
            # label; there is no handshake with the server.
            self.status_dot.configure(text_color=theme.YELLOW_WARN)
            self.status_label.configure(text=f"Ready via UDP → {host}:{port}")
            self._add_bubble(f"UDP target set to {host}:{port} (no handshake in UDP)", sent=False, system=True)

        self.connect_btn.configure(text="Disconnect", fg_color=theme.RED_ERR, hover_color="#b91c1c")
        self.protocol_switch.configure(state="disabled")

    def disconnect(self):
        self.connected = False
        for sock in (self.tcp_socket, self.udp_socket):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        self.tcp_socket = None
        self.udp_socket = None
        self.status_dot.configure(text_color=theme.RED_ERR)
        self.status_label.configure(text="Disconnected")
        self.connect_btn.configure(text="Connect", fg_color=theme.BUTTON, hover_color=theme.BUTTON_HOVER)
        self.protocol_switch.configure(state="normal")

    def _on_close(self):
        self.disconnect()
        self.destroy()

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def send_message(self):
        text = self.msg_entry.get().strip()
        if not text:
            return
        if not self.connected:
            self._add_bubble("Not connected — click Connect first.", sent=False, system=True)
            return

        protocol = self.protocol_switch.get()
        priority = self.priority_switch.get().upper()
        callsign = self.callsign_entry.get().strip() or "UNIT"
        wire_text = messages.encode_message(callsign, priority, text)
        bubble_kwargs = dict(
            sent=True, header=f"{callsign}  ·  {priority}",
            header_color=theme.PRIORITY_COLORS[priority], proto=protocol,
        )

        if protocol == "TCP":
            # TCP never simulates loss: the point of the demo is that TCP's
            # guarantees mean nothing is dropped here.
            try:
                self.tcp_socket.sendall(wire_text.encode("utf-8"))
                self.sent_count += 1
                self._add_bubble(text, **bubble_kwargs)
            except OSError as exc:
                self._add_bubble(f"Send failed, connection lost: {exc}", sent=False, system=True)
                self.disconnect()
        else:
            loss_probability = self.loss_slider.get() / 100.0
            if random.random() < loss_probability:
                # Simulated loss: sendto() is deliberately never called, so
                # the server genuinely never receives this packet -- exactly
                # like a real dropped UDP datagram.
                self.dropped_count += 1
                self._add_bubble(text, dropped=True, **bubble_kwargs)
            else:
                try:
                    self.udp_socket.sendto(wire_text.encode("utf-8"), self.udp_target)
                    self.sent_count += 1
                    self._add_bubble(text, **bubble_kwargs)
                except OSError as exc:
                    self._add_bubble(f"UDP send error: {exc}", sent=False, system=True)

        self._refresh_stats()
        self.msg_entry.delete(0, "end")

    def _refresh_stats(self):
        self.sent_card.value_label.configure(text=str(self.sent_count))
        self.recv_card.value_label.configure(text=str(self.received_count))
        self.drop_card.value_label.configure(text=str(self.dropped_count))

    # ------------------------------------------------------------------
    # Receiving (background threads -> queue -> GUI thread)
    # ------------------------------------------------------------------
    def _tcp_listen(self):
        sock = self.tcp_socket
        while self.connected and sock:
            try:
                data = sock.recv(BUFFER_SIZE)
            except OSError:
                break
            if not data:
                self.event_queue.put(("system", "Command Center closed the TCP connection."))
                break
            self.event_queue.put(("recv", data.decode("utf-8", errors="replace")))

    def _udp_listen(self):
        sock = self.udp_socket
        while self.connected and sock:
            try:
                data, _addr = sock.recvfrom(BUFFER_SIZE)
            except OSError:
                break
            self.event_queue.put(("recv", data.decode("utf-8", errors="replace")))

    def _drain_queue(self):
        while not self.event_queue.empty():
            kind, payload = self.event_queue.get()
            if kind == "recv":
                self.received_count += 1
                # The server echoes each report back as "ACK:<report>".
                body = payload[4:] if payload.startswith("ACK:") else payload
                _call, _prio, text = messages.decode_message(body)
                self._add_bubble(f"✓  Received: {text}", sent=False,
                                 header="COMMAND CENTER  ·  ACK",
                                 header_color=theme.GREEN_OK,
                                 proto=self.protocol_switch.get())
                self._refresh_stats()
            elif kind == "system":
                self._add_bubble(payload, sent=False, system=True)
        self.after(100, self._drain_queue)


if __name__ == "__main__":
    app = FieldUnit()
    app.mainloop()
