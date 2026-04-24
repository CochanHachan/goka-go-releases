# -*- coding: utf-8 -*-
"""碁華 昇段・昇級ポップアップ"""
import logging
import tkinter as tk
import math
import random
import os

from igo.elo import _is_dan_rank
from igo.lang import L

logger = logging.getLogger(__name__)


class PromotionPopup(tk.Toplevel):
    """昇段・昇級を祝う桜吹雪ポップアップ"""

    def __init__(self, master=None, rank="1段", player_name=""):
        super().__init__(master)
        self.rank = str(rank)
        self.player_name = str(player_name)
        self.width = 900
        self.height = 520
        self.bg = "#fdeff2"
        self.sakura_images = []
        self.particles = []

        self.withdraw()
        self.overrideredirect(True)
        self.resizable(False, False)

        self.canvas = tk.Canvas(
            self, width=self.width, height=self.height,
            bg=self.bg, highlightthickness=0)
        self.canvas.pack()

        # 画像読み込み
        # os.chdir()はPythonのCWDのみ変更するため、Tcl/TkのCWDは変わらない。
        # self.tk.eval("cd {...}")でTcl内部のCWDを一時変更してから相対パスで読む。
        img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image")
        img_dir_tcl = img_dir.replace("\\", "/")
        try:
            old_tcl_cwd = self.tk.eval("pwd")
            self.tk.eval("cd {%s}" % img_dir_tcl)
            for name in ["sakura_0.png", "sakura_1.png", "sakura_2.png", "sakura_3.png"]:
                try:
                    img = tk.PhotoImage(file=name)
                    self.sakura_images.append(img)
                except tk.TclError:
                    logger.debug("Failed to load sakura image: %s", name, exc_info=True)
            self.tk.eval("cd {%s}" % old_tcl_cwd.replace("\\", "/"))
        except (tk.TclError, OSError):
            logger.debug("Failed to load sakura images from %s", img_dir, exc_info=True)

        # 桜パーティクル（背面）→ テキスト（前面）の順で作成
        # 画像読み込みの成否に関わらず必ず粒子を生成する
        self._create_particles(40)
        self._build_ui()
        self._running = False

    def _make_message(self):
        is_dan = _is_dan_rank(self.rank)
        if self.player_name:
            key = "promo_template_dan" if is_dan else "promo_template_kyu"
            return L(key).format(self.player_name, self.rank)
        else:
            key = "promo_template_dan_noname" if is_dan else "promo_template_kyu_noname"
            return L(key).format(self.rank)

    def _build_ui(self):
        cx, cy = self.width // 2, self.height // 2
        self.text_id = self._draw_gold_text(
            cx, cy, self._make_message(), ("メイリオ", 40, "bold"))
        self.canvas.tag_raise(self.text_id)
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Return>", lambda e: self.close())
        # クリック閉じは300ms遅延（直前ダイアログのクリックで即閉じ防止）
        self.after(300, lambda: self.bind("<Button-1>", lambda e: self.close()))

    def _draw_gold_text(self, x, y, text, font):
        # 細い黒アウトライン（1px、8方向）
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            self.canvas.create_text(x + dx, y + dy, text=text,
                                    fill="black", font=font, justify="center")
        # 影
        self.canvas.create_text(x+2, y+2, text=text,
                                fill="#8B6914", font=font, justify="center")
        # 金色テキスト本体
        return self.canvas.create_text(x, y, text=text,
                                       fill="#ffd700", font=font, justify="center")

    def _create_particles(self, count):
        use_images = len(self.sakura_images) > 0
        petal_colors = ["#ff69b4", "#ffb7c5", "#ff85a1", "#ff1493", "#ffc0cb"]
        for i in range(count):
            x = random.uniform(0, self.width)
            # 最初から画面内に均一配置（すぐに桜が見えるように）
            y = random.uniform(0, self.height)
            if use_images:
                img = random.choice(self.sakura_images)
                item = self.canvas.create_image(x, y, image=img)
                size = 0
            else:
                img = None
                size = random.uniform(12, 20)
                c = random.choice(petal_colors)
                item = self.canvas.create_oval(
                    x - size, y - size * 0.6,
                    x + size, y + size * 0.6,
                    fill=c, outline="#c2185b", width=1)
            self.particles.append({
                "item": item, "x": x, "y": y,
                "speed": random.uniform(1.5, 3),
                "angle": random.uniform(0, math.pi * 2),
                "use_image": use_images,
                "size": size,
                "img": img,   # PhotoImage参照をここでも保持（GC防止）
            })

    def _animate(self):
        if not self._running:
            return
        for p in self.particles:
            p["angle"] += 0.05
            p["y"] += p["speed"]
            p["x"] += math.sin(p["angle"]) * 0.8
            if p["use_image"]:
                self.canvas.coords(p["item"], p["x"], p["y"])
            else:
                s = p["size"]
                self.canvas.coords(p["item"],
                                   p["x"] - s, p["y"] - s * 0.6,
                                   p["x"] + s, p["y"] + s * 0.6)
            if p["y"] > self.height:
                p["y"] = -20
                p["x"] = random.uniform(0, self.width)
        self.after(33, self._animate)

    def show(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - self.width) // 2
        y = (sh - self.height) // 2
        self.geometry("{}x{}+{}+{}".format(self.width, self.height, x, y))
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self._running = True
        self._animate()

    def close(self):
        self._running = False
        self.destroy()
