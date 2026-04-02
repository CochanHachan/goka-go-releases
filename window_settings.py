# -*- coding: utf-8 -*-
"""画面設定の保存・復元クラス (SQLite)"""
import json
import os
import sqlite3


class WindowSettings:
    """画面サイズ・位置・列幅などをSQLiteに保存・復元する。

    Usage:
        settings = WindowSettings(db_path, "admin")
        settings.restore_window(root)          # 起動時
        col_widths = settings.load("column_widths")  # 列幅取得
        ...
        settings.save_window(root, tree)       # 終了時
    """

    _TABLE = "ui_settings"

    def __init__(self, db_path: str, screen_name: str):
        self._db_path = db_path
        self._screen_name = screen_name
        self._ensure_table()

    # --- public API ---

    def save(self, key: str, value):
        """キーと値を保存する。値はJSON化して格納。"""
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {self._TABLE} "
                "(screen_name, key, value) VALUES (?, ?, ?)",
                (self._screen_name, key, json.dumps(value, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, key: str, default=None):
        """キーに対応する値を取得する。存在しなければdefaultを返す。"""
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT value FROM {self._TABLE} "
                "WHERE screen_name = ? AND key = ?",
                (self._screen_name, key),
            ).fetchone()
            if row:
                return json.loads(row[0])
            return default
        except Exception:
            return default
        finally:
            conn.close()

    def save_window(self, root, tree=None, ncols: int = 0):
        """ウィンドウのgeometryと列幅をまとめて保存する。

        Args:
            root: tkinter root/toplevel
            tree: tksheet.Sheet (列幅保存が必要な場合)
            ncols: 列数 (tree指定時に必要)
        """
        try:
            if root.state() == "iconic":
                return  # 最小化中は保存しない
            self.save("geometry", root.geometry())
        except Exception:
            pass
        if tree and ncols > 0:
            try:
                widths = [tree.column_width(column=i) for i in range(ncols)]
                self.save("column_widths", widths)
            except Exception:
                pass

    def restore_window(self, root, default_geometry: str = ""):
        """ウィンドウのgeometryを復元する。

        Args:
            root: tkinter root/toplevel
            default_geometry: 保存値がない場合のデフォルト
        """
        geo = self.load("geometry")
        if geo:
            try:
                root.geometry(geo)
            except Exception:
                if default_geometry:
                    root.geometry(default_geometry)
        elif default_geometry:
            root.geometry(default_geometry)

    def restore_column_widths(self, tree, ncols: int,
                              defaults: list = None):
        """列幅を復元する。

        Args:
            tree: tksheet.Sheet
            ncols: 現在の列数
            defaults: デフォルト列幅リスト
        Returns:
            True if restored, False if defaults were used
        """
        widths = self.load("column_widths")
        if widths and len(widths) == ncols:
            for i, w in enumerate(widths):
                tree.column_width(column=i, width=w)
            return True
        if defaults and len(defaults) == ncols:
            for i, w in enumerate(defaults):
                tree.column_width(column=i, width=w)
        return False

    # --- internal ---

    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        return conn

    def _ensure_table(self):
        conn = self._connect()
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE} (
                    screen_name TEXT NOT NULL,
                    key         TEXT NOT NULL,
                    value       TEXT,
                    PRIMARY KEY (screen_name, key)
                )
            """)
            conn.commit()
        finally:
            conn.close()
