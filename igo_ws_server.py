#!/usr/bin/env python3
"""
囲碁対局 WebSocket サーバー
Cloud VM上で動作し、LAN外のクライアント同士を中継する。

機能:
  1. ユーザー登録（ログイン）: クライアント接続時にhandle_nameを登録
  2. オンライン一覧: 接続中ユーザーの一覧を全員にブロードキャスト
  3. 対局申し込み: 特定ユーザーへの対局オファーを中継
  4. 対局受諾/拒否: オファーへの応答を中継
  5. 対局中メッセージ中継: move, pass, resign, timeout を対戦相手に転送
  6. ハートビート: 接続維持の確認

ポート: 8765
"""

import asyncio
import json
import logging
import time
from collections import defaultdict

try:
    import websockets
except ImportError:
    print("websockets が必要です: pip3 install websockets")
    raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("igo_ws")

# ---- State ----

# handle_name -> websocket
connected_users = {}

# handle_name -> user info dict (handle, rank, elo, ...)
user_info = {}

# Active games: frozenset({player1, player2}) -> True
active_games = {}

# handle_name -> opponent handle_name (bidirectional)
game_pairs = {}


async def broadcast_online_list():
    """Send the current online user list to all connected clients."""
    online = []
    for handle, info in user_info.items():
        if handle in connected_users:
            online.append({
                "handle": handle,
                "rank": info.get("rank", ""),
                "elo": info.get("elo", 0),
            })
    msg = json.dumps({"type": "online_list", "users": online}, ensure_ascii=False)
    # Send to all connected websockets
    to_remove = []
    for handle, ws in list(connected_users.items()):
        try:
            await ws.send(msg)
        except Exception:
            to_remove.append(handle)
    for h in to_remove:
        await handle_user_disconnect(h)


async def send_to_user(handle, msg_dict):
    """Send a JSON message to a specific user."""
    ws = connected_users.get(handle)
    if ws:
        try:
            await ws.send(json.dumps(msg_dict, ensure_ascii=False))
            return True
        except Exception:
            return False
    return False


async def handle_user_disconnect(handle):
    """Clean up when a user disconnects."""
    connected_users.pop(handle, None)
    user_info.pop(handle, None)

    # If in a game, notify opponent
    opponent = game_pairs.pop(handle, None)
    if opponent:
        game_pairs.pop(opponent, None)
        key = frozenset({handle, opponent})
        active_games.pop(key, None)
        await send_to_user(opponent, {
            "type": "opponent_disconnected",
            "handle": handle
        })

    logger.info("User disconnected: %s", handle)
    await broadcast_online_list()


async def handle_message(ws, handle, msg):
    """Process a message from an authenticated user."""
    msg_type = msg.get("type")

    if msg_type == "match_offer":
        # Forward match offer to target user
        target = msg.get("target")
        if target and target in connected_users:
            await send_to_user(target, {
                "type": "match_offer",
                "from": handle,
                "rank": msg.get("rank", ""),
                "elo": msg.get("elo", 0),
                "main_time": msg.get("main_time", 600),
                "byo_time": msg.get("byo_time", 30),
                "byo_periods": msg.get("byo_periods", 5),
                "komi": msg.get("komi", 6.5),
            })
            logger.info("Match offer: %s -> %s", handle, target)

    elif msg_type == "match_offer_broadcast":
        # Broadcast match offer to ALL online users (except sender)
        offer_msg = {
            "type": "match_offer",
            "from": handle,
            "rank": msg.get("rank", ""),
            "elo": msg.get("elo", 0),
            "main_time": msg.get("main_time", 600),
            "byo_time": msg.get("byo_time", 30),
            "byo_periods": msg.get("byo_periods", 5),
            "komi": msg.get("komi", 6.5),
        }
        for other_handle, other_ws in list(connected_users.items()):
            if other_handle != handle:
                try:
                    await other_ws.send(json.dumps(offer_msg, ensure_ascii=False))
                except Exception:
                    pass
        logger.info("Match offer broadcast from: %s", handle)

    elif msg_type == "match_accept":
        # Accept a match offer
        target = msg.get("target")  # the person who offered
        if target and target in connected_users:
            # Set up game pair
            game_pairs[handle] = target
            game_pairs[target] = handle
            key = frozenset({handle, target})
            active_games[key] = True

            # Randomly assign black/white
            import random
            if random.choice([True, False]):
                offerer_color = "black"
                accepter_color = "white"
            else:
                offerer_color = "white"
                accepter_color = "black"

            # Notify the offerer that their match was accepted
            await send_to_user(target, {
                "type": "match_accepted",
                "from": handle,
                "rank": msg.get("rank", ""),
                "elo": msg.get("elo", 0),
                "your_color": offerer_color,
            })
            # Notify the accepter with game start info
            await send_to_user(handle, {
                "type": "match_started",
                "opponent": target,
                "rank": user_info.get(target, {}).get("rank", ""),
                "elo": user_info.get(target, {}).get("elo", 0),
                "your_color": accepter_color,
            })
            logger.info("Match started: %s vs %s (black=%s)",
                        handle, target,
                        target if offerer_color == "black" else handle)

            # Notify all OTHER users that this match offer is taken
            taken_msg = {
                "type": "match_taken",
                "offerer": target,
                "accepter": handle,
            }
            for other_handle, other_ws in list(connected_users.items()):
                if other_handle != handle and other_handle != target:
                    try:
                        await other_ws.send(json.dumps(taken_msg, ensure_ascii=False))
                    except Exception:
                        pass

    elif msg_type == "match_decline":
        # Decline a match offer
        target = msg.get("target")
        if target and target in connected_users:
            await send_to_user(target, {
                "type": "match_declined",
                "from": handle,
            })
            logger.info("Match declined: %s declined %s", handle, target)

    elif msg_type == "match_cancel":
        # Cancel own match offer
        # Broadcast cancellation to all users
        cancel_msg = {
            "type": "match_cancelled",
            "from": handle,
        }
        for other_handle, other_ws in list(connected_users.items()):
            if other_handle != handle:
                try:
                    await other_ws.send(json.dumps(cancel_msg, ensure_ascii=False))
                except Exception:
                    pass
        logger.info("Match cancelled by: %s", handle)

    elif msg_type in ("move", "pass", "resign", "timeout", "score_result"):
        # Game messages: forward to opponent
        opponent = game_pairs.get(handle)
        if opponent:
            forward_msg = dict(msg)
            forward_msg["from"] = handle
            await send_to_user(opponent, forward_msg)
            logger.debug("Game msg %s: %s -> %s", msg_type, handle, opponent)

            # If resign or timeout, end the game
            if msg_type in ("resign", "timeout"):
                game_pairs.pop(handle, None)
                game_pairs.pop(opponent, None)
                key = frozenset({handle, opponent})
                active_games.pop(key, None)
                logger.info("Game ended (%s): %s vs %s", msg_type, handle, opponent)

    elif msg_type == "game_end":
        # Explicit game end (e.g., after scoring)
        opponent = game_pairs.pop(handle, None)
        if opponent:
            game_pairs.pop(opponent, None)
            key = frozenset({handle, opponent})
            active_games.pop(key, None)
            await send_to_user(opponent, {"type": "game_end", "from": handle})
            logger.info("Game ended (explicit): %s vs %s", handle, opponent)

    elif msg_type == "heartbeat":
        # Client ping - respond with pong
        await ws.send(json.dumps({"type": "pong"}))

    else:
        logger.warning("Unknown message type: %s from %s", msg_type, handle)


async def handler(ws):
    """Handle a single WebSocket connection."""
    handle = None
    try:
        # First message must be login
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        msg = json.loads(raw)
        if msg.get("type") != "login":
            await ws.send(json.dumps({"type": "error", "message": "First message must be login"}))
            return

        handle = msg.get("handle")
        if not handle:
            await ws.send(json.dumps({"type": "error", "message": "handle is required"}))
            return

        # If already connected, close old connection
        old_ws = connected_users.get(handle)
        if old_ws:
            try:
                await old_ws.close()
            except Exception:
                pass

        connected_users[handle] = ws
        user_info[handle] = {
            "handle": handle,
            "rank": msg.get("rank", ""),
            "elo": msg.get("elo", 0),
        }
        logger.info("User logged in: %s (rank=%s, elo=%s)",
                     handle, msg.get("rank"), msg.get("elo"))

        # Confirm login
        await ws.send(json.dumps({"type": "login_ok", "handle": handle}))

        # Broadcast updated online list
        await broadcast_online_list()

        # Message loop
        async for raw in ws:
            try:
                msg = json.loads(raw)
                await handle_message(ws, handle, msg)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from %s", handle)
            except Exception as e:
                logger.error("Error handling message from %s: %s", handle, e)

    except asyncio.TimeoutError:
        logger.warning("Login timeout")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.error("Connection error: %s", e)
    finally:
        if handle:
            await handle_user_disconnect(handle)


async def main():
    port = 8765
    logger.info("Starting Igo WebSocket server on port %d ...", port)
    async with websockets.serve(handler, "0.0.0.0", port):
        logger.info("Server is running. Press Ctrl+C to stop.")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
