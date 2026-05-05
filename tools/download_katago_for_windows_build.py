#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 用 PyInstaller ビルド向けに KataGo 本体・モデルを ./katago に展開する。"""
from __future__ import annotations

import gzip
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    katago_url = (
        "https://github.com/lightvector/KataGo/releases/download/"
        "v1.16.4/katago-v1.16.4-opencl-windows-x64.zip"
    )
    katago_zip = "katago-opencl.zip"
    urllib.request.urlretrieve(katago_url, katago_zip)

    katago_dir = root / "katago"
    katago_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(katago_zip, "r") as zf:
        for member in zf.infolist():
            name = member.filename
            if name.endswith((".exe", ".dll", ".cfg", ".pem")):
                member.filename = os.path.basename(name)
                zf.extract(member, katago_dir)

    model_url = (
        "https://media.katagotraining.org/uploaded/networks/models/kata1/"
        "kata1-b28c512nbt-s12763923712-d5805955894.bin.gz"
    )
    req = urllib.request.Request(
        model_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req) as resp, open("model.bin.gz", "wb") as out:
        shutil.copyfileobj(resp, out)
    with gzip.open("model.bin.gz", "rb") as src, open(katago_dir / "model.bin", "wb") as dst:
        shutil.copyfileobj(src, dst)

    human_url = (
        "https://github.com/lightvector/KataGo/releases/download/"
        "v1.15.0/b18c384nbt-humanv0.bin.gz"
    )
    urllib.request.urlretrieve(human_url, "human_model.bin.gz")
    with gzip.open("human_model.bin.gz", "rb") as src, open(katago_dir / "human_model.bin", "wb") as dst:
        shutil.copyfileobj(src, dst)

    kgd = katago_dir / "KataGoData"
    kgd.mkdir(parents=True, exist_ok=True)
    (kgd / ".keep").write_text("", encoding="utf-8")
    print("OK: KataGo bundle in", katago_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
