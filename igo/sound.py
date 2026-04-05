# -*- coding: utf-8 -*-
"""碁華 着手音"""
import os
import platform

from igo.config import _get_install_dir


_stone_sound_path = None


def _find_stone_sound():
    """stone_click.wav のパスを返す。"""
    global _stone_sound_path
    if _stone_sound_path and os.path.exists(_stone_sound_path):
        return _stone_sound_path
    # インストール先 or スクリプトと同じフォルダを探す
    for d in [_get_install_dir(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]:
        p = os.path.join(d, "stone_click.wav")
        if os.path.exists(p):
            _stone_sound_path = p
            return p
    return None


def _play_stone_sound():
    """着手音を非同期で再生する。"""
    try:
        if platform.system() != "Windows":
            return
        import winsound
        path = _find_stone_sound()
        if path:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass

