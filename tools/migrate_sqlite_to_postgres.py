#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite users テーブルを PostgreSQL に移行する。"""
from __future__ import annotations

import os
import sqlite3
import sys


def _env(name: str, required: bool = True, default: str = "") -> str:
    v = os.environ.get(name, default).strip()
    if required and not v:
        raise RuntimeError(f"Missing env: {name}")
    return v


def main() -> int:
    sqlite_path = _env("GOKA_SQLITE_PATH", required=False, default="igo_users.db")
    pg_host = _env("GOKA_PG_HOST")
    pg_port = int(_env("GOKA_PG_PORT", required=False, default="5432"))
    pg_db = _env("GOKA_PG_DB")
    pg_user = _env("GOKA_PG_USER")
    pg_pass = os.environ.get("GOKA_PG_PASS", "")
    pg_sslmode = _env("GOKA_PG_SSLMODE", required=False, default="require")

    try:
        import psycopg2
    except ImportError as e:
        raise RuntimeError("Please install psycopg2-binary first") from e

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(
        host=pg_host,
        port=pg_port,
        dbname=pg_db,
        user=pg_user,
        password=pg_pass,
        sslmode=pg_sslmode,
    )
    try:
        cur = dst.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                real_name TEXT NOT NULL,
                handle_name TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_enc TEXT NOT NULL DEFAULT '',
                elo DOUBLE PRECISION NOT NULL DEFAULT 0,
                rank TEXT NOT NULL DEFAULT '30級',
                language TEXT NOT NULL DEFAULT 'ja',
                email TEXT NOT NULL DEFAULT '',
                login_count INTEGER NOT NULL DEFAULT 0,
                match_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        dst.commit()

        table_row = src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not table_row:
            print(f"SQLite source has no users table: {sqlite_path}")
            return 0

        cols = {
            str(r["name"]).lower()
            for r in src.execute("PRAGMA table_info(users)").fetchall()
        }
        has_language = "language" in cols
        has_email = "email" in cols
        has_login_count = "login_count" in cols
        has_match_count = "match_count" in cols

        select_sql = (
            "SELECT id, real_name, handle_name, password_hash, salt, password_enc, elo, rank, "
            + ("language" if has_language else "'ja' AS language")
            + ", "
            + ("email" if has_email else "'' AS email")
            + ", "
            + ("COALESCE(login_count, 0) AS login_count" if has_login_count else "0 AS login_count")
            + ", "
            + ("COALESCE(match_count, 0) AS match_count" if has_match_count else "0 AS match_count")
            + ", created_at FROM users ORDER BY id"
        )
        rows = src.execute(select_sql).fetchall()
        if not rows:
            print("No rows in sqlite users table.")
            return 0

        inserted = 0
        for r in rows:
            cur.execute(
                """
                INSERT INTO users (
                  id, real_name, handle_name, password_hash, salt, password_enc, elo, rank, language, email,
                  login_count, match_count, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (handle_name) DO UPDATE SET
                  real_name=EXCLUDED.real_name,
                  password_hash=EXCLUDED.password_hash,
                  salt=EXCLUDED.salt,
                  password_enc=EXCLUDED.password_enc,
                  elo=EXCLUDED.elo,
                  rank=EXCLUDED.rank,
                  language=EXCLUDED.language,
                  email=EXCLUDED.email,
                  login_count=EXCLUDED.login_count,
                  match_count=EXCLUDED.match_count,
                  created_at=EXCLUDED.created_at
                """,
                (
                    r["id"],
                    r["real_name"],
                    r["handle_name"],
                    r["password_hash"],
                    r["salt"],
                    r["password_enc"],
                    r["elo"],
                    r["rank"],
                    r["language"] if "language" in r.keys() else "ja",
                    r["email"] if "email" in r.keys() else "",
                    int(r["login_count"]) if "login_count" in r.keys() else 0,
                    int(r["match_count"]) if "match_count" in r.keys() else 0,
                    r["created_at"],
                ),
            )
            inserted += 1
        dst.commit()

        cur.execute("SELECT COALESCE(MAX(id), 0) FROM users")
        max_id = int(cur.fetchone()[0])
        cur.execute("SELECT setval(pg_get_serial_sequence('users','id'), %s, true)", (max_id,))
        dst.commit()
        print(f"Migrated users: {inserted}, max_id={max_id}")
        return 0
    finally:
        try:
            src.close()
        finally:
            dst.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
