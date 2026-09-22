"""
client.py
---------
TCP + UDP Chat Client.

TCP  -> Port 5050
UDP  -> Port 5001

The user can switch between TCP and UDP to demonstrate
the difference between reliable and unreliable communication.
"""

import socket
import threading
import queue
import random
import datetime

import customtkinter as ctk
import theme


# ---------------------------------------------------------
# APPLICATION SETTINGS
# ---------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BUFFER_SIZE = 4096

TCP_PORT = 5050
UDP_PORT = 5001


def now():
    """Return the current time for chat messages."""
    return datetime.datetime.now().strftime("%H:%M:%S")


# =========================================================
# CHAT CLIENT
# =========================================================

class ChatClient(ctk.CTk):

    def __init__(self):
        super().__init__()

        # -------------------------------------------------
        # Window settings
        # -------------------------------------------------

        self.title("TCP / UDP Chat Client")
        self.geometry("520x720")
        self.minsize(420, 560)
        self.configure(fg_color=theme.BG_MAIN)

        # -------------------------------------------------
        # Networking variables
        # -------------------------------------------------

        self.tcp_socket = None
        self.udp_socket = None

        self.udp_target = None

        self.connected = False

        self.listen_thread = None

        # -------------------------------------------------
        # Statistics
        # -------------------------------------------------

        self.sent_count = 0
        self.received_count = 0
        self.dropped_count = 0

        # -------------------------------------------------
        # Queue
        # -------------------------------------------------
        # Networking runs in background threads.
        # Tkinter GUI updates must happen on the main thread.
        # The queue safely transfers received messages.

        self.event_queue = queue.Queue()

        # Build interface

        self._build_ui()

        # Check queue every 100 milliseconds

        self.after(100, self._drain_queue)

        # Handle closing the window

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # =====================================================
    # USER INTERFACE
    # =====================================================

    def _build_ui(self):

        # -------------------------------------------------
        # Connection panel
        # -------------------------------------------------

        panel = ctk.CTkFrame(
            self,
            fg_color=theme.BG_PANEL,
            corner_radius=0
        )

        panel.pack(
            side="top",
            fill="x"
        )

        inner = ctk.CTkFrame(
            panel,
            fg_color="transparent"
        )

        inner.pack(
            fill="x",
            padx=16,
            pady=14
        )

        # -------------------------------------------------
        # Protocol selector
        # -------------------------------------------------

        ctk.CTkLabel(
            inner,
            text="Protocol",
            text_color=theme.TEXT_MUTED
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        self.protocol_switch = ctk.CTkSegmentedButton(
            inner,
            values=["TCP", "UDP"],
            command=self._on_protocol_change,
            selected_color=theme.TCP_COLOR,
            selected_hover_color=theme.TCP_COLOR
        )

        self.protocol_switch.set("TCP")

        self.protocol_switch.grid(
            row=1,
            column=0,
            sticky="w",
            pady=(4, 12)
        )

        # -------------------------------------------------
        # Protocol badge
        # -------------------------------------------------

        self.protocol_badge = ctk.CTkLabel(
            inner,
            text="TCP  (reliable)",
            fg_color=theme.TCP_COLOR,
            text_color="white",
            corner_radius=8,
            width=140,
            height=28,
            font=(theme.FONT_FAMILY, 12, "bold")
        )

        self.protocol_badge.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=(16, 0),
            sticky="w"
        )

        # -------------------------------------------------
        # Server IP
        # -------------------------------------------------

        ctk.CTkLabel(
            inner,
            text="Server IP",
            text_color=theme.TEXT_MUTED
        ).grid(
            row=2,
            column=0,
            sticky="w"
        )

        self.ip_entry = ctk.CTkEntry(
            inner,
            width=160
        )

        self.ip_entry.insert(
            0,
            "127.0.0.1"
        )

        self.ip_entry.grid(
            row=3,
            column=0,
            sticky="w",
            pady=(2, 10)
        )

        # -------------------------------------------------
        # Port
        # -------------------------------------------------

        ctk.CTkLabel(
            inner,
            text="Port",
            text_color=theme.TEXT_MUTED
        ).grid(
            row=2,
            column=1,
            sticky="w",
            padx=(16, 0)
        )

        self.port_entry = ctk.CTkEntry(
            inner,
            width=90
        )

        # TCP now uses port 5050
        self.port_entry.insert(
            0,
            str(TCP_PORT)
        )

        self.port_entry.grid(
            row=3,
            column=1,
            sticky="w",
            padx=(16, 0),
            pady=(2, 10)
        )

        # -------------------------------------------------
        # Connect button
        # -------------------------------------------------

        self.connect_btn = ctk.CTkButton(
            inner,
            text="Connect",
            command=self.toggle_connection,
            width=110
        )

        self.connect_btn.grid(
            row=3,
            column=2,
            sticky="w",
            padx=(16, 0)
        )

        # -------------------------------------------------
        # Connection status
        # -------------------------------------------------

        self.status_dot = ctk.CTkLabel(
            inner,
            text="●",
            text_color=theme.RED_ERR,
            font=(theme.FONT_FAMILY, 16)
        )

        self.status_dot.grid(
            row=4,
            column=0,
            sticky="w",
            pady=(4, 0)
        )

        self.status_label = ctk.CTkLabel(
            inner,
            text="Disconnected",
            text_color=theme.TEXT_MUTED
        )

        self.status_label.grid(
            row=4,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(4, 0)
        )

        # -------------------------------------------------
        # UDP Packet Loss Simulation
        # -------------------------------------------------

        self.loss_label = ctk.CTkLabel(
            inner,
            text="Simulated packet loss (UDP only): 30%",
            text_color=theme.TEXT_MUTED
        )

        self.loss_label.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(12, 0)
        )

        self.loss_slider = ctk.CTkSlider(
            inner,
            from_=0,
            to=90,
            number_of_steps=18,
            command=self._on_loss_change,
            width=340
        )

        self.loss_slider.set(30)

        self.loss_slider.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(4, 0)
        )

        # -------------------------------------------------
        # Statistics
        # -------------------------------------------------

        stats = ctk.CTkFrame(
            self,
            fg_color=theme.BG_MAIN,
            corner_radius=0
        )

        stats.pack(
            side="top",
            fill="x",
            padx=16,
            pady=(10, 0)
        )

        self.sent_card = self._stat_card(
            stats,
            "Sent",
            theme.TEXT_PRIMARY
        )

        self.sent_card.grid(
            row=0,
            column=0,
            padx=(0, 6),
            sticky="ew"
        )

        self.recv_card = self._stat_card(
            stats,
            "Received",
            theme.GREEN_OK
        )

        self.recv_card.grid(
            row=0,
            column=1,
            padx=6,
            sticky="ew"
        )

        self.drop_card = self._stat_card(
            stats,
            "Dropped",
            theme.RED_ERR
        )

        self.drop_card.grid(
            row=0,
            column=2,
            padx=(6, 0),
            sticky="ew"
        )

        for column in range(3):
            stats.grid_columnconfigure(
                column,
                weight=1
            )

        # -------------------------------------------------
        # Chat area
        # -------------------------------------------------

        self.chat_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.BG_PANEL,
            corner_radius=12
        )

        self.chat_frame.pack(
            side="top",
            fill="both",
            expand=True,
            padx=16,
            pady=12
        )

        # -------------------------------------------------
        # Message input
        # -------------------------------------------------

        entry_row = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )

        entry_row.pack(
            side="bottom",
            fill="x",
            padx=16,
            pady=(0, 16)
        )

        self.msg_entry = ctk.CTkEntry(
            entry_row,
            placeholder_text="Type a message..."
        )

        self.msg_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8)
        )

        # Press Enter to send

        self.msg_entry.bind(
            "<Return>",
            lambda event: self.send_message()
        )

        self.send_btn = ctk.CTkButton(
            entry_row,
            text="Send",
            width=90,
            command=self.send_message
        )

        self.send_btn.pack(
            side="left"
        )

    # =====================================================
    # STATISTICS CARD
    # =====================================================

    def _stat_card(self, parent, label, color):

        card = ctk.CTkFrame(
            parent,
            fg_color=theme.BG_CARD,
            corner_radius=12
        )

        ctk.CTkLabel(
            card,
            text=label,
            text_color=theme.TEXT_MUTED
        ).pack(
            anchor="w",
            padx=12,
            pady=(8, 0)
        )

        value_label = ctk.CTkLabel(
            card,
            text="0",
            text_color=color,
            font=(theme.FONT_FAMILY, 22, "bold")
        )

        value_label.pack(
            anchor="w",
            padx=12,
            pady=(0, 8)
        )

        card.value_label = value_label

        return card

    # =====================================================
    # CHAT BUBBLES
    # =====================================================

    def _add_bubble(
        self,
        text,
        *,
        sent,
        dropped=False,
        system=False
    ):

        row = ctk.CTkFrame(
            self.chat_frame,
            fg_color="transparent"
        )

        row.pack(
            fill="x",
            pady=4,
            padx=6
        )

        # System messages

        if system:

            label = ctk.CTkLabel(
                row,
                text=text,
                text_color=theme.BUBBLE_SYSTEM_TEXT,
                font=(theme.FONT_FAMILY, 11, "italic")
            )

            label.pack(anchor="center")

            self._scroll_to_bottom()

            return

        # Dropped UDP message

        if dropped:

            fg = theme.BUBBLE_DROPPED
            txt_color = theme.BUBBLE_DROPPED_TEXT
            border = theme.BUBBLE_DROPPED_BORDER

            prefix = "✕ dropped: "

        # Sent message

        elif sent:

            fg = theme.BUBBLE_SENT
            txt_color = theme.BUBBLE_SENT_TEXT
            border = theme.BUBBLE_SENT

            prefix = ""

        # Received message

        else:

            fg = theme.BUBBLE_RECEIVED
            txt_color = theme.BUBBLE_RECEIVED_TEXT
            border = theme.BUBBLE_RECEIVED

            prefix = ""

        bubble = ctk.CTkFrame(
            row,
            fg_color=fg,
            corner_radius=theme.CORNER_RADIUS,
            border_width=2 if dropped else 0,
            border_color=border
        )

        bubble.pack(
            side="right" if sent else "left"
        )

        ctk.CTkLabel(
            bubble,
            text=f"{prefix}{text}",
            text_color=txt_color,
            wraplength=300,
            justify="left",
            font=(theme.FONT_FAMILY, 13)
        ).pack(
            padx=12,
            pady=(8, 2)
        )

        ctk.CTkLabel(
            bubble,
            text=now(),
            text_color=txt_color,
            font=(theme.FONT_FAMILY, 9)
        ).pack(
            anchor="e" if sent else "w",
            padx=12,
            pady=(0, 6)
        )

        self._scroll_to_bottom()

    def _scroll_to_bottom(self):

        self.chat_frame.update_idletasks()

        self.chat_frame._parent_canvas.yview_moveto(1.0)

    # =====================================================
    # PROTOCOL SWITCHING
    # =====================================================

    def _on_protocol_change(self, value):

        # Disconnect existing socket before switching protocol

        if self.connected:
            self.disconnect()

        # -------------------------------------------------
        # TCP selected
        # -------------------------------------------------

        if value == "TCP":

            self.protocol_badge.configure(
                text="TCP  (reliable)",
                fg_color=theme.TCP_COLOR
            )

            # Automatically change port to 5050

            self.port_entry.delete(
                0,
                "end"
            )

            self.port_entry.insert(
                0,
                str(TCP_PORT)
            )

        # -------------------------------------------------
        # UDP selected
        # -------------------------------------------------

        else:

            self.protocol_badge.configure(
                text="UDP  (unreliable)",
                fg_color=theme.UDP_COLOR
            )

            # Automatically change port to 5001

            self.port_entry.delete(
                0,
                "end"
            )

            self.port_entry.insert(
                0,
                str(UDP_PORT)
            )

    # =====================================================
    # PACKET LOSS SLIDER
    # =====================================================

    def _on_loss_change(self, value):

        self.loss_label.configure(
            text=f"Simulated packet loss (UDP only): {int(value)}%"
        )

    # =====================================================
    # CONNECT / DISCONNECT
    # =====================================================

    def toggle_connection(self):

        if self.connected:
            self.disconnect()

        else:
            self.connect()

    def connect(self):

        host = self.ip_entry.get().strip()

        try:

            port = int(
                self.port_entry.get()
            )

        except ValueError:

            self._add_bubble(
                "Port must be a number.",
                sent=False,
                system=True
            )

            return

        protocol = self.protocol_switch.get()

        # =================================================
        # TCP CONNECTION
        # =================================================

        if protocol == "TCP":

            # SOCK_STREAM creates a TCP socket

            self.tcp_socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            try:

                # TCP requires a connection with the server

                self.tcp_socket.connect(
                    (host, port)
                )

            except OSError as error:

                self._add_bubble(
                    f"TCP connection failed: {error}",
                    sent=False,
                    system=True
                )

                self.tcp_socket = None

                return

            self.connected = True

            # Start receiving messages in background

            self.listen_thread = threading.Thread(
                target=self._tcp_listen,
                daemon=True
            )

            self.listen_thread.start()

            self.status_dot.configure(
                text_color=theme.GREEN_OK
            )

            self.status_label.configure(
                text=f"Connected (TCP) to {host}:{port}"
            )

            self._add_bubble(
                f"TCP connection established with {host}:{port}",
                sent=False,
                system=True
            )

        # =================================================
        # UDP
        # =================================================

        else:

            # SOCK_DGRAM creates a UDP socket

            self.udp_socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM
            )

            # Let operating system select client-side port

            self.udp_socket.bind(
                ("0.0.0.0", 0)
            )

            # Store server address

            self.udp_target = (
                host,
                port
            )

            self.connected = True

            # Start UDP receiving thread

            self.listen_thread = threading.Thread(
                target=self._udp_listen,
                daemon=True
            )

            self.listen_thread.start()

            # UDP does not actually establish a connection

            self.status_dot.configure(
                text_color=theme.YELLOW_WARN
            )

            self.status_label.configure(
                text=f"Ready (UDP) -> {host}:{port}"
            )

            self._add_bubble(
                f"UDP target set to {host}:{port} (no handshake in UDP)",
                sent=False,
                system=True
            )

        self.connect_btn.configure(
            text="Disconnect"
        )

        # Prevent protocol switching while connected

        self.protocol_switch.configure(
            state="disabled"
        )

    # =====================================================
    # DISCONNECT
    # =====================================================

    def disconnect(self):

        self.connected = False

        for sock in (
            self.tcp_socket,
            self.udp_socket
        ):

            if sock:

                try:
                    sock.close()

                except OSError:
                    pass

        self.tcp_socket = None
        self.udp_socket = None

        self.status_dot.configure(
            text_color=theme.RED_ERR
        )

        self.status_label.configure(
            text="Disconnected"
        )

        self.connect_btn.configure(
            text="Connect"
        )

        self.protocol_switch.configure(
            state="normal"
        )

    # =====================================================
    # WINDOW CLOSE
    # =====================================================

    def _on_close(self):

        self.disconnect()

        self.destroy()

    # =====================================================
    # SEND MESSAGE
    # =====================================================

    def send_message(self):

        text = self.msg_entry.get().strip()

        if not text:
            return

        if not self.connected:

            self._add_bubble(
                "Not connected -- click Connect first.",
                sent=False,
                system=True
            )

            return

        protocol = self.protocol_switch.get()

        # =================================================
        # SEND USING TCP
        # =================================================

        if protocol == "TCP":

            try:

                self.tcp_socket.sendall(
                    text.encode("utf-8")
                )

                self.sent_count += 1

                self._add_bubble(
                    text,
                    sent=True
                )

            except OSError as error:

                self._add_bubble(
                    f"Send failed: {error}",
                    sent=False,
                    system=True
                )

                self.disconnect()

        # =================================================
        # SEND USING UDP
        # =================================================

        else:

            loss_probability = (
                self.loss_slider.get() / 100.0
            )

            # Generate random number between 0 and 1.
            # If it falls below loss probability,
            # simulate a dropped UDP packet.

            if random.random() < loss_probability:

                self.dropped_count += 1

                self._add_bubble(
                    text,
                    sent=True,
                    dropped=True
                )

            else:

                try:

                    self.udp_socket.sendto(
                        text.encode("utf-8"),
                        self.udp_target
                    )

                    self.sent_count += 1

                    self._add_bubble(
                        text,
                        sent=True
                    )

                except OSError as error:

                    self._add_bubble(
                        f"UDP send error: {error}",
                        sent=False,
                        system=True
                    )

        self._refresh_stats()

        self.msg_entry.delete(
            0,
            "end"
        )

    # =====================================================
    # UPDATE STATISTICS
    # =====================================================

    def _refresh_stats(self):

        self.sent_card.value_label.configure(
            text=str(self.sent_count)
        )

        self.recv_card.value_label.configure(
            text=str(self.received_count)
        )

        self.drop_card.value_label.configure(
            text=str(self.dropped_count)
        )

    # =====================================================
    # TCP RECEIVE THREAD
    # =====================================================

    def _tcp_listen(self):

        sock = self.tcp_socket

        while self.connected and sock:

            try:

                data = sock.recv(
                    BUFFER_SIZE
                )

            except OSError:
                break

            if not data:

                self.event_queue.put(
                    (
                        "system",
                        "Server closed the TCP connection."
                    )
                )

                break

            self.event_queue.put(
                (
                    "recv",
                    data.decode(
                        "utf-8",
                        errors="replace"
                    )
                )
            )

    # =====================================================
    # UDP RECEIVE THREAD
    # =====================================================

    def _udp_listen(self):

        sock = self.udp_socket

        while self.connected and sock:

            try:

                data, address = sock.recvfrom(
                    BUFFER_SIZE
                )

            except OSError:
                break

            self.event_queue.put(
                (
                    "recv",
                    data.decode(
                        "utf-8",
                        errors="replace"
                    )
                )
            )

    # =====================================================
    # PROCESS RECEIVED MESSAGES
    # =====================================================

    def _drain_queue(self):

        while not self.event_queue.empty():

            kind, payload = self.event_queue.get()

            if kind == "recv":

                self.received_count += 1

                self._add_bubble(
                    payload,
                    sent=False
                )

                self._refresh_stats()

            elif kind == "system":

                self._add_bubble(
                    payload,
                    sent=False,
                    system=True
                )

        # Check queue again after 100 ms

        self.after(
            100,
            self._drain_queue
        )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    app = ChatClient()

    app.mainloop()