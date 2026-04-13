#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
碁華 Goka GO — バックエンドサーバー
REST API (FastAPI) + WebSocket 中継サーバー

起動方法:
    pip install fastapi uvicorn websockets
    python server.py

ポート: 8000
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

try:
    import uvicorn
except ImportError:
    print("uvicorn が必要です: pip install uvicorn")
    raise

try:
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    print("fastapi が必要です: pip install fastapi")
    raise

# ---------------------------------------------------------------------------
# ロギング設定
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("goka_server")

# ---------------------------------------------------------------------------
# 定数（環境変数で上書き可能 — ステージング環境用）
# ---------------------------------------------------------------------------
DB_PATH = Path(os.environ.get("GOKA_DB_PATH",
               str(Path(__file__).parent / "igo_users.db")))
PORT = int(os.environ.get("GOKA_PORT", "8000"))
_ENV_LABEL = os.environ.get("GOKA_ENV", "production")

# ---------------------------------------------------------------------------
# AIボット定義
# ---------------------------------------------------------------------------
AI_BOTS = {
    # 級位者 (20級〜1級)  AIロボ1(弱)〜AIロボ30(最強)
    "AIロボ1":  {"elo": 430,  "rank": "20級", "visits": 1},
    "AIロボ2":  {"elo": 490,  "rank": "19級", "visits": 1},
    "AIロボ3":  {"elo": 550,  "rank": "18級", "visits": 2},
    "AIロボ4":  {"elo": 610,  "rank": "17級", "visits": 2},
    "AIロボ5":  {"elo": 670,  "rank": "16級", "visits": 3},
    "AIロボ6":  {"elo": 730,  "rank": "15級", "visits": 3},
    "AIロボ7":  {"elo": 790,  "rank": "14級", "visits": 4},
    "AIロボ8":  {"elo": 850,  "rank": "13級", "visits": 5},
    "AIロボ9":  {"elo": 910,  "rank": "12級", "visits": 6},
    "AIロボ10": {"elo": 970,  "rank": "11級", "visits": 8},
    "AIロボ11": {"elo": 1050, "rank": "10級", "visits": 10},
    "AIロボ12": {"elo": 1150, "rank": "9級",  "visits": 14},
    "AIロボ13": {"elo": 1250, "rank": "8級",  "visits": 18},
    "AIロボ14": {"elo": 1350, "rank": "7級",  "visits": 24},
    "AIロボ15": {"elo": 1450, "rank": "6級",  "visits": 32},
    "AIロボ16": {"elo": 1550, "rank": "5級",  "visits": 42},
    "AIロボ17": {"elo": 1650, "rank": "4級",  "visits": 56},
    "AIロボ18": {"elo": 1750, "rank": "3級",  "visits": 75},
    "AIロボ19": {"elo": 1850, "rank": "2級",  "visits": 100},
    "AIロボ20": {"elo": 1975, "rank": "1級",  "visits": 130},
    # 段位者 (初段〜9段)
    "AIロボ21": {"elo": 2125, "rank": "1段",  "visits": 180},
    "AIロボ22": {"elo": 2275, "rank": "2段",  "visits": 250},
    "AIロボ23": {"elo": 2425, "rank": "3段",  "visits": 350},
    "AIロボ24": {"elo": 2575, "rank": "4段",  "visits": 500},
    "AIロボ25": {"elo": 2725, "rank": "5段",  "visits": 700},
    "AIロボ26": {"elo": 2850, "rank": "6段",  "visits": 1000},
    "AIロボ27": {"elo": 2950, "rank": "7段",  "visits": 1500},
    "AIロボ28": {"elo": 3050, "rank": "8段",  "visits": 2000},
    "AIロボ29": {"elo": 3150, "rank": "9段",  "visits": 3000},
    "AIロボ30": {"elo": 3250, "rank": "9段",  "visits": 5000},
}

# ---------------------------------------------------------------------------
# メモリ上のトークン管理  {token: handle_name}
# ---------------------------------------------------------------------------
active_tokens: Dict[str, str] = {}

# ---------------------------------------------------------------------------
# WebSocket 状態管理
# ---------------------------------------------------------------------------
# handle_name -> WebSocket
connected_users: Dict[str, WebSocket] = {}

# handle_name -> user info dict (handle, rank, elo)
ws_user_info: Dict[str, dict] = {}

# handle_name -> bool (AIロボと対局するかどうか、デフォルトTrue)
ai_preference: Dict[str, bool] = {}

# handle_name -> dict (ユーザー別ボット対局時間設定)
# {"main_time": int(秒), "byo_time": int(秒), "byo_periods": int}
bot_time_preferences: Dict[str, dict] = {}

# handle_name -> str  ユーザーの詳細ステータス
# "ログイン" / "対局申請中" / "対局申請受付中" / "申請中・受付中" / "対局中" / "検討中"
user_status: Dict[str, str] = {}

# handle_name -> opponent handle_name (双方向)
game_pairs: Dict[str, str] = {}

# frozenset({p1, p2}) -> True
active_games: Dict[frozenset, bool] = {}

# AIボット自動タイマー管理
# handle -> asyncio.Task (ログイン後のボット申込タイマー)
bot_offer_timers: Dict[str, asyncio.Task] = {}
# handle -> asyncio.Task (対局申込後のボット承諾タイマー)
bot_accept_timers: Dict[str, asyncio.Task] = {}
# handle -> pending offer info (タイムアウト時にボットが承諾するための情報)
pending_offers: Dict[str, dict] = {}

BOT_AUTO_DELAY = 60  # 秒 — ボットが挑戦状を送るまでの待機時間
# 重要: この値はクライアント側の _hosting_timeout（get_offer_timeout_ms）より
# 十分短くなければならない。同じかそれ以上だとクライアントが先にキャンセルし、
# ボットの挑戦状が届かなくなる。


def _get_offer_timeout_sec() -> int:
    """管理者画面の offer_timeout_min 設定を秒単位で返す（デフォルト: 180秒）。"""
    try:
        settings = _load_settings()
        minutes = int(settings.get("offer_timeout_min", 3))
        return max(1, minutes) * 60
    except Exception:
        return 180


def _find_closest_bot(elo: float) -> Optional[str]:
    """ELOが最も近いAIボットを返す。"""
    if not AI_BOTS:
        return None
    return min(AI_BOTS.keys(), key=lambda name: abs(AI_BOTS[name]["elo"] - elo))


# ---------------------------------------------------------------------------
# データベース初期化
# ---------------------------------------------------------------------------
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """起動時にDBとテーブルを自動作成する。"""
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            real_name       TEXT    NOT NULL,
            handle_name     TEXT    NOT NULL UNIQUE,
            password_hash   TEXT    NOT NULL,
            salt            TEXT    NOT NULL,
            password_enc    TEXT    NOT NULL DEFAULT '',
            elo             REAL    NOT NULL DEFAULT 0,
            rank            TEXT    NOT NULL DEFAULT '30級',
            language        TEXT    NOT NULL DEFAULT 'ja',
            email           TEXT    NOT NULL DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # password_enc カラムが無い既存DBに追加
    try:
        conn.execute("ALTER TABLE users ADD COLUMN password_enc TEXT NOT NULL DEFAULT ''")
        conn.commit()
        logger.info("Added password_enc column to users table")
    except sqlite3.OperationalError:
        pass  # 既にカラムが存在する場合
    # email カラムが無い既存DBに追加
    try:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        conn.commit()
        logger.info("Added email column to users table")
    except sqlite3.OperationalError:
        pass  # 既にカラムが存在する場合
    conn.commit()
    conn.close()
    logger.info("Database initialized: %s", DB_PATH)


# ---------------------------------------------------------------------------
# パスワードユーティリティ
# ---------------------------------------------------------------------------
# password_enc には base64 プレフィックス "B64:" または Fernet 暗号文を保存
# base64 は一時保管用。管理者画面がローカルの鍵で暗号化して書き戻す。

def _b64_encode_password(password: str) -> str:
    """パスワードをbase64で仮保管形式にする。"""
    return "B64:" + base64.b64encode(password.encode("utf-8")).decode("ascii")

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_hex(32)


# ---------------------------------------------------------------------------
# Pydantic リクエストモデル
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    real_name: str
    handle_name: str
    password: str
    rank: str = "30級"
    elo: Optional[float] = None
    email: str = ""


class LoginRequest(BaseModel):
    handle_name: str
    password: str


class UpdateEloRequest(BaseModel):
    elo: float
    token: str


# ---------------------------------------------------------------------------
# FastAPI アプリ
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Goka GO server [%s] starting on port %d (db=%s)",
               _ENV_LABEL, PORT, DB_PATH)
    yield
    logger.info("Goka GO server [%s] shutting down.", _ENV_LABEL)


app = FastAPI(title="Goka GO API", version="1.0.0", lifespan=lifespan)

# CORS 全許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST API エンドポイント
# ---------------------------------------------------------------------------

@app.post("/api/register")
async def register(req: RegisterRequest):
    """ユーザー登録。"""
    if not req.real_name or not req.handle_name or not req.password:
        return {"success": False, "message": "必須項目が不足しています"}

    salt = secrets.token_hex(16)
    pw_hash = hash_password(req.password, salt)
    pw_enc = _b64_encode_password(req.password)

    conn = get_db_connection()
    try:
        # ELO 初期値: クライアントから送られたeloを優先、なければrankから推定
        elo = req.elo if req.elo is not None else _rank_to_initial_elo(req.rank)
        conn.execute(
            "INSERT INTO users (real_name, handle_name, password_hash, salt, password_enc, elo, rank, email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (req.real_name, req.handle_name, pw_hash, salt, pw_enc, elo, req.rank, req.email)
        )
        conn.commit()
        logger.info("Registered new user: %s", req.handle_name)
        return {"success": True, "message": "登録しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "そのハンドルネームはすでに使用されています"}
    finally:
        conn.close()


@app.post("/api/login")
async def login(req: LoginRequest):
    """ログイン。成功時にトークンを返す。"""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE handle_name = ?", (req.handle_name,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"success": False, "token": "", "user": None, "message": "ユーザーが見つかりません"}

    expected = hash_password(req.password, row["salt"])
    if expected != row["password_hash"]:
        return {"success": False, "token": "", "user": None, "message": "パスワードが正しくありません"}

    # 既存ユーザーの暗号化パスワードが未設定なら追記（移行用）
    if not (row["password_enc"] if row["password_enc"] else ""):
        try:
            pw_enc = _b64_encode_password(req.password)
            conn2 = get_db_connection()
            conn2.execute("UPDATE users SET password_enc = ? WHERE handle_name = ?",
                          (pw_enc, req.handle_name))
            conn2.commit()
            conn2.close()
            logger.info("Migrated password_enc for: %s", req.handle_name)
        except Exception as e:
            logger.warning("Failed to migrate password_enc: %s", e)

    token = generate_token()
    active_tokens[token] = req.handle_name
    logger.info("Login: %s", req.handle_name)

    return {
        "success": True,
        "token": token,
        "user": {
            "handle_name": row["handle_name"],
            "real_name": row["real_name"],
            "elo": row["elo"],
            "rank": row["rank"],
            "language": row["language"] if row["language"] else "ja",
        }
    }


@app.get("/api/users")
async def get_users():
    """全ユーザー一覧を返す。"""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, handle_name, real_name, elo, rank, password_enc, email, created_at FROM users ORDER BY elo DESC"
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        pw_enc = row["password_enc"] if row["password_enc"] else ""
        hn = row["handle_name"]
        result.append({
            "id": row["id"],
            "handle_name": hn,
            "real_name": row["real_name"],
            "elo": row["elo"],
            "rank": row["rank"],
            "password_enc": pw_enc,
            "email": row["email"] if row["email"] else "",
            "created_at": row["created_at"],
            "online": hn in connected_users,
            "status": user_status.get(hn, ""),
            "opponent": game_pairs.get(hn, ""),
        })
    return result


@app.put("/api/user/{handle_name}/elo")
async def update_elo(handle_name: str, req: UpdateEloRequest):
    """ELO レートを更新する。トークン認証必須。"""
    if req.token not in active_tokens and req.token != "admin":
        raise HTTPException(status_code=401, detail="無効なトークンです")

    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE handle_name = ?", (handle_name,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

        conn.execute(
            "UPDATE users SET elo = ? WHERE handle_name = ?",
            (req.elo, handle_name)
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("ELO updated: %s -> %.1f", handle_name, req.elo)
    return {"success": True}


class UpdateLanguageRequest(BaseModel):
    handle_name: str
    language: str
    token: str

@app.put("/api/user/language")
async def update_user_language(req: UpdateLanguageRequest):
    """ユーザーの言語設定を更新する。"""
    if req.token not in active_tokens or active_tokens[req.token] != req.handle_name:
        return {"success": False, "message": "Unauthorized"}
    if req.language not in ("ja", "en", "zh", "ko"):
        return {"success": False, "message": "Invalid language code"}
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET language = ? WHERE handle_name = ?",
                     (req.language, req.handle_name))
        conn.commit()
    finally:
        conn.close()
    logger.info("Language updated: %s -> %s", req.handle_name, req.language)
    return {"success": True}


class UpdatePasswordEncRequest(BaseModel):
    handle_name: str
    password_enc: str

@app.put("/api/user/password_enc")
async def update_password_enc(req: UpdatePasswordEncRequest):
    """管理者が暗号化パスワードを更新する（base64→Fernet移行用）。"""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET password_enc = ? WHERE handle_name = ?",
                     (req.password_enc, req.handle_name))
        conn.commit()
    finally:
        conn.close()
    return {"success": True}


@app.delete("/api/user/{handle_name}")
async def delete_user(handle_name: str):
    """ユーザーを削除する。"""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE handle_name = ?", (handle_name,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
        conn.execute("DELETE FROM users WHERE handle_name = ?", (handle_name,))
        conn.commit()
    finally:
        conn.close()
    logger.info("User deleted: %s", handle_name)
    return {"success": True}


@app.get("/api/online")
async def get_online():
    """現在オンラインのユーザー一覧を返す。"""
    result = []
    for handle, info in ws_user_info.items():
        if handle in connected_users:
            result.append({
                "handle_name": handle,
                "elo": info.get("elo", 0),
            })
    return result


# ---------------------------------------------------------------------------
# グローバル設定 API
# ---------------------------------------------------------------------------
SETTINGS_PATH = Path(os.environ.get("GOKA_SETTINGS_PATH",
                     str(Path(__file__).parent / "app_settings.json")))


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"theme": "light", "offer_timeout_min": 3,
                "fischer_main_time": 300, "fischer_increment": 10}


def _save_settings(settings: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


class UpdateSettingsRequest(BaseModel):
    theme: Optional[str] = None
    offer_timeout_min: Optional[int] = None
    fischer_main_time: Optional[int] = None
    fischer_increment: Optional[int] = None


@app.get("/api/settings")
async def get_settings():
    """グローバル設定を返す。"""
    return _load_settings()


@app.put("/api/settings")
async def update_settings(req: UpdateSettingsRequest):
    """グローバル設定を更新する。"""
    settings = _load_settings()
    if req.theme is not None:
        settings["theme"] = req.theme
    if req.offer_timeout_min is not None:
        settings["offer_timeout_min"] = req.offer_timeout_min
    if req.fischer_main_time is not None:
        settings["fischer_main_time"] = req.fischer_main_time
    if req.fischer_increment is not None:
        settings["fischer_increment"] = req.fischer_increment
    _save_settings(settings)
    logger.info("Settings updated: %s", settings)
    return {"success": True, "settings": settings}


# ---------------------------------------------------------------------------
# WebSocket: 既存プロトコルをそのまま中継
# ---------------------------------------------------------------------------

async def ws_broadcast_online_list():
    """接続中の全クライアントにオンラインリストを送信する。"""
    online = [
        {
            "handle": h,
            "rank": ws_user_info[h].get("rank", ""),
            "elo": ws_user_info[h].get("elo", 0),
        }
        for h in ws_user_info
        if h in connected_users
    ]
    # AIボットを常にオンラインに追加
    for bot_name, bot_info in AI_BOTS.items():
        online.append({
            "handle": bot_name,
            "rank": bot_info["rank"],
            "elo": bot_info["elo"],
            "is_bot": True,
        })
    msg = json.dumps({"type": "online_list", "users": online}, ensure_ascii=False)
    dead = []
    for handle, ws in list(connected_users.items()):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append((handle, ws))
    for h, ws in dead:
        await ws_disconnect(h, ws)


async def ws_send(handle: str, msg_dict: dict) -> bool:
    """特定ユーザーへ JSON メッセージを送信する。"""
    ws = connected_users.get(handle)
    if ws:
        try:
            await ws.send_text(json.dumps(msg_dict, ensure_ascii=False))
            return True
        except Exception:
            return False
    return False


async def ws_disconnect(handle: str, ws: WebSocket = None):
    """ユーザー切断時のクリーンアップ。

    ws が指定された場合、現在の接続と一致するときだけクリーンアップを行う。
    再接続で新しい WebSocket が登録済みなら、古い接続のクリーンアップは
    新しい接続を壊さないようにスキップする。
    """
    # 新しい接続が既に登録されている場合はスキップ（再接続レース防止）
    if ws is not None and connected_users.get(handle) is not ws:
        logger.info("WS disconnect skipped (superseded): %s", handle)
        return

    connected_users.pop(handle, None)
    ws_user_info.pop(handle, None)
    ai_preference.pop(handle, None)
    user_status.pop(handle, None)

    # 対局申請中だった場合、他クライアントに通知して申請を削除
    if handle in pending_offers:
        pending_offers.pop(handle, None)
        _cancel_bot_timers(handle)
        taken_msg = json.dumps({"type": "match_taken", "offerer": handle, "accepter": ""},
                               ensure_ascii=False)
        for other_handle, other_ws in list(connected_users.items()):
            try:
                await other_ws.send_text(taken_msg)
            except Exception:
                pass

    opponent = game_pairs.pop(handle, None)
    if opponent:
        game_pairs.pop(opponent, None)
        active_games.pop(frozenset({handle, opponent}), None)
        await ws_send(opponent, {"type": "opponent_disconnected", "handle": handle})

    logger.info("WS disconnected: %s", handle)
    await ws_broadcast_online_list()


def _get_bot_time_settings(handle: str = "") -> dict:
    """ボットオファー用の時間パラメータを返す。

    ユーザー別設定があればそれを優先し、なければ管理者設定を使う。
    """
    # ユーザー別設定を優先
    if handle and handle in bot_time_preferences:
        user_cfg = bot_time_preferences[handle]
        if user_cfg.get("time_control") == "fischer":
            # ユーザーがFischerを選択 → 管理者のFischer設定を使う
            settings = _load_settings()
            fischer_main = settings.get("fischer_main_time")
            fischer_inc = settings.get("fischer_increment")
            if fischer_main is not None and fischer_inc is not None:
                return {
                    "main_time": int(fischer_main),
                    "byo_time": 0,
                    "byo_periods": 0,
                    "time_control": "fischer",
                    "fischer_increment": int(fischer_inc),
                }
            # Fischer設定が管理者未設定の場合はデフォルト秒読みにフォールバック
        else:
            return {
                "main_time": int(user_cfg.get("main_time", 600)),
                "byo_time": int(user_cfg.get("byo_time", 30)),
                "byo_periods": int(user_cfg.get("byo_periods", 5)),
                "time_control": "byoyomi",
                "fischer_increment": 0,
            }
    # 管理者設定（Fischer対応）
    settings = _load_settings()
    fischer_main = settings.get("fischer_main_time")
    fischer_inc = settings.get("fischer_increment")
    if fischer_main is not None and fischer_inc is not None:
        return {
            "main_time": int(fischer_main),
            "byo_time": 0,
            "byo_periods": 0,
            "time_control": "fischer",
            "fischer_increment": int(fischer_inc),
        }
    return {
        "main_time": 600,
        "byo_time": 30,
        "byo_periods": 5,
        "time_control": "byoyomi",
        "fischer_increment": 0,
    }


async def _bot_auto_offer(handle: str):
    """対局申請後、BOT_AUTO_DELAY 秒で棋力の近いボットが挑戦状を送る。

    注意: スリープ時間はクライアント側の hosting_timeout（get_offer_timeout_ms）
    より短くすること。同じ値だとクライアントが先にキャンセルしてしまう。
    """
    try:
        await asyncio.sleep(BOT_AUTO_DELAY)
        # まだ接続中かつ対局中でないか確認
        if handle not in connected_users or handle in game_pairs:
            return
        # AI対局がオフなら何もしない
        if not ai_preference.get(handle, True):
            return
        info = ws_user_info.get(handle, {})
        elo = info.get("elo", 0)
        bot_name = _find_closest_bot(elo)
        if not bot_name:
            return
        bot_info = AI_BOTS[bot_name]
        _cur = user_status.get(handle, "ログイン")
        if _cur == "対局申請中":
            user_status[handle] = "申請・受付"
        else:
            user_status[handle] = "対局受付中"
        time_cfg = _get_bot_time_settings(handle)
        await ws_send(handle, {
            "type": "match_offer",
            "from": bot_name,
            "rank": bot_info["rank"],
            "elo": bot_info["elo"],
            "main_time": time_cfg["main_time"],
            "byo_time": time_cfg["byo_time"],
            "byo_periods": time_cfg["byo_periods"],
            "komi": 7.5,
            "is_bot": True,
            "time_control": time_cfg["time_control"],
            "fischer_increment": time_cfg["fischer_increment"],
        })
        logger.info("Bot auto-offer: %s -> %s", bot_name, handle)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Bot auto-offer error for %s: %s", handle, e)
    finally:
        bot_offer_timers.pop(handle, None)


async def _bot_auto_accept(handle: str):
    """対局申込後、BOT_AUTO_DELAY 秒で承諾がなければボットが挑戦状を送る。

    注意: スリープ時間はクライアント側の hosting_timeout（get_offer_timeout_ms）
    より短くすること。同じ値だとクライアントが先にキャンセルしてしまう。
    """
    try:
        await asyncio.sleep(BOT_AUTO_DELAY)
        # まだ接続中かつ対局中でないか確認
        if handle not in connected_users or handle in game_pairs:
            return
        # AI対局がオフなら何もしない
        if not ai_preference.get(handle, True):
            return
        offer_info = pending_offers.pop(handle, None)
        if not offer_info:
            return
        info = ws_user_info.get(handle, {})
        elo = info.get("elo", 0)
        bot_name = _find_closest_bot(elo)
        if not bot_name:
            return
        bot_info = AI_BOTS[bot_name]
        # ボットからの挑戦状として送信（ユーザーが承諾してから対局開始）
        _cur = user_status.get(handle, "ログイン")
        if _cur == "対局申請中":
            user_status[handle] = "申請・受付"
        else:
            user_status[handle] = "対局受付中"
        time_cfg = _get_bot_time_settings(handle)
        await ws_send(handle, {
            "type": "match_offer",
            "from": bot_name,
            "rank": bot_info["rank"],
            "elo": bot_info["elo"],
            "main_time": time_cfg["main_time"],
            "byo_time": time_cfg["byo_time"],
            "byo_periods": time_cfg["byo_periods"],
            "komi": 7.5,
            "is_bot": True,
            "time_control": time_cfg["time_control"],
            "fischer_increment": time_cfg["fischer_increment"],
        })
        logger.info("Bot auto-offer (after timeout): %s -> %s", bot_name, handle)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Bot auto-accept error for %s: %s", handle, e)
    finally:
        bot_accept_timers.pop(handle, None)


def _cancel_bot_timers(handle: str):
    """指定ユーザーのボットタイマーをすべてキャンセルする。"""
    task = bot_offer_timers.pop(handle, None)
    if task:
        task.cancel()
    task = bot_accept_timers.pop(handle, None)
    if task:
        task.cancel()
    pending_offers.pop(handle, None)


async def ws_handle_message(ws: WebSocket, handle: str, msg: dict):
    """クライアントからのメッセージを処理・中継する。"""
    msg_type = msg.get("type")

    if msg_type == "match_offer":
        # ユーザーが対局申込 → ボット自動申込タイマーをキャンセル
        _cancel_bot_timers(handle)
        target = msg.get("target")
        # AIボットへの申込は自動承諾
        if target and target in AI_BOTS:
            bot_info = AI_BOTS[target]
            import random
            user_color = random.choice(["black", "white"])
            bot_color = "white" if user_color == "black" else "black"
            game_pairs[handle] = target
            game_pairs[target] = handle
            active_games[frozenset({handle, target})] = True
            user_status[handle] = "対局中"
            await ws_send(handle, {
                "type": "match_accepted",
                "from": target,
                "rank": bot_info["rank"],
                "elo": bot_info["elo"],
                "your_color": user_color,
                "is_bot": True,
                "bot_visits": bot_info["visits"],
            })
            logger.info("AI match auto-accepted: %s vs %s", handle, target)
            # ボット対局でも他ユーザーに通知して挑戦状リストから消す
            taken_msg = json.dumps(
                {"type": "match_taken", "offerer": handle, "accepter": ""},
                ensure_ascii=False
            )
            for other_handle, other_ws in list(connected_users.items()):
                if other_handle != handle:
                    try:
                        await other_ws.send_text(taken_msg)
                    except Exception:
                        pass
        elif target and target in connected_users:
            # 個別申込 → 既に受付中なら「申請・受付」、そうでなければ「対局申請中」
            _my = user_status.get(handle, "ログイン")
            if _my in ("対局受付中", "申請・受付"):
                user_status[handle] = "申請・受付"
            else:
                user_status[handle] = "対局申請中"
            # 相手は受付中（既に申請中なら「申請・受付」）
            _cur = user_status.get(target, "ログイン")
            if _cur == "対局申請中":
                user_status[target] = "申請・受付"
            elif _cur not in ("対局中", "検討中"):
                user_status[target] = "対局受付中"
            await ws_send(target, {
                "type": "match_offer",
                "from": handle,
                "rank": msg.get("rank", ""),
                "elo": msg.get("elo", 0),
                "main_time": msg.get("main_time", 600),
                "byo_time": msg.get("byo_time", 30),
                "byo_periods": msg.get("byo_periods", 5),
                "komi": msg.get("komi", 7.5),
                "time_control": msg.get("time_control", "byoyomi"),
                "fischer_increment": msg.get("fischer_increment", 0),
            })
            logger.info("Match offer: %s -> %s", handle, target)
            # 1分後にボットが自動承諾するタイマー開始
            pending_offers[handle] = {"target": target}
            bot_accept_timers[handle] = asyncio.create_task(
                _bot_auto_accept(handle)
            )

    elif msg_type == "match_offer_broadcast":
        # ボット自動申込タイマーをキャンセル
        _cancel_bot_timers(handle)
        # 既に受付中なら「申請・受付」、そうでなければ「対局申請中」
        _my = user_status.get(handle, "ログイン")
        if _my in ("対局受付中", "申請・受付"):
            user_status[handle] = "申請・受付"
        else:
            user_status[handle] = "対局申請中"
        offer_msg = {
            "type": "match_offer",
            "from": handle,
            "rank": msg.get("rank", ""),
            "elo": msg.get("elo", 0),
            "main_time": msg.get("main_time", 600),
            "byo_time": msg.get("byo_time", 30),
            "byo_periods": msg.get("byo_periods", 5),
            "komi": msg.get("komi", 7.5),
            "time_control": msg.get("time_control", "byoyomi"),
            "fischer_increment": msg.get("fischer_increment", 0),
        }
        payload = json.dumps(offer_msg, ensure_ascii=False)
        for other_handle, other_ws in list(connected_users.items()):
            if other_handle != handle:
                try:
                    await other_ws.send_text(payload)
                except Exception:
                    pass
        logger.info("Match offer broadcast from: %s", handle)
        pending_offers[handle] = {"broadcast": True}
        # 対局申請後 BOT_AUTO_DELAY 秒で棋力の近いボットが挑戦状を送る
        bot_offer_timers[handle] = asyncio.create_task(
            _bot_auto_offer(handle)
        )

    elif msg_type == "match_accept":
        target = msg.get("target")
        # 承諾された相手のボットタイマーをキャンセル
        if target:
            _cancel_bot_timers(target)
        _cancel_bot_timers(handle)
        # AIボットの申込を承諾 → 即対局開始
        if target and target in AI_BOTS:
            bot_info = AI_BOTS[target]
            import random
            accepter_color = random.choice(["black", "white"])
            game_pairs[handle] = target
            game_pairs[target] = handle
            active_games[frozenset({handle, target})] = True
            user_status[handle] = "対局中"
            await ws_send(handle, {
                "type": "match_started",
                "opponent": target,
                "rank": bot_info["rank"],
                "elo": bot_info["elo"],
                "your_color": accepter_color,
                "is_bot": True,
                "bot_visits": bot_info["visits"],
            })
            logger.info("User accepted bot offer: %s vs %s", handle, target)
            # ボット対局でも他ユーザーに通知して挑戦状リストから消す
            taken_msg = json.dumps(
                {"type": "match_taken", "offerer": handle, "accepter": ""},
                ensure_ascii=False
            )
            for other_handle, other_ws in list(connected_users.items()):
                if other_handle != handle:
                    try:
                        await other_ws.send_text(taken_msg)
                    except Exception:
                        pass
        elif target and target in connected_users:
            game_pairs[handle] = target
            game_pairs[target] = handle
            active_games[frozenset({handle, target})] = True
            user_status[handle] = "対局中"
            user_status[target] = "対局中"

            import random
            offerer_color = random.choice(["black", "white"])
            accepter_color = "white" if offerer_color == "black" else "black"

            await ws_send(target, {
                "type": "match_accepted",
                "from": handle,
                "rank": msg.get("rank", ""),
                "elo": msg.get("elo", 0),
                "your_color": offerer_color,
            })
            await ws_send(handle, {
                "type": "match_started",
                "opponent": target,
                "rank": ws_user_info.get(target, {}).get("rank", ""),
                "elo": ws_user_info.get(target, {}).get("elo", 0),
                "your_color": accepter_color,
            })
            logger.info("Match started: %s vs %s", handle, target)

            # 両プレイヤーの pending_offers をクリーンアップ
            pending_offers.pop(handle, None)
            pending_offers.pop(target, None)

            # 両プレイヤーの申請を他の全員に通知（対局中は挑戦状リストから消す）
            taken_players = [target, handle]
            for player in taken_players:
                taken_msg = json.dumps(
                    {"type": "match_taken", "offerer": player, "accepter": ""},
                    ensure_ascii=False
                )
                for other_handle, other_ws in list(connected_users.items()):
                    if other_handle not in (handle, target):
                        try:
                            await other_ws.send_text(taken_msg)
                        except Exception:
                            pass

    elif msg_type == "match_decline":
        target = msg.get("target")
        if target:
            await ws_send(target, {"type": "match_declined", "from": handle})
            logger.info("Match declined: %s declined %s", handle, target)

    elif msg_type == "match_cancel":
        # 既に対局中なら無視（対局成立後にクライアントが遅れて送る場合がある）
        if user_status.get(handle) == "対局中":
            logger.debug("Ignoring match_cancel from %s (already in game)", handle)
        else:
            # reason="timeout" はホスティング期間の自動終了 → ボットタイマーは継続
            # reason="user"（デフォルト）はユーザーが明示的にキャンセル → ボットタイマーもキャンセル
            cancel_reason = msg.get("reason", "user")
            if cancel_reason != "timeout":
                _cancel_bot_timers(handle)
            # 個別申込の場合、相手のステータスを修正
            offer_info = pending_offers.get(handle, {})
            target_of_cancel = offer_info.get("target")
            if target_of_cancel and target_of_cancel in connected_users:
                _cur = user_status.get(target_of_cancel, "ログイン")
                if _cur == "申請・受付":
                    user_status[target_of_cancel] = "対局申請中"
                elif _cur == "対局受付中":
                    user_status[target_of_cancel] = "ログイン"
            pending_offers.pop(handle, None)
            # 申請・受付 → 申請を取り消すので「対局受付中」に戻る
            _my = user_status.get(handle, "ログイン")
            if _my == "申請・受付":
                user_status[handle] = "対局受付中"
            else:
                user_status[handle] = "ログイン"
            cancel_msg = json.dumps(
                {"type": "match_cancelled", "from": handle}, ensure_ascii=False
            )
            for other_handle, other_ws in list(connected_users.items()):
                if other_handle != handle:
                    try:
                        await other_ws.send_text(cancel_msg)
                    except Exception:
                        pass
            logger.info("Match cancelled by: %s", handle)

    elif msg_type in ("move", "pass", "resign", "timeout", "score_result"):
        opponent = game_pairs.get(handle)
        if opponent:
            forward = dict(msg)
            forward["from"] = handle
            await ws_send(opponent, forward)
            logger.debug("Game msg %s: %s -> %s", msg_type, handle, opponent)

            if msg_type in ("resign", "timeout"):
                game_pairs.pop(handle, None)
                game_pairs.pop(opponent, None)
                active_games.pop(frozenset({handle, opponent}), None)
                user_status[handle] = "ログイン"
                if opponent in connected_users:
                    user_status[opponent] = "ログイン"
                logger.info("Game ended (%s): %s vs %s", msg_type, handle, opponent)

    elif msg_type == "game_end":
        opponent = game_pairs.pop(handle, None)
        if opponent:
            game_pairs.pop(opponent, None)
            active_games.pop(frozenset({handle, opponent}), None)
            user_status[handle] = "ログイン"
            if opponent in connected_users:
                user_status[opponent] = "ログイン"
            await ws_send(opponent, {"type": "game_end", "from": handle})
            logger.info("Game ended (explicit): %s vs %s", handle, opponent)

    elif msg_type == "set_ai_preference":
        enabled = msg.get("ai_enabled", True)
        ai_preference[handle] = bool(enabled)
        logger.info("AI preference: %s = %s", handle, enabled)
        if not enabled:
            # AIオフにした場合、既存のボットタイマーをキャンセル
            _cancel_bot_timers(handle)

    elif msg_type == "set_bot_conditions":
        time_control = msg.get("time_control", "byoyomi")
        if time_control == "fischer":
            bot_time_preferences[handle] = {"time_control": "fischer"}
            logger.info("Bot conditions: %s = Fischer (admin settings)", handle)
        else:
            main_time = msg.get("main_time", 600)
            byo_time = msg.get("byo_time", 30)
            byo_periods = msg.get("byo_periods", 5)
            bot_time_preferences[handle] = {
                "time_control": "byoyomi",
                "main_time": int(main_time),
                "byo_time": int(byo_time),
                "byo_periods": int(byo_periods),
            }
            logger.info("Bot conditions: %s = main=%ds byo=%ds periods=%d",
                        handle, int(main_time), int(byo_time), int(byo_periods))

    elif msg_type == "reset_state":
        # クライアントが初期化ボタンを押した → ログイン直後の状態に戻す
        # 対局中なら相手に切断通知
        opponent = game_pairs.pop(handle, None)
        if opponent:
            game_pairs.pop(opponent, None)
            active_games.pop(frozenset({handle, opponent}), None)
            if opponent in connected_users:
                user_status[opponent] = "ログイン"
            await ws_send(opponent, {"type": "opponent_disconnected", "handle": handle})
        pending_offers.pop(handle, None)
        user_status[handle] = "ログイン"
        # ボットタイマーをキャンセル（対局申請時に再開される）
        _cancel_bot_timers(handle)
        logger.info("State reset: %s", handle)

    elif msg_type == "set_status":
        # クライアントから明示的にステータスを設定
        new_status = msg.get("status", "ログイン")
        if new_status in ("ログイン", "対局申請中", "対局受付中", "申請・受付", "対局中", "検討中"):
            user_status[handle] = new_status
            logger.debug("Status set: %s = %s", handle, new_status)

    elif msg_type == "heartbeat":
        await ws.send_text(json.dumps({"type": "pong"}))

    else:
        logger.warning("Unknown WS message type: %s from %s", msg_type, handle)


@app.websocket("/ws/{handle_name}/{token}")
async def websocket_endpoint(websocket: WebSocket, handle_name: str, token: str):
    """WebSocket エンドポイント。URL パスでハンドル名とトークンを受け取る。"""
    # トークン認証
    if token not in active_tokens or active_tokens[token] != handle_name:
        await websocket.close(code=4001, reason="認証エラー")
        logger.warning("WS auth failed: handle=%s token=%s", handle_name, token[:8])
        return

    await websocket.accept()

    # DBからユーザー情報を取得（同期処理なのでイベントループを譲らない）
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT elo, rank FROM users WHERE handle_name = ?", (handle_name,)
        ).fetchone()
        elo = row["elo"] if row else 0
        rank = row["rank"] if row else ""
    finally:
        conn.close()

    # 既存接続があれば切断（新しい接続を先に登録 → login_ok 送信 → old_ws close の順）
    # login_ok を old_ws.close() より先に送ることで、close 中に他のコルーチンが
    # online_list 等を送ってもクライアントは既に login_ok 受信済みとなる。
    old_ws = connected_users.get(handle_name)
    connected_users[handle_name] = websocket  # 先に登録 → old_ws の finally がスキップされる
    ws_user_info[handle_name] = {"handle": handle_name, "rank": rank, "elo": elo}
    user_status[handle_name] = "ログイン"
    logger.info("WS connected: %s (elo=%.0f)", handle_name, elo)

    # login_ok を送信（old_ws.close() より先に送る — クライアントが最初に受け取るメッセージを保証）
    await websocket.send_text(
        json.dumps({"type": "login_ok", "handle": handle_name}, ensure_ascii=False)
    )

    if old_ws:
        try:
            await old_ws.close()
        except Exception:
            pass

    await ws_broadcast_online_list()

    # ボットの自動挑戦はログイン時ではなく、対局申請ボタンを押した後に開始
    # （match_offer_broadcast / match_offer 受信時に bot_accept_timers で開始）

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                await ws_handle_message(websocket, handle_name, msg)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from %s", handle_name)
            except Exception as e:
                logger.error("WS message error from %s: %s", handle_name, e)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WS connection error (%s): %s", handle_name, e)
    finally:
        # ws を渡すことで、再接続済みなら古い接続のクリーンアップをスキップ
        if connected_users.get(handle_name) is websocket:
            _cancel_bot_timers(handle_name)
        await ws_disconnect(handle_name, websocket)


# ---------------------------------------------------------------------------
# ランク → ELO 変換（簡易テーブル）
# ---------------------------------------------------------------------------
# (rank, elo_min, elo_max) - クライアントの ELO_RANGES と完全一致
_RANK_ELO_RANGES = [
    ("9段", 3100, 3300), ("8段", 3000, 3099), ("7段", 2900, 2999),
    ("6段", 2800, 2899), ("5段", 2650, 2799), ("4段", 2500, 2649),
    ("3段", 2350, 2499), ("2段", 2200, 2349), ("1段", 2050, 2199),
    ("1級", 1900, 2049), ("2級", 1800, 1899), ("3級", 1700, 1799),
    ("4級", 1600, 1699), ("5級", 1500, 1599), ("6級", 1400, 1499),
    ("7級", 1300, 1399), ("8級", 1200, 1299), ("9級", 1100, 1199),
    ("10級", 1000, 1099), ("11級", 940, 999), ("12級", 880, 939),
    ("13級", 820, 879), ("14級", 760, 819), ("15級", 700, 759),
    ("16級", 640, 699), ("17級", 580, 639), ("18級", 520, 579),
    ("19級", 460, 519), ("20級", 400, 459),
]


def _rank_to_initial_elo(rank: str) -> float:
    """ランク文字列から初期 ELO を返す（範囲の中央値）。"""
    for r, elo_min, elo_max in _RANK_ELO_RANGES:
        if r == rank:
            return float((elo_min + elo_max) // 2)
    # 数字抽出してフォールバック
    import re
    m = re.match(r"(\d+)(段|級)", rank)
    if m:
        for r, elo_min, elo_max in _RANK_ELO_RANGES:
            if r == rank:
                return float((elo_min + elo_max) // 2)
    return 430.0  # 20級の中央値


# ---------------------------------------------------------------------------
# 管理用エンドポイント（リモートデプロイ用）
# ---------------------------------------------------------------------------
ADMIN_TOKEN = os.environ.get("GOKA_ADMIN_TOKEN", "goka-deploy-2026")
REPO_DIR = os.environ.get("GOKA_REPO_DIR",
                          os.path.dirname(os.path.abspath(__file__)))
_GIT_BRANCH = os.environ.get("GOKA_GIT_BRANCH", "main")


def _check_admin_token(request: Request) -> bool:
    token = request.headers.get("X-Token", "")
    return token == ADMIN_TOKEN


@app.post("/admin/update")
async def admin_update(request: Request):
    """GitHubから最新コードを取得してサーバーを再起動する。"""
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        # リクエストボディからブランチ指定を取得（なければ環境変数のデフォルト）
        branch = _GIT_BRANCH
        try:
            body = await request.json()
            if body and body.get("branch"):
                branch = body["branch"]
        except Exception:
            pass  # bodyなし or JSONでない場合はデフォルトブランチを使う

        # 指定ブランチをチェックアウトしてからpull
        if branch != _GIT_BRANCH:
            checkout = subprocess.run(
                ["git", "checkout", branch],
                cwd=REPO_DIR, capture_output=True, text=True, timeout=30
            )
            if checkout.returncode != 0:
                # ブランチがローカルにない場合はfetchしてからcheckout
                subprocess.run(
                    ["git", "fetch", "origin", branch],
                    cwd=REPO_DIR, capture_output=True, text=True, timeout=60
                )
                checkout = subprocess.run(
                    ["git", "checkout", branch],
                    cwd=REPO_DIR, capture_output=True, text=True, timeout=30
                )
                if checkout.returncode != 0:
                    return JSONResponse(
                        content={"status": "error",
                                 "git": checkout.stdout + checkout.stderr},
                        status_code=500)

        # git pull
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=60
        )
        git_output = result.stdout + result.stderr

        if result.returncode != 0:
            return JSONResponse(content={"status": "error", "git": git_output}, status_code=500)

        # 変更があった場合のみ再起動
        if "Already up to date" in git_output:
            return {"status": "no_change", "git": git_output}

        # サーバー再起動（環境変数を引き継いで新しいプロセスを起動してから自分を終了）
        subprocess.Popen(
            [sys.executable, os.path.join(REPO_DIR, "server.py")],
            cwd=REPO_DIR,
            start_new_session=True,
            env={**os.environ},
        )
        # 少し待ってから自分を終了
        asyncio.get_event_loop().call_later(1.0, lambda: os.kill(os.getpid(), 9))
        return {"status": "updating", "git": git_output}
    except Exception as e:
        logger.error("Deploy error: %s", e)
        return JSONResponse(content={"status": "error", "detail": str(e)}, status_code=500)


@app.get("/admin/status")
async def admin_status(request: Request):
    """サーバーの状態を返す。"""
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")
    return {
        "env": _ENV_LABEL,
        "port": PORT,
        "online_users": len(connected_users),
        "users": list(connected_users.keys()),
        "active_games": len(active_games),
        "pid": os.getpid(),
    }


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
