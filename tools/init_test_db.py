#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本番と別ファイルの SQLite を、server.init_db() と同じ DDL で初期化する（uvicorn 不要）。

空ファイルまたは未作成パス向け。既存 DB のパスワードハッシュ修復はサーバー起動時の
init_db に任せる（このツールは DDL のみ）。

使い方（リポジトリルートで）:
  python tools/init_test_db.py
  python tools/init_test_db.py path/to/igo_users_staging.db
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _apply_users_ddl(conn: sqlite3.Connection) -> None:
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
    try:
        conn.execute("ALTER TABLE users ADD COLUMN password_enc TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    default = repo / "igo_users_test.db"
    arg = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    target = Path(arg).resolve() if arg else default.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    try:
        _apply_users_ddl(conn)
    finally:
        conn.close()

    print("OK: database schema ready at", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
