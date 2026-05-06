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

import json
import os
import re
import sys
import tempfile
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

        # ── version-admin.json をサイト直下にアップロード ──
        download_url = os.environ.get("ADMIN_DOWNLOAD_URL", "").strip()
        if download_url:
            version = _detect_version(local_dir)
            if version:
                base_dir = "/" + remote_base if remote_base else "/"
                manifest = {
                    "version": version,
                    "download_url": download_url,
                    "release_notes": f"v{version}",
                }
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                try:
                    json.dump(manifest, tmp, ensure_ascii=False, indent=2)
                    tmp.close()
                    dest = base_dir.rstrip("/") + "/version-admin.json"
                    sftp.put(tmp.name, dest)
                    print(f"Uploaded version-admin.json -> {dest}")
                    print(f"  {json.dumps(manifest, indent=2)}")
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
