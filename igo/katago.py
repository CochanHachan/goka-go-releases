# -*- coding: utf-8 -*-
"""ç¢è¯ KataGo AI ã¨ã³ã¸ã³"""
import logging
import os
import platform
import subprocess
import threading
import json
import math
import time as _time
import queue as _queue

from igo.constants import BLACK, WHITE, EMPTY, APP_DATA_DIR_NAME
from igo.config import _get_install_dir

logger = logging.getLogger(__name__)


def _katago_home_data_dir():
    """Return a writable directory for KataGo cached data (OpenCL tuning, etc.).

    KataGo defaults to writing under DIR/KataGoData next to katago.exe, but that
    can be problematic on Windows (install dir permissions, OneDrive paths).
    KataGo supports overriding via config key `homeDataDir` (also via
    `-override-config homeDataDir=...`).
    """
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", "") or os.path.expanduser("~")
        data_dir = os.path.join(base, APP_DATA_DIR_NAME, "katago")
    else:
        data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", APP_DATA_DIR_NAME, "katago")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        # Fall back to install dir behavior if we cannot create the directory.
        return ""
    # KataGo accepts forward slashes on Windows too; avoids escaping issues.
    return data_dir.replace("\\", "/")


class KataGoGTP:
    """KataGo GTP process for AI games."""

    def __init__(self, visits=50, human_profile="", human_lambda=100000000, fallback_visits=None):
        self.visits = visits
        self.human_profile = human_profile
        self.human_lambda = human_lambda
        self.fallback_visits = fallback_visits if fallback_visits is not None else visits
        self.proc = None
        self._lock = threading.Lock()
        self._stdout_q = _queue.Queue()
        self._gtp_log_path = os.path.join(os.path.expanduser("~"), "goka_katago_gtp_log.txt")
        # OpenCL autotuning detection (stderr) — KataGo prints e.g. "Performing autotuning..."
        self._opencl_autotune_in_progress = False
        self._opencl_tuning_lock = threading.Lock()
        # Optional: invoked from stderr reader thread with event name (use root.after in UI).
        self._stderr_status_callback = None

    def _append_gtp_log(self, text):
        try:
            with open(self._gtp_log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(text + "\n")
        except OSError:
            pass

    def start(self):
        """Start KataGo GTP process."""
        katago_dir = os.path.join(_get_install_dir(), "katago")
        _exe = "katago.exe" if platform.system() == "Windows" else "katago"
        katago_exe = os.path.join(katago_dir, _exe)
        model_file = os.path.join(katago_dir, "model.bin")
        human_model_file = os.path.join(katago_dir, "human_model.bin")
        config_file = os.path.join(katago_dir, "default_gtp.cfg")

        if not os.path.exists(katago_exe):
            raise RuntimeError("KataGoãè¦ã¤ããã¾ãã: " + katago_exe)
        if not os.path.exists(model_file):
            raise RuntimeError("ã¢ãã«ãã¡ã¤ã«ãè¦ã¤ããã¾ãã: " + model_file)
        if not os.path.exists(config_file):
            # default_gtp.cfg ãå­å¨ããªãå ´åã¯æå°éã®è¨­å®ã§èªåçæãã
            logger.warning("default_gtp.cfg not found at %s â creating minimal config", config_file)
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
                raise RuntimeError("default_gtp.cfg ã®çæã«å¤±æãã¾ãã: {}".format(e))

        use_human = (self.human_profile
                     and os.path.exists(human_model_file))
        if self.human_profile and not os.path.exists(human_model_file):
            logger.warning(
                "human_model.bin not found at %s â falling back to standard mode "
                "(visits: %d â %d)",
                human_model_file, self.visits, self.fallback_visits,
            )

        home_data = _katago_home_data_dir()
        home_cfg = ("homeDataDir={}".format(home_data) if home_data else "")

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
            if home_cfg:
                override = home_cfg + "," + override
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
            if home_cfg:
                override = home_cfg + "," + override
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

        from datetime import datetime
        self._append_gtp_log(
            "--- KataGo session {} ---".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        self._append_gtp_log("cmd: {}".format(" ".join(cmd)))

        # stdout を別スレッドで読み取り、send_command 側はキューから取得する。
        # readline() の無期限ブロックを避けるため。
        def _drain_gtp_stdout():
            try:
                for raw in self.proc.stdout:
                    try:
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    except Exception:
                        line = ""
                    self._stdout_q.put(line)
            except OSError:
                pass
            finally:
                # 終端マーカー
                self._stdout_q.put(None)

        threading.Thread(target=_drain_gtp_stdout, daemon=True).start()

        # KataGo GTPã¢ã¼ãã®stderrãããã¯ã°ã©ã¦ã³ãã§èª­ã¿æ¨ã¦ã¤ã¤ã­ã°ã«è¨é²ããã
        # stderr=DEVNULL ã ã¨KataGoãèµ·åå¤±æãã¦ãåå ãå¨ãããããªãããã
        # ãã¤ãã§åãåã£ã¦ãã¡ã¤ã«ã«è¨é²ããã
        self._stderr_lines = []

        def _drain_gtp_stderr():
            try:
                for raw in self.proc.stderr:
                    self._stderr_lines.append(raw)
                    try:
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    except Exception:
                        line = "<decode-error>"
                    self._append_gtp_log("[stderr] {}".format(line))
                    low = line.lower()
                    ev = None
                    with self._opencl_tuning_lock:
                        if "performing autotuning" in low:
                            self._opencl_autotune_in_progress = True
                            ev = "opencl_autotune_start"
                        if "done tuning" in low:
                            self._opencl_autotune_in_progress = False
                            ev = "opencl_autotune_done"
                    cb = self._stderr_status_callback
                    if ev and cb:
                        try:
                            cb(ev)
                        except Exception:
                            pass
            except OSError:
                pass
            # ãã­ã»ã¹çµäºæã«ã­ã°ã«æ¸ãåºã
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

    def set_stderr_status_callback(self, callback):
        """stderr 解析用コールバック。別スレッドから呼ばれるため UI 更新は root.after 等で委譲すること。

        callback(event: str) — event は "opencl_autotune_start" / "opencl_autotune_done"
        """
        self._stderr_status_callback = callback

    def is_opencl_autotuning(self):
        with self._opencl_tuning_lock:
            return bool(self._opencl_autotune_in_progress)

    def send_command(self, cmd, timeout_s=None):
        """Send a GTP command and return the response.

        timeout_s: 応答終端(= / ?)を待つ最大秒数。タイムアウト時は None。
        """
        if not self.proc or self.proc.poll() is not None:
            # ãã­ã»ã¹ãæ­»ãã§ããå ´åã¯GTPã­ã°ã«è¨é²
            exit_code = self.proc.poll() if self.proc else None
            logger.warning("GTP send_command skipped (proc dead, exit=%s): %s", exit_code, cmd)
            self._append_gtp_log("[send_command] proc dead exit={} cmd={}".format(exit_code, cmd))
            return None
        with self._lock:
            try:
                self._append_gtp_log("[send_command] >> {}".format(cmd))
                self.proc.stdin.write((cmd + "\n").encode("utf-8"))
                self.proc.stdin.flush()
                buf_lines = []
                deadline = _time.time() + float(timeout_s or 0) if timeout_s is not None else None
                while True:
                    if timeout_s is not None:
                        remaining = max(0.0, deadline - _time.time())
                        if remaining <= 0:
                            logger.warning("GTP send_command timeout: %s", cmd)
                            self._append_gtp_log("[send_command] timeout cmd={}".format(cmd))
                            return None
                    try:
                        line = self._stdout_q.get(timeout=min(1.0, remaining) if timeout_s is not None else 1.0)
                    except _queue.Empty:
                        # proc が死んでいたら終了
                        if self.proc.poll() is not None:
                            return None
                        continue
                    if line is None:
                        self._append_gtp_log("[send_command] stdout closed cmd={}".format(cmd))
                        return None
                    if line == "":
                        continue
                    buf_lines.append(line)
                    self._append_gtp_log("[send_command] << {}".format(line))
                    # GTP の応答終端は成功 "=" または失敗 "?"。
                    # "=" だけを終端条件にすると、"?" 応答時に
                    # 次行待ちでブロックし AI 対局が停止しうる。
                    if line.lstrip().startswith("=") or line.lstrip().startswith("?"):
                        break
                return "\n".join(buf_lines)
            except (OSError, BrokenPipeError, ValueError):
                logger.warning("GTP send_command failed: %s", cmd, exc_info=True)
                self._append_gtp_log("[send_command] exception cmd={}".format(cmd))
                return None

    def set_boardsize(self, size=19):
        return self.send_command("boardsize {}".format(size))

    def set_komi(self, komi=7.5):
        return self.send_command("komi {}".format(komi))

    def clear_board(self):
        return self.send_command("clear_board")

    def play(self, color, vertex):
        """Tell KataGo about a move. color='B'/'W', vertex='D4'/'pass'."""
        return self.send_command("play {} {}".format(color, vertex))

    def time_left(self, color, seconds, stones=0):
        """Send time_left GTP command so KataGo knows the remaining time.

        color: 'B' or 'W'
        seconds: remaining seconds (int)
        stones: stones left in period (0 for Fischer/sudden death)
        """
        return self.send_command("time_left {} {} {}".format(color, int(seconds), int(stones)))

    def genmove(self, color):
        """Ask KataGo to generate a move. Returns vertex like 'D4' or 'pass'."""
        resp = self.send_command("genmove {}".format(color), timeout_s=120)
        if resp and resp.startswith("="):
            move = resp.split()[-1].strip()
            return move
        return None

    def stop(self):
        """Stop KataGo process."""
        if self.proc:
            try:
                self.proc.stdin.write(b"quit\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                logger.debug("KataGo quit/wait failed, killing", exc_info=True)
                try:
                    self.proc.kill()
                except OSError:
                    logger.debug("KataGo kill also failed", exc_info=True)
            self.proc = None

    @staticmethod
    def gtp_vertex_to_coords(vertex):
        """Convert GTP vertex (e.g. 'D4') to board coords (col, row)."""
        if vertex.lower() == "pass" or vertex.lower() == "resign":
            return vertex.lower(), -1, -1
        col_letter = vertex[0].upper()
        col = ord(col_letter) - ord('A')
        if col >= 8:  # GTP skips 'I'
            col -= 1
        row = 19 - int(vertex[1:])
        return "move", col, row

    @staticmethod
    def coords_to_gtp_vertex(x, y, size=19):
        """Convert board coords (col, row) to GTP vertex (e.g. 'D4')."""
        col_letter = chr(ord('A') + (x if x < 8 else x + 1))  # skip I
        row_num = size - y
        return "{}{}".format(col_letter, row_num)

def _get_katago_data_dir():
    """Return a writable directory for KataGo data (OpenCL tuning etc.).

    Uses %LOCALAPPDATA%/GokaGo/katago on Windows, ~/.local/share/GokaGo/katago
    on Linux.  Falls back to a temp directory if creation fails.
    """
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", "")
        if not base:
            base = os.path.expanduser("~")
        data_dir = os.path.join(base, APP_DATA_DIR_NAME, "katago")
    else:
        data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", APP_DATA_DIR_NAME, "katago")
    try:
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    except OSError:
        import tempfile
        return tempfile.gettempdir()


def _ensure_analysis_config(katago_dir):
    """Return a path to a complete analysis config for KataGo v1.16.4+.

    ALWAYS writes our own config to a user-writable directory so that
    every required key (especially nnMaxBatchSize) is guaranteed present.
    The stock analysis_example.cfg shipped with KataGo is intentionally
    NOT used because it lacks nnMaxBatchSize and has a logDir that
    points to a read-only path under Program Files.
    """
    data_dir = _get_katago_data_dir()
    log_dir = os.path.join(data_dir, "analysis_logs").replace("\\", "/")
    cfg_path = os.path.join(data_dir, "goka_analysis.cfg")
    config_text = (
        "# Goka Go analysis config (auto-managed, do not edit)\n"
        "logToStderr = false\n"
        "logSearchInfo = false\n"
        "logAllRequests = false\n"
        "logAllResponses = false\n"
        "logDir = {log_dir}\n"
        "reportAnalysisWinratesAs = BLACK\n"
        "numSearchThreads = 1\n"
        "numAnalysisThreads = 1\n"
        "nnMaxBatchSize = 1\n"
        "nnCacheSizePowerOfTwo = 18\n"
        "maxVisits = 500\n"
    ).format(log_dir=log_dir)
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(config_text)
        return cfg_path
    except OSError:
        pass
    stock = os.path.join(katago_dir, "analysis_example.cfg")
    if os.path.exists(stock):
        return stock
    return cfg_path


def _log_katago_stderr(stderr_lines):
    """Write captured KataGo stderr to a diagnostic log file.

    This helps diagnose why KataGo analysis fails (e.g. missing OpenCL,
    permission errors, config problems).  The log is written to the
    user's home directory so it is always writable.
    """
    if not stderr_lines:
        return
    try:
        log_path = os.path.join(os.path.expanduser("~"), "goka_katago_log.txt")
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            from datetime import datetime
            f.write("\n--- KataGo stderr {} ---\n".format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            for raw in stderr_lines:
                f.write(raw.decode("utf-8", errors="replace"))
    except OSError:
        logger.debug("Failed to write KataGo stderr log", exc_info=True)


def _moves_to_katago(move_history, size=19):
    """Convert GoGame move_history to KataGo moves format."""
    moves = []
    for action, player, x, y in move_history:
        color = "B" if player == BLACK else "W"
        if action == "pass":
            moves.append([color, "pass"])
        elif action == "move":
            col_letter = chr(ord('A') + (x if x < 8 else x + 1))  # skip I
            row_num = size - y
            moves.append([color, f"{col_letter}{row_num}"])
        elif action == "resign":
            break
    return moves


def _katago_score(move_history, komi=7.5, size=19, rules="chinese"):
    """Run KataGo analysis to get score.

    Returns (score_lead, ownership_list) or raises RuntimeError.
    score_lead > 0 means Black leads.
    """
    katago_dir = os.path.join(_get_install_dir(), "katago")
    _exe = "katago.exe" if platform.system() == "Windows" else "katago"
    katago_exe = os.path.join(katago_dir, _exe)
    model_file = os.path.join(katago_dir, "model.bin")
    config_file = _ensure_analysis_config(katago_dir)

    if not os.path.exists(katago_exe):
        raise RuntimeError("KataGoが見つかりません: " + katago_exe)
    if not os.path.exists(model_file):
        raise RuntimeError("モデルファイルが見つかりません: " + model_file)

    katago_moves = _moves_to_katago(move_history, size)

    query = {
        "id": "score",
        "rules": rules,
        "komi": komi,
        "boardXSize": size,
        "boardYSize": size,
        "moves": katago_moves,
        "analyzeTurns": [len(katago_moves)],
        "maxVisits": 100,
        "includeOwnership": True,
    }

    proc = subprocess.Popen(
        [katago_exe, "analysis", "-config", config_file, "-model", model_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=katago_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )

    try:
        stderr_lines = []

        def _drain_stderr():
            try:
                for raw in proc.stderr:
                    stderr_lines.append(raw)
            except OSError:
                logger.debug("_katago_score stderr drain error", exc_info=True)

        threading.Thread(target=_drain_stderr, daemon=True).start()

        query_str = json.dumps(query) + "\n"
        proc.stdin.write(query_str.encode("utf-8"))
        proc.stdin.flush()
        proc.stdin.close()

        import queue as _queue
        line_q = _queue.Queue()

        def _reader():
            try:
                for raw_line in proc.stdout:
                    line_q.put(raw_line)
            except (OSError, ValueError):
                logger.debug("_katago_score reader error", exc_info=True)
            line_q.put(None)

        reader_t = threading.Thread(target=_reader, daemon=True)
        reader_t.start()

        t0 = _time.time()
        while _time.time() - t0 < 120:
            try:
                line = line_q.get(timeout=2.0)
            except _queue.Empty:
                if proc.poll() is not None:
                    _log_katago_stderr(stderr_lines)
                    raise RuntimeError("KataGoが予期せず終了しました")
                continue
            if line is None:
                _log_katago_stderr(stderr_lines)
                raise RuntimeError("KataGoが予期せず終了しました")
            text = line.decode("utf-8").strip()
            if text:
                try:
                    resp = json.loads(text)
                    if resp.get("id") == "score":
                        root_info = resp.get("rootInfo", {})
                        score_lead = root_info.get("scoreLead", 0)
                        ownership = resp.get("ownership", [])
                        return score_lead, ownership
                except json.JSONDecodeError:
                    pass

        _log_katago_stderr(stderr_lines)
        raise RuntimeError("応答タイムアウト")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _katago_winrate(move_history, komi=7.5, size=19, rules="chinese"):
    """Run KataGo analysis to get win rate.
    Returns (black_winrate, white_winrate) as percentages (0-100).
    """
    katago_dir = os.path.join(_get_install_dir(), "katago")
    _exe = "katago.exe" if platform.system() == "Windows" else "katago"
    katago_exe = os.path.join(katago_dir, _exe)
    model_file = os.path.join(katago_dir, "model.bin")
    config_file = _ensure_analysis_config(katago_dir)

    if not os.path.exists(katago_exe) or not os.path.exists(model_file):
        return None, None

    katago_moves = _moves_to_katago(move_history, size)

    query = {
        "id": "winrate",
        "rules": rules,
        "komi": komi,
        "boardXSize": size,
        "boardYSize": size,
        "moves": katago_moves,
        "analyzeTurns": [len(katago_moves)],
        "maxVisits": 100,
        "includeOwnership": False,
    }

    proc = subprocess.Popen(
        [katago_exe, "analysis", "-config", config_file, "-model", model_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=katago_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )

    try:
        stderr_lines = []

        def _drain_stderr():
            try:
                for raw in proc.stderr:
                    stderr_lines.append(raw)
            except OSError:
                logger.debug("_katago_winrate stderr drain error", exc_info=True)

        threading.Thread(target=_drain_stderr, daemon=True).start()

        query_str = json.dumps(query) + "\n"
        proc.stdin.write(query_str.encode("utf-8"))
        proc.stdin.flush()
        proc.stdin.close()

        import queue as _queue
        line_q = _queue.Queue()

        def _reader():
            try:
                for raw_line in proc.stdout:
                    line_q.put(raw_line)
            except (OSError, ValueError):
                logger.debug("_katago_winrate reader error", exc_info=True)
            line_q.put(None)

        reader_t = threading.Thread(target=_reader, daemon=True)
        reader_t.start()

        t0 = _time.time()
        while _time.time() - t0 < 30:
            try:
                line = line_q.get(timeout=2.0)
            except _queue.Empty:
                if proc.poll() is not None:
                    _log_katago_stderr(stderr_lines)
                    break
                continue
            if line is None:
                _log_katago_stderr(stderr_lines)
                break
            text = line.decode("utf-8").strip()
            if text:
                try:
                    resp = json.loads(text)
                    if resp.get("id") == "winrate":
                        root_info = resp.get("rootInfo", {})
                        winrate = root_info.get("winrate", 0.5)
                        black_wr = winrate * 100
                        white_wr = (1 - winrate) * 100
                        return round(black_wr, 1), round(white_wr, 1)
                except json.JSONDecodeError:
                    pass

        return None, None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def calculate_territory_chinese(board, komi=7.5, move_history=None, rules="chinese"):
    """Calculate score using KataGo analysis API.

    Returns (winner_str, result_text) e.g. ("白", "6目半勝ち")
    rules: "chinese" or "japanese" (passed to KataGo).
    If move_history is provided, uses KataGo for accurate scoring.
    Falls back to simple counting if KataGo is unavailable.
    """
    _used_fallback = False
    if move_history is not None:
        try:
            score_lead, _ = _katago_score(move_history, komi, rules=rules)
            raw_diff = abs(score_lead)
            komi_frac = komi - int(komi)
            if abs(komi_frac - 0.5) < 0.01:
                diff = round(raw_diff - 0.5) + 0.5
            else:
                diff = round(raw_diff)
            if diff <= 0:
                return ("引き分け", "持碁")
            if diff == 0.5:
                diff_str = "半目"
            elif diff == int(diff):
                diff_str = "{}目".format(int(diff))
            else:
                diff_str = "{}目半".format(int(diff))
            if score_lead > 0:
                return ("黒", diff_str + "勝ち")
            else:
                return ("白", diff_str + "勝ち")
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            try:
                log_path = os.path.join(os.path.expanduser("~"), "goka_katago_log.txt")
                with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                    from datetime import datetime
                    f.write("\n--- KataGo score fallback {} ---\n".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    f.write("Error: {}\n".format(exc))
                    f.write("Falling back to simple counting (dead stones NOT detected)\n")
            except OSError:
                logger.warning("Failed to write KataGo score fallback log", exc_info=True)
            _used_fallback = True

    # Fallback: simple Chinese counting (no dead stone detection)
    size = len(board)

    def neighbors(x, y):
        for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if 0 <= nx < size and 0 <= ny < size:
                yield nx, ny

    visited = [[False] * size for _ in range(size)]
    black_territory = 0
    white_territory = 0

    for y in range(size):
        for x in range(size):
            if board[y][x] == EMPTY and not visited[y][x]:
                region = []
                border_colors = set()
                stack = [(x, y)]
                while stack:
                    cx, cy = stack.pop()
                    if visited[cy][cx]:
                        continue
                    visited[cy][cx] = True
                    region.append((cx, cy))
                    for nx, ny in neighbors(cx, cy):
                        if board[ny][nx] == EMPTY and not visited[ny][nx]:
                            stack.append((nx, ny))
                        elif board[ny][nx] != EMPTY:
                            border_colors.add(board[ny][nx])
                if border_colors == {BLACK}:
                    black_territory += len(region)
                elif border_colors == {WHITE}:
                    white_territory += len(region)

    black_stones = sum(1 for y in range(size) for x in range(size) if board[y][x] == BLACK)
    white_stones = sum(1 for y in range(size) for x in range(size) if board[y][x] == WHITE)
    black_score = black_stones + black_territory
    white_score = white_stones + white_territory + komi

    diff = abs(black_score - white_score)
    if diff == 0.5:
        diff_str = "半目"
    elif diff == int(diff):
        diff_str = "{}目".format(int(diff))
    else:
        diff_str = "{}y目半".format(int(diff))

    _suffix = "（簡易計算）" if _used_fallback else ""
    if black_score > white_score:
        return ("黒", diff_str + "勝ち" + _suffix)
    elif white_score > black_score:
        return ("白", diff_str + "勝ち" + _suffix)
    else:
        return ("引き分け", "持碁" + _suffix)

