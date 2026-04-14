# -*- coding: utf-8 -*-
"""碁華 碁盤ロジック"""
import json
import logging
import math
import os
import platform
import subprocess
import threading
import time as _time

from igo.constants import BOARD_SIZE, EMPTY, BLACK, WHITE, TIME_LIMIT

logger = logging.getLogger(__name__)


def _neighbors(x, y):
    for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
        if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
            yield nx, ny

def _get_group(board, x, y):
    color = board[y][x]
    if color == EMPTY:
        return set(), set()
    group = set()
    liberties = set()
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in group:
            continue
        group.add((cx, cy))
        for nx, ny in _neighbors(cx, cy):
            if board[ny][nx] == EMPTY:
                liberties.add((nx, ny))
            elif board[ny][nx] == color and (nx, ny) not in group:
                stack.append((nx, ny))
    return group, liberties

def _remove_group(board, group):
    for x, y in group:
        board[y][x] = EMPTY
    return len(group)

def _board_key(board):
    return tuple(tuple(row) for row in board)


# ---------------------------------------------------------------------------
# KataGo GTP エンジン（AI対局用）
# ---------------------------------------------------------------------------
class KataGoGTP:
    """KataGo GTP process for AI games."""

    def __init__(self, visits=50):
        self.visits = visits
        self.proc = None
        self._lock = threading.Lock()

    def start(self):
        """Start KataGo GTP process."""
        katago_dir = os.path.join(_get_install_dir(), "katago")
        _exe = "katago.exe" if platform.system() == "Windows" else "katago"
        katago_exe = os.path.join(katago_dir, _exe)
        model_file = os.path.join(katago_dir, "model.bin")
        config_file = os.path.join(katago_dir, "default_gtp.cfg")

        if not os.path.exists(katago_exe):
            raise RuntimeError("KataGoが見つかりません: " + katago_exe)
        if not os.path.exists(model_file):
            raise RuntimeError("モデルファイルが見つかりません: " + model_file)

        override = "maxVisits={},numSearchThreads=1,ponderingEnabled=false".format(
            self.visits)

        self.proc = subprocess.Popen(
            [katago_exe, "gtp", "-config", config_file, "-model", model_file,
             "-override-config", override],
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
    katago_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "katago")
    _exe = "katago.exe" if platform.system() == "Windows" else "katago"
    katago_exe = os.path.join(katago_dir, _exe)
    model_file = os.path.join(katago_dir, "model.bin")
    config_file = os.path.join(katago_dir, "analysis_example.cfg")

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
        "maxVisits": 200,
        "includeOwnership": True,
    }

    proc = subprocess.Popen(
        [katago_exe, "analysis", "-config", config_file, "-model", model_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=katago_dir,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    try:
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
                    raise RuntimeError("KataGoが予期せず終了しました")
                continue
            if line is None:
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
    katago_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "katago")
    _exe = "katago.exe" if platform.system() == "Windows" else "katago"
    katago_exe = os.path.join(katago_dir, _exe)
    model_file = os.path.join(katago_dir, "model.bin")
    config_file = os.path.join(katago_dir, "analysis_example.cfg")

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
        "maxVisits": 50,
        "includeOwnership": False,
    }

    proc = subprocess.Popen(
        [katago_exe, "analysis", "-config", config_file, "-model", model_file],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=katago_dir,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    try:
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
                    break
                continue
            if line is None:
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
    if move_history is not None:
        try:
            score_lead, _ = _katago_score(move_history, komi, rules=rules)
            raw_diff = abs(score_lead)
            # When komi is half-integer (X.5), score difference is always X.5
            komi_frac = komi - int(komi)
            if abs(komi_frac - 0.5) < 0.01:
                diff = math.floor(raw_diff) + 0.5
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
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
            logger.warning("KataGo scoring failed, falling back to simple counting", exc_info=True)

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

    if black_score > white_score:
        return ("黒", diff_str + "勝ち")
    elif white_score > black_score:
        return ("白", diff_str + "勝ち")
    else:
        return ("引き分け", "持碁")


class GoGame:
    def __init__(self):
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.current_player = BLACK
        self.prev_board_key = None
        self.captured_black = 0
        self.captured_white = 0
        self.time_black = TIME_LIMIT
        self.time_white = TIME_LIMIT
        self.game_over = False
        self.winner = None
        self.consecutive_passes = 0
        self.move_history = []

    def place_stone(self, x, y):
        if not (0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE):
            return False, []
        if self.board[y][x] != EMPTY:
            return False, []
        opponent = WHITE if self.current_player == BLACK else BLACK
        self.board[y][x] = self.current_player
        captured = []
        total_captured = 0
        for nx, ny in _neighbors(x, y):
            if self.board[ny][nx] == opponent:
                group, liberties = _get_group(self.board, nx, ny)
                if len(liberties) == 0:
                    total_captured += _remove_group(self.board, group)
                    captured.extend(group)
        own_group, own_liberties = _get_group(self.board, x, y)
        if len(own_liberties) == 0:
            self.board[y][x] = EMPTY
            for cx, cy in captured:
                self.board[cy][cx] = opponent
            return False, []
        new_key = _board_key(self.board)
        if new_key == self.prev_board_key:
            self.board[y][x] = EMPTY
            for cx, cy in captured:
                self.board[cy][cx] = opponent
            return False, []
        self.prev_board_key = new_key
        if self.current_player == BLACK:
            self.captured_black += total_captured
        else:
            self.captured_white += total_captured
        self.consecutive_passes = 0
        self.move_history.append(("move", self.current_player, x, y))
        self.current_player = opponent
        return True, captured

    def time_out(self, player):
        self.game_over = True
        self.winner = WHITE if player == BLACK else BLACK

    def pass_turn(self):
        if self.game_over:
            return
        self.move_history.append(("pass", self.current_player, -1, -1))
        self.consecutive_passes += 1
        if self.consecutive_passes >= 2:
            self.game_over = True
            # Simple scoring: count territory + captures
            return
        self.current_player = WHITE if self.current_player == BLACK else BLACK

    def resign(self, player):
        if self.game_over:
            return
        self.move_history.append(("resign", player, -1, -1))
        self.game_over = True
        self.winner = WHITE if player == BLACK else BLACK

