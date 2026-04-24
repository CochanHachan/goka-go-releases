# -*- coding: utf-8 -*-
"""碁華 ネットワーク対局"""
import logging
import socket
import threading
import json
import struct
import time as _time

from igo.constants import NET_UDP_PORT, NET_BROADCAST_INTERVAL

logger = logging.getLogger(__name__)


def _net_send(sock, msg_dict):
    """Send a JSON message with 4-byte length prefix."""
    data = json.dumps(msg_dict, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(data)) + data)

def _net_recv(sock):
    """Receive a JSON message with 4-byte length prefix. Returns dict or None."""
    try:
        hdr = b""
        while len(hdr) < 4:
            chunk = sock.recv(4 - len(hdr))
            if not chunk:
                return None
            hdr += chunk
        length = struct.unpack("!I", hdr)[0]
        if length > 1048576:
            return None
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.debug("_net_recv failed", exc_info=True)
        return None


# --------------- Game Server (host side) ---------------

class GameServer:
    """TCP server + UDP broadcaster for hosting a match."""
    def __init__(self, name, rank, main_time, byo_time, byo_periods, on_connect_cb, komi=7.5, elo=0,
                 time_control="byoyomi", fischer_increment=0):
        self.name = name
        self.rank = rank
        self.elo = elo
        self.main_time = main_time
        self.byo_time = byo_time
        self.byo_periods = byo_periods
        self.komi = komi
        self.time_control = time_control
        self.fischer_increment = fischer_increment
        self.on_connect_cb = on_connect_cb  # called with (socket, addr, opponent_info)
        self._running = False
        self._tcp_sock = None
        self._udp_sock = None

    def start(self):
        self._running = True
        # TCP
        self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_sock.settimeout(1.0)
        self._tcp_sock.bind(("", 0))  # dynamic port
        self._tcp_sock.listen(1)
        self._port = self._tcp_sock.getsockname()[1]
        # UDP broadcast
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._broadcast_loop, daemon=True).start()

    def stop(self):
        self._running = False
        try:
            self._tcp_sock.close()
        except OSError:
            logger.debug("TCP socket close failed", exc_info=True)
        try:
            self._udp_sock.close()
        except OSError:
            logger.debug("UDP socket close failed", exc_info=True)

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._tcp_sock.accept()
                msg = _net_recv(conn)
                if msg and msg.get("type") == "match_accept":
                    self.on_connect_cb(conn, addr, msg)
                    return
                else:
                    conn.close()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    logger.debug("accept_loop error", exc_info=True)
                    continue
                return

    def _broadcast_loop(self):
        offer = json.dumps({
            "type": "match_offer",
            "name": self.name,
            "rank": self.rank,
            "elo": self.elo,
            "main_time": self.main_time,
            "byo_time": self.byo_time,
            "byo_periods": self.byo_periods,
            "komi": self.komi,
            "time_control": self.time_control,
            "fischer_increment": self.fischer_increment,
            "port": self._port,
        }, ensure_ascii=False).encode("utf-8")
        while self._running:
            try:
                self._udp_sock.sendto(offer, ("<broadcast>", NET_UDP_PORT))
            except OSError:
                logger.debug("UDP broadcast failed", exc_info=True)
            _time.sleep(NET_BROADCAST_INTERVAL)


# --------------- Network Game (active connection) ---------------

class NetworkGame:
    """Manages an active TCP connection for a game in progress."""
    def __init__(self, sock, on_message_cb, on_disconnect_cb):
        self.sock = sock
        self.on_message_cb = on_message_cb
        self.on_disconnect_cb = on_disconnect_cb
        self._running = False

    def start(self):
        self._running = True
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except OSError:
            logger.debug("NetworkGame socket close failed", exc_info=True)

    def send(self, msg_dict):
        try:
            _net_send(self.sock, msg_dict)
        except OSError:
            logger.warning("NetworkGame send failed", exc_info=True)
            self.stop()

    def _recv_loop(self):
        while self._running:
            msg = _net_recv(self.sock)
            if msg is None:
                self._running = False
                self.on_disconnect_cb()
                return
            self.on_message_cb(msg)
