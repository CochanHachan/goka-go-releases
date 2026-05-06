#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ステージング成果物を SFTP でサーバーにアップロードする。

環境変数（必須）:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS
任意:
  GOKA_FTP_REMOTE      … 例: public_html（デフォルト: 空）
  GOKA_FTP_PORT        … 既定22（SFTP）
  ADMIN_DOWNLOAD_URL   … 設定時、version-admin.json もサイト直下にアップロード

引数:
  staging_ftp_upload.py <local_dir> <remote_subdir>
  例: staging_ftp_upload.py /tmp/staging staging/releases
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path


def _detect_version(local_dir: Path) -> str:
    """ステージング成果物またはソースコードからバージョンを検出する。"""
    vj = local_dir / "version_staging.json"
    if vj.exists():
        try:
            d = json.loads(vj.read_text(encoding="utf-8"))
            ver = str(d.get("version", "")).strip()
            if ver:
                print(f"  Version from {vj}: {ver}")
                return ver
        except Exception as e:
            print(f"  WARNING: {vj}: {e}")

    for cpath in [Path("igo/constants.py"), local_dir / "igo" / "constants.py"]:
        if cpath.exists():
            try:
                m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', cpath.read_text(encoding="utf-8"))
                if m:
                    print(f"  Version from {cpath}: {m.group(1)}")
                    return m.group(1)
            except Exception as e:
                print(f"  WARNING: {cpath}: {e}")

    return ""


def _sftp_connect():
    """高速 SFTP 接続を確立する。"""
    import paramiko

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "").strip().strip("/")
    port = int(os.environ.get("GOKA_FTP_PORT", "22").strip())

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # 高速転送のためウィンドウサイズを最大化
    ssh.connect(
        host,
        port=port,
        username=user,
        password=password,
        timeout=120,
        banner_timeout=60,
    )
    transport = ssh.get_transport()
    if transport is not None:
        transport.default_window_size = 2147483647  # ~2GB
        transport.packetizer.REKEY_BYTES = pow(2, 40)
        transport.packetizer.REKEY_PACKETS = pow(2, 40)

    sftp = ssh.open_sftp()
    # SFTP チャンネルのバッファサイズを拡大
    channel = sftp.get_channel()
    if channel is not None:
        channel.in_window_size = 2147483647
        channel.out_window_size = 2147483647

    return ssh, sftp, remote_base


def _ensure_dir(sftp, parts: list[str]) -> str:
    """ディレクトリを再帰的に作成し、最終パスを返す。"""
    current = "/"
    for p in parts:
        current = current.rstrip("/") + "/" + p
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)
    return current


def _upload_with_progress(sftp, local_path: str, remote_path: str) -> None:
    """進捗表示付きで高速アップロード。"""
    file_size = os.path.getsize(local_path)
    start = time.time()

    def _progress(transferred: int, total: int) -> None:
        if total > 0:
            pct = transferred * 100 // total
            elapsed = time.time() - start
            speed = transferred / elapsed / 1024 / 1024 if elapsed > 0 else 0
            if pct % 25 == 0 or transferred == total:
                print(f"    {pct}% ({transferred // 1024 // 1024}MB / {total // 1024 // 1024}MB) @ {speed:.1f} MB/s")

    sftp.put(local_path, remote_path, callback=_progress)
    elapsed = time.time() - start
    speed = file_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
    print(f"    Completed in {elapsed:.1f}s ({speed:.1f} MB/s)")


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: staging_ftp_upload.py <local_dir> <remote_subdir>", file=sys.stderr)
        return 1

    local_dir = Path(sys.argv[1])
    remote_subdir = sys.argv[2].strip("/")

    if not local_dir.is_dir():
        print(f"ERROR: {local_dir} is not a directory", file=sys.stderr)
        return 1

    # ファイル一覧を事前に取得してサイズを表示
    files = sorted([f for f in local_dir.iterdir() if f.is_file()])
    total_size = sum(f.stat().st_size for f in files)
    print(f"Files to upload: {len(files)} ({total_size / 1024 / 1024:.1f} MB total)")
    for f in files:
        print(f"  {f.name}: {f.stat().st_size / 1024 / 1024:.1f} MB")

    ssh, sftp, remote_base = _sftp_connect()

    target_parts = [p for p in f"{remote_base}/{remote_subdir}".split("/") if p]

    try:
        remote_dir = _ensure_dir(sftp, target_parts)
        uploaded = 0
        upload_start = time.time()

        for fpath in files:
            size_mb = fpath.stat().st_size / 1024 / 1024
            print(f"Uploading {fpath.name} ({size_mb:.1f} MB)...")
            remote_path = remote_dir.rstrip("/") + "/" + fpath.name
            _upload_with_progress(sftp, str(fpath), remote_path)
            uploaded += 1

        total_elapsed = time.time() - upload_start
        print(f"Done. {uploaded} files uploaded to /{'/'.join(target_parts)} in {total_elapsed:.1f}s")

        # ── version-admin.json をサイト直下にアップロード ──
        download_url = os.environ.get("ADMIN_DOWNLOAD_URL", "").strip()
        print(f"\n--- version-admin.json upload ---")
        print(f"ADMIN_DOWNLOAD_URL = '{download_url}'")

        if download_url:
            version = _detect_version(local_dir)
            print(f"Detected version: '{version}'")
            if version:
                base_dir = "/" + remote_base if remote_base else "/"
                manifest = {
                    "version": version,
                    "download_url": download_url,
                    "release_notes": f"v{version}",
                }
                print(f"Manifest: {json.dumps(manifest, indent=2)}")
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
                try:
                    json.dump(manifest, tmp, ensure_ascii=False, indent=2)
                    tmp.close()
                    dest = base_dir.rstrip("/") + "/version-admin.json"
                    print(f"Uploading to: {dest}")
                    sftp.put(tmp.name, dest)
                    print(f"OK: Uploaded version-admin.json -> {dest}")
                except Exception as e:
                    print(f"ERROR: Failed to upload version-admin.json: {e}", file=sys.stderr)
                    raise
                finally:
                    os.unlink(tmp.name)
            else:
                print("WARNING: Could not detect version, skipping version-admin.json")
        else:
            print("INFO: ADMIN_DOWNLOAD_URL not set, skipping version-admin.json")
    finally:
        sftp.close()
        ssh.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
