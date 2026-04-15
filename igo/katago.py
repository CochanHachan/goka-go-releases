# -*- coding: utf-8 -*-
"""碁華 KataGo AI エンジン"""
import logging
import os
import platform
import subprocess
import threading
import json
import math
import time as _time

from igo.constants import BLACK, WHITE, EMPTY
from igo.config import _get_install_dir

logger = logging.getLogger(__name__)


class KataGoGTP:
    """KataGo GTP process for AI games."""

    def __init__(self, visits=50, human_profile="", human_lambda=100000000, fallback_visits=None):
        self.visits = visits
        self.human_profile = human_profile
        self.human_lambda = human_lambda
        self.fallback_visits = fallback_visits if fallback_visits is not None else visits
        self.proc = None
        self._lock = threading.Lock()

    def start(self):
        """Start KataGo GTP process."""
        katago_dir = os.path.join(_get_install_dir(), "katago")
        _exe = "katago.exe" if platform.system() == "Windows" else "katago"
        katago_exe = os.path.join(katago_dir, _exe)
        model_file = os.path.join(katago_dir, "model.bin")
        human_model_file = os.path.join(katago_dir, "human_model.bin")
        config_file = os.path.join(katago_dir, "default_gtp.cfg")

        if not os.path.exists(katago_exe):
            raise RuntimeError("KataGoが見つかりません: " + katago_exe)
        if not os.path.exists(model_file):
            raise RuntimeError("モデルファイルが見つかりません: " + model_file)
        if not os.path.exists(config_file):
            # default_gtp.cfg が存在しない場合は最小限の設定で自動生成する
            logger.warning("default_gtp.cfg not found at %s — creating minimal config", config_file)
            try:
                minimal_cfg = (
                    "# Goka Go GTP config (auto-generated)\n"
                    "logToStderr = true\n"
                    "logSearchInfo = false\n"
                    "numSearchThreads = 1\n"
                    "ponderingEnabled = false\n"
                    "reportAnalysisWinratesAs = BLACK\n"
                )
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(minimal_cfg)
            except OSError as e:
                raise RuntimeError("default_gtp.cfg の生成に失敗しました: {}".format(e))

        use_human = (self.human_profile
                     and os.path.exists(human_model_file))
        if self.human_profile and not os.path.exists(human_model_file):
            logger.warning(
                "human_model.bin not found at %s — falling back to standard mode "
                "(visits: %d → %d)",
                human_model_file, self.visits, self.fallback_visits,
            )

        if use_human:
            override = (
                "maxVisits={},numSearchThreads=1,ponderingEnabled=false,"
                "humanSLProfile={},"
                "humanSLChosenMoveProp=1.0,"
                "humanSLChosenMoveIgnorePass=true,"
                "humanSLChosenMovePiklLambda={},"
                "allowResignation=true,"
                "resignThreshold=-0.99,"
                "resignConsecTurns=20,"
                "resignMinScoreDifference=40"
            ).format(self.visits, self.human_profile, self.human_lambda)
            cmd = [
                katago_exe, "gtp",
                "-config", config_file,
                "-model", model_file,
                "-human-model", human_model_file,
                "-override-config", override,
            ]
        else:
            effective_visits = self.fallback_visits if self.human_profile else self.visits
            override = "maxVisits={},numSearchThreads=1,ponderingEnabled=false".format(
                effective_visits)
            cmd = [
                katago_exe, "gtp",
                "-config", config_file,
                "-model", model_file,
                "-override-config", override,
            ]
        logger.info("KataGo start: human_profile=%s, visits=%d, use_human=%s",
                    self.human_profile, self.visits, use_human)

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=katago_dir,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )

        # KataGo GTPモードのstderrをバックグラウンドで読み捨てつつログに記録する。
        # stderr=DEVNULL だとKataGoが起動失敗しても原因が全くわからないため、
        # パイプで受け取ゃてファイルに記録する。
        self._stderr_lines = []

        def _drain_gtp_stderr():
            try:
                for raw in self.proc.stderr:
                    self._stderr_lines.append(raw)
            except OSError:
                pass
            # プロセスき終了時にログに書き出す
            if self._stderr_lines:
                try:
                    log_path = os.path.join(os.path.expanduser("~"), "goka_katago_gtp_log.txt")
                    with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                        from datetime import datetime
                        f.write("\n--- KataGo GTP stderr {} ---\n".format(
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        for line in self._stderr_lines:
                            f.write(line.decode("utf-8", errors="replace"))
                except OSError:
                    pass

        threading.Thread(target=_drain_gtp_stderr, daemon=True).start()

    def send_command(self, cmd):
        """Send a GTP command and return the response."""
        if not self.proc or self.proc.poll() is not None:
            # プロセスが死んでいる場合はGTPログに記録
            exit_code = self.proc.poll() if self.proc else None
            logger.warning("GTP send_command skipped (proc dead, exit=%s): %s", exit_code, cmd)
            return None
        with self._lock:
            try:
                self.proc.stdin.write((cmd + "\n").encode("utf-8"))
                self.proc.stdin.flush()
                response_lines = []
                while True:
                    line = self.proc.stdout.readline().decode("utf-8")
                    if line.strip() == "" and response_lines:
                        break
                    if line == "":
                        break
                    response_lines.append(line.strip())
                return "\n".join(response_lines)
            except (OSError, BrokenPipeError, ValueError):
                logger.warning("GTP send_command failed: %s", cmd, exc_info=True)
                return None
