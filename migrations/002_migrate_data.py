#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
碁華 DB マイグレーション: 002 データ移行
SQLite → PostgreSQL へ既存データを移行する。

対象:
  1. users テーブル → users / user_auth / user_stats / user_preferences
  2. app_settings.json → app_settings テーブル
  3. ui_settings (SQLite) → user_ui_settings テーブル

実行:
  # 環境変数を設定
  export GOKA_PG_DSN="postgresql://user:pass@host:5432/goka"
  export GOKA_SQLITE_PATH="./igo_users.db"           # 旧 users DB
  export GOKA_UI_SETTINGS_PATH="./ui_settings.db"    # 旧 UI 設定 DB (任意)
  export GOKA_SETTINGS_JSON="./app_settings.json"    # 旧設定 JSON (任意)

  python migrations/002_migrate_data.py
"""

import base64
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2 が必要です: pip install psycopg2-binary")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("migrate_data")

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
PG_DSN = os.environ.get("GOKA_PG_DSN", "")
SQLITE_PATH = os.environ.get("GOKA_SQLITE_PATH", "igo_users.db")
UI_SETTINGS_PATH = os.environ.get("GOKA_UI_SETTINGS_PATH", "ui_settings.db")
SETTINGS_JSON_PATH = os.environ.get("GOKA_SETTINGS_JSON", "app_settings.json")


def _b64_decode_password(password_enc: str) -> str:
    """B64: 形式の password_enc を復号。"""
    if not isinstance(password_enc, str) or not password_enc.startswith("B64:"):
        return ""
    try:
        return base64.b64decode(password_enc[4:]).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 1. users テーブル移行
# ---------------------------------------------------------------------------
def migrate_users(pg_conn, sqlite_path: str):
    """SQLite users → PostgreSQL users/user_auth/user_stats/user_preferences"""
    if not Path(sqlite_path).exists():
        logger.warning("SQLite DB が見つかりません: %s — users 移行をスキップ", sqlite_path)
        return 0

    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row

    # カラム一覧を取得（旧バージョン対応）
    cur = sq_conn.execute("PRAGMA table_info(users)")
    col_names = {c[1] for c in cur.fetchall()}

    rows = sq_conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    logger.info("SQLite users: %d 件を移行開始", len(rows))

    migrated = 0
    pg_cur = pg_conn.cursor()

    for row in rows:
        handle = row["handle_name"]
        real_name = row["real_name"]

        # カラムの存在チェック付き取得
        email = row["email"] if "email" in col_names else ""
        password_hash = row["password_hash"]
        salt = row["salt"]
        password_enc = row["password_enc"] if "password_enc" in col_names else ""
        elo = row["elo"] if "elo" in col_names else (row["elo_rating"] if "elo_rating" in col_names else 0)
        rank = row["rank"] if "rank" in col_names else "30級"
        language = row["language"] if "language" in col_names else "ja"
        created_at = row["created_at"] if "created_at" in col_names else None

        pg_cur.execute("SAVEPOINT sp_user")
        try:
            # 1) users テーブル
            pg_cur.execute("""
                INSERT INTO users (handle_name, real_name, email, created_at, updated_at, is_active)
                VALUES (%s, %s, %s, COALESCE(%s::timestamptz, NOW()), NOW(), TRUE)
                ON CONFLICT (handle_name) DO NOTHING
                RETURNING id
            """, (handle, real_name, email or "", created_at))

            result = pg_cur.fetchone()
            if result is None:
                pg_cur.execute("RELEASE SAVEPOINT sp_user")
                logger.info("  [既存] %s — スキップ", handle)
                continue
            user_id = result[0]

            # 2) user_auth テーブル
            pg_cur.execute("""
                INSERT INTO user_auth (user_id, password_hash, salt, password_enc, password_version, updated_at)
                VALUES (%s, %s, %s, %s, 1, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, password_hash, salt, password_enc or ""))

            # 3) user_stats テーブル
            pg_cur.execute("""
                INSERT INTO user_stats (user_id, elo, rank, login_count, match_count, updated_at)
                VALUES (%s, %s, %s, 0, 0, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, float(elo), rank))

            # 4) user_preferences テーブル
            pg_cur.execute("""
                INSERT INTO user_preferences (user_id, language, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, language))

            pg_cur.execute("RELEASE SAVEPOINT sp_user")
            migrated += 1
            logger.info("  [OK] %s (id=%d, rank=%s)", handle, user_id, rank)

        except Exception as e:
            logger.error("  [ERR] %s — %s", handle, e)
            pg_cur.execute("ROLLBACK TO SAVEPOINT sp_user")
            continue

    pg_conn.commit()
    sq_conn.close()
    logger.info("users 移行完了: %d / %d 件", migrated, len(rows))
    return migrated


# ---------------------------------------------------------------------------
# 2. app_settings.json 移行
# ---------------------------------------------------------------------------
def migrate_app_settings(pg_conn, json_path: str):
    """app_settings.json → PostgreSQL app_settings テーブル"""
    if not Path(json_path).exists():
        logger.warning("app_settings.json が見つかりません: %s — スキップ", json_path)
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("app_settings.json の読み込みに失敗: %s", e)
        return False

    pg_cur = pg_conn.cursor()

    # 既知のカラムのみ更新
    known_keys = {
        "theme": str,
        "offer_timeout_min": int,
        "fischer_main_time": int,
        "fischer_increment": int,
        "bot_offer_delay": int,
        "board_frame_height": float,
        "match_apply_height": float,
        "challenge_accept_height": float,
        "sakura_dialog_height": float,
    }

    set_clauses = []
    values = []
    for key, cast_fn in known_keys.items():
        if key in settings:
            set_clauses.append(f"{key} = %s")
            values.append(cast_fn(settings[key]))

    if set_clauses:
        values.append(1)  # WHERE id = 1
        pg_cur.execute(
            f"UPDATE app_settings SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = %s",
            values
        )
        pg_conn.commit()
        logger.info("app_settings 移行完了: %d 項目を更新", len(set_clauses))
        return True

    logger.info("app_settings: 更新対象なし")
    return False


# ---------------------------------------------------------------------------
# 3. ui_settings (SQLite) 移行
# ---------------------------------------------------------------------------
def migrate_ui_settings(pg_conn, ui_db_path: str):
    """SQLite ui_settings → PostgreSQL user_ui_settings"""
    if not Path(ui_db_path).exists():
        logger.warning("ui_settings.db が見つかりません: %s — スキップ", ui_db_path)
        return 0

    sq_conn = sqlite3.connect(ui_db_path)
    sq_conn.row_factory = sqlite3.Row

    # テーブル存在チェック
    tables = sq_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ui_settings'"
    ).fetchone()
    if not tables:
        logger.warning("ui_settings テーブルが存在しません — スキップ")
        sq_conn.close()
        return 0

    rows = sq_conn.execute("SELECT screen_name, key, value FROM ui_settings").fetchall()
    logger.info("ui_settings: %d 件を移行開始", len(rows))

    pg_cur = pg_conn.cursor()
    migrated = 0

    # user_id=1 (admin) にひも付ける（旧 ui_settings はユーザー区別なし）
    # 実運用時は適切な user_id を指定する
    default_user_id = 1

    # user_id=1 が存在するか確認
    pg_cur.execute("SELECT id FROM users WHERE id = %s", (default_user_id,))
    if pg_cur.fetchone() is None:
        logger.warning("user_id=%d が存在しません — ui_settings 移行をスキップ", default_user_id)
        sq_conn.close()
        return 0

    for row in rows:
        screen_name = row["screen_name"]
        setting_key = row["key"]
        raw_value = row["value"]

        # JSON として解析を試行
        try:
            setting_value = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError):
            setting_value = raw_value  # そのまま文字列として格納

        pg_cur.execute("SAVEPOINT sp_ui")
        try:
            pg_cur.execute("""
                INSERT INTO user_ui_settings (user_id, screen_name, setting_key, setting_value, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (user_id, screen_name, setting_key)
                DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
            """, (default_user_id, screen_name, setting_key, json.dumps(setting_value, ensure_ascii=False)))
            pg_cur.execute("RELEASE SAVEPOINT sp_ui")
            migrated += 1
        except Exception as e:
            logger.error("  [ERR] %s/%s — %s", screen_name, setting_key, e)
            pg_cur.execute("ROLLBACK TO SAVEPOINT sp_ui")

    pg_conn.commit()
    sq_conn.close()
    logger.info("ui_settings 移行完了: %d / %d 件", migrated, len(rows))
    return migrated


# ---------------------------------------------------------------------------
# 4. game_records (SQLite) 移行
# ---------------------------------------------------------------------------
def migrate_game_records(pg_conn, sqlite_path: str):
    """SQLite game_records → PostgreSQL games / game_players / game_records"""
    if not Path(sqlite_path).exists():
        logger.warning("SQLite DB が見つかりません: %s — game_records 移行をスキップ", sqlite_path)
        return 0

    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row

    # テーブル存在チェック
    tables = sq_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='game_records'"
    ).fetchone()
    if not tables:
        logger.warning("game_records テーブルが存在しません — スキップ")
        sq_conn.close()
        return 0

    rows = sq_conn.execute(
        "SELECT * FROM game_records ORDER BY id"
    ).fetchall()
    logger.info("game_records: %d 件を移行開始", len(rows))

    pg_cur = pg_conn.cursor()
    migrated = 0

    for row in rows:
        pg_cur.execute("SAVEPOINT sp_game")
        try:
            played_at = row["played_at"]
            black_name = row["black_name"]
            white_name = row["white_name"]
            result = row["result"] or ""
            komi = row["komi"] if "komi" in row.keys() else 7.5
            move_count = row["move_count"] if "move_count" in row.keys() else 0
            sgf_text = row["sgf_text"] if "sgf_text" in row.keys() else ""
            black_rank = row["black_rank"] if "black_rank" in row.keys() else ""
            white_rank = row["white_rank"] if "white_rank" in row.keys() else ""

            # 勝者の判定
            winner_handle = None
            if result.startswith("B+"):
                winner_handle = black_name
            elif result.startswith("W+"):
                winner_handle = white_name

            # 勝者の user_id を取得
            winner_user_id = None
            if winner_handle:
                pg_cur.execute("SELECT id FROM users WHERE handle_name = %s", (winner_handle,))
                r = pg_cur.fetchone()
                if r:
                    winner_user_id = r[0]

            # games テーブルに挿入
            pg_cur.execute("""
                INSERT INTO games (started_at, ended_at, status, result, winner_user_id, komi, move_count, source)
                VALUES (COALESCE(%s::timestamptz, NOW()), COALESCE(%s::timestamptz, NOW()), 'finished', %s, %s, %s, %s, 'migrated')
                RETURNING id
            """, (played_at, played_at, result, winner_user_id, komi, move_count))
            game_id = pg_cur.fetchone()[0]

            # game_players: 黒
            pg_cur.execute("SELECT id FROM users WHERE handle_name = %s", (black_name,))
            black_user = pg_cur.fetchone()
            if black_user:
                pg_cur.execute("""
                    INSERT INTO game_players (game_id, user_id, color, rank_at_game, elo_at_game)
                    VALUES (%s, %s, 'B', %s, 0)
                    ON CONFLICT DO NOTHING
                """, (game_id, black_user[0], black_rank))

            # game_players: 白
            pg_cur.execute("SELECT id FROM users WHERE handle_name = %s", (white_name,))
            white_user = pg_cur.fetchone()
            if white_user:
                pg_cur.execute("""
                    INSERT INTO game_players (game_id, user_id, color, rank_at_game, elo_at_game)
                    VALUES (%s, %s, 'W', %s, 0)
                    ON CONFLICT DO NOTHING
                """, (game_id, white_user[0], white_rank))

            # game_records: SGF
            pg_cur.execute("""
                INSERT INTO game_records (game_id, sgf_text, created_at, updated_at)
                VALUES (%s, %s, COALESCE(%s::timestamptz, NOW()), NOW())
                ON CONFLICT DO NOTHING
            """, (game_id, sgf_text, played_at))

            pg_cur.execute("RELEASE SAVEPOINT sp_game")
            migrated += 1

        except Exception as e:
            logger.error("  [ERR] record id=%s — %s", row["id"], e)
            pg_cur.execute("ROLLBACK TO SAVEPOINT sp_game")

    pg_conn.commit()
    sq_conn.close()
    logger.info("game_records 移行完了: %d / %d 件", migrated, len(rows))
    return migrated


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    if not PG_DSN:
        print("エラー: GOKA_PG_DSN 環境変数を設定してください")
        print("例: export GOKA_PG_DSN='postgresql://user:pass@host:5432/goka'")
        sys.exit(1)

    logger.info("=== 碁華 データ移行開始 ===")
    logger.info("PostgreSQL: %s", PG_DSN.split("@")[-1] if "@" in PG_DSN else "(接続情報)")
    logger.info("SQLite: %s", SQLITE_PATH)

    pg_conn = psycopg2.connect(PG_DSN)

    try:
        # 1. users 移行
        migrate_users(pg_conn, SQLITE_PATH)

        # 2. app_settings.json 移行
        migrate_app_settings(pg_conn, SETTINGS_JSON_PATH)

        # 3. ui_settings 移行
        migrate_ui_settings(pg_conn, UI_SETTINGS_PATH)

        # 4. game_records 移行
        migrate_game_records(pg_conn, SQLITE_PATH)

    finally:
        pg_conn.close()

    logger.info("=== 碁華 データ移行完了 ===")


if __name__ == "__main__":
    main()
