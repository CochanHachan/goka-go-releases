#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ステージング成果物を SFTP でサーバーにアップロードする。

環境変数（必須）:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS
任意:
  GOKA_FTP_REMOTE  … 例: public_html（デフォルト: 空）
  GOKA_FTP_PORT    … 既定22（SFTP）

引数:
  staging_ftp_upload.py <local_dir> <remote_subdir>
  例: staging_ftp_upload.py /tmp/staging staging/releases
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: staging_ftp_upload.py <local_dir> <remote_subdir>", file=sys.stderr)
        return 1

    local_dir = Path(sys.argv[1])
    remote_subdir = sys.argv[2].strip("/")

    if not local_dir.is_dir():
        print(f"ERROR: {local_dir} is not a directory", file=sys.stderr)
        return 1

    import paramiko

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "").strip().strip("/")
    port = int(os.environ.get("GOKA_FTP_PORT", "22").strip())

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        return 1

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=90)
    sftp = ssh.open_sftp()

    target_parts = [p for p in f"{remote_base}/{remote_subdir}".split("/") if p]

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
        remote_dir = ensure_dir(target_parts)
        uploaded = 0
        for fpath in local_dir.iterdir():
            if fpath.is_file():
                size_mb = fpath.stat().st_size / 1024 / 1024
                print(f"Uploading {fpath.name} ({size_mb:.1f} MB)...")
                remote_path = remote_dir.rstrip("/") + "/" + fpath.name
                sftp.put(str(fpath), remote_path)
                uploaded += 1
                print(f"  OK {fpath.name}")
        print(f"Done. {uploaded} files uploaded to /{'/'.join(target_parts)}")
    finally:
        sftp.close()
        ssh.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
