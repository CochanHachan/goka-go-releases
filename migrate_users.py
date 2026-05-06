#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
既存ローカルDBのユーザーをGCPサーバーに移行するスクリプト
実行: python migrate_users.py
"""

import sqlite3
import urllib.request
import json
import os

API_BASE_URL = "http://20.48.18.153:8000"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "igo_users.db")


def api_post(endpoint, data):
    raw = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        API_BASE_URL + endpoint,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    if not os.path.exists(DB_PATH):
        print("ローカルDBが見つかりません:", DB_PATH)
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT handle_name, real_name, password_plain, rank, elo_rating FROM users ORDER BY id"
    ).fetchall()
    conn.close()

    print("{}件のアカウントを移行します...\n".format(len(rows)))

    success = 0
    skip = 0
    fail = 0

    for row in rows:
        handle = row["handle_name"]
        name   = row["real_name"]
        pw     = row["password_plain"]
        rank   = row["rank"] or "30級"

        if not pw:
            print("[SKIP] {} - パスワードが空のためスキップ".format(handle))
            skip += 1
            continue

        try:
            result = api_post("/api/register", {
                "real_name": name,
                "handle_name": handle,
                "password": pw,
                "rank": rank,
            })
            if result.get("success"):
                print("[OK]   {} ({}) 登録成功".format(handle, rank))
                success += 1
            else:
                msg = result.get("message", "")
                if "既に使われています" in msg or "already" in msg.lower():
                    print("[既存] {} - サーバーに既に登録済み".format(handle))
                    skip += 1
                else:
                    print("[FAIL] {} - {}".format(handle, msg))
                    fail += 1
        except Exception as e:
            print("[ERR]  {} - {}".format(handle, e))
            fail += 1

    print("\n完了: 成功={} スキップ={} 失敗={}".format(success, skip, fail))


if __name__ == "__main__":
    main()
