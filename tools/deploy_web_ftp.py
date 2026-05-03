# -*- coding: utf-8 -*-
"""web/ を FTP(S) でサーバーの public_html 直下に再帰アップロードする。

環境変数（必須）:
  GOKA_FTP_HOST   例: sv1234.xserver.jp（サーバーパネル「FTP設定」に記載）
  GOKA_FTP_USER   FTPアカウント
  GOKA_FTP_PASS   FTPパスワード

任意:
  GOKA_FTP_REMOTE   先頭スラッシュなし。デフォルト: public_html
  GOKA_FTP_TLS      1（デフォルト）= FTPS、0 = 平文FTP

PowerShell 例:
  cd ...\\goka-go-releases
  $env:GOKA_FTP_HOST="svxxxx.xserver.jp"
  $env:GOKA_FTP_USER="your_ftp_user"
  $env:GOKA_FTP_PASS="..."
  py -3 tools/deploy_web_ftp.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "public_html").strip().strip("/")
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

    repo = Path(__file__).resolve().parent.parent
    web = repo / "web"
    if not web.is_dir():
        print("ERROR: web/ not found:", web, file=sys.stderr)
        return 1

    def cwd_from_root(parts: list[str]) -> None:
        ftp.cwd("/")
        for p in parts:
            if not p:
                continue
            try:
                ftp.cwd(p)
            except error_perm:
                try:
                    ftp.mkd(p)
                except error_perm:
                    pass
                ftp.cwd(p)

    base_parts = [p for p in remote_base.split("/") if p]

    try:
        uploaded = 0
        for root, _dirs, files in os.walk(web):
            rel = Path(root).relative_to(web)
            sub = [x for x in rel.parts if x]
            cwd_from_root(base_parts + sub)
            for name in files:
                lp = Path(root) / name
                with open(lp, "rb") as f:
                    ftp.storbinary(f"STOR {name}", f)
                uploaded += 1
                print("+", lp.relative_to(repo))
        print("Done. Files uploaded:", uploaded)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
