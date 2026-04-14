# -*- coding: utf-8 -*-
"""碁華 秒読み音声再生（多言語対応）

言語ごとのプレフィックス:
  ja → J / JP    en → E / EP    zh → C / CP    ko → K / KP

再生ルール（秒読みフェーズのみ）:
  秒読み開始時     → {prefix}ByoyomiStart.mp3
  60〜10秒(10秒刻み) → {prefix}{sec}sec.mp3
  9〜1秒           → {prefix}P{sec:02d}c.mp3
  0秒 (時間切れ)   → {prefix}TimeOut.mp3
"""
import logging
import os
import threading

from igo.config import _get_install_dir
from igo.lang import get_language

_logger = logging.getLogger(__name__)


# pygame.mixer を遅延初期化
_mixer_ready = False
_sound_dir = None

# 再生ファイルのキャッシュ
_cache = {}


def _init_mixer():
    """pygame.mixer を初期化する（初回のみ）。"""
    global _mixer_ready, _sound_dir
    if _mixer_ready:
        return True
    try:
        import pygame
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        _mixer_ready = True
    except (ImportError, OSError, RuntimeError) as e:
        _logger.warning("mixer init failed: %s", e, exc_info=True)
        return False

    # sounds/ フォルダを探す
    for d in [_get_install_dir(),
              os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]:
        candidate = os.path.join(d, "sounds")
        if os.path.isdir(candidate):
            _sound_dir = candidate
            break
    return True


def _get_sound(filename):
    """ファイル名からpygame.mixer.Soundを取得（キャッシュ付き）。"""
    if filename in _cache:
        return _cache[filename]
    if not _sound_dir:
        return None
    path = os.path.join(_sound_dir, filename)
    if not os.path.exists(path):
        return None
    try:
        import pygame
        snd = pygame.mixer.Sound(path)
        _cache[filename] = snd
        return snd
    except (ImportError, OSError, RuntimeError) as e:
        _logger.warning("sound load failed: %s %s", filename, e, exc_info=True)
        return None


# 言語コード → 音声ファイルプレフィックス
_LANG_PREFIX = {"ja": "J", "en": "E", "zh": "C", "ko": "K"}
_LANG_PREFIX_P = {"ja": "JP", "en": "EP", "zh": "CP", "ko": "KP"}


def _prefix():
    return _LANG_PREFIX.get(get_language(), "J")


def _prefix_p():
    return _LANG_PREFIX_P.get(get_language(), "JP")


def play_byoyomi_start():
    """秒読み開始音声を再生する。"""
    filename = "{}ByoyomiStart.mp3".format(_prefix())
    threading.Thread(target=_play, args=(filename,), daemon=True).start()


def play_byoyomi_sound(remaining_seconds):
    """秒読み残り秒数に応じて音声を再生する。"""
    filename = _seconds_to_filename(remaining_seconds)
    if not filename:
        return
    threading.Thread(target=_play, args=(filename,), daemon=True).start()


def play_timeout_sound():
    """時間切れ音声を再生する。"""
    filename = "{}TimeOut.mp3".format(_prefix())
    threading.Thread(target=_play, args=(filename,), daemon=True).start()


def play_robot_appear():
    """ロボ出現時の音声を再生する。"""
    threading.Thread(target=_play, args=("robot_appear.mp3",), daemon=True).start()


def _seconds_to_filename(sec):
    """残り秒数に対応するファイル名を返す。該当なしならNone。"""
    # 10秒刻み（単位付き）: 60, 50, 40, 30, 20, 10
    if sec in (60, 50, 40, 30, 20, 10):
        return "{}{:02d}sec.mp3".format(_prefix(), sec)
    # 9〜1秒（数字のみ）
    if 1 <= sec <= 9:
        return "{}{:02d}c.mp3".format(_prefix_p(), sec)
    # 時間切れ
    if sec <= 0:
        return "{}TimeOut.mp3".format(_prefix())
    return None


def _play(filename):
    """実際の再生処理（スレッド内で実行）。"""
    try:
        if not _init_mixer():
            return
        snd = _get_sound(filename)
        if snd:
            snd.play()
    except (ImportError, OSError, RuntimeError) as e:
        _logger.warning("play error: %s %s", filename, e, exc_info=True)
