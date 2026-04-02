# -*- coding: utf-8 -*-
"""碁華 設定管理"""
import os
import sys
import json
import socket

from igo.constants import API_BASE_URL


def _get_app_data_dir():
    """Return writable app data directory (works in both dev and PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller exe: use %APPDATA%\GokaGo
        base = os.environ.get('APPDATA') or os.path.dirname(sys.executable)
        app_dir = os.path.join(base, 'GokaGo')
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
            except Exception:
                pass
        else:
            # Create default config
            try:
                default_cfg = {"theme": "light", "language": "ja"}
                with open(app_cfg, "w", encoding="utf-8") as f:
                    json.dump(default_cfg, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
    # Fetch theme from server and apply locally
    try:
        import urllib.request as _ur
        _req = _ur.Request(API_BASE_URL + "/api/settings")
        with _ur.urlopen(_req, timeout=3) as _resp:
            server_settings = json.loads(_resp.read().decode("utf-8"))
        server_theme = server_settings.get("theme")
        if server_theme and server_theme in ("dark", "light"):
            cfg = {}
            if os.path.exists(app_cfg):
                with open(app_cfg, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            if cfg.get("theme") != server_theme:
                cfg["theme"] = server_theme
                with open(app_cfg, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Server unreachable, use local config


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
                    except Exception:
                        pass
                print("[WARN] db_path not accessible: {} -> using local DB".format(p))
            else:
                # Local path - just check directly
                if os.path.exists(os.path.dirname(p)):
                    return p
                print("[WARN] db_path not accessible: {} -> using local DB".format(p))
    except Exception:
        pass
    return os.path.join(script_dir, "igo_users.db")


def get_offer_timeout_ms():
    """Get match offer timeout in milliseconds from config (default 180000 = 3 min)."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        minutes = int(cfg.get("offer_timeout_min", 3))
        return max(1, minutes) * 60 * 1000
    except Exception:
        return 180000
