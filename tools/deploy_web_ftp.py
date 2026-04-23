# -*- coding: utf-8 -*-
"""web/ 以下を FTP(S) でリモートへ再帰アップロードする（デバッグ版）。

環境変数:
  GOKA_FTP_HOST     必須: FTP/FTPS ホスト
  GOKA_FTP_USER     必須: ユーザー名
  GOKA_FTP_PASS     必須: パスワード
  GOKA_FTP_REMOTE   任意: 配置先ディレクトリ
  GOKA_FTP_TLS      任意: "1" なら FTPS, "0" なら FTP
  GOKA_FTP_PORT     任意: ポート番号（既定 21）
  GOKA_FTP_DEBUG    任意: "1" で ftplib の通信ログを出す
"""

from __future__ import annotations

import os
import sys
import socket
from pathlib import Path


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def mask_text(value: str, keep: int = 2) -> str:
    if not value:
        return "(empty)"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}***{value[-keep:]}"


def safe_len(value: str) -> int:
    return len(value) if value is not None else 0


def print_env_summary(
    host: str,
    user: str,
    password: str,
    remote_base: str,
    use_tls: bool,
    port: int,
    debug: bool,
) -> None:
    print("=== FTP DEBUG CONFIG ===")
    print(f"GOKA_FTP_HOST set : {bool(host)} value={host!r}")
    print(
        f"GOKA_FTP_USER set : {bool(user)} len={safe_len(user)} masked={mask_text(user)}"
    )
    print(f"GOKA_FTP_PASS set : {bool(password)} len={safe_len(password)}")
    print(f"GOKA_FTP_REMOTE   : {remote_base!r}")
    print(f"GOKA_FTP_TLS      : {use_tls}")
    print(f"GOKA_FTP_PORT     : {port}")
    print(f"GOKA_FTP_DEBUG    : {debug}")
    print("========================")


def connect_and_login(host: str, port: int, user: str, password: str, use_tls: bool, debug: bool):
    if use_tls:
        from ftplib import FTP_TLS
        ftp = FTP_TLS()
    else:
        from ftplib import FTP
        ftp = FTP()

    if debug:
        ftp.set_debuglevel(2)

    print(f"[STEP] connect: host={host!r} port={port} tls={use_tls}")
    ftp.connect(host, port, timeout=90)
    print("[OK] connected")

    print(f"[STEP] login: user={user!r} pass_len={len(password)}")
    ftp.login(user, password)
    print("[OK] logged in")

    if use_tls:
        print("[STEP] FTPS data channel protection: prot_p()")
        ftp.prot_p()
        print("[OK] prot_p done")

    print("[STEP] pwd")
    current = ftp.pwd()
    print(f"[OK] pwd={current!r}")

    return ftp


def cwd_from_root(ftp, parts, error_perm_cls) -> None:
    print("[STEP] cwd('/')")
    ftp.cwd("/")
    for p in parts:
        print(f"[STEP] cwd({p!r})")
        try:
            ftp.cwd(p)
            print(f"[OK] entered {p!r}")
        except error_perm_cls as e:
            print(f"[INFO] cwd failed for {p!r}: {e}")
            print(f"[STEP] mkd({p!r})")
            try:
                ftp.mkd(p)
                print(f"[OK] created {p!r}")
            except error_perm_cls as mkd_e:
                print(f"[INFO] mkd failed for {p!r}: {mkd_e}")
            ftp.cwd(p)
            print(f"[OK] entered {p!r} after mkd")


def main() -> int:
    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()

    # 元の挙動に近づけつつ、確認しやすいように生値とstrip後を比較できるようにする
    raw_password = os.environ.get("GOKA_FTP_PASS", "")
    password = raw_password

    raw_remote = os.environ.get("GOKA_FTP_REMOTE", "")
    remote_base = raw_remote.strip().strip("/")

    use_tls = env_bool("GOKA_FTP_TLS", True)
    debug = env_bool("GOKA_FTP_DEBUG", False)

    port_raw = os.environ.get("GOKA_FTP_PORT", "21").strip()
    try:
        port = int(port_raw)
    except ValueError:
        print(f"ERROR: GOKA_FTP_PORT must be integer: {port_raw!r}", file=sys.stderr)
        return 1

    print_env_summary(
        host=host,
        user=user,
        password=password,
        remote_base=remote_base,
        use_tls=use_tls,
        port=port,
        debug=debug,
    )

    if raw_password != raw_password.strip():
        print(
            "[WARN] GOKA_FTP_PASS has leading/trailing whitespace or newline."
            " Secret value may contain an accidental newline."
        )

    if not host or not user or not password:
        print(
            "ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS",
            file=sys.stderr,
        )
        return 1

    try:
        print(f"[STEP] DNS lookup: {host!r}")
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addrs = sorted({item[4][0] for item in infos})
        print(f"[OK] resolved addresses: {addrs}")
    except Exception as e:
        print(f"[WARN] DNS lookup failed: {e}")

    if use_tls:
        from ftplib import error_perm
    else:
        from ftplib import error_perm

    ftp = None
    try:
        ftp = connect_and_login(
            host=host,
            port=port,
            user=user,
            password=password,
            use_tls=use_tls,
            debug=debug,
        )

        repo = Path(__file__).resolve().parent.parent
        web = repo / "web"
        print(f"[STEP] local web dir check: {web}")
        if not web.is_dir():
            print(f"ERROR: web/ not found: {web}", file=sys.stderr)
            return 1

        base_parts = [p for p in remote_base.split("/") if p]
        print(f"[INFO] remote base parts: {base_parts}")

        uploaded = 0
        for root, _dirs, files in os.walk(web):
            rel = Path(root).relative_to(web)
            sub = [x for x in rel.parts if x]
            target_parts = base_parts + sub
            print(f"[STEP] enter remote dir: {target_parts}")
            cwd_from_root(ftp, target_parts, error_perm)

            for name in files:
                lp = Path(root) / name
                size = lp.stat().st_size
                print(f"[STEP] upload: {lp.relative_to(repo)} size={size}")
                with open(lp, "rb") as f:
                    ftp.storbinary(f"STOR {name}", f)
                uploaded += 1
                print(f"[OK] uploaded: {lp.relative_to(repo)}")

        print(f"Done. Files uploaded: {uploaded}")
        return 0

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    finally:
        if ftp is not None:
            try:
                print("[STEP] quit")
                ftp.quit()
                print("[OK] quit")
            except Exception as e:
                print(f"[INFO] quit failed, fallback close(): {e}")
                try:
                    ftp.close()
                    print("[OK] close")
                except Exception as close_e:
                    print(f"[WARN] close failed too: {close_e}")


if __name__ == "__main__":
    raise SystemExit(main())