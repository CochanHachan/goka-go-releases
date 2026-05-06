#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version-admin.json を生成してサイト直下に SFTP アップロードする。

管理者アプリの自動アップデート用。ステージングパイプラインから呼ばれる。

必須環境変数:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS
  ADMIN_VERSION        … アプリバージョン (例: 1.2.191)
  ADMIN_DOWNLOAD_URL   … 管理者アプリ ZIP の URL

任意:
  GOKA_FTP_REMOTE      … 例: public_html
  ADMIN_RELEASE_NOTES  … リリースノート
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    version = os.environ.get("ADMIN_VERSION", "").strip()
    download_url = os.environ.get("ADMIN_DOWNLOAD_URL", "").strip()

    if not version or not download_url:
        print("ERROR: ADMIN_VERSION and ADMIN_DOWNLOAD_URL required", file=sys.stderr)
        return 1

    notes = os.environ.get("ADMIN_RELEASE_NOTES", "").strip() or f"v{version}"

    manifest = {
        "version": version,
        "download_url": download_url,
        "release_notes": notes,
    }
    body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    print(f"version-admin.json: {json.dumps(manifest, indent=2)}")

    import paramiko

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "").strip().strip("/")

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        return 1

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=22, username=user, password=password, timeout=90)
    sftp = ssh.open_sftp()

    try:
        # remote_base のディレクトリを確認・作成
        base_parts = [p for p in remote_base.split("/") if p]
        current = "/"
        for p in base_parts:
            current = current.rstrip("/") + "/" + p
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

        remote_path = current.rstrip("/") + "/version-admin.json"
        with sftp.open(remote_path, "wb") as f:
            f.write(body)
        print(f"Uploaded version-admin.json -> {remote_path}")
    finally:
        sftp.close()
        ssh.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
