#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ステージング成果物を SFTP でサーバーにアップロードする。

個別ファイル転送方式: 各ファイルを個別に SFTP 転送。
大容量ファイルでも接続が安定。リトライ + SSH keepalive 付き。

環境変数（必須）:
  GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS
任意:
  GOKA_FTP_REMOTE      … アップロード先ルート（デフォルト: /var/www/html）
  GOKA_FTP_PORT        … 既定22（SFTP）
  ADMIN_DOWNLOAD_URL   … 設定時、version-admin-check.json も Web ルートにアップロード

引数:
  staging_ftp_upload.py <local_dir> <remote_subdir>
  例: staging_ftp_upload.py /tmp/staging staging/releases
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

MAX_RETRIES = 3
RETRY_DELAY = 5


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


def _ssh_connect():
    """SSH/SFTP 接続を確立する（keepalive 付き）。"""
    import paramiko

    host = os.environ.get("GOKA_FTP_HOST", "").strip()
    user = os.environ.get("GOKA_FTP_USER", "").strip()
    password = os.environ.get("GOKA_FTP_PASS", "")
    remote_base = os.environ.get("GOKA_FTP_REMOTE", "/var/www/html").strip()
    port = int(os.environ.get("GOKA_FTP_PORT", "22").strip())

    if not host or not user or not password:
        print("ERROR: Set GOKA_FTP_HOST, GOKA_FTP_USER, GOKA_FTP_PASS", file=sys.stderr)
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

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
        transport.set_keepalive(15)
        transport.default_window_size = 2 ** 30  # 1GB (safe value)
        transport.packetizer.REKEY_BYTES = pow(2, 40)
        transport.packetizer.REKEY_PACKETS = pow(2, 40)

    sftp = ssh.open_sftp()
    channel = sftp.get_channel()
    if channel is not None:
        channel.in_window_size = 2 ** 30
        channel.out_window_size = 2 ** 30

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
    """進捗表示付きアップロード。"""
    file_size = os.path.getsize(local_path)
    start = time.time()
    last_pct_reported = -1

    def _progress(transferred: int, total: int) -> None:
        nonlocal last_pct_reported
        if total > 0:
            pct = transferred * 100 // total
            elapsed = time.time() - start
            speed = transferred / elapsed / 1024 / 1024 if elapsed > 0 else 0
            milestone = pct // 10
            if milestone > last_pct_reported or transferred == total:
                last_pct_reported = milestone
                print(f"    {pct}% ({transferred // 1024 // 1024}MB / {total // 1024 // 1024}MB) @ {speed:.1f} MB/s")

    sftp.put(local_path, remote_path, callback=_progress)
    elapsed = time.time() - start
    speed = file_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
    print(f"    Done: {elapsed:.1f}s ({speed:.1f} MB/s)")


def _upload_file_with_retry(ssh_params, remote_dir: str, local_path: str, filename: str) -> None:
    """ファイルを個別にアップロード（リトライ付き）。接続が切れたら再接続する。"""
    remote_path = remote_dir.rstrip("/") + "/" + filename
    file_mb = os.path.getsize(local_path) / 1024 / 1024

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"\n  [{attempt}/{MAX_RETRIES}] Uploading {filename} ({file_mb:.1f} MB) -> {remote_path}")
            ssh, sftp, _ = _ssh_connect()
            try:
                _upload_with_progress(sftp, local_path, remote_path)
                return  # success
            finally:
                sftp.close()
                ssh.close()
        except Exception as e:
            print(f"    ERROR: {e}")
            if attempt < MAX_RETRIES:
                print(f"    Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                raise RuntimeError(f"Failed to upload {filename} after {MAX_RETRIES} attempts: {e}")


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: staging_ftp_upload.py <local_dir> <remote_subdir>", file=sys.stderr)
        return 1

    local_dir = Path(sys.argv[1])
    remote_subdir = sys.argv[2].strip("/")

    if not local_dir.is_dir():
        print(f"ERROR: {local_dir} is not a directory", file=sys.stderr)
        return 1

    files = sorted([f for f in local_dir.iterdir() if f.is_file()])
    total_size = sum(f.stat().st_size for f in files)
    print(f"Files to upload: {len(files)} ({total_size / 1024 / 1024:.1f} MB total)")
    for f in files:
        print(f"  {f.name}: {f.stat().st_size / 1024 / 1024:.1f} MB")

    # 初回接続でディレクトリ作成
    ssh, sftp, remote_base = _ssh_connect()
    target_parts = [p for p in f"{remote_base}/{remote_subdir}".split("/") if p]

    try:
        remote_dir = _ensure_dir(sftp, target_parts)
    finally:
        sftp.close()
        ssh.close()

    # ── ファイル個別転送（リトライ付き・接続を毎回新規作成） ──
    upload_start = time.time()
    print("\n--- Uploading files individually (with retry) ---")

    for fpath in files:
        _upload_file_with_retry(None, remote_dir, str(fpath), fpath.name)

    total_elapsed = time.time() - upload_start
    print(f"\nDone. {len(files)} files deployed to /{'/'.join(target_parts)} in {total_elapsed:.1f}s")

    # ── version-admin JSON を Web ルート直下に配置 ──
    # /var/www/html/version-admin-check.json → https://goka-igo.com/version-admin-check.json
    download_url = os.environ.get("ADMIN_DOWNLOAD_URL", "").strip()
    print(f"\n--- version-admin-check.json upload ---")
    print(f"ADMIN_DOWNLOAD_URL = '{download_url}'")
    # remote_base = Web ルート（/var/www/html）
    web_root = remote_base.rstrip("/")
    print(f"Web root: {web_root}")

    if download_url:
        version = _detect_version(local_dir)
        print(f"Detected version: '{version}'")
        if version:
            manifest = {
                "version": version,
                "admin_download_url": download_url,
                "release_notes": f"v{version}",
            }
            print(f"Manifest: {json.dumps(manifest, indent=2)}")
            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)

            # 旧アプリ互換用（download_url キーも含む）
            old_manifest = {
                "version": version,
                "download_url": download_url,
                "admin_download_url": download_url,
                "release_notes": f"v{version}",
            }
            old_manifest_json = json.dumps(old_manifest, ensure_ascii=False, indent=2)

            import stat as _stat
            import tempfile as _tempfile

            ssh, sftp, _ = _ssh_connect()
            try:
                # Web ルート直下に配置（/var/www/html/version-admin-check.json）
                for fname, content in [
                    ("version-admin-check.json", manifest_json),
                    ("version-admin.json", old_manifest_json),
                ]:
                    dest = web_root + "/" + fname
                    print(f"Writing to: {dest}")
                    tmp = _tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
                    try:
                        tmp.write(content)
                        tmp.close()
                        sftp.put(tmp.name, dest)
                        sftp.chmod(dest, _stat.S_IRUSR | _stat.S_IWUSR | _stat.S_IRGRP | _stat.S_IROTH)  # 644
                        print(f"OK: Uploaded {fname} -> {dest} (chmod 644)")
                    finally:
                        os.unlink(tmp.name)

                # 読み返し確認
                for fname in ["version-admin-check.json", "version-admin.json"]:
                    dest = web_root + "/" + fname
                    with sftp.open(dest, "r") as f:
                        verify = f.read().decode("utf-8")
                    print(f"Verify ({fname}): {verify}")
            finally:
                sftp.close()
                ssh.close()
        else:
            print("WARNING: Could not detect version, skipping version-admin-check.json")
    else:
        print("INFO: ADMIN_DOWNLOAD_URL not set, skipping version-admin-check.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
