# -*- coding: utf-8 -*-
"""碁華 (Goka GO) - パッケージ初期化"""
import logging as _logging
import os as _os

# ファイルログ設定 — 例外の握りつぶしをなくし、問題を可視化する
from igo.constants import APP_DATA_DIR_NAME as _APP_DATA_DIR_NAME
_log_dir = _os.path.join(
    _os.environ.get("APPDATA") or _os.path.expanduser("~"),
    _APP_DATA_DIR_NAME,
)
try:
    _os.makedirs(_log_dir, exist_ok=True)
except OSError:
    _log_dir = None  # fallback: no file logging

if _log_dir:
    _log_path = _os.path.join(_log_dir, "goka_debug.log")
    _logging.basicConfig(
        level=_logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            _logging.FileHandler(_log_path, encoding="utf-8", delay=True),
        ],
    )
