# -*- coding: utf-8 -*-
"""碁華 設定管理"""
import logging
import os
import sys
import json
import socket
import ctypes

from igo.constants import API_BASE_URL, APP_DATA_SUBDIR

logger = logging.getLogger(__name__)


def _get_app_data_dir():
    """Return writable app data directory (works in both dev and PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller exe: use %APPDATA%\GokaGo
        base = os.environ.get('APPDATA') or os.path.dirname(sys.executable)
        app_dir = os.path.join(base, APP_DATA_SUBDIR)
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
        server_board_h = server_settings.get("board_frame_height")
        server_match_h = server_settings.get("match_apply_height")
        server_challenge_h = server_settings.get("challenge_accept_height")
        server_sakura_h = server_settings.get("sakura_dialog_height")
        if server_fischer_main is not None:
            if cfg.get("fischer_main_time") != server_fischer_main:
                cfg["fischer_main_time"] = server_fischer_main
                changed = True
        if server_fischer_inc is not None:
            if cfg.get("fischer_increment") != server_fischer_inc:
                cfg["fischer_increment"] = server_fischer_inc
                changed = True
        if server_board_h is not None:
            if cfg.get("board_frame_height") != server_board_h:
                cfg["board_frame_height"] = server_board_h
                changed = True
        if server_match_h is not None:
            if cfg.get("match_apply_height") != server_match_h:
                cfg["match_apply_height"] = server_match_h
                changed = True
        if server_challenge_h is not None:
            if cfg.get("challenge_accept_height") != server_challenge_h:
                cfg["challenge_accept_height"] = server_challenge_h
                changed = True
        if server_sakura_h is not None:
            if cfg.get("sakura_dialog_height") != server_sakura_h:
                cfg["sakura_dialog_height"] = server_sakura_h
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


def get_ui_height_ratio(key: str, default_ratio: float) -> float:
    """Get UI height ratio from config.

    Accepts values like 0.9, 90, "90%". Returns clamped ratio [0.1, 1.0].
    """
    ratio = float(default_ratio)
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        raw = str(cfg.get(key, "")).strip()
        if raw:
            s = raw.replace(",", "").strip()
            if s.endswith("%"):
                s = s[:-1].strip()
            v = float(s)
            if v > 1.0:
                ratio = v / 100.0
            else:
                ratio = v
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        logger.debug("Failed to read %s, using default", key, exc_info=True)
    if ratio < 0.1:
        ratio = 0.1
    if ratio > 1.0:
        ratio = 1.0
    return ratio


def get_primary_work_area_rect():
    """Return (left, top, width, height) of primary work area on Windows."""
    if sys.platform != "win32":
        return None
    try:
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
        ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
        )
        if not ok:
            return None
        w = int(rect.right - rect.left)
        h = int(rect.bottom - rect.top)
        if w < 320 or h < 240:
            return None
        return int(rect.left), int(rect.top), w, h
    except Exception:
        return None

