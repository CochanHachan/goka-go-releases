#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostgreSQL の users テーブルを JSON バックアップする。"""
from __future__ import annotations

import datetime
import gzip
import json
import os
from pathlib import Path

import psycopg2


def _env(name: str, default: str = "", required: bool = False) -> str:
    v = os.environ.get(name, default).strip()
    if required and not v:
        raise RuntimeError(f"Missing env: {name}")
    return v


def main() -> int:
    host = _env("GOKA_PG_HOST", required=True)
    port = int(_env("GOKA_PG_PORT", "5432"))
    db = _env("GOKA_PG_DB", required=True)
    user = _env("GOKA_PG_USER", required=True)
    password = os.environ.get("GOKA_PG_PASS", "")
    sslmode = _env("GOKA_PG_SSLMODE", "require")
    out_dir = Path(_env("GOKA_PG_BACKUP_DIR", "pg_backups")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"users_backup_{ts}.json.gz"

    con = psycopg2.connect(
        host=host,
        port=port,
        dbname=db,
        user=user,
        password=password,
        sslmode=sslmode,
    )
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, real_name, handle_name, password_hash, salt, password_enc,
                   elo, rank, language, email, login_count, match_count, created_at
            FROM users
            ORDER BY id
            """
        )
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = {cols[i]: r[i] for i in range(len(cols))}
            c = d.get("created_at")
            if hasattr(c, "isoformat"):
                d["created_at"] = c.isoformat(sep=" ")
            rows.append(d)
    finally:
        con.close()

    payload = {
        "exported_at_utc": ts,
        "row_count": len(rows),
        "db": db,
        "host": host,
        "rows": rows,
    }
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(out_path)
    print("rows", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
