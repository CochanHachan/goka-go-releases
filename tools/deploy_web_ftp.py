# -*- coding: utf-8 -*-
"""web/ を SFTP でサーバーの public_html 直下に再帰アップロードする。

環境変数（必須）:
  GOKA_FTP_HOST   例: your-vps-host.example.com
  GOKA_FTP_USER   SSH/SFTPアカウント
  GOKA_FTP_PASS   SSH/SFTPパスワード

任意:
  GOKA_FTP_REMOTE   先頭スラッシュなし。デフォルト: public_html
  GOKA_FTP_PORT     既定22（SFTP）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    import paramiko

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "public_html").strip().strip("/")
    port = int(os.environ.get("GOKA_FTP_PORT", "22").strip())

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        return 1

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=90)
    sftp = ssh.open_sftp()

    repo = Path(__file__).resolve().parent.parent
    web = repo / "web"
    if not web.is_dir():
        print("ERROR: web/ not found:", web, file=sys.stderr)
        return 1

    base_parts = [p for p in remote_base.split("/") if p]

    def ensure_dir(parts: list[str]) -> str:
        current = "/"
        for p in parts:
            current = current.rstrip("/") + "/" + p
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)
        return current

    try:
        uploaded = 0
        for root, _dirs, files in os.walk(web):
            rel = Path(root).relative_to(web)
            sub = [x for x in rel.parts if x]
            remote_dir = ensure_dir(base_parts + sub)
            for name in files:
                lp = Path(root) / name
                remote_path = remote_dir.rstrip("/") + "/" + name
                sftp.put(str(lp), remote_path)
                uploaded += 1
                print("+", lp.relative_to(repo))
        print("Done. Files uploaded:", uploaded)
    finally:
        sftp.close()
        ssh.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
