# -*- coding: utf-8 -*-
"""碁華 テーマシステム"""
import logging
import os
import json

from igo.config import _get_app_data_dir
from igo.lang import set_language, get_language

logger = logging.getLogger(__name__)

THEMES = {
    "dark": {
        # Background
        "root_bg":          "#1a1a1a",
        "container_bg":     "#1e1e1e",
        "input_bg":         "#2a2a2a",
        "button_bg":        "#3a3a3a",
        "hover_bg":         "#4a4a4a",
        # Text
        "text_primary":     "#e0e0e0",
        "text_secondary":   "#cccccc",
        "text_disabled":    "#888888",
        # Accent
        "accent_gold":      "#DCB35C",
        "accent_gold_active": "#c9a84e",
        "accent_green":     "#4CAF50",
        "accent_green_active": "#45a049",
        "accent_red":       "#882222",
        "accent_red_active": "#aa3333",
        "error_red":        "#FF4444",
        "active_green":     "#00FF88",
        "link_blue":        "#7799CC",
        # Border
        "border":           "#555555",
        "grid_line":        "#333333",
        "separator":        "#444444",
        "board_outline":    "#9B7B3C",
        # Toolbar
        "toolbar_bg":       "#f0f0f0",
        "toolbar_fg":       "#333333",
        "toolbar_hover":    "#d0d0d0",
        "toolbar_separator": "#cccccc",
        # Selection / panel
        "select_bg":        "#4a4a4a",
        "select_fg":        "#e0e0e0",
        "panel_highlight":  "#DCB35C",
        "panel_inactive":   "#555555",
        # Combobox
        "combo_field_bg":   "#2a2a2a",
        "combo_arrow_bg":   "#3a3a3a",
        "combo_list_bg":    "#2a2a2a",
        "combo_list_fg":    "#e0e0e0",
        "combo_list_select_bg": "#DCB35C",
        "combo_list_select_fg": "#1a1a1a",
        # Timer
        "timer_active":     "#00FF88",
        "timer_inactive":   "#cccccc",
        "timer_byoyomi":    "#FF4444",
        # RGB tuples (for stone rendering)
        "panel_bg_rgb":     (30, 30, 30),
        "board_bg_rgb":     (244, 206, 120),
        # Player panel
        "rank_fg":          "#999999",
        "cap_fg":           "#888888",
        # Overlay text
        "overlay_gold":     "#DCB35C",
        "overlay_red":      "red",
        # Delete button
        "delete_bg":        "#882222",
        "delete_fg":        "#e0e0e0",
        "delete_active":    "#aa3333",
    },
    "light": {
        # Background
        "root_bg":          "#f5f5f5",
        "container_bg":     "#ffffff",
        "input_bg":         "#e8e8e8",
        "button_bg":        "#d8d8d8",
        "hover_bg":         "#c8c8c8",
        # Text
        "text_primary":     "#1a1a1a",
        "text_secondary":   "#555555",
        "text_disabled":    "#999999",
        # Accent
        "accent_gold":      "#DCB35C",
        "accent_gold_active": "#c9a84e",
        "accent_green":     "#4CAF50",
        "accent_green_active": "#45a049",
        "accent_red":       "#882222",
        "accent_red_active": "#aa3333",
        "error_red":        "#CC0000",
        "active_green":     "#008844",
        "link_blue":        "#3366AA",
        # Border
        "border":           "#cccccc",
        "grid_line":        "#333333",
        "separator":        "#cccccc",
        "board_outline":    "#9B7B3C",
        # Toolbar
        "toolbar_bg":       "#e8e8e8",
        "toolbar_fg":       "#333333",
        "toolbar_hover":    "#d0d0d0",
        "toolbar_separator": "#bbbbbb",
        # Selection / panel
        "select_bg":        "#c8c8c8",
        "select_fg":        "#1a1a1a",
        "panel_highlight":  "#DCB35C",
        "panel_inactive":   "#cccccc",
        # Combobox
        "combo_field_bg":   "#e8e8e8",
        "combo_arrow_bg":   "#d8d8d8",
        "combo_list_bg":    "#ffffff",
        "combo_list_fg":    "#1a1a1a",
        "combo_list_select_bg": "#DCB35C",
        "combo_list_select_fg": "#1a1a1a",
        # Timer
        "timer_active":     "#008844",
        "timer_inactive":   "#555555",
        "timer_byoyomi":    "#CC0000",
        # RGB tuples (for stone rendering)
        "panel_bg_rgb":     (255, 255, 255),
        "board_bg_rgb":     (244, 206, 120),
        # Player panel
        "rank_fg":          "#777777",
        "cap_fg":           "#999999",
        # Overlay text
        "overlay_gold":     "#DCB35C",
        "overlay_red":      "#CC0000",
        # Delete button
        "delete_bg":        "#CC4444",
        "delete_fg":        "#ffffff",
        "delete_active":    "#aa3333",
    },
}

_current_theme = THEMES["light"]  # module-level default


def _load_theme_from_config():
    """Load theme setting from igo_config.json."""
    global _current_theme
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        name = cfg.get("theme", "light")
        if name in THEMES:
            _current_theme = THEMES[name]
    except (OSError, json.JSONDecodeError, KeyError):
        logger.warning("Failed to load theme from config", exc_info=True)


def T(key):
    """Shorthand to get a theme color value."""
    return _current_theme[key]


def get_current_theme_name():
    """Return current theme name ('dark' or 'light')."""
    for name, theme in THEMES.items():
        if theme is _current_theme:
            return name
    return "dark"


def _load_language_from_config():
    """Load language setting from igo_config.json."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        lang = cfg.get("language", "ja")
        set_language(lang)
    except (OSError, json.JSONDecodeError, KeyError):
        logger.warning("Failed to load language from config", exc_info=True)


def _save_language_to_config(lang):
    """Save language setting to igo_config.json."""
    try:
        cfg_path = os.path.join(_get_app_data_dir(), "igo_config.json")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.debug("No existing config, creating new", exc_info=True)
            cfg = {}
        cfg["language"] = lang
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        logger.warning("Failed to save language to config", exc_info=True)
