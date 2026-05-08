#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version-admin.json を生成してサイト直下に SFTP アップロードする。

管理者アプリの自動アップデート用。ステージングパイプラインから呼ばれる。

必須環境変数:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS
  ADMIN_DOWNLOAD_URL   … 管理者アプリ ZIP の URL

バージョン取得（優先順位）:
  1) 環境変数 ADMIN_VERSION
  2) STAGING_DIR/version_staging.json の "version" フィールド
  3) igo/constants.py の APP_VERSION

任意:
  GOKA_FTP_REMOTE      … 例: public_html
  STAGING_DIR          … ステージング成果物のディレクトリ
  ADMIN_RELEASE_NOTES  … リリースノート
"""
from __future__ import annotations

import json
import os
import re
import sys


def _detect_version() -> str:
    """バージョンを自動検出する。"""
    # 1) 環境変数
    ver = os.environ.get("ADMIN_VERSION", "").strip()
    if ver:
        print(f"Version from ADMIN_VERSION env: {ver}")
        return ver

    # 2) version_staging.json（ステージング成果物）
    staging_dir = os.environ.get("STAGING_DIR", "").strip()
    if staging_dir:
        vj_path = os.path.join(staging_dir, "version_staging.json")
        if os.path.exists(vj_path):
            try:
                with open(vj_path, encoding="utf-8") as f:
                    d = json.load(f)
                ver = str(d.get("version", "")).strip()
                if ver:
                    print(f"Version from {vj_path}: {ver}")
                    return ver
            except Exception as e:
                print(f"WARNING: Failed to read {vj_path}: {e}")

    # 3) igo/constants.py
    for cpath in ["igo/constants.py", os.path.join(staging_dir or ".", "igo", "constants.py")]:
        if os.path.exists(cpath):
            try:
                text = open(cpath, encoding="utf-8").read()
                m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
                if m:
                    ver = m.group(1)
                    print(f"Version from {cpath}: {ver}")
                    return ver
            except Exception as e:
                print(f"WARNING: Failed to read {cpath}: {e}")

    return ""


def main() -> int:
    version = _detect_version()
    download_url = os.environ.get("ADMIN_DOWNLOAD_URL", "").strip()

    if not version:
        print("ERROR: Could not detect version", file=sys.stderr)
        return 1
    if not download_url:
        print("ERROR: ADMIN_DOWNLOAD_URL required", file=sys.stderr)
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
        base_parts = [p for p in remote_base.split("/") if p]
        current = "/"
        for p in base_parts:
            current = current.rstrip("/") + "/" + p
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

        remote_path = current.rstrip("/") + "/version-admin-check.json"
        with sftp.open(remote_path, "wb") as f:
            f.write(body)
        print(f"Uploaded version-admin-check.json -> {remote_path}")
    finally:
        sftp.close()
        ssh.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
