# -*- coding: utf-8 -*-
"""碁華 SGF ファイル入出力"""
import os
import re as _re

from igo.constants import BLACK, WHITE


def _parse_sgf_text(content):
    """Parse SGF from text string (not file). Returns (move_list, metadata)."""
    import re as _re
    metadata = {}
    for tag in ["PB", "PW", "BR", "WR", "SZ", "KM", "RE", "DT", "RU"]:
        m = _re.search(tag + r"\[([^\]]*)\]", content)
        if m:
            metadata[tag] = m.group(1)
    moves = []
    move_pattern = _re.compile(r";(B|W)\[([a-z]{0,2})\]")
    for m in move_pattern.finditer(content):
        color = BLACK if m.group(1) == "B" else WHITE
        coord = m.group(2)
        if coord == "" or len(coord) < 2:
            moves.append(("pass", color, -1, -1))
        else:
            x = ord(coord[0]) - ord("a")
            y = ord(coord[1]) - ord("a")
            moves.append(("move", color, x, y))
    return moves, metadata


# --------------- Game Board GUI ---------------

# --------------- SGF Utilities ---------------

def save_sgf(filepath, move_history, black_name="", white_name="",
             black_rank="", white_rank="", board_size=19, komi=6.5, result=""):
    """Save game record as SGF file."""
    sgf = "(;GM[1]FF[4]CA[UTF-8]SZ[{}]".format(board_size)
    sgf += "KM[{}]".format(komi)
    if black_name:
        sgf += "PB[{}]".format(black_name)
    if white_name:
        sgf += "PW[{}]".format(white_name)
    if black_rank:
        sgf += "BR[{}]".format(black_rank)
    if white_rank:
        sgf += "WR[{}]".format(white_rank)
    if result:
        sgf += "RE[{}]".format(result)
    import datetime as _dt
    sgf += "DT[{}]".format(_dt.date.today().isoformat())
    for action, player, x, y in move_history:
        color = "B" if player == BLACK else "W"
        if action == "move":
            coord = chr(ord("a") + x) + chr(ord("a") + y)
            sgf += ";{}[{}]".format(color, coord)
        elif action == "pass":
            sgf += ";{}[]".format(color)
        elif action == "resign":
            break
    sgf += ")\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(sgf)


def load_sgf(filepath):
    """Load SGF file. Returns (move_list, metadata)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    metadata = {}
    import re as _re
    for tag in ["PB", "PW", "BR", "WR", "SZ", "KM", "RE", "DT"]:
        m = _re.search(tag + r"\[([^\]]*)\]", content)
        if m:
            metadata[tag] = m.group(1)
    moves = []
    move_pattern = _re.compile(r";(B|W)\[([a-z]{0,2})\]")
    for m in move_pattern.finditer(content):
        color = BLACK if m.group(1) == "B" else WHITE
        coord = m.group(2)
        if coord == "" or len(coord) < 2:
            moves.append(("pass", color, -1, -1))
        else:
            x = ord(coord[0]) - ord("a")
            y = ord(coord[1]) - ord("a")
            moves.append(("move", color, x, y))
    return moves, metadata
