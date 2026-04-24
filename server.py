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
import copy
import hashlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
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
    # human_profile: KataGo humanSLProfile（人間らしい着手を再現）
    # visits: maxVisits（Human SLモード用。級位者は40=パス/投了判定用、段位者は強さに応じて増加）
    # fallback_visits: human_model.bin が無い場合のフォールバック用 maxVisits
    # human_lambda: humanSLChosenMovePiklLambda
    #   大きい値(100000000)=Human SLモデルに完全追従（級位者向け）
    #   小さい値→KataGoの最善手に近づく（高段者の悪手抑制に使用）
    "AIロボ1":  {"elo": 430,  "rank": "20級", "visits": 40, "fallback_visits": 1,    "human_profile": "preaz_20k", "human_lambda": 100000000},
    "AIロボ2":  {"elo": 490,  "rank": "19級", "visits": 40, "fallback_visits": 1,    "human_profile": "preaz_19k", "human_lambda": 100000000},
    "AIロボ3":  {"elo": 550,  "rank": "18級", "visits": 40, "fallback_visits": 2,    "human_profile": "preaz_18k", "human_lambda": 100000000},
    "AIロボ4":  {"elo": 610,  "rank": "17級", "visits": 40, "fallback_visits": 2,    "human_profile": "preaz_17k", "human_lambda": 100000000},
    "AIロボ5":  {"elo": 670,  "rank": "16級", "visits": 40, "fallback_visits": 3,    "human_profile": "preaz_16k", "human_lambda": 100000000},
    "AIロボ6":  {"elo": 730,  "rank": "15級", "visits": 40, "fallback_visits": 3,    "human_profile": "preaz_15k", "human_lambda": 100000000},
    "AIロボ7":  {"elo": 790,  "rank": "14級", "visits": 40, "fallback_visits": 4,    "human_profile": "preaz_14k", "human_lambda": 100000000},
    "AIロボ8":  {"elo": 850,  "rank": "13級", "visits": 40, "fallback_visits": 5,    "human_profile": "preaz_13k", "human_lambda": 100000000},
    "AIロボ9":  {"elo": 910,  "rank": "12級", "visits": 40, "fallback_visits": 6,    "human_profile": "preaz_12k", "human_lambda": 100000000},
    "AIロボ10": {"elo": 970,  "rank": "11級", "visits": 40, "fallback_visits": 8,    "human_profile": "preaz_11k", "human_lambda": 100000000},
    "AIロボ11": {"elo": 1050, "rank": "10級", "visits": 40, "fallback_visits": 10,   "human_profile": "preaz_10k", "human_lambda": 100000000},
    "AIロボ12": {"elo": 1150, "rank": "9級",  "visits": 40, "fallback_visits": 14,   "human_profile": "preaz_9k",  "human_lambda": 100000000},
    "AIロボ13": {"elo": 1250, "rank": "8級",  "visits": 40, "fallback_visits": 18,   "human_profile": "preaz_8k",  "human_lambda": 100000000},
    "AIロボ14": {"elo": 1350, "rank": "7級",  "visits": 40, "fallback_visits": 24,   "human_profile": "preaz_7k",  "human_lambda": 100000000},
    "AIロボ15": {"elo": 1450, "rank": "6級",  "visits": 40, "fallback_visits": 32,   "human_profile": "preaz_6k",  "human_lambda": 100000000},
    "AIロボ16": {"elo": 1550, "rank": "5級",  "visits": 40, "fallback_visits": 42,   "human_profile": "preaz_5k",  "human_lambda": 100000000},
    "AIロボ17": {"elo": 1650, "rank": "4級",  "visits": 40, "fallback_visits": 56,   "human_profile": "preaz_4k",  "human_lambda": 100000000},
    "AIロボ18": {"elo": 1750, "rank": "3級",  "visits": 40, "fallback_visits": 75,   "human_profile": "preaz_3k",  "human_lambda": 100000000},
    "AIロボ19": {"elo": 1850, "rank": "2級",  "visits": 40, "fallback_visits": 100,  "human_profile": "preaz_2k",  "human_lambda": 100000000},
    "AIロボ20": {"elo": 1975, "rank": "1級",  "visits": 40, "fallback_visits": 130,  "human_profile": "preaz_1k",  "human_lambda": 100000000},
    # 段位者 (初段〜9段)
    # 高段者は humanSLProfile の生モデルだけでは棋力が足りないため visits を増やし、
    # humanSLChosenMovePiklLambda を段階的に下げて悪手を抑制する
    "AIロボ21": {"elo": 2125, "rank": "1段",  "visits": 40,   "fallback_visits": 180,  "human_profile": "preaz_1d", "human_lambda": 100000000},
    "AIロボ22": {"elo": 2275, "rank": "2段",  "visits": 40,   "fallback_visits": 250,  "human_profile": "preaz_2d", "human_lambda": 100000000},
    "AIロボ23": {"elo": 2425, "rank": "3段",  "visits": 40,   "fallback_visits": 350,  "human_profile": "preaz_3d", "human_lambda": 100000000},
    "AIロボ24": {"elo": 2575, "rank": "4段",  "visits": 100,  "fallback_visits": 500,  "human_profile": "preaz_4d", "human_lambda": 10000},
    "AIロボ25": {"elo": 2725, "rank": "5段",  "visits": 200,  "fallback_visits": 700,  "human_profile": "preaz_5d", "human_lambda": 1000},
    "AIロボ26": {"elo": 2850, "rank": "6段",  "visits": 400,  "fallback_visits": 1000, "human_profile": "preaz_6d", "human_lambda": 100},
    "AIロボ27": {"elo": 2950, "rank": "7段",  "visits": 800,  "fallback_visits": 1500, "human_profile": "preaz_7d", "human_lambda": 50},
    "AIロボ28": {"elo": 3050, "rank": "8段",  "visits": 1500, "fallback_visits": 2000, "human_profile": "preaz_8d", "human_lambda": 20},
    "AIロボ29": {"elo": 3150, "rank": "9段",  "visits": 3000, "fallback_visits": 3000, "human_profile": "preaz_9d", "human_lambda": 10},
    "AIロボ30": {"elo": 3250, "rank": "9段",  "visits": 5000, "fallback_visits": 5000, "human_profile": "preaz_9d", "human_lambda": 5},
}

# 言語別ELO対応表に合わせるためのオフセット（igo/elo.py の定義に準拠）
_BOT_ELO_OFFSET_BY_LANG = {
    "ja": 0,      # 日本基準
    "en": 50,     # EGF/AGA基準
    "zh": 100,    # 中国基準
    "ko": -300,   # 韓国オンライン基準
}


def _normalize_lang(lang: Optional[str]) -> str:
    if lang in _BOT_ELO_OFFSET_BY_LANG:
        return lang
    return "ja"


def _build_ai_bots_by_lang():
    """言語別にELOを平行移動したAIボット辞書を作る。"""
    out = {}
    for lang, offset in _BOT_ELO_OFFSET_BY_LANG.items():
        bots = copy.deepcopy(AI_BOTS)
        if offset:
            for _name, info in bots.items():
                info["elo"] = int(info["elo"] + offset)
        out[lang] = bots
    return out


AI_BOTS_BY_LANG = _build_ai_bots_by_lang()


def _bots_for_lang(lang: Optional[str]):
    return AI_BOTS_BY_LANG.get(_normalize_lang(lang), AI_BOTS_BY_LANG["ja"])


def _bot_info_for_user(bot_name: str, lang: Optional[str]):
    bots = _bots_for_lang(lang)
    return bots.get(bot_name)

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

BOT_AUTO_DELAY = 30  # 秒 — ボットが挑戦状を送るまでのデフォルト待機時間（本番既定）
# 重要: この値はクライアント側の _hosting_timeout（get_offer_timeout_ms）より
# 十分短くなければならない。同じかそれ以上だとクライアントが先にキャンセルし、
# ボットの挑戦状が届かなくなる。


def _get_bot_delay() -> int:
    """app_settings.json の bot_offer_delay（秒）を返す。キーが無いときだけ BOT_AUTO_DELAY を使う。

    本番で「30秒にしたのに長い」場合は、多くのケースで JSON に古い bot_offer_delay が残っている。
    """
    try:
        settings = _load_settings()
        return int(settings.get("bot_offer_delay", BOT_AUTO_DELAY))
    except Exception:
        return BOT_AUTO_DELAY


def _get_offer_timeout_sec() -> int:
    """管理者画面の offer_timeout_min 設定を秒単位で返す（デフォルト: 180秒）。"""
    try:
        settings = _load_settings()
        minutes = int(settings.get("offer_timeout_min", 3))
        return max(1, minutes) * 60
    except Exception:
        return 180


def _find_closest_bot(elo: float, lang: str = "ja") -> Optional[str]:
    """ELOが最も近いAIボットを返す。"""
    bots = _bots_for_lang(lang)
    if not bots:
        return None
    return min(bots.keys(), key=lambda name: abs(bots[name]["elo"] - elo))


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
    # DB 設計メモ（碁華）:
    # - users は handle_name を業務上の一意キーとしつつ、不変の内部参照用に id を必ず持つ。
    # - 他テーブルは、業務上すでに安定した一意カラムがあるなら無理に数値 id を増やさない。
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

    # 既存データ移行: password_enc(B64) を正として password_hash/salt の不整合を自動修復
    # （正しいパスワード入力でもログイン不可になる状態をサーバー側で回収）
    try:
        rows = conn.execute(
            "SELECT handle_name, password_hash, salt, password_enc FROM users"
        ).fetchall()
        repaired = 0
        for row in rows:
            plain = _b64_decode_password(row["password_enc"])
            if not plain:
                continue
            expected = hash_password(plain, row["salt"])
            if expected == row["password_hash"]:
                continue
            new_salt = secrets.token_hex(16)
            new_hash = hash_password(plain, new_salt)
            conn.execute(
                "UPDATE users SET salt = ?, password_hash = ? WHERE handle_name = ?",
                (new_salt, new_hash, row["handle_name"])
            )
            repaired += 1
        if repaired:
            conn.commit()
            logger.warning("Repaired password hash mismatch users: %d", repaired)
    except Exception as e:
        logger.warning("Password hash auto-repair skipped: %s", e)

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


def _b64_decode_password(password_enc: str) -> str:
    """B64: 形式の password_enc を復号。復号不可時は空文字を返す。"""
    if not isinstance(password_enc, str) or not password_enc.startswith("B64:"):
        return ""
    try:
        return base64.b64decode(password_enc[4:]).decode("utf-8")
    except Exception:
        return ""

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
    try:
        _st = _load_settings()
        _bod = _st.get("bot_offer_delay")
        logger.info(
            "Goka GO server [%s] starting on port %d (db=%s); "
            "bot_offer_delay from app_settings=%r (code default if key missing=%ds); settings file=%s",
            _ENV_LABEL, PORT, DB_PATH, _bod, BOT_AUTO_DELAY, SETTINGS_PATH,
        )
    except Exception as _e:
        logger.warning("Could not read app_settings at startup: %s", _e)
        logger.info(
            "Goka GO server [%s] starting on port %d (db=%s)",
            _ENV_LABEL, PORT, DB_PATH,
        )
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
        # サーバー側回収: password_enc(B64) と一致する場合はその場で hash/salt を修復
        plain = _b64_decode_password(row["password_enc"] if row["password_enc"] else "")
        if not plain or plain != req.password:
            return {"success": False, "token": "", "user": None, "message": "パスワードが正しくありません"}
        try:
            new_salt = secrets.token_hex(16)
            new_hash = hash_password(req.password, new_salt)
            conn_fix = get_db_connection()
            conn_fix.execute(
                "UPDATE users SET salt = ?, password_hash = ? WHERE handle_name = ?",
                (new_salt, new_hash, req.handle_name)
            )
            conn_fix.commit()
            conn_fix.close()
            logger.warning("Recovered login hash mismatch: %s", req.handle_name)
            row = dict(row)
            row["salt"] = new_salt
            row["password_hash"] = new_hash
        except Exception as e:
            logger.warning("Failed to recover login hash mismatch: %s (%s)", req.handle_name, e)
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
    # WebSocket接続中ユーザーのメモリ情報も即時反映
    if req.handle_name in ws_user_info:
        ws_user_info[req.handle_name]["language"] = req.language
    logger.info("Language updated: %s -> %s", req.handle_name, req.language)
    return {"success": True}


class UpdatePasswordEncRequest(BaseModel):
    handle_name: str
    password_enc: str


class AdminResetTestPasswordsRequest(BaseModel):
    password: str = "2052"
    dry_run: bool = False


class AdminSetUserPasswordRequest(BaseModel):
    handle_name: str
    password: str

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
                "fischer_main_time": 300, "fischer_increment": 10,
                "bot_offer_delay": 30}


def _save_settings(settings: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


class UpdateSettingsRequest(BaseModel):
    theme: Optional[str] = None
    offer_timeout_min: Optional[int] = None
    fischer_main_time: Optional[int] = None
    fischer_increment: Optional[int] = None
    bot_offer_delay: Optional[int] = None


@app.get("/api/settings")
async def get_settings():
    """グローバル設定を返す。"""
    return _load_settings()


@app.get("/api/runtime-info")
async def get_runtime_info():
    """管理者画面向け: 接続先の環境とDB識別情報を返す。"""
    return {
        "env": _ENV_LABEL,
        "db_path": str(DB_PATH),
        "settings_path": str(SETTINGS_PATH),
        "port": PORT,
    }


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
    if req.bot_offer_delay is not None:
        settings["bot_offer_delay"] = max(10, min(600, req.bot_offer_delay))
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
    # オンライン一覧は共通表示のため ja 基準の一覧を配信
    for bot_name, bot_info in _bots_for_lang("ja").items():
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
        delay = _get_bot_delay()
        logger.info(
            "Bot auto-offer (broadcast path): handle=%s sleeping %ds before bot match_offer",
            handle,
            delay,
        )
        await asyncio.sleep(delay)
        # まだ接続中かつ対局中でないか確認
        if handle not in connected_users or handle in game_pairs:
            return
        # AI対局がオフなら何もしない
        if not ai_preference.get(handle, True):
            return
        info = ws_user_info.get(handle, {})
        elo = info.get("elo", 0)
        lang = _normalize_lang(info.get("language"))
        bot_name = _find_closest_bot(elo, lang)
        if not bot_name:
            return
        bot_info = _bot_info_for_user(bot_name, lang)
        if not bot_info:
            return
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
        logger.info("Bot auto-offer (delay=%ds): %s -> %s", delay, bot_name, handle)
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
        delay = _get_bot_delay()
        logger.info(
            "Bot auto-offer (pending human path): handle=%s sleeping %ds before bot match_offer",
            handle,
            delay,
        )
        await asyncio.sleep(delay)
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
        lang = _normalize_lang(info.get("language"))
        bot_name = _find_closest_bot(elo, lang)
        if not bot_name:
            return
        bot_info = _bot_info_for_user(bot_name, lang)
        if not bot_info:
            return
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
        logger.info("Bot auto-offer (after timeout, delay=%ds): %s -> %s", delay, bot_name, handle)
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
        if target:
            my_lang = _normalize_lang(ws_user_info.get(handle, {}).get("language"))
            my_bots = _bots_for_lang(my_lang)
        else:
            my_bots = {}
        if target and target in my_bots:
            bot_info = my_bots[target]
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
                "bot_fallback_visits": bot_info.get("fallback_visits", bot_info["visits"]),
                "bot_human_profile": bot_info.get("human_profile", ""),
                "bot_human_lambda": bot_info.get("human_lambda", 100000000),
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
            # bot_offer_delay 秒後に相手承諾がなければボットが挑戦状を送るタイマー開始
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
        if target:
            my_lang = _normalize_lang(ws_user_info.get(handle, {}).get("language"))
            my_bots = _bots_for_lang(my_lang)
        else:
            my_bots = {}
        if target and target in my_bots:
            bot_info = my_bots[target]
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
                "bot_fallback_visits": bot_info.get("fallback_visits", bot_info["visits"]),
                "bot_human_profile": bot_info.get("human_profile", ""),
                "bot_human_lambda": bot_info.get("human_lambda", 100000000),
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
            "SELECT elo, rank, language FROM users WHERE handle_name = ?",
            (handle_name,)
        ).fetchone()
        elo = row["elo"] if row else 0
        rank = row["rank"] if row else ""
        language = _normalize_lang(row["language"] if row and row["language"] else "ja")
    finally:
        conn.close()

    # 既存接続があれば切断（新しい接続を先に登録 → login_ok 送信 → old_ws close の順）
    # login_ok を old_ws.close() より先に送ることで、close 中に他のコルーチンが
    # online_list 等を送ってもクライアントは既に login_ok 受信済みとなる。
    old_ws = connected_users.get(handle_name)
    connected_users[handle_name] = websocket  # 先に登録 → old_ws の finally がスキップされる
    ws_user_info[handle_name] = {
        "handle": handle_name,
        "rank": rank,
        "elo": elo,
        "language": language,
    }
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
DB_BACKUP_DIR = os.environ.get(
    "GOKA_DB_BACKUP_DIR", os.path.join(REPO_DIR, "backups", "db")
)
DB_BACKUP_KEEP = int(os.environ.get("GOKA_DB_BACKUP_KEEP", "30"))


def _check_admin_token(request: Request) -> bool:
    token = request.headers.get("X-Token", "")
    return token == ADMIN_TOKEN


def _backup_db(tag: str = "manual") -> str:
    """SQLite DB を時刻付きファイルへバックアップし、古い世代を削除する。"""
    ts = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(DB_BACKUP_DIR, exist_ok=True)
    dst = os.path.join(DB_BACKUP_DIR, f"igo_users-{ts}-{tag}.db")

    src_conn = sqlite3.connect(str(DB_PATH))
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    try:
        backups = sorted(
            [
                os.path.join(DB_BACKUP_DIR, f)
                for f in os.listdir(DB_BACKUP_DIR)
                if f.startswith("igo_users-") and f.endswith(".db")
            ],
            key=os.path.getmtime
        )
        keep = max(3, DB_BACKUP_KEEP)
        for old in backups[:-keep]:
            try:
                os.unlink(old)
            except OSError:
                pass
    except OSError:
        pass

    return dst


def _cleanup_old_releases(keep: int = 3) -> str:
    """古いリリースzipを削除してディスク容量を確保する（sudo不要）。"""
    releases_dir = os.path.join(REPO_DIR, "releases")
    if not os.path.isdir(releases_dir):
        return ""
    try:
        zips = sorted(
            [f for f in os.listdir(releases_dir) if f.endswith(".zip")],
            key=lambda f: os.path.getmtime(os.path.join(releases_dir, f)),
        )
        to_delete = zips[:-keep] if len(zips) > keep else []
        freed = 0
        for fname in to_delete:
            fpath = os.path.join(releases_dir, fname)
            try:
                freed += os.path.getsize(fpath)
                os.unlink(fpath)
            except OSError:
                pass
        if to_delete:
            return f"古いリリース{len(to_delete)}件削除({freed // 1024 // 1024}MB解放)"
    except Exception:
        pass
    return ""


def _cleanup_pycache() -> None:
    """__pycache__ ディレクトリを削除する。"""
    try:
        for dirpath, dirnames, _filenames in os.walk(REPO_DIR):
            if "__pycache__" in dirnames:
                shutil.rmtree(
                    os.path.join(dirpath, "__pycache__"), ignore_errors=True
                )
    except Exception:
        pass


def _ensure_disk_space() -> str:
    """デプロイ前にディスク容量を確保する。git fetch失敗のデッドロックを防止。"""
    disk = shutil.disk_usage("/")
    free_mb = disk.free // 1024 // 1024
    if free_mb >= 50:
        return ""
    msgs = []
    # 1. 古いリリースzipを削除（最大効果: 数GB）
    r = _cleanup_old_releases(keep=3)
    if r:
        msgs.append(r)
    # 2. __pycache__ 削除
    _cleanup_pycache()
    # 3. git shallow化を試行
    try:
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", "main"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            ["git", "reflog", "expire", "--expire=now", "--all"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=30,
        )
        subprocess.run(
            ["git", "gc", "--prune=now"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=120,
        )
    except Exception:
        pass
    disk2 = shutil.disk_usage("/")
    freed = (disk2.free - disk.free) // 1024 // 1024
    if freed > 0:
        msgs.append(f"合計{freed}MB解放")
    return "; ".join(msgs) if msgs else ""


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
            if body and isinstance(body.get("branch"), str) and body["branch"]:
                branch = body["branch"]
        except Exception:
            pass  # bodyなし or JSONでない場合はデフォルトブランチを使う

        # ブランチ名のバリデーション（gitオプションインジェクション防止）
        if branch.startswith("-"):
            return JSONResponse(
                content={"status": "error", "detail": "Invalid branch name"},
                status_code=400)

        # ディスク容量不足時は自動クリーンアップ（デッドロック防止）
        cleanup_msg = await asyncio.to_thread(_ensure_disk_space)
        backup_path = await asyncio.to_thread(_backup_db, "pre-update")

        # 現在のコミットハッシュを記録（ブランチ切り替え検出用）
        old_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10
        ).stdout.strip()

        # 常にfetch → checkoutしてからpull（前回のデプロイで別ブランチに
        # 切り替わっている可能性があるため、毎回明示的にcheckoutする）
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=60
        )
        if fetch_result.returncode != 0:
            return JSONResponse(
                content={"status": "error",
                         "git": fetch_result.stdout + fetch_result.stderr,
                         "cleanup": cleanup_msg,
                         "db_backup": backup_path},
                status_code=500)
        checkout = subprocess.run(
            ["git", "checkout", branch],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=30
        )
        if checkout.returncode != 0:
            return JSONResponse(
                content={"status": "error",
                         "git": checkout.stdout + checkout.stderr,
                         "db_backup": backup_path},
                status_code=500)

        # git pull
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=60
        )
        git_output = result.stdout + result.stderr

        if result.returncode != 0:
            return JSONResponse(
                content={"status": "error", "git": git_output, "db_backup": backup_path},
                status_code=500
            )

        # コミットハッシュを比較してコード変更を検出
        # （ブランチ切り替え時は git pull が "Already up to date" でもコードは変わっている）
        new_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10
        ).stdout.strip()

        if old_hash == new_hash:
            return {
                "status": "no_change",
                "git": git_output,
                "cleanup": cleanup_msg,
                "db_backup": backup_path
            }

        # サーバー再起動（環境変数を引き継いで新しいプロセスを起動してから自分を終了）
        subprocess.Popen(
            [sys.executable, os.path.join(REPO_DIR, "server.py")],
            cwd=REPO_DIR,
            start_new_session=True,
            env={**os.environ},
        )
        # 少し待ってから自分を終了
        asyncio.get_event_loop().call_later(1.0, lambda: os.kill(os.getpid(), 9))
        return {
            "status": "updating",
            "git": git_output,
            "cleanup": cleanup_msg,
            "db_backup": backup_path
        }
    except Exception as e:
        logger.error("Deploy error: %s", e)
        return JSONResponse(content={"status": "error", "detail": str(e)}, status_code=500)


@app.post("/admin/backup")
async def admin_backup(request: Request):
    """DBバックアップを手動実行する。"""
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        backup_path = await asyncio.to_thread(_backup_db, "manual")
        return {"status": "ok", "db_backup": backup_path}
    except (OSError, sqlite3.Error) as e:
        return JSONResponse(
            content={"status": "error", "detail": str(e)},
            status_code=500
        )


@app.post("/admin/reset-test-passwords")
async def admin_reset_test_passwords(
    request: Request, body: AdminResetTestPasswordsRequest
):
    """emailが空のテスト用アカウントのパスワードを一括リセットする。"""
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")

    new_password = (body.password or "").strip()
    if len(new_password) < 4:
        return JSONResponse(
            content={"status": "error", "detail": "password must be at least 4 characters"},
            status_code=400
        )

    try:
        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT handle_name
            FROM users
            WHERE email IS NULL OR TRIM(email) = ''
            ORDER BY id
            """
        ).fetchall()
        targets = [r["handle_name"] for r in rows]

        if body.dry_run:
            conn.close()
            return {"status": "dry_run", "target_count": len(targets), "targets": targets}

        backup_path = await asyncio.to_thread(_backup_db, "pre-reset-test-passwords")
        pw_enc = _b64_encode_password(new_password)
        updated = 0
        for handle in targets:
            salt = secrets.token_hex(16)
            pw_hash = hash_password(new_password, salt)
            conn.execute(
                "UPDATE users SET salt = ?, password_hash = ?, password_enc = ? WHERE handle_name = ?",
                (salt, pw_hash, pw_enc, handle)
            )
            updated += 1
        conn.commit()
        conn.close()
        logger.warning(
            "Admin reset test passwords executed: count=%d, backup=%s",
            updated, backup_path
        )
        return {
            "status": "ok",
            "updated_count": updated,
            "updated_handles": targets,
            "db_backup": backup_path
        }
    except (OSError, sqlite3.Error) as e:
        return JSONResponse(
            content={"status": "error", "detail": str(e)},
            status_code=500
        )


@app.post("/admin/set-user-password")
async def admin_set_user_password(request: Request, body: AdminSetUserPasswordRequest):
    """指定ユーザー1件のパスワードを管理者トークンで更新する。"""
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")

    handle = (body.handle_name or "").strip()
    password = (body.password or "").strip()
    if not handle:
        return JSONResponse(
            content={"status": "error", "detail": "handle_name is required"},
            status_code=400
        )
    if len(password) < 4:
        return JSONResponse(
            content={"status": "error", "detail": "password must be at least 4 characters"},
            status_code=400
        )

    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT id FROM users WHERE handle_name = ?",
            (handle,)
        ).fetchone()
        if row is None:
            conn.close()
            return JSONResponse(
                content={"status": "error", "detail": "user not found"},
                status_code=404
            )

        backup_path = await asyncio.to_thread(_backup_db, f"pre-set-password-{handle}")
        salt = secrets.token_hex(16)
        pw_hash = hash_password(password, salt)
        pw_enc = _b64_encode_password(password)
        conn.execute(
            "UPDATE users SET salt = ?, password_hash = ?, password_enc = ? WHERE handle_name = ?",
            (salt, pw_hash, pw_enc, handle)
        )
        conn.commit()
        conn.close()
        logger.warning("Admin set user password: %s", handle)
        return {"status": "ok", "handle_name": handle, "db_backup": backup_path}
    except (OSError, sqlite3.Error) as e:
        return JSONResponse(
            content={"status": "error", "detail": str(e)},
            status_code=500
        )


@app.post("/admin/hotpatch")
async def admin_hotpatch(request: Request):
    """server.pyをHTTP経由で直接更新する（git不要のフォールバックデプロイ）。

    ディスク容量不足でgit fetchが失敗する場合の緊急デプロイ手段。
    既存ファイルの上書きなので追加ディスク容量は不要。
    """
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        body = await request.body()
        if len(body) < 100:
            return JSONResponse(
                content={"status": "error", "detail": "Request body too small"},
                status_code=400)

        content = body.decode("utf-8")
        # 基本的な安全チェック: Pythonファイルであること
        if "import " not in content or "def " not in content:
            return JSONResponse(
                content={"status": "error",
                         "detail": "Content does not look like a Python file"},
                status_code=400)

        target = os.path.join(REPO_DIR, "server.py")

        # まずディスク容量を確保（古いリリース削除）
        _cleanup_old_releases(keep=3)
        _cleanup_pycache()

        # 既存ファイルを上書き（truncate→writeなので追加容量不要）
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        # サーバー再起動
        subprocess.Popen(
            [sys.executable, target],
            cwd=REPO_DIR,
            start_new_session=True,
            env={**os.environ},
        )
        asyncio.get_event_loop().call_later(1.0, lambda: os.kill(os.getpid(), 9))
        return {"status": "hotpatch_applied", "size": len(content)}
    except Exception as e:
        logger.error("Hotpatch error: %s", e)
        return JSONResponse(
            content={"status": "error", "detail": str(e)}, status_code=500)


@app.get("/admin/status")
async def admin_status(request: Request):
    """サーバーの状態を返す。"""
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")
    disk = shutil.disk_usage("/")
    return {
        "env": _ENV_LABEL,
        "port": PORT,
        "online_users": len(connected_users),
        "users": list(connected_users.keys()),
        "active_games": len(active_games),
        "pid": os.getpid(),
        "disk_total_mb": round(disk.total / 1024 / 1024),
        "disk_used_mb": round(disk.used / 1024 / 1024),
        "disk_free_mb": round(disk.free / 1024 / 1024),
    }


@app.post("/admin/disk-cleanup")
async def admin_disk_cleanup(request: Request):
    """ディスク容量を確保するためのクリーンアップを実行する。

    sudo不要のユーザーレベルクリーンアップを優先的に実行する:
    1. 古いリリースzipファイルの削除（最新3つのみ残す）
    2. __pycache__ / .pyc ファイルの削除
    3. gitリポジトリのshallow化（履歴を深さ1に変換）
    4. sudo可能な場合はシステムレベルのクリーンアップも試行
    """
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")

    if _ENV_LABEL != "production":
        return JSONResponse(
            content={"status": "error",
                     "detail": "This endpoint is only available on the production server"},
            status_code=400)

    async def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
        return await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=180, **kwargs
        )

    log_lines: list = []
    disk_before = shutil.disk_usage("/")
    log_lines.append(f"クリーンアップ前: 空き {disk_before.free // 1024 // 1024}MB")

    # --- ユーザーレベルクリーンアップ（sudo不要） ---

    # 1. 古いリリースzipファイルの削除（最大の容量節約が期待できる）
    releases_dir = os.path.join(REPO_DIR, "releases")
    if os.path.isdir(releases_dir):
        try:
            zips = sorted(
                [f for f in os.listdir(releases_dir) if f.endswith(".zip")],
                key=lambda f: os.path.getmtime(os.path.join(releases_dir, f)),
            )
            keep_count = 3  # 最新3つのみ残す
            to_delete = zips[:-keep_count] if len(zips) > keep_count else []
            deleted_size = 0
            for fname in to_delete:
                fpath = os.path.join(releases_dir, fname)
                try:
                    fsize = os.path.getsize(fpath)
                    os.unlink(fpath)
                    deleted_size += fsize
                except OSError:
                    pass
            deleted_mb = deleted_size // 1024 // 1024
            log_lines.append(
                f"古いリリースzip: {len(to_delete)}件削除 ({deleted_mb}MB解放)、"
                f"{min(len(zips), keep_count)}件残存"
            )
        except Exception as e:
            log_lines.append(f"古いリリースzip: スキップ ({e})")

    # 2. __pycache__ / .pyc ファイルの削除
    try:
        pycache_count = 0
        pycache_size = 0
        for dirpath, dirnames, filenames in os.walk(REPO_DIR):
            if "__pycache__" in dirnames:
                cache_dir = os.path.join(dirpath, "__pycache__")
                try:
                    dir_size = sum(
                        os.path.getsize(os.path.join(cache_dir, f))
                        for f in os.listdir(cache_dir)
                        if os.path.isfile(os.path.join(cache_dir, f))
                    )
                    shutil.rmtree(cache_dir)
                    pycache_count += 1
                    pycache_size += dir_size
                except OSError:
                    pass
        log_lines.append(
            f"__pycache__: {pycache_count}ディレクトリ削除 "
            f"({pycache_size // 1024}KB解放)"
        )
    except Exception as e:
        log_lines.append(f"__pycache__: スキップ ({e})")

    # 3. gitリポジトリのshallow化（大幅な容量節約）
    if os.path.isdir(REPO_DIR):
        try:
            # まず現在のgitサイズを確認
            git_dir = os.path.join(REPO_DIR, ".git")
            git_size_before = 0
            for dirpath, _dirnames, filenames in os.walk(git_dir):
                for f in filenames:
                    try:
                        git_size_before += os.path.getsize(
                            os.path.join(dirpath, f)
                        )
                    except OSError:
                        pass

            # shallow化を試行: fetch --depth 1 → reflog expire → gc
            r = await _run(
                ["git", "fetch", "--depth", "1", "origin", "main"],
                cwd=REPO_DIR,
            )
            if r.returncode == 0:
                await _run(
                    ["git", "reflog", "expire", "--expire=now", "--all"],
                    cwd=REPO_DIR,
                )
                await _run(
                    ["git", "gc", "--prune=now"],
                    cwd=REPO_DIR,
                )
                git_size_after = 0
                for dirpath, _dirnames, filenames in os.walk(git_dir):
                    for f in filenames:
                        try:
                            git_size_after += os.path.getsize(
                                os.path.join(dirpath, f)
                            )
                        except OSError:
                            pass
                freed_git = (git_size_before - git_size_after) // 1024 // 1024
                log_lines.append(
                    f"git shallow化: 成功 "
                    f"({git_size_before // 1024 // 1024}MB → "
                    f"{git_size_after // 1024 // 1024}MB、"
                    f"{freed_git}MB解放)"
                )
            else:
                log_lines.append(
                    f"git shallow化: スキップ ({r.stderr.strip()[:80]})"
                )
        except Exception as e:
            log_lines.append(f"git shallow化: スキップ ({e})")

    # --- システムレベルクリーンアップ（sudo必要、失敗してもOK） ---
    sudo_cmds = [
        (["sudo", "-n", "apt-get", "clean"], "apt cache"),
        (["sudo", "-n", "apt-get", "autoremove", "-y"], "apt autoremove"),
        (["sudo", "-n", "journalctl", "--vacuum-size=50M"], "journal logs"),
    ]
    for cmd, label in sudo_cmds:
        try:
            r = await _run(cmd)
            if r.returncode == 0:
                log_lines.append(f"{label}: クリーンアップ成功")
            else:
                log_lines.append(f"{label}: スキップ (sudo権限なし)")
        except Exception as e:
            log_lines.append(f"{label}: スキップ ({e})")

    disk_after = shutil.disk_usage("/")
    freed = (disk_after.free - disk_before.free) // 1024 // 1024
    log_lines.append(f"クリーンアップ後: 空き {disk_after.free // 1024 // 1024}MB (解放: {freed}MB)")

    return {
        "status": "success",
        "disk_free_mb_before": disk_before.free // 1024 // 1024,
        "disk_free_mb_after": disk_after.free // 1024 // 1024,
        "freed_mb": freed,
        "log": log_lines,
    }


@app.post("/admin/setup-staging")
async def admin_setup_staging(request: Request):
    """ステージング環境をリモートからセットアップする（SSH不要）。

    本番サーバーから呼び出すことで、同じVM上にステージング用の
    別クローン＋別プロセスを起動する。
    """
    if not _check_admin_token(request):
        raise HTTPException(status_code=403, detail="forbidden")

    # ステージング環境は本番サーバー上でのみ実行可能
    if _ENV_LABEL != "production":
        return JSONResponse(
            content={"status": "error",
                     "detail": "This endpoint is only available on the production server"},
            status_code=400)

    staging_port = 8001
    staging_dir = REPO_DIR + "-staging"
    staging_db = os.path.join(staging_dir, "igo_users_staging.db")
    staging_settings = os.path.join(staging_dir, "app_settings_staging.json")
    log_lines: list = []

    def _log(msg: str) -> None:
        logger.info("[setup-staging] %s", msg)
        log_lines.append(msg)

    async def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
        return await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=120, **kwargs
        )

    try:
        # 0. ディスク容量チェック＆自動クリーンアップ
        disk = shutil.disk_usage("/")
        free_mb = disk.free // 1024 // 1024
        _log(f"ディスク空き容量: {free_mb}MB")
        if free_mb < 200:
            _log("空き容量不足のため自動クリーンアップを実行...")

            # ユーザーレベル: 古いリリースzipを削除（最新3つのみ残す）
            releases_dir = os.path.join(REPO_DIR, "releases")
            if os.path.isdir(releases_dir):
                try:
                    zips = sorted(
                        [f for f in os.listdir(releases_dir) if f.endswith(".zip")],
                        key=lambda f: os.path.getmtime(
                            os.path.join(releases_dir, f)
                        ),
                    )
                    keep_count = 3
                    for fname in (zips[:-keep_count] if len(zips) > keep_count else []):
                        try:
                            os.unlink(os.path.join(releases_dir, fname))
                        except OSError:
                            pass
                    _log(f"古いリリースzip削除: {max(0, len(zips) - keep_count)}件")
                except Exception:
                    pass

            # ユーザーレベル: __pycache__ 削除
            try:
                for dirpath, dirnames, _filenames in os.walk(REPO_DIR):
                    if "__pycache__" in dirnames:
                        shutil.rmtree(
                            os.path.join(dirpath, "__pycache__"),
                            ignore_errors=True,
                        )
            except Exception:
                pass

            # ユーザーレベル: git shallow化
            if os.path.isdir(REPO_DIR):
                try:
                    r = await _run(
                        ["git", "fetch", "--depth", "1", "origin", "main"],
                        cwd=REPO_DIR,
                    )
                    if r.returncode == 0:
                        await _run(
                            ["git", "reflog", "expire", "--expire=now", "--all"],
                            cwd=REPO_DIR,
                        )
                        await _run(["git", "gc", "--prune=now"], cwd=REPO_DIR)
                except Exception:
                    pass

            # システムレベル（sudo不要なら実行）
            for cmd in [
                ["sudo", "-n", "apt-get", "clean"],
                ["sudo", "-n", "apt-get", "autoremove", "-y"],
                ["sudo", "-n", "journalctl", "--vacuum-size=50M"],
            ]:
                try:
                    await _run(cmd)
                except Exception:
                    pass

            disk = shutil.disk_usage("/")
            free_mb = disk.free // 1024 // 1024
            _log(f"クリーンアップ後の空き容量: {free_mb}MB")
            if free_mb < 100:
                return JSONResponse(
                    content={"status": "error",
                             "detail": f"ディスク空き容量が不足しています ({free_mb}MB)。"
                                        "VMのディスク拡張が必要です。",
                             "disk_free_mb": free_mb,
                             "log": log_lines},
                    status_code=500)

        # 1. ステージング用リポジトリの準備
        if os.path.isdir(staging_dir):
            _log(f"既存のステージングリポジトリを更新: {staging_dir}")
            r = await _run(["git", "fetch", "origin"], cwd=staging_dir)
            if r.returncode != 0:
                return JSONResponse(
                    content={"status": "error", "detail": "git fetch failed",
                             "output": r.stdout + r.stderr},
                    status_code=500)
            await _run(["git", "checkout", "main"], cwd=staging_dir)
            r = await _run(["git", "pull", "origin", "main"], cwd=staging_dir)
            _log(f"git pull: {r.stdout.strip()}")
        else:
            _log(f"ステージングリポジトリをクローン: {staging_dir}")
            remote_url = (await _run(
                ["git", "remote", "get-url", "origin"], cwd=REPO_DIR
            )).stdout.strip()
            r = await _run(["git", "clone", "--depth", "1", remote_url, staging_dir])
            if r.returncode != 0:
                return JSONResponse(
                    content={"status": "error", "detail": "git clone failed",
                             "output": r.stdout + r.stderr},
                    status_code=500)
            _log("クローン完了（shallow clone）")

        # 2. 既存のステージングプロセスを停止
        _log("既存のステージングプロセスを確認...")
        ps_result = await _run(["pgrep", "-f", f"{staging_dir}/server.py"])
        if ps_result.returncode == 0:
            old_pids = ps_result.stdout.strip().split("\n")
            for pid_str in old_pids:
                pid_str = pid_str.strip()
                if pid_str and pid_str.isdigit():
                    try:
                        os.kill(int(pid_str), 9)
                        _log(f"旧ステージングプロセスを停止: PID {pid_str}")
                    except (ProcessLookupError, PermissionError):
                        pass

        # 3. ステージングサーバーをバックグラウンドで起動
        _log(f"ステージングサーバーを起動: ポート {staging_port}")
        staging_env = {
            **os.environ,
            "GOKA_PORT": str(staging_port),
            "GOKA_DB_PATH": staging_db,
            "GOKA_SETTINGS_PATH": staging_settings,
            "GOKA_ENV": "staging",
            "GOKA_GIT_BRANCH": "main",
            "GOKA_REPO_DIR": staging_dir,
        }
        staging_proc = subprocess.Popen(
            [sys.executable, os.path.join(staging_dir, "server.py")],
            cwd=staging_dir,
            start_new_session=True,
            env=staging_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log(f"ステージングサーバー起動: PID {staging_proc.pid}")

        # 4. 起動確認（最大15秒待機）
        staging_ok = False
        for i in range(15):
            await asyncio.sleep(1)
            try:
                req = urllib.request.Request(
                    f"http://localhost:{staging_port}/admin/status",
                    headers={"X-Token": ADMIN_TOKEN},
                )
                def _check_staging():
                    with urllib.request.urlopen(req, timeout=3) as r:
                        return json.loads(r.read().decode("utf-8"))
                data = await asyncio.to_thread(_check_staging)
                if data.get("env") == "staging":
                    staging_ok = True
                    _log(f"ステージングサーバー応答確認: {data}")
                    break
            except Exception:
                continue

        if not staging_ok:
            _log("警告: ステージングサーバーの応答を確認できませんでした")

        # 5. ファイアウォール設定を試行
        fw_msg = ""
        fw_check = await _run(["which", "gcloud"])
        if fw_check.returncode == 0:
            _log("gcloudでファイアウォールルール作成を試行...")
            fw_result = await _run([
                "gcloud", "compute", "firewall-rules", "create", "goka-staging",
                "--allow=tcp:8001",
                "--description=Allow staging server port 8001",
                "--quiet",
            ])
            if fw_result.returncode == 0:
                fw_msg = "ファイアウォールルール作成成功"
            elif "already exists" in (fw_result.stderr or ""):
                fw_msg = "ファイアウォールルールは既に存在"
            else:
                fw_msg = f"ファイアウォール設定失敗（手動設定が必要かもしれません）: {fw_result.stderr.strip()}"
            _log(fw_msg)
        else:
            fw_msg = "gcloudコマンドが見つかりません。ファイアウォールは手動設定が必要です"
            _log(fw_msg)

        # 6. systemdサービスの作成を試行（永続化）
        systemd_msg = ""
        service_content = f"""[Unit]
Description=Goka GO Staging Server (port {staging_port})
After=network.target

[Service]
Type=simple
User={os.environ.get('USER', 'user')}
WorkingDirectory={staging_dir}
Environment=GOKA_PORT={staging_port}
Environment=GOKA_DB_PATH={staging_db}
Environment=GOKA_SETTINGS_PATH={staging_settings}
Environment=GOKA_ENV=staging
Environment=GOKA_GIT_BRANCH=main
Environment=GOKA_REPO_DIR={staging_dir}
EnvironmentFile=-/etc/goka-staging.env
ExecStart={sys.executable} {staging_dir}/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        service_path = "/etc/systemd/system/goka-staging.service"
        try:
            # sudoなしで書き込みを試行（権限があれば成功する）
            # 管理トークンを制限付きファイルに書き込み（0600権限）
            env_file = "/etc/goka-staging.env"
            env_content = f"GOKA_ADMIN_TOKEN={ADMIN_TOKEN}\n"
            await _run(
                ["sudo", "-n", "tee", env_file],
                input=env_content,
            )
            await _run(["sudo", "-n", "chmod", "0600", env_file])

            write_result = await _run(
                ["sudo", "-n", "tee", service_path],
                input=service_content,
            )
            if write_result.returncode == 0:
                await _run(["sudo", "-n", "systemctl", "daemon-reload"])
                await _run(["sudo", "-n", "systemctl", "enable", "goka-staging"])
                # バックグラウンドプロセスをsystemdに切り替え
                if staging_proc.poll() is None:
                    os.kill(staging_proc.pid, 9)
                start_result = await _run(["sudo", "-n", "systemctl", "start", "goka-staging"])
                if start_result.returncode != 0:
                    # systemd起動失敗時はプロセスを再起動（フォールバック）
                    _log("systemd起動失敗、プロセスとして再起動...")
                    staging_proc = subprocess.Popen(
                        [sys.executable, os.path.join(staging_dir, "server.py")],
                        cwd=staging_dir,
                        start_new_session=True,
                        env=staging_env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    systemd_msg = "systemd起動失敗。プロセスとして再起動済み"
                else:
                    systemd_msg = "systemdサービス作成・起動成功（永続化完了）"
            else:
                systemd_msg = "systemdサービス作成スキップ（sudo権限なし）。プロセスとして起動中"
        except Exception as e:
            systemd_msg = f"systemdサービス作成スキップ: {e}。プロセスとして起動中"
        _log(systemd_msg)

        return {
            "status": "success" if staging_ok else "partial",
            "staging_port": staging_port,
            "staging_dir": staging_dir,
            "staging_pid": staging_proc.pid,
            "staging_ok": staging_ok,
            "firewall": fw_msg,
            "systemd": systemd_msg,
            "log": log_lines,
        }

    except Exception as e:
        logger.error("Staging setup error: %s", e)
        return JSONResponse(
            content={"status": "error", "detail": str(e), "log": log_lines},
            status_code=500)


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
