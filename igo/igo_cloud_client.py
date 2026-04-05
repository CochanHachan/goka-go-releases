"""
囲碁対局 WebSocket クライアント
Tkinter (sync) と asyncio (async) のブリッジを提供する。

使い方:
    client = CloudClient(server_url, on_message_callback, on_disconnect_callback)
    client.connect(handle, rank, elo)
    client.send({"type": "match_offer_broadcast", ...})
    client.disconnect()
"""

import asyncio
import json
import threading
import logging

try:
    import websockets
except ImportError:
    websockets = None
    print("websockets が必要です: pip install websockets")

logger = logging.getLogger("igo_cloud")


class CloudClient:
    """WebSocket client for cloud-based Go game server."""

    def __init__(self, server_url, on_message_cb, on_disconnect_cb=None):
        """
        Args:
            server_url: WebSocket URL, e.g. "ws://34.153.211.101:8765"
            on_message_cb: callable(msg_dict) - called on UI thread via root.after
            on_disconnect_cb: callable() - called when connection drops
        """
        self.server_url = server_url
        self.on_message_cb = on_message_cb
        self.on_disconnect_cb = on_disconnect_cb
        self._ws = None
        self._loop = None
        self._thread = None
        self._running = False
        self._handle = None
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def connect(self, handle, rank="", elo=0, token=""):
        """Connect to the server and login. Non-blocking."""
        if self._running:
            return
        self._handle = handle
        self._rank = rank
        self._elo = elo
        self._token = token
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Disconnect from the server."""
        self._running = False
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)

    def send(self, msg_dict):
        """Send a message to the server. Thread-safe."""
        if self._loop and self._ws and self._connected:
            asyncio.run_coroutine_threadsafe(self._send(msg_dict), self._loop)

    def _run_loop(self):
        """Run asyncio event loop in background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_listen())
        except Exception as e:
            logger.error("CloudClient loop error: %s", e)
        finally:
            self._connected = False
            self._running = False
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _connect_and_listen(self):
        """Connect and listen for messages."""
        retry_delay = 2
        max_retry_delay = 30

        while self._running:
            try:
                # Build authenticated WS URL: /ws/{handle}/{token}
                ws_url = "{}/ws/{}/{}".format(self.server_url, self._handle, self._token)
                logger.info("Connecting to %s ...", ws_url)
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    # Server authenticates via URL; wait for login_ok
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    resp = json.loads(raw)
                    if resp.get("type") == "login_ok":
                        self._connected = True
                        logger.info("Connected as: %s", self._handle)
                        retry_delay = 2  # reset retry delay on success
                    else:
                        logger.error("Login failed: %s", resp)
                        return

                    # Message loop
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            if msg.get("type") == "pong":
                                continue  # heartbeat response, ignore
                            self.on_message_cb(msg)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON from server")
                        except Exception as e:
                            logger.error("Error handling message: %s", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Connection lost: %s. Reconnecting in %ds...", e, retry_delay)
                self._connected = False
                self._ws = None
                if self.on_disconnect_cb:
                    self.on_disconnect_cb()
                if not self._running:
                    break
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

        self._connected = False
        self._ws = None

    async def _send(self, msg_dict):
        """Send a message over WebSocket."""
        if self._ws:
            try:
                await self._ws.send(json.dumps(msg_dict, ensure_ascii=False))
            except Exception as e:
                logger.error("Send error: %s", e)

    async def _close_ws(self):
        """Close the WebSocket connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
