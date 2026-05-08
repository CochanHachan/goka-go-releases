# -*- coding: utf-8 -*-
"""碁華 設定管理"""
import logging
import os
import sys
import json
import socket

from igo.constants import API_BASE_URL, APP_DATA_DIR_NAME

logger = logging.getLogger(__name__)

# サーバーから取得した設定をメモリにキャッシュ
_server_settings_cache = None


def _get_app_data_dir():
    """Return writable app data directory (works in both dev and PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller exe: use %APPDATA%\GokaGo (or GokaGoTest for beta)
        base = os.environ.get('APPDATA') or os.path.dirname(sys.executable)
        app_dir = os.path.join(base, APP_DATA_DIR_NAME)
    else:
        # Development: use script directory
        # __file__ is inside igo/, so go up one level
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def _get_install_dir():
    """Return the installation directory (where the exe or script is located)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fetch_server_settings():
    """サーバーから設定を取得してメモリにキャッシュする。"""
    global _server_settings_cache
    try:
        import urllib.request as _ur
        _req = _ur.Request(API_BASE_URL + "/api/settings")
        with _ur.urlopen(_req, timeout=5) as _resp:
            _server_settings_cache = json.loads(_resp.read().decode("utf-8"))
        logger.info("Server settings loaded: %s", _server_settings_cache)
    except Exception:
        logger.warning("Failed to fetch server settings", exc_info=True)
        _server_settings_cache = None


def _get_server_setting(key: str, default=None):
    """メモリキャッシュからサーバー設定値を取得する。未取得なら自動取得。"""
    if _server_settings_cache is None:
        _fetch_server_settings()
    if _server_settings_cache is None:
        return default
    val = _server_settings_cache.get(key)
    return val if val is not None else default


def _init_config_if_needed():
    """起動時にサーバーから設定を取得してメモリにキャッシュする。
    ローカル igo_config.json はテーマ・言語の保存にのみ使用。"""
    # サーバーから設定を取得（メモリキャッシュ）
    _fetch_server_settings()
    # ローカル config はテーマ・言語用に初期化だけしておく
    app_cfg = os.path.join(_get_app_data_dir(), "igo_config.json")
    if not os.path.exists(app_cfg):
        install_cfg = os.path.join(_get_install_dir(), "igo_config.json")
        if os.path.exists(install_cfg):
            try:
                import shutil
                shutil.copy2(install_cfg, app_cfg)
            except OSError:
                logger.warning("Failed to copy config from install dir", exc_info=True)
        else:
            try:
                default_cfg = {"theme": "light", "language": "ja"}
                with open(app_cfg, "w", encoding="utf-8") as f:
                    json.dump(default_cfg, f, ensure_ascii=False, indent=2)
            except OSError:
                logger.warning("Failed to create default config", exc_info=True)
    # テーマをサーバーから反映
    server_theme = _get_server_setting("theme")
    if server_theme and server_theme in ("dark", "light"):
        try:
            cfg = {}
            if os.path.exists(app_cfg):
                with open(app_cfg, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            if cfg.get("theme") != server_theme:
                cfg["theme"] = server_theme
                with open(app_cfg, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
        except (OSError, json.JSONDecodeError):
            logger.debug("Failed to update theme in local config", exc_info=True)


def _get_db_path():
    """Get database path from config, or default to app data directory."""
    script_dir = _get_app_data_dir()
    try:
        # Try app data dir first, then installation dir
        cfg_path = os.path.join(script_dir, "igo_config.json")
        if not os.path.exists(cfg_path):
            cfg_path = os.path.join(_get_install_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        p = cfg.get("db_path", "")
        if p:
            # For UNC paths, do a quick socket check instead of os.path.isdir
            if p.startswith("\\\\"):
                # Extract hostname from \\hostname\share\...
                parts = p.replace("\\\\", "").split("\\")
                host = parts[0] if parts else ""
                if host:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.5)
                        s.connect((host, 445))  # SMB port
                        s.close()
                        return p
                    except OSError:
                        logger.debug("UNC path check failed for %s", p, exc_info=True)
                print("[WARN] db_path not accessible: {} -> using local DB".format(p))
            else:
                # Local path - just check directly
                if os.path.exists(os.path.dirname(p)):
                    return p
                print("[WARN] db_path not accessible: {} -> using local DB".format(p))
    except (OSError, json.JSONDecodeError, KeyError, AttributeError):
        logger.warning("Failed to read db_path from config", exc_info=True)
    return os.path.join(script_dir, "igo_users.db")


def get_primary_work_area_rect():
    """Return (left, top, width, height) of the primary monitor work area, or None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = (
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            )

        rect = RECT()
        SPI_GETWORKAREA = 48
        if not ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return None
        left = int(rect.left)
        top = int(rect.top)
        w = int(rect.right - rect.left)
        h = int(rect.bottom - rect.top)
        if w >= 320 and h >= 240:
            return (left, top, w, h)
    except Exception:
        pass
    return None


def get_ui_height_ratio(key: str, default: float = 0.5) -> float:
    """サーバー設定から UI 高さ比率を取得する。"""
    val = _get_server_setting(key)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return default


def get_ui_width_ratio(key: str, default: float = 0.5) -> float:
    """サーバー設定から UI 横幅比率を取得する。"""
    val = _get_server_setting(key)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return default


def get_offer_timeout_ms():
    """サーバー設定から対局申込タイムアウト（ミリ秒）を取得する。"""
    val = _get_server_setting("offer_timeout_min")
    if val is not None:
        try:
            return max(1, int(val)) * 60 * 1000
        except (ValueError, TypeError):
            pass
    return 180000


def get_fischer_settings():
    """サーバー設定からフィッシャー時間設定を取得する。
    Returns (main_time_seconds, increment_seconds). Default: (300, 10)."""
    main_t = _get_server_setting("fischer_main_time")
    inc = _get_server_setting("fischer_increment")
    try:
        m = max(60, int(main_t)) if main_t is not None else 300
        i = max(1, int(inc)) if inc is not None else 10
        return (m, i)
    except (ValueError, TypeError):
        return (300, 10)

