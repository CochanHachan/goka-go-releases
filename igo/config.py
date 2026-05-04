# -*- coding: utf-8 -*-
"""碁華 設定管理"""
import logging
import os
import sys
import json
import socket

from igo.constants import API_BASE_URL, APP_DATA_DIR_NAME

logger = logging.getLogger(__name__)


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


def _init_config_if_needed():
    """On first run, copy igo_config.json from install dir to app data dir.
    Also fetch theme from server if available."""
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
            # Create default config
            try:
                default_cfg = {"theme": "light", "language": "ja"}
                with open(app_cfg, "w", encoding="utf-8") as f:
                    json.dump(default_cfg, f, ensure_ascii=False, indent=2)
            except OSError:
                logger.warning("Failed to create default config", exc_info=True)
    # Fetch theme from server and apply locally
    try:
        import urllib.request as _ur
        _req = _ur.Request(API_BASE_URL + "/api/settings")
        with _ur.urlopen(_req, timeout=3) as _resp:
            server_settings = json.loads(_resp.read().decode("utf-8"))
        server_theme = server_settings.get("theme")
        server_timeout = server_settings.get("offer_timeout_min")
        cfg = {}
        if os.path.exists(app_cfg):
            with open(app_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        changed = False
        if server_theme and server_theme in ("dark", "light"):
            if cfg.get("theme") != server_theme:
                cfg["theme"] = server_theme
                changed = True
        if server_timeout is not None:
            if cfg.get("offer_timeout_min") != server_timeout:
                cfg["offer_timeout_min"] = server_timeout
                changed = True
        server_fischer_main = server_settings.get("fischer_main_time")
        server_fischer_inc = server_settings.get("fischer_increment")
        if server_fischer_main is not None:
            if cfg.get("fischer_main_time") != server_fischer_main:
                cfg["fischer_main_time"] = server_fischer_main
                changed = True
        if server_fischer_inc is not None:
            if cfg.get("fischer_increment") != server_fischer_inc:
                cfg["fischer_increment"] = server_fischer_inc
                changed = True
        if changed:
            with open(app_cfg, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
    except (OSError, ValueError, KeyError, AttributeError):
        logger.debug("Server unreachable, using local config", exc_info=True)


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
    """Get a UI height ratio from config. Returns default if not set."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        val = cfg.get(key)
        if val is not None:
            return float(val)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        logger.debug("Failed to read %s, using default", key, exc_info=True)
    return default


def get_ui_width_ratio(key: str, default: float = 0.5) -> float:
    """Get a UI width ratio from config. Returns default if not set."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        val = cfg.get(key)
        if val is not None:
            return float(val)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        logger.debug("Failed to read %s, using default", key, exc_info=True)
    return default


def get_offer_timeout_ms():
    """Get match offer timeout in milliseconds from config (default 180000 = 3 min)."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        minutes = int(cfg.get("offer_timeout_min", 3))
        return max(1, minutes) * 60 * 1000
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        logger.debug("Failed to read offer_timeout, using default", exc_info=True)
        return 180000

def get_fischer_settings():
    """Get Fischer time control settings from config.
    Returns (main_time_seconds, increment_seconds). Default: (300, 10)."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        main_t = int(cfg.get("fischer_main_time", 300))
        inc = int(cfg.get("fischer_increment", 10))
        return (max(60, main_t), max(1, inc))
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        logger.debug("Failed to read fischer settings, using defaults", exc_info=True)
        return (300, 10)

