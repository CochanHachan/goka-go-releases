#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""igo/constants_env.py をテスト版ビルド用（staging + beta）に書き換える。

GitHub Actions / Azure Pipelines / 手元 PyInstaller から共通利用する。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def patch(path: Path, beta_version: str, update_url: str) -> None:
    if any(c in beta_version for c in ('"', "'", "\n", "\r")):
        print("ERROR: invalid beta_version", file=sys.stderr)
        sys.exit(2)
    if any(c in update_url for c in ('"', "'", "\n", "\r")):
        print("ERROR: invalid update_url", file=sys.stderr)
        sys.exit(2)
    text = path.read_text(encoding="utf-8")
    reps = [
        ('_ENV = "production"', '_ENV = "staging"'),
        ('_APP_EDITION = "release"', '_APP_EDITION = "beta"'),
        ('BETA_CHANNEL_VERSION = ""', 'BETA_CHANNEL_VERSION = "{}"'.format(beta_version)),
    ]
    for a, b in reps:
        if a not in text:
            print("ERROR: {!r} not found in {}".format(a, path), file=sys.stderr)
            sys.exit(1)
        text = text.replace(a, b, 1)
    text, n = re.subn(
        r'CLIENT_UPDATE_CHECK_URL\s*=\s*"[^"]*"',
        'CLIENT_UPDATE_CHECK_URL = "{}"'.format(update_url),
        text,
        count=1,
    )
    if n != 1:
        print("ERROR: CLIENT_UPDATE_CHECK_URL not found in {}".format(path), file=sys.stderr)
        sys.exit(1)
    path.write_text(text, encoding="utf-8")
    print("Patched for beta:", path, "BETA_CHANNEL_VERSION=", beta_version, "UPDATE_URL=", update_url)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "beta_version",
        nargs="?",
        default="2.0.0",
        help="BETA_CHANNEL_VERSION（表示・識別用の埋め込みバージョン文字列）",
    )
    p.add_argument(
        "--file",
        type=Path,
        default=None,
        help="constants_env.py のパス（既定: リポジトリの igo/constants_env.py）",
    )
    p.add_argument(
        "--update-url",
        default="https://goka-igo.com/version-beta.json",
        help="テスト版の起動時自動更新チェックURL",
    )
    args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    path = args.file or (root / "igo" / "constants_env.py")
    if not path.is_file():
        print("ERROR: not found:", path, file=sys.stderr)
        return 1
    patch(
        path,
        (args.beta_version or "2.0.0").strip() or "2.0.0",
        (args.update_url or "").strip() or "https://goka-igo.com/version-beta.json",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
