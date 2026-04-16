# -*- coding: utf-8 -*-
"""碁華 秒読み音声再生（多言語対応）

言語ごとのプレフィックス:
  ja → J / JP    en → E / EP    zh → C / CP    ko → K / KP

再生ルール（秒読みフェーズのみ）:
  秒読み開始時     → {prefix}ByoyomiStart.wav
  60〜10秒(10秒刻み) → {prefix}{sec}sec.wav
  9〜1秒           → {prefix}P{sec:02d}c.wav
  0秒 (時間切れ)   → {prefix}TimeOut.wav
"""
import logging
import os
import sys
import threading

from igo.config import _get_install_dir
from igo.lang import get_language

_logger = logging.getLogger(__name__)


# pygame.mixer を遅延初期化
_mixer_ready = False
_sound_dir = None

def _init_mixer():
    """pygame.mixer を初期化する（初回のみ）。"""
    global _mixer_ready, _sound_dir
    if _mixer_ready:
        return True
    try:
        import pygame
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        _mixer_ready = True
    except Exception as e:
        _logger.warning("mixer init failed: %s", e, exc_info=True)
        return False

    # sounds/ フォルダを探す
    # PyInstaller onefile/onedir では _MEIPASS(_internal) 配下に展開される場合がある。
    meipass = getattr(sys, "_MEIPASS", None)
    search_dirs = [d for d in [
        meipass,
        _get_install_dir(),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ] if d]
    for d in search_dirs:
        candidate = os.path.join(d, "sounds")
        if os.path.isdir(candidate):
            _sound_dir = candidate
            break
    return True


# 言語コード → 音声ファイルプレフィックス
_LANG_PREFIX = {"ja": "J", "en": "E", "zh": "C", "ko": "K"}
_LANG_PREFIX_P = {"ja": "JP", "en": "EP", "zh": "CP", "ko": "KP"}


def _prefix():
    return _LANG_PREFIX.get(get_language(), "J")


def _prefix_p():
    return _LANG_PREFIX_P.get(get_language(), "JP")


def play_byoyomi_start():
    """秒読み開始音声を再生する。"""
    filename = "{}ByoyomiStart.wav".format(_prefix())
    threading.Thread(target=_play, args=(filename,), daemon=True).start()


def play_byoyomi_sound(remaining_seconds):
    """秒読み残り秒数に応じて音声を再生する。"""
    filename = _seconds_to_filename(remaining_seconds)
    if not filename:
        return
    threading.Thread(target=_play, args=(filename,), daemon=True).start()


def play_timeout_sound():
    """時間切れ音声を再生する。"""
    filename = "{}TimeOut.wav".format(_prefix())
    threading.Thread(target=_play, args=(filename,), daemon=True).start()


def play_challenge_arrived():
    """挑戦状受信時に通知音を再生する。"""
    threading.Thread(target=_play_challenge_arrived_direct, daemon=True).start()


def _play_challenge_arrived_direct():
    """J03sec.wav を pygame 公開APIで直接再生する。"""
    try:
        if not _init_mixer():
            return
        path = _resolve_sound_path("J03sec.wav")
        if path:
            import pygame
            pygame.mixer.Sound(path).play()
        else:
            _logger.warning("sound file not found: %s (sound_dir=%s)", "J03sec.wav", _sound_dir)
    except Exception as e:
        _logger.warning("challenge sound play failed: %s", e, exc_info=True)


def play_robot_appear_localized():
    """ロボ挑戦受信時に言語別の robot_appear 音声を再生する。"""
    lang = get_language()
    prefix = {"ja": "J", "en": "E", "zh": "C", "ko": "K"}.get(lang, "J")
    threading.Thread(
        target=_play_robot_appear_localized_direct,
        args=(prefix,),
        daemon=True,
    ).start()


def _play_robot_appear_localized_direct(prefix):
    """{prefix}robot_appear.wav を _play 経由なしで再生する。"""
    try:
        if not _init_mixer():
            return
        if not _sound_dir:
            return
        filename = "{}robot_appear.wav".format(prefix)
        path = os.path.join(_sound_dir, filename)
        if not os.path.exists(path):
            _logger.warning("sound file not found: %s (sound_dir=%s)", filename, _sound_dir)
            return
        import pygame
        pygame.mixer.Sound(path).play()
    except Exception as e:
        _logger.warning("robot appear sound failed: %s", e, exc_info=True)


def _seconds_to_filename(sec):
    """残り秒数に対応するファイル名を返す。該当なしならNone。"""
    # 10秒刻み（単位付き）: 60, 50, 40, 30, 20, 10
    if sec in (60, 50, 40, 30, 20, 10):
        return "{}{:02d}sec.wav".format(_prefix(), sec)
    # 9〜1秒（数字のみ）
    if 1 <= sec <= 9:
        return "{}{:02d}c.wav".format(_prefix_p(), sec)
    # 時間切れ
    if sec <= 0:
        return "{}TimeOut.wav".format(_prefix())
    return None


def _play(filename):
    """実際の再生処理（スレッド内で実行）。

    秒読み・SE は短いクリップが多いため、グローバルに1曲しか再生できない
    `mixer.music` ではなく `mixer.Sound` を使う（WAV 前提）。
    """
    try:
        if not _init_mixer():
            return
        path = _resolve_sound_path(filename)
        if path:
            _play_sound(path)
        else:
            _logger.warning("sound file not found: %s (sound_dir=%s)", filename, _sound_dir)
    except Exception as e:
        _logger.warning("play error: %s %s", filename, e, exc_info=True)


def _resolve_sound_path(filename):
    """ファイル名からフルパスを返す。存在しなければ None。"""
    if not _sound_dir:
        return None
    path = os.path.join(_sound_dir, filename)
    if os.path.exists(path):
        return path
    return None


def _play_sound(path):
    try:
        import pygame
        sound = pygame.mixer.Sound(path)
        sound.play()
    except Exception as e:
        _logger.warning("sound play failed: %s %s", path, e, exc_info=True)
