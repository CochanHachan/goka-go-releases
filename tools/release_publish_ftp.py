#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""リリース用 ZIP と version.json を SFTP/FTPS でサーバーへアップロードする。

Azure Pipelines の「ステージング → 本番」連続デプロイで使う。手元の手動アップロード不要。

必須環境変数:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS

任意:
  GOKA_FTP_REMOTE       … 例 public_html（先頭末尾スラッシュなし）
  GOKA_FTP_TLS          … 1=FTPS、0=平文FTP（SFTP利用時は無視）
  GOKA_FTP_PORT         … 既定22（SFTP）。21を指定するとFTPS/FTPにフォールバック。

必須引数（または環境変数で代替）:
  --version             … 例 1.2.162
  --zip-go PATH         … goka_go_*.zip のローカルパス
  --zip-admin PATH      … goka_admin_*.zip のローカルパス

任意引数:
  --path-prefix SEG     … リモート・URL の先頭パス（例 staging）。空=サイト直下の version.json / releases/
  --public-base URL     … 既定 https://goka-igo.com（末尾スラッシュなし）
  --release-notes TEXT  … version.json の release_notes

環境変数で引数を渡す場合:
  GOKA_RELEASE_VERSION, GOKA_RELEASE_ZIP_GO, GOKA_RELEASE_ZIP_ADMIN
  GOKA_RELEASE_PATH_PREFIX, GOKA_PUBLIC_BASE_URL, GOKA_RELEASE_NOTES
"""
from __future__ import annotations

import argparse
import io
import json
import os
import stat
import sys
from pathlib import Path


def _sftp_connect():
    """SFTP (paramiko) で接続する。"""
    import paramiko

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    raw_remote = os.environ.get("GOKA_FTP_REMOTE", "")
    remote_base = raw_remote.strip().strip("/")
    port = int(os.environ.get("GOKA_FTP_PORT", "22").strip())

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=120)
    sftp = ssh.open_sftp()

    base_parts = [p for p in remote_base.split("/") if p]

    def cwd_from_root(parts: list[str]) -> str:
        """ディレクトリを再帰的に作成し、最終パスを返す。"""
        current = "/"
        for p in parts:
            current = current.rstrip("/") + "/" + p
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)
        return current

    return sftp, ssh, cwd_from_root, base_parts


def _upload_file(sftp, cwd_from_root, base_parts: list[str], rel_parts: list[str], local: Path) -> None:
    """base_parts + rel_parts のディレクトリに local のファイルをアップロード。"""
    dir_parts = base_parts + rel_parts[:-1]
    remote_dir = cwd_from_root(dir_parts)
    name = rel_parts[-1]
    remote_path = remote_dir.rstrip("/") + "/" + name
    sftp.put(str(local), remote_path)


def _upload_bytes(sftp, cwd_from_root, base_parts: list[str], rel_parts: list[str], data: bytes) -> None:
    dir_parts = base_parts + rel_parts[:-1]
    remote_dir = cwd_from_root(dir_parts)
    name = rel_parts[-1]
    remote_path = remote_dir.rstrip("/") + "/" + name
    with sftp.open(remote_path, "wb") as f:
        f.write(data)


def _build_manifest(
    version: str,
    public_base: str,
    path_prefix: str,
    release_notes: str,
) -> dict:
    pb = public_base.rstrip("/")
    prefix = path_prefix.strip().strip("/")
    if prefix:
        base_url = "{}/{}".format(pb, prefix)
    else:
        base_url = pb
    dl_go = "{}/releases/goka_go_{}.zip".format(base_url, version)
    dl_ad = "{}/releases/goka_admin_{}.zip".format(base_url, version)
    return {
        "version": version,
        "download_url": dl_go,
        "admin_download_url": dl_ad,
        "release_notes": release_notes or "v{}".format(version),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default=os.environ.get("GOKA_RELEASE_VERSION", "").strip())
    ap.add_argument("--zip-go", dest="zip_go", default=os.environ.get("GOKA_RELEASE_ZIP_GO", "").strip())
    ap.add_argument("--zip-admin", dest="zip_admin", default=os.environ.get("GOKA_RELEASE_ZIP_ADMIN", "").strip())
    ap.add_argument(
        "--path-prefix",
        default=os.environ.get("GOKA_RELEASE_PATH_PREFIX", "").strip(),
        help="リモート上のサブディレクトリ（例 staging）。空=本番直下。",
    )
    ap.add_argument(
        "--public-base",
        default=os.environ.get("GOKA_PUBLIC_BASE_URL", "https://goka-igo.com").strip(),
    )
    ap.add_argument(
        "--release-notes",
        default=os.environ.get("GOKA_RELEASE_NOTES", "").strip(),
    )
    args = ap.parse_args()

    ver = args.version
    if not ver:
        print("ERROR: --version or GOKA_RELEASE_VERSION required", file=sys.stderr)
        return 1
    zg = Path(args.zip_go) if args.zip_go else None
    za = Path(args.zip_admin) if args.zip_admin else None
    if not zg or not zg.is_file():
        print("ERROR: --zip-go or GOKA_RELEASE_ZIP_GO must point to an existing file", file=sys.stderr)
        return 1
    if not za or not za.is_file():
        print("ERROR: --zip-admin or GOKA_RELEASE_ZIP_ADMIN must point to an existing file", file=sys.stderr)
        return 1

    prefix_parts = [p for p in args.path_prefix.strip().split("/") if p]
    manifest = _build_manifest(ver, args.public_base, args.path_prefix, args.release_notes)
    body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    sftp, ssh, cwd_from_root, base_parts = _sftp_connect()
    try:
        go_name = "goka_go_{}.zip".format(ver)
        ad_name = "goka_admin_{}.zip".format(ver)
        rel_version = prefix_parts + ["version.json"]
        rel_go = prefix_parts + ["releases", go_name]
        rel_ad = prefix_parts + ["releases", ad_name]

        print("Upload version.json ->", "/".join(rel_version))
        _upload_bytes(sftp, cwd_from_root, base_parts, rel_version, body)
        # version-admin.json: 管理者アプリ自動更新用
        admin_manifest = {
            "version": ver,
            "download_url": manifest["admin_download_url"],
            "release_notes": manifest.get("release_notes", ""),
        }
        admin_body = json.dumps(admin_manifest, ensure_ascii=False, indent=2).encode("utf-8")
        rel_version_admin = prefix_parts + ["version-admin.json"]
        print("Upload version-admin.json ->", "/".join(rel_version_admin))
        _upload_bytes(sftp, cwd_from_root, base_parts, rel_version_admin, admin_body)
        print("Upload", go_name)
        _upload_file(sftp, cwd_from_root, base_parts, rel_go, zg)
        print("Upload", ad_name)
        _upload_file(sftp, cwd_from_root, base_parts, rel_ad, za)
        print("OK. Manifest:", manifest)
    finally:
        sftp.close()
        ssh.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
