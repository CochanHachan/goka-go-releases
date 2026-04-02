#!/usr/bin/env python3
"""Reusable glossy 3D button widget for Tkinter applications."""
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFilter


class GlossyButton(tk.Canvas):
    """A custom Canvas-based button with 3D appearance, gloss, and focus highlight.

    Usage::

        import tkinter as tk
        from glossy_button import GlossyButton

        root = tk.Tk()
        btn = GlossyButton(root, text="OK", width=150, height=40,
                           base_color=(50, 100, 200),
                           command=lambda: print("clicked"))
        btn.pack(pady=20)
        root.mainloop()
    """

    def __init__(self, master, text="Button", width=180, height=44,
                 base_color=(60, 160, 60), text_color="white",
                 font=("Yu Gothic UI", 13, "bold"), command=None,
                 focus_border_width=3, focus_border_color=None,
                 depth=1.0, **kwargs):
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, borderwidth=0, **kwargs)
        self._text = text
        self._width = width
        self._height = height
        self._base_color = base_color
        self._text_color = text_color
        self._font = font
        self._command = command
        self._focus_border_width = focus_border_width
        self._focus_border_color = focus_border_color
        self._depth = max(0.0, depth)
        self._state = "normal"  # normal, hover, pressed, focused

        # Pre-render button images for each state
        self._images = {}
        self._build_images()

        # Draw initial state
        self._draw("normal")

        # Bind events
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Return>", self._on_key_activate)
        self.bind("<space>", self._on_key_activate)

        # Make focusable
        self.configure(takefocus=True)

    def _lighten(self, color, amount=30):
        return tuple(min(255, c + amount) for c in color)

    def _darken(self, color, amount=30):
        return tuple(max(0, c - amount) for c in color)

    def _blend(self, c1, c2, t):
        """Linearly blend two RGB tuples. t=0 gives c1, t=1 gives c2."""
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    def _smooth(self, t):
        """Smoothstep interpolation for natural transitions."""
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _calc_gradient(self, base, t, is_pressed, bot_override=None):
        """Calculate gradient color at position t (0..1) with smooth transitions."""
        d = self._depth
        if is_pressed:
            top_color = self._darken(base, int(25 * d))
            bot_color = self._darken(base, int(10 * d))
            return self._blend(top_color, bot_color, self._smooth(t))
        else:
            highlight = self._lighten(base, int(50 * d))
            bot_color = bot_override if bot_override is not None else self._darken(base, int(30 * d))
            return self._blend(highlight, bot_color, self._smooth(t))

    def _render_button(self, base, is_pressed=False, focus_border=False):
        """Render a glossy 3D button image using Pillow."""
        scale = 5
        w, h = self._width * scale, self._height * scale
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        radius = 8 * scale

        # Button body
        margin = 2 * scale
        top = margin if not is_pressed else margin + 1 * scale
        bottom = h - margin if not is_pressed else h - margin + 1 * scale
        body_rect = [margin, top, w - margin, bottom]

        # Outer border (changes color on focus)
        if focus_border:
            border_color = self._focus_border_color if self._focus_border_color is not None else (80, 140, 220)
        else:
            border_color = self._darken(base, 60)
        draw.rounded_rectangle(body_rect, radius=radius, fill=border_color)

        # When focused, ensure gradient bottom always contrasts with border
        bot_override = None
        if focus_border:
            bot_override = self._lighten(border_color, 30)

        # Inner body with smooth gradient
        bw = self._focus_border_width * scale if focus_border else scale
        inner = [margin + bw, top + bw, w - margin - bw, bottom - bw]
        inner_radius = max(1, radius - bw)

        # Rounded corner mask
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(inner, radius=inner_radius, fill=255)

        # Create body with gradient and apply mask
        body_only = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        body_draw = ImageDraw.Draw(body_only)
        body_h = inner[3] - inner[1]
        for y_off in range(body_h):
            t = y_off / max(1, body_h - 1)
            yy = inner[1] + y_off
            r, g, b = self._calc_gradient(base, t, is_pressed, bot_override)
            body_draw.line([(inner[0], yy), (inner[2], yy)],
                           fill=(r, g, b, 255))

        body_masked = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        body_masked.paste(body_only, mask=mask)

        # Composite border fill + gradient body
        border_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(border_layer).rounded_rectangle(
            body_rect, radius=radius, fill=border_color)
        img = Image.alpha_composite(img, border_layer)
        img = Image.alpha_composite(img, body_masked)

        # Subtle glossy highlight (soft ellipse, top area)
        d = self._depth
        if not is_pressed and d > 0:
            gloss = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gloss_h = body_h // 3
            gloss_alpha = min(255, int(35 * d))
            ImageDraw.Draw(gloss).ellipse(
                [inner[0] + 4 * scale, inner[1],
                 inner[2] - 4 * scale, inner[1] + gloss_h],
                fill=(255, 255, 255, gloss_alpha)
            )
            gloss = gloss.filter(ImageFilter.GaussianBlur(radius=2 * scale))
            img = Image.alpha_composite(img, gloss)

        # Thin top edge highlight
        if d > 0:
            hl_alpha = min(255, int((50 if not is_pressed else 20) * d))
            hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(hl).rounded_rectangle(
                [inner[0] + scale, inner[1], inner[2] - scale, inner[1] + scale],
                radius=max(1, inner_radius // 2),
                fill=(255, 255, 255, hl_alpha)
            )
            img = Image.alpha_composite(img, hl)

        return img.resize((self._width, self._height), Image.LANCZOS)

    def _build_images(self):
        """Pre-render all button state images."""
        base = self._base_color
        hover = self._lighten(base, 20)
        pressed = self._darken(base, 20)
        self._images["normal"] = ImageTk.PhotoImage(self._render_button(base))
        self._images["hover"] = ImageTk.PhotoImage(self._render_button(hover))
        self._images["pressed"] = ImageTk.PhotoImage(
            self._render_button(pressed, is_pressed=True))
        self._images["focused"] = ImageTk.PhotoImage(
            self._render_button(base, focus_border=True))
        self._images["focused_hover"] = ImageTk.PhotoImage(
            self._render_button(hover, focus_border=True))

    def _draw(self, state):
        self.delete("all")
        img_key = state if state in self._images else "normal"
        self.create_image(0, 0, anchor="nw", image=self._images[img_key])
        cx, cy = self._width // 2, self._height // 2
        if state == "pressed":
            cy += 1
        # Text shadow for depth
        self.create_text(cx + 1, cy + 1, text=self._text,
                         font=self._font, fill="#333333", anchor="center")
        self.create_text(cx, cy, text=self._text,
                         font=self._font, fill=self._text_color, anchor="center")

    def _on_enter(self, event):
        if self._state == "focused":
            self._draw("focused_hover")
        else:
            self._state = "hover"
            self._draw("hover")

    def _on_leave(self, event):
        if self._state == "focused" or self.focus_get() == self:
            self._state = "focused"
            self._draw("focused")
        else:
            self._state = "normal"
            self._draw("normal")

    def _on_press(self, event):
        self._state = "pressed"
        self.focus_set()
        self._draw("pressed")

    def _on_release(self, event):
        self._state = "focused"
        if 0 <= event.x < self._width and 0 <= event.y < self._height:
            self._draw("focused_hover")
        else:
            self._draw("focused")
        if self._command and 0 <= event.x < self._width and 0 <= event.y < self._height:
            self._command()

    def _on_focus_in(self, event):
        if self._state == "pressed":
            return
        self._state = "focused"
        mx = self.winfo_pointerx() - self.winfo_rootx()
        my = self.winfo_pointery() - self.winfo_rooty()
        if 0 <= mx < self._width and 0 <= my < self._height:
            self._draw("focused_hover")
        else:
            self._draw("focused")

    def _on_focus_out(self, event):
        mx = self.winfo_pointerx() - self.winfo_rootx()
        my = self.winfo_pointery() - self.winfo_rooty()
        if 0 <= mx < self._width and 0 <= my < self._height:
            self._state = "hover"
            self._draw("hover")
        else:
            self._state = "normal"
            self._draw("normal")

    def _on_key_activate(self, event):
        """Activate button via Enter or Space key."""
        self._draw("pressed")
        self.after(100, lambda: self._draw("focused"))
        if self._command:
            self._command()
