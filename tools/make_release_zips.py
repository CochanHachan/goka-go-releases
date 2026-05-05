#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyInstaller 済みの dist/goka_go と dist/igo_admin から配布 ZIP を作る。

前提:
  pyinstaller goka_go.spec --noconfirm
  python tools/copy_katago_into_dist.py   # クライアントに KataGo 同梱後
  pyinstaller igo_admin.spec --noconfirm

使い方:
  python tools/make_release_zips.py 1.2.162
  python tools/make_release_zips.py 1.2.162 path/to/out_dir
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _make_zip(src_dir: Path, dst_zip: Path) -> None:
    dst_zip.parent.mkdir(parents=True, exist_ok=True)
    if dst_zip.is_file():
        dst_zip.unlink()
    base_dir = src_dir.parent.resolve()
    base_name = str(dst_zip.parent / "_tmp_release_archive")
    shutil.make_archive(
        base_name,
        "zip",
        root_dir=str(base_dir),
        base_dir=src_dir.name,
    )
    tmp = base_name + ".zip"
    os.replace(tmp, str(dst_zip))


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    if len(sys.argv) < 2:
        print("Usage: python tools/make_release_zips.py VERSION [out_dir]", file=sys.stderr)
        return 1
    ver = sys.argv[1].strip()
    out_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (root / "dist_release")
    out_dir.mkdir(parents=True, exist_ok=True)

    go_src = root / "dist" / "goka_go"
    ad_src = root / "dist" / "igo_admin"
    if not go_src.is_dir():
        print("ERROR: missing", go_src, file=sys.stderr)
        return 1
    if not ad_src.is_dir():
        print("ERROR: missing", ad_src, file=sys.stderr)
        return 1

    go_zip = out_dir / "goka_go_{}.zip".format(ver)
    ad_zip = out_dir / "goka_admin_{}.zip".format(ver)
    _make_zip(go_src, go_zip)
    _make_zip(ad_src, ad_zip)
    print("OK:", go_zip)
    print("OK:", ad_zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
