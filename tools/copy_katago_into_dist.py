#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""./katago を dist/goka_go/katago にコピーする（PyInstaller 後）。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src = root / "katago"
    dst = root / "dist" / "goka_go" / "katago"
    if not src.is_dir():
        print("ERROR: missing", src, file=sys.stderr)
        return 1
    shutil.copytree(src, dst, dirs_exist_ok=True)
    print("OK:", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
