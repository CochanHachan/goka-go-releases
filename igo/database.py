# -*- coding: utf-8 -*-
"""碁華 ユーザーデータベース"""
import sqlite3
import hashlib
import secrets

from igo.config import _get_db_path
from igo.elo import rank_to_initial_elo
from igo.constants import BLACK, WHITE


class UserDatabase:
    def __init__(self):
        db_path = _get_db_path()
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                real_name TEXT NOT NULL,
                handle_name TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                rank TEXT NOT NULL DEFAULT '30\u7d1a',
                password_plain TEXT NOT NULL DEFAULT '',
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.conn.commit()
        # Migration: add password_plain column if missing
        cur = self.conn.execute("PRAGMA table_info(users)")
        col_names = [c[1] for c in cur.fetchall()]
        if "password_plain" not in col_names:
            self.conn.execute("ALTER TABLE users ADD COLUMN password_plain TEXT NOT NULL DEFAULT ''")
            self.conn.commit()
        if "elo_rating" not in col_names:
            self.conn.execute("ALTER TABLE users ADD COLUMN elo_rating INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()
            for row in self.conn.execute("SELECT id, rank FROM users").fetchall():
                elo = rank_to_initial_elo(row[1])
                self.conn.execute("UPDATE users SET elo_rating = ? WHERE id = ?", (elo, row[0]))
            self.conn.commit()
        if "language" not in col_names:
            self.conn.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'ja'")
            self.conn.commit()
        cur = self.conn.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            self.create_user("\u7ba1\u7406\u8005", "admin", "admin", "---", is_admin=1)
        # Create game_records table
        self._ensure_game_records_table()

    def _hash_password(self, password, salt):
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def create_user(self, real_name, handle_name, password, rank, is_admin=0, elo_rating=0, language="ja"):
        salt = secrets.token_hex(16)
        pw_hash = self._hash_password(password, salt)
        try:
            self.conn.execute(
                "INSERT INTO users (real_name, handle_name, password_hash, salt, rank, is_admin, password_plain, elo_rating, language) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (real_name, handle_name, pw_hash, salt, rank, is_admin, password, elo_rating, language)
            )
            self.conn.commit()
            return True, ""
        except sqlite3.IntegrityError:
            return False, "\u305d\u306e\u30cf\u30f3\u30c9\u30eb\u30cd\u30fc\u30e0\u306f\u65e2\u306b\u4f7f\u308f\u308c\u3066\u3044\u307e\u3059"

    def authenticate(self, handle_name, password):
        cur = self.conn.execute(
            "SELECT * FROM users WHERE handle_name = ?", (handle_name,))
        user = cur.fetchone()
        if user is None:
            return None
        pw_hash = self._hash_password(password, user["salt"])
        if pw_hash == user["password_hash"]:
            return user
        return None

    def update_elo(self, user_id, new_elo, new_rank):
        self.conn.execute(
            "UPDATE users SET elo_rating = ?, rank = ? WHERE id = ?",
            (new_elo, new_rank, user_id))
        self.conn.commit()

    def set_user_language(self, user_id, lang):
        self.conn.execute("UPDATE users SET language = ? WHERE id = ?", (lang, user_id))
        self.conn.commit()

    def get_all_users(self):
        cur = self.conn.execute(
            "SELECT id, handle_name, real_name, rank, is_admin, created_at, password_plain, elo_rating FROM users ORDER BY id")
        return cur.fetchall()

    def delete_user(self, user_id):
        self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.conn.commit()

    # ---------- game_records table ----------

    def _ensure_game_records_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS game_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                black_name TEXT NOT NULL,
                black_rank TEXT NOT NULL DEFAULT '',
                white_name TEXT NOT NULL,
                white_rank TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL DEFAULT '',
                komi REAL NOT NULL DEFAULT 6.5,
                move_count INTEGER NOT NULL DEFAULT 0,
                sgf_text TEXT NOT NULL DEFAULT ''
            )
        """)
        self.conn.commit()

    def save_game_record(self, black_name, black_rank, white_name, white_rank,
                         result, komi, move_history):
        """Save a completed game record. Returns the new record id."""
        self._ensure_game_records_table()
        import datetime as _dt
        played_at = _dt.datetime.now().strftime("%Y/%m/%d %H:%M")
        # Build SGF text in memory
        sgf = "(;GM[1]FF[4]CA[UTF-8]SZ[19]"
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
        sgf += "DT[{}]".format(_dt.date.today().isoformat())
        move_count = 0
        for action, player, x, y in move_history:
            color = "B" if player == BLACK else "W"
            if action == "move":
                coord = chr(ord("a") + x) + chr(ord("a") + y)
                sgf += ";{}[{}]".format(color, coord)
                move_count += 1
            elif action == "pass":
                sgf += ";{}[]".format(color)
            elif action == "resign":
                break
        sgf += ")\n"
        cur = self.conn.execute(
            "INSERT INTO game_records (played_at, black_name, black_rank, white_name, white_rank, "
            "result, komi, move_count, sgf_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (played_at, black_name, black_rank, white_name, white_rank,
             result, komi, move_count, sgf))
        self.conn.commit()
        return cur.lastrowid

    def get_game_records_for_user(self, handle_name):
        """Get all game records where the user played as black or white."""
        self._ensure_game_records_table()
        cur = self.conn.execute(
            "SELECT id, played_at, black_name, white_name, result "
            "FROM game_records WHERE black_name = ? OR white_name = ? "
            "ORDER BY id DESC",
            (handle_name, handle_name))
        return cur.fetchall()

    def get_game_record_sgf(self, record_id):
        """Get the SGF text for a specific game record."""
        self._ensure_game_records_table()
        cur = self.conn.execute(
            "SELECT sgf_text FROM game_records WHERE id = ?", (record_id,))
        row = cur.fetchone()
        return row[0] if row else None

