# -*- coding: utf-8 -*-
"""PyInstaller の dist/igo_admin を staging と同じ構造の ZIP にまとめる。

前提: pyinstaller igo_admin.spec --noconfirm が成功していること。

使い方:
  py -3 tools/package_igo_admin_zip.py
  py -3 tools/package_igo_admin_zip.py path/to/out.zip

出力既定: ユーザーの「ダウンロード」フォルダ（Downloads / ダウンロード）に
  goka-admin-local.zip（ルートに igo_admin/ フォルダが付く）
  ※成果物は作業用リポジトリ内に置かず、OS の標準ダウンロード先へ出す。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys


def _default_downloads_dir() -> str:
    """Windows: Downloads または ダウンロード。無ければホーム直下の Downloads。"""
    home = os.path.expanduser("~")
    for name in ("Downloads", "ダウンロード"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            return p
    return os.path.join(home, "Downloads")


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "dist", "igo_admin")
    if not os.path.isdir(src):
        print("ERROR: not found:", src, file=sys.stderr)
        print("Run: pyinstaller igo_admin.spec --noconfirm", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description="Zip dist/igo_admin for distribution.")
    default_zip = os.path.join(_default_downloads_dir(), "goka-admin-local.zip")
    ap.add_argument(
        "out_zip",
        nargs="?",
        default=default_zip,
        help="出力 ZIP パス（既定: ダウンロード/goka-admin-local.zip）",
    )
    args = ap.parse_args()
    out_zip = os.path.abspath(args.out_zip)
    os.makedirs(os.path.dirname(out_zip) or ".", exist_ok=True)
    if os.path.isfile(out_zip):
        os.remove(out_zip)

    base_dir = os.path.dirname(os.path.abspath(src))
    base_name = os.path.join(os.path.dirname(out_zip), "_tmp_igo_admin_archive")
    shutil.make_archive(
        base_name,
        "zip",
        root_dir=base_dir,
        base_dir=os.path.basename(src),
    )
    tmp = base_name + ".zip"
    os.replace(tmp, out_zip)
    mb = os.path.getsize(out_zip) / (1024 * 1024)
    print("Wrote", out_zip, f"({mb:.1f} MB)")
    print("Extract then run: igo_admin\\igo_admin.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
