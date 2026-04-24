#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dist/goka_go を dist/goka-go-beta.zip にまとめる。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    src_dir = root / "dist" / "goka_go"
    dst_zip = root / "dist" / "goka-go-beta.zip"
    if not src_dir.is_dir():
        print("ERROR: missing", src_dir, file=sys.stderr)
        return 1
    dst_zip.parent.mkdir(parents=True, exist_ok=True)
    base_dir = src_dir.parent.resolve()
    base_name = str(dst_zip.parent / "_tmp_archive")
    shutil.make_archive(base_name, "zip", root_dir=str(base_dir), base_dir=src_dir.name)
    tmp_zip = base_name + ".zip"
    os.replace(tmp_zip, str(dst_zip))
    print("OK:", dst_zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
