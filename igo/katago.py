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
            stderr=subprocess.DEVNULL,
            cwd=katago_dir,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )

    def send_command(self, cmd):
        """Send a GTP command and return the response."""
        if not self.proc or self.proc.poll() is not None:
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

    def set_boardsize(self, size=19):
        self.send_command("boardsize {}".format(size))

    def set_komi(self, komi=7.5):
        self.send_command("komi {}".format(komi))

    def clear_board(self):
        self.send_command("clear_board")

    def play(self, color, vertex):
        """Tell KataGo about a move. color='B'/'W', vertex='D4'/'pass'."""
        return self.send_command("play {} {}".format(color, vertex))

    def genmove(self, color):
        """Ask KataGo to generate a move. Returns vertex like 'D4' or 'pass'."""
        resp = self.send_command("genmove {}".format(color))
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
        data_dir = os.path.join(base, "GokaGo", "katago")
    else:
        data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "GokaGo", "katago")
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
    # Last resort: return stock config (will likely fail on nnMaxBatchSize)
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
        "maxVisits": 500,
        "includeOwnership": True,
    }

    # Our own config (written by _ensure_analysis_config to a user-writable
    # directory) already contains logDir, nnMaxBatchSize, and all other
    # required keys.  No -override-config is needed.
    proc = subprocess.Popen(
        [katago_exe, "analysis", "-config", config_file, "-model", model_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=katago_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )

    try:
        # Drain stderr in a background thread to prevent pipe-buffer
        # deadlock.  KataGo writes OpenCL initialisation messages to
        # stderr; if the 64 KB pipe buffer fills up before we read it,
        # KataGo blocks and the whole analysis hangs.
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

        # Use a reader thread to avoid readline() blocking forever
        import queue as _queue
        line_q = _queue.Queue()

        def _reader():
            try:
                for raw_line in proc.stdout:
                    line_q.put(raw_line)
            except (OSError, ValueError):
                logger.debug("_katago_score reader error", exc_info=True)
            line_q.put(None)  # sentinel

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
        "maxVisits": 1,
        "includeOwnership": False,
    }

    # Our own config already contains all required keys (see _katago_score).
    proc = subprocess.Popen(
        [katago_exe, "analysis", "-config", config_file, "-model", model_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=katago_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )

    try:
        # Drain stderr to prevent pipe-buffer deadlock (see _katago_score).
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
            # When komi is half-integer (X.5), score difference is always X.5
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
            # Log the failure so it can be diagnosed
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
        diff_str = "{}目半".format(int(diff))

    # When using fallback, append label so the user knows dead stones
    # were NOT detected and the result may be inaccurate.
    _suffix = "（簡易計算）" if _used_fallback else ""
    if black_score > white_score:
        return ("黒", diff_str + "勝ち" + _suffix)
    elif white_score > black_score:
        return ("白", diff_str + "勝ち" + _suffix)
    else:
        return ("引き分け", "持碁" + _suffix)

