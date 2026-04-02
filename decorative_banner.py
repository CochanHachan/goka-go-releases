#!/usr/bin/env python3
"""Reusable decorative banner widget for Tkinter applications.

Gold-bordered navy banner with elegant decorations, suitable for
notification headers, alerts, and important messages.
"""
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFont
import numpy as np
import os


class DecorativeBanner(tk.Canvas):
    """A custom Canvas-based banner with gold border, navy gradient
    background with horizontal shading, and decorative accents.

    Usage::

        import tkinter as tk
        from decorative_banner import DecorativeBanner

        root = tk.Tk()
        banner = DecorativeBanner(root, text="対局の申し込みです！",
                                  width=460, height=52)
        banner.pack(pady=20)
        root.mainloop()
    """

    # Font search paths -- bold gothic preferred (matching reference image)
    _FONT_CANDIDATES = [
        # Bold gothic (closest to reference image)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        # Windows gothic / bold
        "C:/Windows/Fonts/yugothb.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        # macOS
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴ ProN W6.otf",
        # Linux serif fallback
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/opentype/ipafont-mincho/ipam.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]

    def __init__(self, master, text="Banner", width=460, height=52,
                 font=None, font_size=None, text_color=(235, 210, 140),
                 text_stroke_color=(20, 15, 5),
                 border_color_top=(245, 220, 160),
                 border_color_bottom=(180, 150, 75),
                 bg_edge=(30, 35, 60), bg_center=(75, 90, 140),
                 line_color=(180, 160, 100), diamond_color=(210, 185, 120),
                 border_width=None,
                 **kwargs):
        # Canvas 1px wider/taller to prevent right/bottom edge clipping on Windows
        super().__init__(master, width=width + 1, height=height + 1,
                         highlightthickness=0, borderwidth=0, **kwargs)
        self._text = text
        self._width = width
        self._height = height
        self._font_spec = font
        self._font_size = font_size
        self._text_color = text_color
        self._text_stroke_color = text_stroke_color
        self._border_color_top = border_color_top
        self._border_color_bottom = border_color_bottom
        self._bg_edge = bg_edge
        self._bg_center = bg_center
        self._line_color = line_color
        self._diamond_color = diamond_color
        self._border_width = border_width  # None = auto

        self._photo = None
        self._render()

    def _find_font(self, size):
        """Find an available font, preferring user-specified font."""
        if self._font_spec is not None:
            if os.path.isfile(self._font_spec):
                try:
                    return ImageFont.truetype(self._font_spec, size)
                except (OSError, IOError):
                    pass
            try:
                return ImageFont.truetype(self._font_spec, size)
            except (OSError, IOError):
                pass

        for path in self._FONT_CANDIDATES:
            if os.path.isfile(path):
                try:
                    return ImageFont.truetype(path, size)
                except (OSError, IOError):
                    continue
        return ImageFont.load_default()

    @staticmethod
    def _smooth_np(t):
        """Vectorized smoothstep."""
        t = np.clip(t, 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    def _smooth(self, t):
        """Smoothstep for natural gradient transitions."""
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _blend(self, c1, c2, t):
        """Linearly blend two RGB tuples."""
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    def _render(self):
        """Render the banner image and display it on the canvas."""
        scale = 4
        sw, sh = self._width * scale, self._height * scale

        # Border width: user-specified or auto (proportional to height)
        if self._border_width is not None:
            bw = self._border_width * scale
        else:
            bw = max(2 * scale, sh // 14)  # thin border matching reference

        # --- Background with horizontal gradient (using numpy for speed) ---
        xs = np.arange(sw, dtype=np.float64)
        ys = np.arange(sh, dtype=np.float64)
        xx, yy = np.meshgrid(xs, ys)

        # Horizontal factor: 0 at edges, 1 at center (strong contrast)
        hx = xx / max(1, sw - 1)
        h_factor = self._smooth_np(1.0 - np.abs(hx - 0.5) * 2.0)

        # Subtle vertical factor (lighter at top)
        vy = yy / max(1, sh - 1)
        v_factor = (1.0 - vy) * 0.10

        t = np.clip(h_factor + v_factor, 0.0, 1.0)

        edge = np.array(self._bg_edge, dtype=np.float64)
        center = np.array(self._bg_center, dtype=np.float64)

        pixels = np.zeros((sh, sw, 4), dtype=np.uint8)
        for ch in range(3):
            pixels[:, :, ch] = np.clip(
                edge[ch] + (center[ch] - edge[ch]) * t, 0, 255
            ).astype(np.uint8)
        pixels[:, :, 3] = 255

        img = Image.fromarray(pixels, "RGBA")

        # --- Gold border with vertical gradient (using numpy) ---
        border_arr = np.zeros((sh, sw, 4), dtype=np.uint8)

        y_idx = np.arange(sh)[:, None]
        x_idx = np.arange(sw)[None, :]
        in_border = ((y_idx < bw) | (y_idx >= sh - bw) |
                     (x_idx < bw) | (x_idx >= sw - bw))

        bt = self._smooth_np(y_idx.astype(np.float64) / max(1, sh - 1))
        top_c = np.array(self._border_color_top, dtype=np.float64)
        bot_c = np.array(self._border_color_bottom, dtype=np.float64)

        # Horizontal brightness variation on border (brighter at center)
        hx_b = x_idx.astype(np.float64) / max(1, sw - 1)
        h_bright = self._smooth_np(1.0 - np.abs(hx_b - 0.5) * 2.0) * 0.22

        for ch in range(3):
            base = top_c[ch] + (bot_c[ch] - top_c[ch]) * bt
            bright = base + base * h_bright
            val = np.clip(bright, 0, 255).astype(np.uint8)
            border_arr[:, :, ch] = np.where(in_border, val, 0)
        border_arr[:, :, 3] = np.where(in_border, 255, 0).astype(np.uint8)

        border_layer = Image.fromarray(border_arr, "RGBA")
        img = Image.alpha_composite(img, border_layer)

        draw = ImageDraw.Draw(img)

        # --- Decorative gold lines (inside border, near top and bottom) ---
        line_alpha = 120
        line_fill = (*self._line_color, line_alpha)
        margin_y = max(3 * scale, int(bw * 0.6))
        line_y_top = bw + margin_y
        line_y_bot = sh - bw - margin_y
        line_x_start = bw + max(4 * scale, sw // 20)
        line_x_end = sw - bw - max(4 * scale, sw // 20)
        line_w = max(1, scale // 2)
        draw.line([(line_x_start, line_y_top), (line_x_end, line_y_top)],
                  fill=line_fill, width=line_w)
        draw.line([(line_x_start, line_y_bot), (line_x_end, line_y_bot)],
                  fill=line_fill, width=line_w)

        # --- Diamond decorations (left and right of text) ---
        ds = max(2 * scale, sh // 12)
        diamond_x_left = bw + max(6 * scale, sw // 18)
        diamond_x_right = sw - bw - max(6 * scale, sw // 18)
        cy = sh // 2
        for cx in [diamond_x_left, diamond_x_right]:
            dl = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            ImageDraw.Draw(dl).polygon(
                [(cx, cy - ds), (cx + ds, cy),
                 (cx, cy + ds), (cx - ds, cy)],
                fill=(*self._diamond_color, 200)
            )
            img = Image.alpha_composite(img, dl)

        # --- Text ---
        auto_font_size = (self._font_size * scale if self._font_size
                          else max(14, int(self._height * scale * 0.38)))
        pil_font = self._find_font(auto_font_size)

        txt = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt)
        bbox = td.textbbox((0, 0), self._text, font=pil_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (sw - tw) // 2
        ty = (sh - th) // 2 - bbox[1]

        # Text shadow (drawn first so it sits behind stroke and main text)
        td.text((tx + scale, ty + scale), self._text, font=pil_font,
                fill=(0, 0, 0, 100))

        # Text stroke (outline) for depth
        stroke_color = (*self._text_stroke_color, 220)
        for dx in (-scale, 0, scale):
            for dy in (-scale, 0, scale):
                if dx == 0 and dy == 0:
                    continue
                td.text((tx + dx, ty + dy), self._text, font=pil_font,
                        fill=stroke_color)

        # Main text
        td.text((tx, ty), self._text, font=pil_font,
                fill=(*self._text_color, 255))
        img = Image.alpha_composite(img, txt)

        # --- Downscale with antialiasing ---
        final = img.resize((self._width, self._height), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(final)
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)

    def update_text(self, text):
        """Update the displayed text and re-render."""
        self._text = text
        self._render()

    def update_size(self, width, height):
        """Update the banner size and re-render."""
        self._width = width
        self._height = height
        self.configure(width=width + 1, height=height + 1)
        self._render()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("DecorativeBanner Demo")
    root.configure(bg="#2c2c2c")
    root.geometry("550x350")

    tk.Label(root, text="DecorativeBanner Demo", fg="white", bg="#2c2c2c",
             font=("", 14, "bold")).pack(pady=(20, 10))

    b1 = DecorativeBanner(root, text="挑戦状が届いています！",
                          width=463, height=52, bg="#2c2c2c")
    b1.pack(pady=8)

    b2 = DecorativeBanner(root, text="対局の申し込みです！",
                          width=400, height=48, bg="#2c2c2c")
    b2.pack(pady=8)

    b3 = DecorativeBanner(root, text="あなたの番です", width=320, height=44,
                          bg="#2c2c2c")
    b3.pack(pady=8)

    b4 = DecorativeBanner(root, text="通知", width=180, height=38,
                          bg="#2c2c2c")
    b4.pack(pady=8)

    root.mainloop()
