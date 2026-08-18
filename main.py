import json
import math
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageTk

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
CONFIG_PATH = Path(__file__).parent / "groups.json"

KEYS = [str(i) for i in range(1, 10)] + [chr(c) for c in range(ord("a"), ord("z") + 1)]

DEFAULT_GROUPS = {
    "type_side": {
        "old_front": {"key": "1", "front": True},
        "old_back": {"key": "2", "front": False},
        "new_front": {"key": "3", "front": True},
        "new_back": {"key": "4", "front": False},
        "new_back_front": {"key": "5", "front": False},
        "not_card": {"key": "6", "front": False},
    },
}


def load_config():
    if CONFIG_PATH.is_file():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    config = {"groups": DEFAULT_GROUPS}
    save_config(config)
    return config


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def list_images(folder):
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS)


def letterbox(img, max_side=900):
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    return img


def rot_cw(img, k):
    k = k % 4
    if k == 0:
        return img
    if k == 1:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if k == 2:
        return cv2.rotate(img, cv2.ROTATE_180)
    return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)


def lb_to_disp(lx, ly, rot, lb_w, lb_h):
    """Map a point from the letterboxed (pre-rotation) image to display pixel coords."""
    if rot == 1:
        return lb_h - 1 - ly, lx
    if rot == 2:
        return lb_w - 1 - lx, lb_h - 1 - ly
    if rot == 3:
        return ly, lb_w - 1 - lx
    return lx, ly


def disp_to_lb(x, y, rot, lb_w, lb_h):
    """Map a display pixel back to letterboxed (pre-rotation) image coords."""
    if rot == 1:
        return y, lb_h - 1 - x
    if rot == 2:
        return lb_w - 1 - x, lb_h - 1 - y
    if rot == 3:
        return lb_w - 1 - y, x
    return x, y


def disp_dims(lb_w, lb_h, rot):
    if rot in (1, 3):
        return lb_h, lb_w
    return lb_w, lb_h


def norm_to_disp(nx, ny, rot, lb_w, lb_h, ow, oh, scale=1.0):
    lx = nx * lb_w
    ly = ny * lb_h
    dx, dy = lb_to_disp(lx, ly, rot, lb_w, lb_h)
    return dx * scale, dy * scale


def disp_to_norm(x, y, rot, lb_w, lb_h, ow, oh, scale=1.0):
    lx, ly = disp_to_lb(x / scale, y / scale, rot, lb_w, lb_h)
    ox = lx / lb_w * ow
    oy = ly / lb_h * oh
    return max(0.0, min(1.0, ox / ow)), max(0.0, min(1.0, oy / oh))


COLORS = [
    (0, 200, 255),
    (0, 255, 0),
    (255, 0, 0),
    (255, 0, 255),
    (0, 255, 255),
    (128, 0, 255),
    (0, 128, 255),
    (255, 255, 0),
]

UI = {
    "bg": "#1b1d21",
    "panel": "#24262b",
    "button": "#33373f",
    "button_hover": "#3e434d",
    "button_active": "#24262b",
    "button_text": "#e8eaed",
    "text": "#e8eaed",
    "muted": "#9aa1a9",
    "accent": "#3d7bfd",
    "accent_hover": "#5290ff",
    "accent_text": "#ffffff",
    "field": "#15171a",
    "border": "#0e0f12",
    "canvas": "#0e0f11",
    "tip_bg": "#2c2f36",
    "tip_fg": "#e8eaed",
    "tip_border": "#4a4f59",
    "warning": "#e0a13d",
    "accent_pressed": "#3267d0",
    "danger": "#e5484d",
    "danger_hover": "#ef6267",
    "danger_pressed": "#c23a40",
    "danger_text": "#ffffff",
}


def rounded_photo(w, h, radius, fill, border=None, border_w=1, ss=2):
    """Render a rounded-rect PNG at 2x supersampling for crisp edges."""
    W, H = w * ss, h * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius * ss,
                        fill=fill, outline=border, width=border_w * ss)
    return ImageTk.PhotoImage(img.resize((w, h), Image.Resampling.LANCZOS))


def theme_tree(widget):
    cls = widget.winfo_class()
    if cls in ("Frame", "Toplevel", "Tk", "LabelFrame"):
        widget.configure(bg=UI["bg"])
    elif cls == "Label":
        widget.configure(bg=UI["bg"], fg=UI["text"])
    elif cls == "Button":
        widget.configure(bg=UI["button"], fg=UI["button_text"],
                         activebackground=UI["button_hover"], activeforeground=UI["button_text"],
                         relief=tk.FLAT, bd=0, highlightthickness=1,
                         highlightbackground=UI["border"], highlightcolor=UI["accent"],
                         padx=7, pady=2, cursor="hand2")
    elif cls in ("Entry", "Spinbox"):
        widget.configure(bg=UI["field"], fg=UI["text"], insertbackground=UI["text"],
                         relief=tk.FLAT, highlightthickness=1, highlightbackground=UI["border"],
                         highlightcolor=UI["accent"])
    elif cls == "Listbox":
        widget.configure(bg=UI["field"], fg=UI["text"], relief=tk.FLAT, bd=0,
                         highlightthickness=1, highlightbackground=UI["border"],
                         highlightcolor=UI["border"], selectbackground=UI["accent"],
                         selectforeground=UI["accent_text"], activestyle="none")
    elif cls == "Checkbutton":
        widget.configure(bg=UI["bg"], fg=UI["text"], activebackground=UI["bg"],
                         activeforeground=UI["text"], selectcolor=UI["field"],
                         highlightthickness=0, bd=0, cursor="hand2")
    for child in widget.winfo_children():
        theme_tree(child)


def setup_ttk(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TCombobox", fieldbackground=UI["field"], background=UI["button"],
                    foreground=UI["text"], arrowcolor=UI["text"],
                    bordercolor=UI["border"], lightcolor=UI["border"], darkcolor=UI["border"])
    style.map("TCombobox",
              fieldbackground=[("readonly", UI["field"])],
              foreground=[("readonly", UI["text"])],
              background=[("readonly", UI["button"]), ("active", UI["button_hover"])],
              selectbackground=[("readonly", UI["field"])],
              selectforeground=[("readonly", UI["text"])])
    root.option_add("*TCombobox*Listbox.background", UI["field"])
    root.option_add("*TCombobox*Listbox.foreground", UI["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", UI["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", UI["accent_text"])


class AddClassDialog(tk.Toplevel):
    def __init__(self, parent, used_keys):
        super().__init__(parent)
        self.title("Add Class")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.used_keys = set(used_keys)

        frame = tk.Frame(self, padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Class name:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(frame, textvariable=self.name_var, width=24)
        self.name_entry.grid(row=0, column=1, sticky=tk.W, pady=4)

        tk.Label(frame, text="Shortcut key:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.key_var = tk.StringVar(value=self._next_key())
        tk.Label(frame, textvariable=self.key_var, width=8, anchor=tk.W).grid(row=1, column=1, sticky=tk.W, pady=4)

        self.front_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="Front class (save orientation rot_0..rot_3)",
                       variable=self.front_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=4)

        btns = tk.Frame(frame)
        btns.grid(row=3, column=0, columnspan=2, pady=(8, 0))
        ModernButton(btns, text="Add", style="accent", width=100,
                     command=self._ok).pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Cancel", width=100,
                     command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.name_entry.focus_set()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        theme_tree(self)

    def _next_key(self):
        for k in KEYS:
            if k not in self.used_keys:
                return k
        return ""

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Add Class", "Class name is required.", parent=self)
            return
        key = self.key_var.get()
        if key in self.used_keys:
            messagebox.showwarning("Add Class", f"Key '{key}' is already in use.", parent=self)
            return
        self.result = {"name": name, "key": key, "front": self.front_var.get()}
        self.destroy()


class ToolTip:
    def __init__(self, widget, text, delay_ms=400):
        self.widget = widget
        self.text = text
        self._tip = None
        self._after_show = None
        self._after_hide = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")
        widget.bind("<FocusOut>", self._leave, add="+")
        widget.bind("<Unmap>", self._leave, add="+")
        widget.bind("<Destroy>", self._destroyed, add="+")
        self._delay_ms = delay_ms

    def _enter(self, event=None):
        self._cancel_all()
        self._after_show = self.widget.after(self._delay_ms, self._show)

    def _leave(self, event=None):
        self._cancel_all()
        self._hide()

    def _cancel_all(self):
        for name in ("_after_show", "_after_hide"):
            aid = getattr(self, name, None)
            if aid is not None:
                try:
                    self.widget.after_cancel(aid)
                except tk.TclError:
                    pass
                setattr(self, name, None)

    def _show(self):
        self._after_show = None
        if self._tip is not None or not self.text:
            return
        w = self.widget
        try:
            if not w.winfo_exists():
                return
            x = w.winfo_rootx() + w.winfo_width() // 2
            y = w.winfo_rooty() + w.winfo_height() + 6
            tip = tk.Toplevel(w)
        except tk.TclError:
            return
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tip, text=self.text, bg=UI["tip_bg"], fg=UI["tip_fg"],
                         relief=tk.FLAT, bd=0, highlightthickness=1,
                         highlightbackground=UI["tip_border"],
                         padx=9, pady=4, font=("TkDefaultFont", 9))
        label.pack()
        self._tip = tip
        tip.bind("<Enter>", self._leave, add="+")
        tip.bind("<Leave>", self._leave, add="+")
        tip.bind("<ButtonPress>", self._leave, add="+")
        self._after_hide = self.widget.after(2500, self._hide)

    def _hide(self, event=None):
        self._cancel_all()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _destroyed(self, event=None):
        self._cancel_all()
        self._hide()


def _icon_groups(d, s, c):
    k = s / 24.0
    for x in (1, 13):
        for y in (1, 13):
            d.rounded_rectangle([x * k, y * k, (x + 10) * k, (y + 10) * k],
                                radius=3 * k, fill=c)


def _icon_prev(d, s, c):
    k = s / 24.0
    d.rectangle([2 * k, 6 * k, 4 * k, 18 * k], fill=c)
    d.polygon([(8 * k, 12 * k), (18 * k, 4 * k), (18 * k, 20 * k)], fill=c)


def _icon_next(d, s, c):
    k = s / 24.0
    d.rectangle([20 * k, 6 * k, 22 * k, 18 * k], fill=c)
    d.polygon([(16 * k, 12 * k), (6 * k, 4 * k), (6 * k, 20 * k)], fill=c)


def _icon_rotate(d, s, c):
    cx = cy = s / 2.0
    r = s / 2.0 - 3 * s / 24.0
    w = max(2, int(2.2 * s / 24.0))
    d.arc([cx - r, cy - r, cx + r, cy + r], start=250, end=430, fill=c, width=w)
    t1 = math.radians(70)
    px = cx + r * math.cos(t1)
    py = cy + r * math.sin(t1)
    tx, ty = -math.sin(t1), math.cos(t1)
    nx, ny = -math.cos(t1), -math.sin(t1)
    h = 7 * s / 24.0
    d.polygon([(px + tx * h, py + ty * h),
               (px - tx * h * 0.4 + nx * h * 0.5, py - ty * h * 0.4 + ny * h * 0.5),
               (px - tx * h * 0.4 - nx * h * 0.5, py - ty * h * 0.4 - ny * h * 0.5)], fill=c)


def _icon_skip(d, s, c):
    k = s / 24.0
    d.polygon([(8 * k, 12 * k), (4 * k, 4 * k), (4 * k, 20 * k)], fill=c)
    d.polygon([(17 * k, 12 * k), (13 * k, 4 * k), (13 * k, 20 * k)], fill=c)


def _icon_undo(d, s, c):
    cx = cy = s / 2.0
    r = s / 2.0 - 4 * s / 24.0
    w = max(2, int(2.2 * s / 24.0))
    d.arc([cx - r, cy - 3 * s / 24.0, cx + r, cy + 3 * s / 24.0],
          start=0, end=180, fill=c, width=w)
    d.polygon([(cx - r - 7 * s / 24.0, cy), (cx - r - 2 * s / 24.0, cy - 4 * s / 24.0),
               (cx - r - 2 * s / 24.0, cy + 4 * s / 24.0)], fill=c)


def _icon_polygon(d, s, c):
    k = s / 24.0
    d.polygon([(12 * k, 2 * k), (20 * k, 7 * k), (17 * k, 19 * k),
               (7 * k, 19 * k), (4 * k, 7 * k)],
              outline=c, width=max(2, int(2.2 * k)))


def _icon_whole(d, s, c):
    k = s / 24.0
    d.rounded_rectangle([2 * k, 3 * k, 22 * k, 21 * k], radius=2 * k,
                        outline=c, width=max(2, int(2.2 * k)))
    d.line([(5 * k, 14 * k), (9 * k, 9 * k), (12 * k, 12 * k), (16 * k, 7 * k)],
           fill=c, width=max(2, int(2.2 * k)))


def _icon_rect(d, s, c):
    k = s / 24.0
    d.rounded_rectangle([2 * k, 2 * k, 22 * k, 22 * k], radius=1.5 * k,
                        outline=c, width=max(2, int(2.2 * k)))


def _icon_save(d, s, c):
    k = s / 24.0
    d.rounded_rectangle([2 * k, 2 * k, 22 * k, 22 * k], radius=2 * k,
                        outline=c, width=max(2, int(2.2 * k)))
    d.rectangle([7 * k, 2 * k, 17 * k, 9 * k], fill=c)
    d.rectangle([7 * k, 13 * k, 17 * k, 22 * k], fill=c)


def _icon_zoom_reset(d, s, c):
    k = s / 24.0
    w = max(2, int(2.2 * k))
    d.ellipse([3 * k, 3 * k, 12 * k, 12 * k], outline=c, width=w)
    d.line([11 * k, 11 * k, 18 * k, 18 * k], fill=c, width=w)
    d.line([5 * k, 7.5 * k, 10 * k, 7.5 * k], fill=c, width=w)


def _icon_next_unlabeled(d, s, c):
    k = s / 24.0
    d.polygon([(13 * k, 12 * k), (5 * k, 4 * k), (5 * k, 20 * k)], fill=c)
    d.ellipse([17 * k, 3 * k, 23 * k, 9 * k], fill=c)


def _icon_quit(d, s, c):
    k = s / 24.0
    w = max(2, int(2.4 * k))
    d.ellipse([4 * k, 4 * k, 20 * k, 20 * k], outline=c, width=w)
    d.rectangle([11 * k, 1 * k, 13 * k, 8 * k], fill=c)


ICON_DRAWS = {
    "groups": _icon_groups,
    "prev": _icon_prev,
    "next": _icon_next,
    "rotate": _icon_rotate,
    "skip": _icon_skip,
    "undo": _icon_undo,
    "polygon": _icon_polygon,
    "whole": _icon_whole,
    "rect": _icon_rect,
    "save": _icon_save,
    "zoom_reset": _icon_zoom_reset,
    "next_unlabeled": _icon_next_unlabeled,
    "quit": _icon_quit,
}


def build_icons(sample_widget, pixel_size=20, icon_color=None):
    try:
        r, g, b = sample_widget.winfo_rgb(sample_widget.cget("bg"))
        dark = (r + g + b) / 3 > 0x7FFF
    except tk.TclError:
        dark = True
    main = icon_color or ((230, 233, 237) if dark else (58, 62, 68))
    icons = {}
    ss = pixel_size * 2
    for name, draw in ICON_DRAWS.items():
        layer = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        draw(ImageDraw.Draw(layer), ss, main)
        r, g, b, a = layer.split()
        shade = Image.new("L", layer.size, 0)
        shadow = Image.merge("RGBA", (shade, shade, shade, a)).transform(
            layer.size, Image.Transform.AFFINE, (1, 0, 0, 0, 1, 1),
            resample=Image.Resampling.NEAREST)
        img = Image.alpha_composite(shadow, layer)
        img = img.resize((pixel_size, pixel_size), Image.Resampling.LANCZOS)
        icons[name] = ImageTk.PhotoImage(img)
    return icons


class ModernButton(tk.Canvas):
    """Canvas-based rounded button with hover / pressed / active states."""

    _STYLES = {
        "default": {"bg": "button", "hover": "button_hover", "pressed": "button_active"},
        "accent": {"bg": "accent", "hover": "accent_hover", "pressed": "accent_pressed"},
        "danger": {"bg": "danger", "hover": "danger_hover", "pressed": "danger_pressed"},
    }

    def __init__(self, parent, command=None, text="", icon=None, icon_active=None,
                 badge=None, width=None, height=34, radius=10, tooltip=None,
                 style="default", font_size=10, parent_bg=None):
        bg = parent_bg or UI["bg"]
        self._command = command
        self._text = text
        self._icon = icon
        self._icon_active = icon_active
        self._badge = str(badge) if badge is not None else None
        self._style = style
        self._active = False
        self._hover = False
        self._pressed = False

        base = tkfont.nametofont("TkDefaultFont")
        fam = base.actual("family")
        sz = base.actual("size")
        self._font = tkfont.Font(family=fam, size=font_size)
        self._badge_font = tkfont.Font(family=fam, size=sz - 1, weight="bold")

        padx = 14
        icon_w = 20 if icon is not None else 0
        gap = 7 if (icon is not None and (text or self._badge)) else 0
        tw = self._font.measure(text) if text else 0
        bw = self._badge_font.measure(self._badge) + 16 if self._badge else 0
        gapb = 9 if (self._badge and (text or icon)) else 0
        self._content_w = icon_w + gap + tw + gapb + bw
        if icon is not None and not text and not self._badge:
            w = height
        else:
            w = width or max(height, int(padx * 2 + self._content_w) + 4)

        super().__init__(parent, width=w, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._h = height
        self._radius = min(radius, height // 2)
        self._bg_id = self.create_image(0, 0, anchor="nw")
        self._icon_id = self._text_id = None
        self._chip_photo = None
        self._icon_off = 0.0
        self._text_off = 0.0
        self._chip_off = 0.0
        self._chip_h = 0
        self._chip_w = 0

        off = 0.0
        if icon is not None:
            self._icon_id = self.create_image(0, height / 2)
            self._icon_off = off + icon_w / 2
            off += icon_w + gap
        if text:
            self._text_id = self.create_text(0, height / 2, text=text, font=self._font)
            self._text_off = off + tw / 2
            off += tw + gapb
        if self._badge:
            self._chip_h = height - 10
            self._chip_w = bw
            self._chip_off = off + bw / 2
            self._chip_photo = rounded_photo(bw, self._chip_h, self._chip_h // 2, UI["accent"])
            self.create_image(0, height / 2, image=self._chip_photo, tags="chip")
            self.create_text(0, height / 2, text=self._badge,
                             fill=UI["accent_text"], font=self._badge_font, tags="chip")

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", self._on_configure)
        if tooltip:
            ToolTip(self, tooltip)
        self._bw = w
        self._layout()
        self._refresh()

    def set_active(self, active):
        self._active = bool(active)
        self._refresh()

    def _layout(self):
        left = (self._bw - self._content_w) / 2
        if self._icon_id is not None:
            self.coords(self._icon_id, left + self._icon_off, self._h / 2)
        if self._text_id is not None:
            self.coords(self._text_id, left + self._text_off, self._h / 2)
        if self._chip_photo is not None:
            self.coords("chip", left + self._chip_off, self._h / 2)

    def _on_configure(self, e):
        if e.width > 0 and e.width != self._bw:
            self._bw = e.width
            self._layout()
            self._refresh()

    def _palette(self):
        if self._active:
            if self._style == "default":
                return (UI["accent"], UI["accent_hover"], UI["accent_pressed"],
                        UI["accent_text"], self._icon_active or self._icon)
            s = self._style
            return UI[s], UI[s + "_hover"], UI[s + "_pressed"], UI[s + "_text"], self._icon
        if self._style == "default":
            return (UI["button"], UI["button_hover"], UI["button_active"],
                    UI["button_text"], self._icon)
        s = self._style
        return UI[s], UI[s + "_hover"], UI[s + "_pressed"], UI[s + "_text"], self._icon

    def _refresh(self):
        if self._pressed:
            variant = "pressed"
        elif self._hover:
            variant = "hover"
        else:
            variant = "bg"
        bg, hover, pressed, text, icon = self._palette()
        fill = {"bg": bg, "hover": hover, "pressed": pressed}[variant]
        border = UI["accent"] if (self._active and self._style == "default") else UI["border"]
        self._photo = rounded_photo(self._bw, self._h, self._radius, fill, border=border)
        self.itemconfig(self._bg_id, image=self._photo)
        if self._icon_id is not None:
            self.itemconfig(self._icon_id, image=icon)
        if self._text_id is not None:
            self.itemconfig(self._text_id, fill=text)

    def _on_enter(self, e):
        self._hover = True
        self._refresh()

    def _on_leave(self, e):
        self._hover = False
        self._pressed = False
        self._refresh()

    def _on_press(self, e):
        self._pressed = True
        self._refresh()

    def _on_release(self, e):
        was = self._pressed
        self._pressed = False
        self._refresh()
        if was and self._command:
            self._command()


class Pill(tk.Canvas):
    """Small rounded chip label (mode / group badges)."""

    def __init__(self, parent, text, fill=UI["accent"], fg=UI["accent_text"],
                 parent_bg=None, font_size=9, padx=10, height=20):
        bg = parent_bg or UI["bg"]
        base = tkfont.nametofont("TkDefaultFont")
        fam = base.actual("family")
        f = tkfont.Font(family=fam, size=font_size, weight="bold")
        w = padx * 2 + f.measure(text) + 2
        super().__init__(parent, width=w, height=height, bg=bg, highlightthickness=0, bd=0)
        self._photo = rounded_photo(w, height, height // 2, fill)
        self.create_image(0, 0, anchor="nw", image=self._photo)
        self.create_text(w // 2, height // 2, text=text, fill=fg, font=f)


class ProgressBar(tk.Canvas):
    def __init__(self, parent, width=220, height=10, radius=5, parent_bg=None):
        bg = parent_bg or UI["bg"]
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self._pw, self._h, self._r = width, height, radius
        self._track = rounded_photo(width, height, radius, UI["field"],
                                    border=UI["border"], border_w=1)
        self.create_image(0, 0, anchor="nw", image=self._track)
        self._fill = None
        self._fill_id = None
        self._value = -1.0
        self.set(0.0)

    def set(self, value):
        value = max(0.0, min(1.0, value))
        if abs(value - self._value) < 0.005:
            return
        self._value = value
        fw = max(4, round(self._pw * value))
        self._fill = rounded_photo(fw, self._h, self._r, UI["accent"])
        if self._fill_id is None:
            self._fill_id = self.create_image(0, 0, anchor="nw", image=self._fill)
        else:
            self.itemconfig(self._fill_id, image=self._fill)


class SetupDialog(tk.Frame):
    def __init__(self, root, config, on_start, on_quit):
        super().__init__(root, padx=14, pady=14)
        self.root = root
        self.config = config
        self.groups = config["groups"]
        self.on_start = on_start
        self.on_quit = on_quit
        self.pack(fill=tk.BOTH, expand=True)
        self._build()
        self.refresh_groups()
        self._mode_manual = False
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_mode_selected())
        self.input_entry.bind("<KeyRelease>", lambda e: self._update_label_detection())
        self.output_entry.bind("<KeyRelease>", lambda e: self._update_label_detection())
        self._update_label_detection()
        theme_tree(self)
        self.hint_label.configure(fg=UI["warning"])

    def _build(self):
        tk.Label(self, text="Input folder (unlabeled images):").grid(row=0, column=0, sticky=tk.W)
        row = tk.Frame(self)
        row.grid(row=1, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(row, textvariable=self.input_var, width=44)
        self.input_entry.pack(side=tk.LEFT, padx=(0, 6))
        ModernButton(row, text="Browse...",
                     command=lambda: self._browse(self.input_var)).pack(side=tk.LEFT)

        tk.Label(self, text="Output folder (labels are saved here):").grid(row=2, column=0, sticky=tk.W)
        row2 = tk.Frame(self)
        row2.grid(row=3, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.output_var = tk.StringVar()
        self.output_entry = tk.Entry(row2, textvariable=self.output_var, width=44)
        self.output_entry.pack(side=tk.LEFT, padx=(0, 6))
        ModernButton(row2, text="Browse...",
                     command=lambda: self._browse(self.output_var)).pack(side=tk.LEFT)

        tk.Label(self, text="Group:").grid(row=4, column=0, sticky=tk.W)
        gframe = tk.Frame(self)
        gframe.grid(row=5, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.group_var = tk.StringVar()
        self.group_combo = ttk.Combobox(gframe, textvariable=self.group_var, state="readonly", width=42)
        self.group_combo.pack(side=tk.LEFT, padx=(0, 6))
        ModernButton(gframe, text="Manage Groups...",
                     command=self.manage_groups).pack(side=tk.LEFT)

        tk.Label(self, text="Mode:").grid(row=6, column=0, sticky=tk.W)
        mframe = tk.Frame(self)
        mframe.grid(row=7, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.mode_var = tk.StringVar(value="classification")
        self.mode_combo = ttk.Combobox(mframe, textvariable=self.mode_var, state="readonly",
                                       values=("classification", "yolo"), width=42)
        self.mode_combo.pack(side=tk.LEFT, padx=(0, 6))

        self.hint_label = tk.Label(self, text="", fg=UI["warning"], justify=tk.LEFT, anchor=tk.W,
                                   wraplength=480)
        self.hint_label.grid(row=8, column=0, sticky=tk.W, pady=(2, 6))

        btns = tk.Frame(self)
        btns.grid(row=9, column=0, pady=(12, 0))
        self.start_btn = ModernButton(btns, text="Start Labeling", style="accent",
                                      width=150, command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=4)
        ModernButton(btns, text="Quit", style="danger", width=100,
                     command=self.on_quit).pack(side=tk.LEFT, padx=4)

    def refresh_groups(self):
        self.group_combo["values"] = list(self.groups)
        current = self.group_var.get()
        if current in self.groups:
            return
        if current:
            self.group_var.set("")
        if self.groups:
            self.group_combo.current(0)

    def _browse(self, var):
        path = filedialog.askdirectory(parent=self.root, mustexist=True)
        if path:
            var.set(path)
            self._update_label_detection()

    def _on_mode_selected(self):
        self._mode_manual = True
        self._update_label_detection()

    def _count_existing_labels(self, input_dir, output_dir):
        if not input_dir.is_dir() or not output_dir.is_dir():
            return 0
        try:
            stems = {p.stem for p in list_images(input_dir)}
        except OSError:
            return 0
        if not stems:
            return 0
        return sum(1 for p in output_dir.glob("*.txt") if p.stem in stems)

    def _update_label_detection(self):
        in_str = self.input_var.get().strip()
        out_str = self.output_var.get().strip()
        if not in_str or not out_str:
            self.hint_label.configure(text="")
            return
        n = self._count_existing_labels(Path(in_str), Path(out_str))
        if n > 0:
            if not self._mode_manual:
                self.mode_var.set("yolo")
                mode_note = "Mode set to 'yolo' so the existing labels are drawn on the images."
            else:
                mode_note = "Switch to 'yolo' mode to draw the existing labels on the images."
            self.hint_label.configure(
                text=f"Detected {n} existing label file(s) in the output folder matching your images. "
                     f"{mode_note}",
                 fg=UI["warning"])
        else:
            self.hint_label.configure(text="")

    def manage_groups(self):
        GroupManager(self.root, self.config)
        self.refresh_groups()

    def _start(self):
        input_dir = Path(self.input_var.get().strip())
        output_dir = Path(self.output_var.get().strip())
        if not input_dir.is_dir():
            messagebox.showwarning("Setup", f"Input folder not found: {input_dir}", parent=self.root)
            return
        if not list_images(input_dir):
            messagebox.showwarning("Setup", f"No images to label in {input_dir}", parent=self.root)
            return
        if not str(output_dir):
            messagebox.showwarning("Setup", "Output folder is required.", parent=self.root)
            return
        group_name = self.group_var.get()
        if not group_name:
            messagebox.showwarning("Setup", "Select a group.", parent=self.root)
            return
        if not self.groups[group_name]:
            messagebox.showwarning("Setup", f"Group '{group_name}' has no classes.", parent=self.root)
            return
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Setup", f"Cannot create output folder: {e}", parent=self.root)
            return
        self.on_start({"group": group_name, "input": input_dir, "output": output_dir,
                       "mode": self.mode_var.get()})


class GroupManager(tk.Toplevel):
    def __init__(self, root, config):
        super().__init__(root)
        self.config = config
        self.groups = config["groups"]
        self.title("Class Groups")
        self.transient(root)
        self.geometry("560x420")
        self._build()
        self.refresh()
        self.grab_set()
        theme_tree(self)

    def _build(self):
        left = tk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 6), pady=12)
        tk.Label(left, text="Groups").pack(anchor=tk.W)
        self.group_list = tk.Listbox(left, height=14)
        self.group_list.pack(fill=tk.BOTH, expand=True)
        self.group_list.bind("<<ListboxSelect>>", lambda e: self.refresh_classes())
        gbtns = tk.Frame(left)
        gbtns.pack(fill=tk.X, pady=4)
        ModernButton(gbtns, text="New Group", width=110, command=self.new_group).pack(side=tk.LEFT, padx=2)
        ModernButton(gbtns, text="Delete Group", width=110, command=self.delete_group).pack(side=tk.LEFT, padx=2)

        right = tk.Frame(self)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 12), pady=12)
        tk.Label(right, text="Classes").pack(anchor=tk.W)
        self.class_list = tk.Listbox(right, height=14)
        self.class_list.pack(fill=tk.BOTH, expand=True)
        cbtns = tk.Frame(right)
        cbtns.pack(fill=tk.X, pady=4)
        ModernButton(cbtns, text="Add Class", width=110, command=self.add_class).pack(side=tk.LEFT, padx=2)
        ModernButton(cbtns, text="Remove Class", width=110, command=self.remove_class).pack(side=tk.LEFT, padx=2)

    def _current_group_name(self):
        sel = self.group_list.curselection()
        return self.group_list.get(sel[0]) if sel else None

    def refresh(self):
        self.group_list.delete(0, tk.END)
        for name in self.groups:
            self.group_list.insert(tk.END, name)
        self.refresh_classes()

    def refresh_classes(self):
        self.class_list.delete(0, tk.END)
        name = self._current_group_name()
        if name is None:
            return
        for cls, entry in self.groups[name].items():
            tag = "front" if entry["front"] else "     "
            self.class_list.insert(tk.END, f"[{entry['key']}] {cls}  ({tag})")

    def new_group(self):
        name = simpledialog.askstring("New Group", "Group name:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.groups:
            messagebox.showwarning("New Group", f"Group '{name}' already exists.", parent=self)
            return
        self.groups[name] = {}
        save_config(self.config)
        self.refresh()
        idx = list(self.groups).index(name)
        self.group_list.selection_clear(0, tk.END)
        self.group_list.selection_set(idx)
        self.group_list.see(idx)
        self.refresh_classes()

    def delete_group(self):
        name = self._current_group_name()
        if name is None:
            return
        if not messagebox.askyesno("Delete Group", f"Delete group '{name}'?", parent=self):
            return
        del self.groups[name]
        save_config(self.config)
        self.refresh()

    def add_class(self):
        name = self._current_group_name()
        if name is None:
            messagebox.showwarning("Add Class", "Select a group first.", parent=self)
            return
        used_keys = {e["key"] for e in self.groups[name].values()}
        dialog = AddClassDialog(self, used_keys)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        cls = dialog.result["name"]
        if cls in self.groups[name]:
            messagebox.showwarning("Add Class", f"Class '{cls}' already exists in this group.", parent=self)
            return
        self.groups[name][cls] = {"key": dialog.result["key"], "front": dialog.result["front"]}
        save_config(self.config)
        self.refresh_classes()

    def remove_class(self):
        name = self._current_group_name()
        if name is None:
            return
        sel = self.class_list.curselection()
        if not sel:
            return
        cls = self.groups[name].keys()
        removed = list(cls)[sel[0]]
        del self.groups[name][removed]
        save_config(self.config)
        self.refresh_classes()


class LabelerApp:
    def __init__(self, root, config, group_name, mode, input_dir, output_dir, orient_dir, files):
        self.root = root
        self.config = config
        self.group_name = group_name
        self.mode = mode
        group = config["groups"][group_name]
        self.classes = list(group.keys())
        self.keymap = {entry["key"]: cls for cls, entry in group.items()}
        self.class_keys = {cls: entry["key"] for cls, entry in group.items()}
        self.front_classes = {cls for cls, entry in group.items() if entry["front"]}

        self.input_dir = input_dir
        self.output_dir = output_dir
        self.orient_dir = orient_dir

        self.files = files
        self.i = 0
        self.rot = 0
        self.img = None
        self.history = []
        self.n_done = 0
        self.start = time.time()

        if self.mode == "yolo":
            self.staged = None
            self.polygons = []
            self.current = []
            self.current_cls = self.classes[0] if self.classes else None
            self.mouse_pos = None
            self.label_history = []
            self.rect_mode = False
            self.rect_start = None
        else:
            self.staged = output_dir / "._staged"
            self.staged.mkdir(parents=True, exist_ok=True)

        self.existing = self._scan_existing()
        self.class_buttons = {}
        self._photo = None
        self._base_photo = None
        self._img_item = None
        self._staged_current = False
        self.zoom = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._pan_origin = None
        self._pan_start = (0, 0)
        self._press_xy = None
        self._press_pan = (0, 0)
        self._panning = False
        self._scaled_photo = None
        self._scaled_scale = None
        self.rect_btn = None

        self._build_ui()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self._show_current()
        self.root.focus_force()

    def _existing_key(self, path):
        return path.stem if self.mode == "yolo" else path.name

    def _scan_existing(self):
        existing = {}
        if self.mode == "yolo":
            for p in self.output_dir.glob("*.txt"):
                existing[p.stem] = True
            return existing
        for cls in self.classes:
            folder = self.output_dir / cls
            if not folder.is_dir():
                continue
            for p in folder.rglob("*"):
                if p.is_file() and p.suffix.lower() in IMG_EXTS:
                    existing[p.name] = cls
        return existing

    def _build_ui(self):
        self.root.title(f"Labeler - {self.mode} - group: {self.group_name}")

        self._icons = build_icons(self.root, icon_color=(230, 233, 237))
        self._icons_white = build_icons(self.root, icon_color=(255, 255, 255))

        # ---- sidebar ----
        sidebar = tk.Frame(self.root, width=196, bg=UI["panel"])
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=UI["panel"])
        brand.pack(fill=tk.X, padx=14, pady=(16, 10))
        tk.Label(brand, text="Labeler", bg=UI["panel"], fg=UI["accent"],
                 font=("TkDefaultFont", 17, "bold")).pack(anchor=tk.W)
        tk.Label(brand, text=f"{self.mode}  ·  {self.group_name}", bg=UI["panel"],
                 fg=UI["muted"], font=("TkDefaultFont", 9)).pack(anchor=tk.W, pady=(2, 0))
        tk.Frame(sidebar, height=1, bg=UI["border"]).pack(fill=tk.X, padx=14, pady=8)

        nav = tk.Frame(sidebar, bg=UI["panel"])
        nav.pack(fill=tk.X, padx=12)

        def navbtn(icon, tip, command, style="default"):
            b = ModernButton(nav, command=command, icon=self._icons[icon],
                             icon_active=self._icons_white[icon], tooltip=tip,
                             style=style, height=36, parent_bg=UI["panel"])
            b.pack(fill=tk.X, pady=3)
            return b

        navbtn("groups", "Manage class groups", self.manage_groups)
        navbtn("next_unlabeled", "Next unlabeled image (n)", self.next_unlabeled)
        navbtn("zoom_reset", "Reset zoom", self.reset_zoom)

        tk.Frame(sidebar, bg=UI["panel"]).pack(fill=tk.BOTH, expand=True)
        navbtn("quit", "Quit (q)", self.quit, style="danger")

        # ---- main area ----
        main = tk.Frame(self.root, bg=UI["bg"])
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # header
        header = tk.Frame(main, bg=UI["panel"])
        header.pack(side=tk.TOP, fill=tk.X)
        hrow = tk.Frame(header, bg=UI["panel"])
        hrow.pack(fill=tk.X, padx=14, pady=8)
        mode_label = "YOLO Mode" if self.mode == "yolo" else "Classification Mode"
        Pill(hrow, text=mode_label, parent_bg=UI["panel"]).pack(side=tk.LEFT)
        tk.Label(hrow, text=f"Group: {self.group_name}", bg=UI["panel"], fg=UI["muted"]).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(hrow, text=f"Classes: {', '.join(self.classes)}", bg=UI["panel"], fg=UI["muted"]).pack(side=tk.LEFT, padx=(10, 0))
        self.done_label = tk.Label(hrow, text="", bg=UI["panel"], fg=UI["muted"])
        self.done_label.pack(side=tk.LEFT, padx=(16, 0))
        tk.Label(hrow, text="Progress", bg=UI["panel"], fg=UI["muted"]).pack(side=tk.RIGHT, padx=(0, 8))
        self.progress_label = tk.Label(hrow, text="", bg=UI["panel"], fg=UI["text"],
                                       font=("TkDefaultFont", 10, "bold"), anchor=tk.E)
        self.progress_label.pack(side=tk.RIGHT, padx=(12, 4))
        self.progress_bar = ProgressBar(hrow, width=200, height=10, parent_bg=UI["panel"])
        self.progress_bar.pack(side=tk.RIGHT, pady=4)
        tk.Frame(header, height=1, bg=UI["border"]).pack(fill=tk.X)

        # toolbar
        toolbar = tk.Frame(main, bg=UI["bg"])
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        def tbutton(icon, tip, command, side=tk.LEFT):
            btn = ModernButton(toolbar, command=command, icon=self._icons[icon],
                               icon_active=self._icons_white[icon], tooltip=tip, height=34)
            btn.pack(side=side, padx=3)
            return btn

        tbutton("prev", "Previous image (Left)", self.prev)
        tbutton("next", "Next image (Right)", self.next_image)
        tbutton("rotate", "Rotate clockwise (r)", self.rotate)
        tbutton("skip", "Skip image (s)", self.skip)
        tbutton("undo", "Undo (u)", self.undo)
        if self.mode == "yolo":
            tbutton("polygon", "Close polygon (c)", self.close_polygon)
            tbutton("whole", "Annotate whole image (w)", self.annotate_whole_image)
            self.rect_btn = tbutton("rect", "Rectangle: 2 clicks (toggle)", self.toggle_rect_mode)
            tbutton("save", "Save & next image (Enter)", self.save_next)
        tbutton("next_unlabeled", "Next unlabeled image (n)", self.next_unlabeled)

        self.display = tk.Canvas(main, bg=UI["canvas"], highlightthickness=0)
        self.display.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.display.bind("<Configure>", lambda e: self._redraw_overlay())
        self.display.bind("<MouseWheel>", self.on_wheel)
        self.display.bind("<Button-4>", lambda e: self._zoom_around(e.x, e.y, 1.25))
        self.display.bind("<Button-5>", lambda e: self._zoom_around(e.x, e.y, 0.8))
        self.display.bind("<Button-2>", self.on_pan_start)
        self.display.bind("<B2-Motion>", self.on_pan_move)
        self.display.bind("<ButtonRelease-2>", self.on_pan_release)
        self.display.bind("<Button-1>", self.on_button_press)
        self.display.bind("<ButtonRelease-1>", self.on_button_release)
        self.display.bind("<B1-Motion>", self.on_pan_left)
        if self.mode == "yolo":
            self.display.bind("<Button-3>", self.on_close_polygon)
            self.display.bind("<Motion>", self.on_hover)

        self.class_bar = tk.Frame(main, bg=UI["bg"])
        self._rebuild_class_bar()

        self.status = tk.Label(main, anchor=tk.W, relief=tk.FLAT, bd=0, bg=UI["panel"],
                               fg=UI["muted"], highlightthickness=1,
                               highlightbackground=UI["border"])
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self.class_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
        self._update_class_highlight()

    def _rebuild_class_bar(self):
        for w in self.class_bar.winfo_children():
            w.destroy()
        self.class_buttons = {}
        for cls in self.classes:
            key = self.class_keys[cls]
            btn = ModernButton(self.class_bar, text=cls, badge=key, height=40,
                               command=lambda c=cls: self._on_class_press(c))
            btn.pack(side=tk.LEFT, padx=4)
            self.class_buttons[cls] = btn
        self._update_class_highlight()

    def _on_class_press(self, cls):
        if self.mode == "yolo":
            self.current_cls = cls
            self._update_class_highlight()
            self._redraw_overlay()
        else:
            self.assign(cls)

    def _update_class_highlight(self):
        for cls, btn in self.class_buttons.items():
            self._set_highlight(btn, self.mode == "yolo" and cls == self.current_cls)
        if self.rect_btn is not None:
            self._set_highlight(self.rect_btn, getattr(self, "rect_mode", False))

    def _set_highlight(self, btn, selected):
        if hasattr(btn, "set_active"):
            btn.set_active(selected)
            return
        btn.configure(bg=UI["accent"] if selected else UI["button"],
                      fg=UI["accent_text"] if selected else UI["button_text"],
                      activebackground=UI["accent_hover"] if selected else UI["button_hover"],
                      activeforeground=UI["accent_text"] if selected else UI["button_text"])

    def _bind_keys(self):
        for key in self.keymap:
            self.root.bind(key, lambda e, k=key: self._on_class_press(self.keymap[k]))
        self.root.bind("r", lambda e: self.rotate())
        self.root.bind("s", lambda e: self.skip())
        self.root.bind("u", lambda e: self.undo())
        self.root.bind("n", lambda e: self.next_unlabeled())
        self.root.bind("<Left>", lambda e: self.prev())
        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("q", lambda e: self.quit())
        if self.mode == "yolo":
            self.root.bind("<Return>", lambda e: self.save_next())
            self.root.bind("c", lambda e: self.close_polygon())
            self.root.bind("w", lambda e: self.annotate_whole_image())
            self.root.bind("<BackSpace>", lambda e: self.backspace_vertex())
            self.root.bind("<Escape>", lambda e: self.cancel_polygon())
        else:
            self.root.bind("<Escape>", lambda e: self.quit())

    def _hint(self):
        parts = [f"[{key}] {self.keymap[key]}" for key in sorted(self.keymap)]
        parts.append("←/→: prev/next")
        if self.mode == "yolo":
            parts.append("left click: add point  right/1st pt/c: close  w: whole image  "
                         "Bksp: remove  Esc: cancel  Enter: save&next")
            parts.append("Rect: 2 clicks = rectangle")
        parts.append("wheel: zoom  drag: pan")
        return "  ".join(parts)

    def _show_current(self):
        if self.i >= len(self.files):
            self._finish()
            return
        path = self.files[self.i]
        self._staged_current = False
        img = cv2.imread(str(path))
        if img is None:
            if self.mode != "yolo" and self.staged is not None:
                staged_path = self.staged / path.name
                if staged_path.is_file():
                    img = cv2.imread(str(staged_path))
                    self._staged_current = True
            if img is None:
                print(f"[skip] cannot read {path}")
                self.i += 1
                self.root.after(0, self._show_current)
                return
        self.img = img
        self.rot = 0
        self.zoom = 1.0
        self._pan_x = 0
        self._pan_y = 0
        if self.mode == "yolo":
            self.polygons = []
            self.current = []
            self.mouse_pos = None
            self.rect_start = None
            self._load_existing_polygons()
            self._update_class_highlight()
        self._render()

    def _load_existing_polygons(self):
        path = self.files[self.i]
        txt = self.output_dir / (path.stem + ".txt")
        if not txt.is_file():
            return
        for line in txt.read_text().splitlines():
            parts = line.split()
            if len(parts) < 7 or len(parts) % 2 == 0:
                continue
            cid = parts[0]
            if not cid.isdigit() or int(cid) >= len(self.classes):
                continue
            coords = parts[1:]
            pts = [(float(coords[j]), float(coords[j + 1])) for j in range(0, len(coords), 2)]
            self.polygons.append({"cls": self.classes[int(cid)], "pts": pts})

    def _render(self):
        lb = letterbox(self.img)
        self.lb_h, self.lb_w = lb.shape[:2]
        self._orig_dims = (self.img.shape[1], self.img.shape[0])
        self._base_bgr = rot_cw(lb, self.rot)
        self._scaled_scale = None
        self._base_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(self._base_bgr, cv2.COLOR_BGR2RGB)))
        self._photo = self._base_photo
        self._redraw_overlay()
        path = self.files[self.i]
        key = self._existing_key(path)
        existing = self.existing.get(key)
        if existing:
            label_info = "annotated" if self.mode == "yolo" else f"label: {existing}"
            self.status.configure(fg="#4ade80")
        else:
            label_info = "label: —"
            self.status.configure(fg=UI["muted"])
        if self.mode == "yolo":
            cls_info = f"class: {self.current_cls}  |  "
            extra = f"  |  {len(self.polygons)} poly, {len(self.current)} pts"
        else:
            cls_info = ""
            extra = ""
        self.status.configure(text=(
            f"({self.i + 1}/{len(self.files)})  {path.name}  |  {label_info}  |  "
            f"{cls_info}rotation {self.rot}  |  {self.n_done} done{extra}  |  {self._hint()}"
        ))
        self._update_header()

    def _update_header(self):
        total = len(self.files)
        idx = min(self.i + 1, total) if total else 0
        self.progress_label.configure(text=f"{idx} / {total}")
        self.progress_bar.set(idx / total if total else 0.0)
        self.done_label.configure(text=f"{self.n_done} done")

    def _canvas_img_pos(self):
        if self._img_item is None:
            return None
        try:
            return self.display.bbox(self._img_item)
        except tk.TclError:
            return None

    def _redraw_overlay(self):
        c = self.display
        c.delete("overlay")
        if self._base_photo is None:
            return
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw <= 1 or ch <= 1:
            return
        dw, dh = disp_dims(self.lb_w, self.lb_h, self.rot)
        fit = min(1.0, cw / dw, ch / dh)
        self._scale = fit * self.zoom
        sw, sh = max(1, round(dw * self._scale)), max(1, round(dh * self._scale))
        if self._scaled_scale != self._scale:
            img = Image.fromarray(self._base_bgr).resize((sw, sh), Image.LANCZOS)
            self._scaled_photo = ImageTk.PhotoImage(img)
            self._scaled_scale = self._scale
        if self.zoom <= 1.0 and self._scale >= 1.0:
            self._photo = self._base_photo
        else:
            self._photo = self._scaled_photo
        iw, ih = self._photo.width(), self._photo.height()
        if iw < cw:
            self._pan_x = (cw - iw) // 2
        else:
            self._pan_x = min(0, max(cw - iw, self._pan_x))
        if ih < ch:
            self._pan_y = (ch - ih) // 2
        else:
            self._pan_y = min(0, max(ch - ih, self._pan_y))
        x0, y0 = self._pan_x, self._pan_y
        if self._img_item is None:
            self._img_item = c.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            c.itemconfig(self._img_item, image=self._photo)
        c.coords(self._img_item, x0, y0)
        c.tag_lower(self._img_item)
        if self.mode != "yolo":
            return
        scale = self._scale
        lb_w, lb_h = self.lb_w, self.lb_h
        ow, oh = self._orig_dims
        for idx, poly in enumerate(self.polygons):
            color = COLORS[idx % len(COLORS)]
            tk_color = "#%02x%02x%02x" % (color[2], color[1], color[0])
            pts = [(x0 + dx, y0 + dy) for dx, dy in (
                norm_to_disp(nx, ny, self.rot, lb_w, lb_h, ow, oh, scale) for nx, ny in poly["pts"])]
            c.create_polygon(pts, outline=tk_color, width=2, fill=tk_color, stipple="gray50", tags="overlay")
            if pts:
                c.create_text(pts[0][0] + 8, pts[0][1] + 8, text=poly["cls"], fill=tk_color,
                              anchor="nw", font=("TkDefaultFont", 10, "bold"), tags="overlay")
        if self.current or self.mouse_pos:
            color = COLORS[self.classes.index(self.current_cls) % len(COLORS)] if self.current_cls else (255, 255, 255)
            tk_color = "#%02x%02x%02x" % (color[2], color[1], color[0])
            pts = [(x0 + dx, y0 + dy) for dx, dy in (
                norm_to_disp(nx, ny, self.rot, lb_w, lb_h, ow, oh, scale) for nx, ny in self.current)]
            for (px, py) in pts:
                c.create_oval(px - 4, py - 4, px + 4, py + 4, fill=tk_color, outline="", tags="overlay")
            if self.mouse_pos:
                line_pts = pts + [(x0 + self.mouse_pos[0], y0 + self.mouse_pos[1])]
            else:
                line_pts = pts
            if len(line_pts) >= 2:
                c.create_line(line_pts, fill=tk_color, width=2, tags="overlay")
        if self.rect_mode and self.rect_start is not None and self.mouse_pos:
            color = COLORS[self.classes.index(self.current_cls) % len(COLORS)] if self.current_cls else (255, 255, 255)
            tk_color = "#%02x%02x%02x" % (color[2], color[1], color[0])
            ax, ay = norm_to_disp(self.rect_start[0], self.rect_start[1], self.rot,
                                  lb_w, lb_h, ow, oh, scale)
            bx, by = self.mouse_pos
            c.create_rectangle(x0 + ax, y0 + ay, x0 + bx, y0 + by,
                               outline=tk_color, width=2, tags="overlay")

    def _event_to_disp(self, event):
        if self._base_photo is None:
            return None
        bbox = self._canvas_img_pos()
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox
        x = event.x - x0
        y = event.y - y0
        sw, sh = self._photo.width(), self._photo.height()
        if x < 0 or y < 0 or x > sw - 1 or y > sh - 1:
            return None
        return x, y

    def on_click(self, event):
        p = self._event_to_disp(event)
        if p is None or self.current_cls is None:
            return
        scale = self._scale
        if self.rect_mode:
            nx, ny = disp_to_norm(p[0], p[1], self.rot, self.lb_w, self.lb_h, *self._orig_dims, scale)
            if self.rect_start is None:
                self.rect_start = (nx, ny)
            else:
                ax, ay = self.rect_start
                self.polygons.append({"cls": self.current_cls,
                                      "pts": [(ax, ay), (nx, ay), (nx, ny), (ax, ny)]})
                self.rect_start = None
            self.mouse_pos = p
            self._redraw_overlay()
            return
        if len(self.current) >= 3:
            fx, fy = norm_to_disp(self.current[0][0], self.current[0][1], self.rot,
                                  self.lb_w, self.lb_h, *self._orig_dims, scale)
            if (p[0] - fx) ** 2 + (p[1] - fy) ** 2 <= 10 * 10:
                self.close_polygon()
                return
        nx, ny = disp_to_norm(p[0], p[1], self.rot, self.lb_w, self.lb_h, *self._orig_dims, scale)
        self.current.append((nx, ny))
        self.mouse_pos = p
        self._redraw_overlay()

    def on_button_press(self, event):
        self._press_xy = (event.x, event.y)
        self._press_pan = (self._pan_x, self._pan_y)
        self._panning = False

    def on_button_release(self, event):
        panning = self._panning
        self._press_xy = None
        self._panning = False
        self.display.config(cursor="")
        if panning:
            return
        if self.mode == "yolo":
            self.on_click(event)

    def on_hover(self, event):
        p = self._event_to_disp(event)
        if p is None:
            return
        self.mouse_pos = p
        self._redraw_overlay()

    def on_pan_left(self, event):
        if self._press_xy is None:
            return
        dx = event.x - self._press_xy[0]
        dy = event.y - self._press_xy[1]
        if not self._panning and dx * dx + dy * dy <= 36:
            return
        if not self._panning:
            self._panning = True
            self.display.config(cursor="hand2")
            self.mouse_pos = None
        self._pan_x = self._press_pan[0] + dx
        self._pan_y = self._press_pan[1] + dy
        self._redraw_overlay()

    def on_wheel(self, event):
        self._zoom_around(event.x, event.y, 1.25 if event.delta > 0 else 0.8)

    def _zoom_around(self, mx, my, factor):
        if self._base_photo is None:
            return
        new_zoom = min(20.0, max(1.0, self.zoom * factor))
        if new_zoom == self.zoom:
            return
        if self._img_item is not None:
            try:
                x0, y0, _, _ = self.display.bbox(self._img_item)
            except tk.TclError:
                x0 = y0 = 0
        else:
            x0 = y0 = 0
        dw, dh = disp_dims(self.lb_w, self.lb_h, self.rot)
        cw, ch = self.display.winfo_width(), self.display.winfo_height()
        fit = min(1.0, cw / dw, ch / dh)
        old_s = fit * self.zoom
        new_s = fit * new_zoom
        if old_s <= 0:
            return
        ix = (mx - x0) / old_s
        iy = (my - y0) / old_s
        if self.mouse_pos is not None:
            self.mouse_pos = (self.mouse_pos[0] * new_s / old_s, self.mouse_pos[1] * new_s / old_s)
        self.zoom = new_zoom
        self._pan_x = mx - ix * new_s
        self._pan_y = my - iy * new_s
        self._redraw_overlay()

    def reset_zoom(self):
        self.zoom = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._redraw_overlay()

    def on_pan_start(self, event):
        self._pan_origin = (event.x, event.y)
        self._pan_start = (self._pan_x, self._pan_y)
        self.display.config(cursor="hand2")

    def on_pan_move(self, event):
        if self._pan_origin is None:
            return
        self._pan_x = self._pan_start[0] + event.x - self._pan_origin[0]
        self._pan_y = self._pan_start[1] + event.y - self._pan_origin[1]
        self._redraw_overlay()

    def on_pan_release(self, event):
        self._pan_origin = None
        self.display.config(cursor="")

    def toggle_rect_mode(self):
        self.rect_mode = not self.rect_mode
        if not self.rect_mode:
            self.rect_start = None
        self._update_class_highlight()
        self._redraw_overlay()

    def close_polygon(self):
        if len(self.current) >= 3:
            self.polygons.append({"cls": self.current_cls, "pts": list(self.current)})
            self.current = []
        self.mouse_pos = None
        self._redraw_overlay()

    def on_close_polygon(self, event):
        self.close_polygon()

    def backspace_vertex(self):
        if self.rect_start is not None:
            self.rect_start = None
            self._redraw_overlay()
        elif self.current:
            self.current.pop()
            self._redraw_overlay()

    def cancel_polygon(self):
        if self.rect_mode:
            self.rect_mode = False
            self.rect_start = None
            self._update_class_highlight()
            self._redraw_overlay()
            return
        if self.current:
            self.current = []
            self.mouse_pos = None
            self._redraw_overlay()

    def annotate_whole_image(self):
        if self.mode != "yolo" or self.img is None:
            return
        if self.current_cls is None:
            return
        self.current = []
        self.mouse_pos = None
        self.polygons.append({"cls": self.current_cls, "pts": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]})
        self._redraw_overlay()

    def save_next(self):
        if self.i >= len(self.files):
            return
        if self.current:
            self.close_polygon()
        if self.rect_start is not None:
            self.rect_start = None
        path = self.files[self.i]
        txt = self._write_txt(path)
        self.label_history.append((path, txt))
        self.existing[self._existing_key(path)] = True
        self.n_done += 1
        self.i += 1
        print(f"[save] {path.name} -> {txt.name} ({len(self.polygons)} polygons, {self.n_done} done)")
        self._show_current()

    def _write_txt(self, path):
        txt = self.output_dir / (path.stem + ".txt")
        lines = []
        for poly in self.polygons:
            cid = self.classes.index(poly["cls"])
            coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in poly["pts"])
            lines.append(f"{cid} {coords}")
        if not lines and self.current_cls is not None:
            cid = self.classes.index(self.current_cls)
            lines.append(str(cid))
        txt.write_text("\n".join(lines) + ("\n" if lines else ""))
        return txt

    def _ensure_dirs(self, cls):
        (self.output_dir / cls).mkdir(parents=True, exist_ok=True)
        for k in range(4):
            (self.orient_dir / f"rot_{k}").mkdir(parents=True, exist_ok=True)

    def assign(self, cls):
        if self.i >= len(self.files):
            return
        path = self.files[self.i]
        img = self.img
        rot = self.rot
        self._ensure_dirs(cls)
        dst = self.output_dir / cls / path.name
        staged_path = self.staged / path.name
        orient_dst = None
        cv2.imwrite(str(dst), rot_cw(img, rot))
        if cls in self.front_classes:
            orient_dst = self.orient_dir / f"rot_{rot}" / path.name
            cv2.imwrite(str(orient_dst), img)
        if path.is_file():
            path.rename(staged_path)
        else:
            old_cls = self.existing.get(path.name)
            if old_cls and old_cls != cls:
                old_dst = self.output_dir / old_cls / path.name
                if old_dst.is_file():
                    old_dst.unlink()
                for k in range(4):
                    old_orient = self.orient_dir / f"rot_{k}" / path.name
                    if old_orient.is_file():
                        old_orient.unlink()
        self.history.append((path, staged_path, dst, orient_dst, rot, cls))
        self.existing[path.name] = cls
        self.n_done += 1
        self.i += 1
        print(f"[label] {path.name} -> {cls} (rot {rot})  ({self.n_done} done)")
        self._show_current()

    def rotate(self):
        if self.img is None:
            return
        self.rot = (self.rot + 1) % 4
        self._render()

    def skip(self):
        if self.i >= len(self.files):
            return
        print(f"[skip] {self.files[self.i].name}")
        self.i += 1
        self._show_current()

    def prev(self):
        if self.i <= 0:
            return
        self.i -= 1
        self._show_current()

    def next_image(self):
        if self.i >= len(self.files) - 1:
            return
        self.i += 1
        self._show_current()

    def _undo_yolo(self):
        if self.rect_start is not None:
            self.rect_start = None
            self._redraw_overlay()
            return
        if self.current:
            self.current = []
            self.mouse_pos = None
            self._render()
            return
        if self.polygons:
            self.polygons.pop()
            self._render()
            return
        if self.label_history:
            prev_path, txt = self.label_history.pop()
            if txt.is_file():
                txt.unlink()
            self.existing.pop(self._existing_key(prev_path), None)
            self.n_done = max(0, self.n_done - 1)
            self.i = max(0, self.i - 1)
            print(f"[undo] removed {txt.name}")
            self._show_current()
            return
        print("[undo] nothing to undo")

    def undo(self):
        if self.mode == "yolo":
            self._undo_yolo()
            return
        if not self.history:
            print("[undo] nothing to undo")
            return
        prev_orig, prev_staged, prev_dst, prev_orient_dst, _rot, _cls = self.history.pop()
        if prev_orient_dst is not None and prev_orient_dst.is_file():
            prev_orient_dst.unlink()
        if prev_dst.is_file():
            prev_dst.unlink()
        prev_staged.rename(prev_orig)
        self.existing.pop(prev_orig.name, None)
        print(f"[undo] moved {prev_dst.name} back to {prev_orig}")
        self._show_current()

    def next_unlabeled(self):
        for j in range(self.i, len(self.files)):
            if self._existing_key(self.files[j]) not in self.existing:
                self.i = j
                self._show_current()
                return
        print("[next] no unlabeled images remain")
        messagebox.showinfo("Next Unlabeled", "No unlabeled images remain.", parent=self.root)

    def manage_groups(self):
        GroupManager(self.root, self.config)

    def _cleanup(self):
        if self.mode == "yolo":
            return
        remaining = list_images(self.staged)
        for p in remaining:
            p.rename(self.input_dir / p.name)
        try:
            self.staged.rmdir()
        except OSError:
            pass
        if remaining:
            print(f"[info] restored {len(remaining)} staged files to {self.input_dir}")

    def _finish(self):
        elapsed = time.time() - self.start
        print(f"\nDone. {self.n_done} images in {elapsed:.0f}s.")
        self._cleanup()
        if self.mode == "yolo":
            messagebox.showinfo("Done",
                                f"Annotated {self.n_done} images in {elapsed:.0f}s.\n"
                                f"YOLO labels saved in {self.output_dir}")
        else:
            print(f"Check your labels in {self.output_dir}")
            print(f"Orientation classes in {self.orient_dir}")
            messagebox.showinfo("Done",
                                f"Labeled {self.n_done} images in {elapsed:.0f}s.\n"
                                f"Check your labels in {self.output_dir}")
        self.root.destroy()

    def quit(self):
        if self.mode == "yolo":
            if (self.polygons or self.current) and not messagebox.askyesno(
                    "Quit", "The current image has unsaved annotations that will be lost.\nQuit anyway?",
                    parent=self.root):
                return
            self.root.destroy()
            return
        if self.history and not messagebox.askyesno(
                "Quit", "Some labels are not yet finalized.\n"
                        "Files will be restored to the input folder and you can resume later.\n"
                        "Quit anyway?"):
            return
        self._cleanup()
        self.root.destroy()


def main():
    config = load_config()

    root = tk.Tk()
    root.configure(bg=UI["bg"])
    setup_ttk(root)
    root.geometry("640x400")
    root.title("Labeler Setup")

    def start_labeling(settings):
        group_name = settings["group"]
        mode = settings["mode"]
        input_dir = settings["input"]
        output_dir = settings["output"]
        orient_dir = output_dir.parent / "orientation"
        files = list_images(input_dir)
        for w in root.winfo_children():
            w.destroy()
        root.geometry("1000x800")
        LabelerApp(root, config, group_name, mode, input_dir, output_dir, orient_dir, files)

    SetupDialog(root, config, on_start=start_labeling, on_quit=root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
