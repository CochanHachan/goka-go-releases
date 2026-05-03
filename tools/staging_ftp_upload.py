#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ステージング成果物を FTP(S) で Xserver にアップロードする。

環境変数（必須）:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS
任意:
  GOKA_FTP_REMOTE  … 例: goka-igo.com/public_html（デフォルト）
  GOKA_FTP_TLS     … 1=FTPS（デフォルト）, 0=平文FTP

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

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "goka-igo.com/public_html").strip().strip("/")
    use_tls = os.environ.get("GOKA_FTP_TLS", "1").strip() != "0"

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        return 1

    if use_tls:
        from ftplib import FTP_TLS, error_perm
        ftp = FTP_TLS()
        ftp.connect(host, 21, timeout=90)
        ftp.login(user, password)
        ftp.prot_p()
    else:
        from ftplib import FTP, error_perm
        ftp = FTP()
        ftp.connect(host, 21, timeout=90)
        ftp.login(user, password)
        error_perm = __import__("ftplib").error_perm

    target_parts = [p for p in f"{remote_base}/{remote_subdir}".split("/") if p]

    def ensure_dir(parts: list[str]) -> None:
        ftp.cwd("/")
        for p in parts:
            try:
                ftp.cwd(p)
            except error_perm:
                try:
                    ftp.mkd(p)
                except error_perm:
                    pass
                ftp.cwd(p)

    try:
        ensure_dir(target_parts)
        uploaded = 0
        for fpath in local_dir.iterdir():
            if fpath.is_file():
                size_mb = fpath.stat().st_size / 1024 / 1024
                print(f"Uploading {fpath.name} ({size_mb:.1f} MB)...")
                with open(fpath, "rb") as f:
                    ftp.storbinary(f"STOR {fpath.name}", f)
                uploaded += 1
                print(f"  ✓ {fpath.name}")
        print(f"Done. {uploaded} files uploaded to /{'/'.join(target_parts)}")
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
