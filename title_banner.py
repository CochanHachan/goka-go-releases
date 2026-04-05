import tkinter as tk
from tkinter import font as tkfont
import math


class TitleBanner(tk.Canvas):
    def __init__(
        self,
        master,
        width=560,
        height=54,
        text="挑戦状が届いています！",

        # 文字
        font_family="Yu Mincho",
        font_size=16,
        font_weight="bold",

        # 文字色
        text_color="#e3bf68",
        text_outline_color="#4a2b0d",
        text_shadow_color="#5e4018",

        # 文字描画
        text_outline_size=0,
        text_shadow_offset=(1, 1),

        # 外枠
        outer_border_color="#b58a42",
        outer_border_width=2,

        # 濃い内枠
        inner_border_color="#5a3b17",
        inner_border_width=2,

        # ハイライト線
        highlight_line_color="#c49a50",
        highlight_line_width=1,

        # さらに内側の濃い線
        inner_line_color="#2a1807",
        inner_line_width=1,

        # 角丸
        corner_radius=9,

        # 余白
        side_margin=6,
        top_margin=6,
        bottom_margin=6,

        # 背景グラデーション
        bg_colors=None,

        # 上部光沢
        gloss_colors=None,

        # 左右ひし形
        diamond_color="#cda854",
        diamond_size=4,
        diamond_offset=26,

        **kwargs
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            highlightthickness=0,
            bd=0,
            bg=kwargs.pop("bg", master.cget("bg") if hasattr(master, "cget") else "#ffffff"),
            **kwargs
        )

        if bg_colors is None:
            bg_colors = [
                (0.00, "#4b6593"),
                (0.16, "#435c88"),
                (0.42, "#374f76"),
                (0.72, "#2c4161"),
                (1.00, "#24354f"),
            ]

        if gloss_colors is None:
            gloss_colors = [
                (0.00, "#6f84ab"),
                (0.40, "#61769d"),
                (1.00, "#55688d"),
            ]

        self.params = {
            "width": width,
            "height": height,
            "text": text,
            "font_family": font_family,
            "font_size": font_size,
            "font_weight": font_weight,
            "text_color": text_color,
            "text_outline_color": text_outline_color,
            "text_shadow_color": text_shadow_color,
            "text_outline_size": text_outline_size,
            "text_shadow_offset": text_shadow_offset,
            "outer_border_color": outer_border_color,
            "outer_border_width": outer_border_width,
            "inner_border_color": inner_border_color,
            "inner_border_width": inner_border_width,
            "highlight_line_color": highlight_line_color,
            "highlight_line_width": highlight_line_width,
            "inner_line_color": inner_line_color,
            "inner_line_width": inner_line_width,
            "corner_radius": corner_radius,
            "side_margin": side_margin,
            "top_margin": top_margin,
            "bottom_margin": bottom_margin,
            "bg_colors": bg_colors,
            "gloss_colors": gloss_colors,
            "diamond_color": diamond_color,
            "diamond_size": diamond_size,
            "diamond_offset": diamond_offset,
        }

        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()

    def set_text(self, text: str):
        self.params["text"] = text
        self.redraw()

    def update_style(self, **kwargs):
        self.params.update(kwargs)
        if "width" in kwargs or "height" in kwargs:
            self.config(
                width=self.params["width"],
                height=self.params["height"],
            )
        self.redraw()

    def redraw(self):
        self.delete("all")

        p = self.params
        w = int(self.winfo_width() or p["width"])
        h = int(self.winfo_height() or p["height"])

        self.config(width=w, height=h)

        x1 = p["side_margin"]
        y1 = p["top_margin"]
        x2 = w - p["side_margin"]
        y2 = h - p["bottom_margin"]

        # 1. 外枠（金）
        self._draw_rounded_rect(
            x1, y1, x2, y2,
            radius=p["corner_radius"],
            fill=p["outer_border_color"],
            outline=p["outer_border_color"],
            width=1
        )

        # 2. 濃い内枠
        obw = p["outer_border_width"]
        ix1 = x1 + obw
        iy1 = y1 + obw
        ix2 = x2 - obw
        iy2 = y2 - obw
        ir = max(2, p["corner_radius"] - 2)

        self._draw_rounded_rect(
            ix1, iy1, ix2, iy2,
            radius=ir,
            fill=p["inner_border_color"],
            outline=p["inner_border_color"],
            width=1
        )

        # 3. 金ハイライト線
        hx1 = ix1 + p["inner_border_width"]
        hy1 = iy1 + p["inner_border_width"]
        hx2 = ix2 - p["inner_border_width"]
        hy2 = iy2 - p["inner_border_width"]

        self._draw_rounded_outline(
            hx1, hy1, hx2, hy2,
            radius=max(2, ir - 2),
            outline=p["highlight_line_color"],
            width=p["highlight_line_width"]
        )

        # 4. さらに内側の濃い線
        line_gap = 2
        self._draw_rounded_outline(
            hx1 + line_gap, hy1 + line_gap, hx2 - line_gap, hy2 - line_gap,
            radius=max(2, ir - 4),
            outline=p["inner_line_color"],
            width=p["inner_line_width"]
        )

        # 5. 本体領域
        content_gap = 4
        bx1 = hx1 + line_gap + content_gap
        by1 = hy1 + line_gap + content_gap
        bx2 = hx2 - line_gap - content_gap
        by2 = hy2 - line_gap - content_gap
        br = max(2, ir - 7)

        self._draw_vertical_gradient_rounded(
            bx1, by1, bx2, by2,
            radius=br,
            color_stops=p["bg_colors"]
        )

        # 6. 上部の光沢（細め）
        gloss_h = max(4, int((by2 - by1) * 0.16))
        self._draw_vertical_gradient_rounded(
            bx1 + 1, by1 + 1, bx2 - 1, by1 + gloss_h,
            radius=max(2, br - 1),
            color_stops=p["gloss_colors"],
            alpha_fade=True
        )

        # 7. 左右ひし形
        ds = p["diamond_size"]
        dleft_x = bx1 + p["diamond_offset"]
        dright_x = bx2 - p["diamond_offset"]
        dy = (by1 + by2) / 2 + 1

        self._draw_diamond(dleft_x, dy, ds, p["diamond_color"])
        self._draw_diamond(dright_x, dy, ds, p["diamond_color"])

        # 8. テキスト
        banner_font = tkfont.Font(
            family=p["font_family"],
            size=p["font_size"],
            weight=p["font_weight"]
        )

        cx = w / 2
        cy = h / 2 - 1

        self._draw_outlined_text(
            cx=cx,
            cy=cy,
            text=p["text"],
            font=banner_font,
            fill=p["text_color"],
            outline_color=p["text_outline_color"],
            outline_size=p["text_outline_size"],
            shadow_color=p["text_shadow_color"],
            shadow_offset=p["text_shadow_offset"],
        )

    def _draw_outlined_text(
        self,
        cx,
        cy,
        text,
        font,
        fill,
        outline_color,
        outline_size=0,
        shadow_color="#000000",
        shadow_offset=(1, 1),
    ):
        sx, sy = shadow_offset

        # 影
        self.create_text(
            cx + sx, cy + sy,
            text=text,
            font=font,
            fill=shadow_color
        )

        # 縁取り
        if outline_size > 0:
            offsets = self._outline_offsets(outline_size)
            for dx, dy in offsets:
                self.create_text(
                    cx + dx, cy + dy,
                    text=text,
                    font=font,
                    fill=outline_color
                )

        # 本文
        self.create_text(
            cx, cy,
            text=text,
            font=font,
            fill=fill
        )

    def _outline_offsets(self, radius):
        result = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= radius + 0.15:
                    result.append((dx, dy))
        return result

    def _draw_diamond(self, cx, cy, size, color):
        self.create_polygon(
            cx, cy - size,
            cx + size, cy,
            cx, cy + size,
            cx - size, cy,
            fill=color,
            outline=""
        )

    def _draw_rounded_rect(self, x1, y1, x2, y2, radius=10, fill="", outline="", width=1):
        radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)

        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=outline,
            width=width
        )

    def _draw_rounded_outline(self, x1, y1, x2, y2, radius=10, outline="", width=1):
        radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)

        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill="",
            outline=outline,
            width=width
        )

    def _draw_vertical_gradient_rounded(self, x1, y1, x2, y2, radius, color_stops, alpha_fade=False):
        height = max(1, int(y2 - y1))
        radius = int(min(radius, (x2 - x1) / 2, height / 2))

        for i in range(height):
            t = i / max(1, height - 1)
            color = self._interp_stops(color_stops, t)

            if i < radius:
                dy = radius - i
                inset = radius - int((max(radius * radius - dy * dy, 0)) ** 0.5)
            elif i >= height - radius:
                dy = i - (height - radius - 1)
                inset = radius - int((max(radius * radius - dy * dy, 0)) ** 0.5)
            else:
                inset = 0

            sx = x1 + inset
            ex = x2 - inset

            if alpha_fade:
                fade_ratio = 1.0 - (t * 0.75)
                bg_base = self["bg"]
                color = self._mix_hex(color, bg_base, 1.0 - fade_ratio)

            self.create_line(sx, y1 + i, ex, y1 + i, fill=color)

    def _interp_stops(self, stops, t):
        stops = sorted(stops, key=lambda x: x[0])

        if t <= stops[0][0]:
            return stops[0][1]
        if t >= stops[-1][0]:
            return stops[-1][1]

        for idx in range(len(stops) - 1):
            t1, c1 = stops[idx]
            t2, c2 = stops[idx + 1]
            if t1 <= t <= t2:
                local_t = (t - t1) / (t2 - t1) if t2 != t1 else 0
                return self._lerp_hex(c1, c2, local_t)

        return stops[-1][1]

    def _hex_to_rgb(self, value):
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(self, rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _lerp_hex(self, c1, c2, t):
        r1, g1, b1 = self._hex_to_rgb(c1)
        r2, g2, b2 = self._hex_to_rgb(c2)
        rgb = (
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
        return self._rgb_to_hex(rgb)

    def _mix_hex(self, c1, c2, ratio):
        return self._lerp_hex(c1, c2, ratio)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("TitleBanner demo")
    root.configure(bg="#efe5d2")

    frame = tk.Frame(root, bg="#efe5d2", padx=16, pady=16)
    frame.pack(fill="both", expand=True)

    banner = TitleBanner(
        frame,
        width=560,
        height=54,
        text="挑戦状が届いています！",
    )
    banner.pack(pady=10)

    root.mainloop()