import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

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
        tk.Button(btns, text="Add", width=10, command=self._ok).pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Cancel", width=10, command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.name_entry.focus_set()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

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

    def _build(self):
        tk.Label(self, text="Input folder (unlabeled images):").grid(row=0, column=0, sticky=tk.W)
        row = tk.Frame(self)
        row.grid(row=1, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(row, textvariable=self.input_var, width=44)
        self.input_entry.pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row, text="Browse...", command=lambda: self._browse(self.input_var)).pack(side=tk.LEFT)

        tk.Label(self, text="Output folder (labels are saved here):").grid(row=2, column=0, sticky=tk.W)
        row2 = tk.Frame(self)
        row2.grid(row=3, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.output_var = tk.StringVar()
        self.output_entry = tk.Entry(row2, textvariable=self.output_var, width=44)
        self.output_entry.pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row2, text="Browse...", command=lambda: self._browse(self.output_var)).pack(side=tk.LEFT)

        tk.Label(self, text="Group:").grid(row=4, column=0, sticky=tk.W)
        gframe = tk.Frame(self)
        gframe.grid(row=5, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.group_var = tk.StringVar()
        self.group_combo = ttk.Combobox(gframe, textvariable=self.group_var, state="readonly", width=42)
        self.group_combo.pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(gframe, text="Manage Groups...", command=self.manage_groups).pack(side=tk.LEFT)

        tk.Label(self, text="Mode:").grid(row=6, column=0, sticky=tk.W)
        mframe = tk.Frame(self)
        mframe.grid(row=7, column=0, sticky=tk.W + tk.E, pady=(2, 10))
        self.mode_var = tk.StringVar(value="classification")
        self.mode_combo = ttk.Combobox(mframe, textvariable=self.mode_var, state="readonly",
                                       values=("classification", "yolo"), width=42)
        self.mode_combo.pack(side=tk.LEFT, padx=(0, 6))

        self.hint_label = tk.Label(self, text="", fg="#b25c00", justify=tk.LEFT, anchor=tk.W,
                                   wraplength=480)
        self.hint_label.grid(row=8, column=0, sticky=tk.W, pady=(2, 6))

        btns = tk.Frame(self)
        btns.grid(row=9, column=0, pady=(12, 0))
        tk.Button(btns, text="Start Labeling", width=16, command=self._start).pack(side=tk.LEFT, padx=4)
        tk.Button(btns, text="Quit", width=10, command=self.on_quit).pack(side=tk.LEFT, padx=4)

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
                fg="#b25c00")
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

    def _build(self):
        left = tk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 6), pady=12)
        tk.Label(left, text="Groups").pack(anchor=tk.W)
        self.group_list = tk.Listbox(left, height=14)
        self.group_list.pack(fill=tk.BOTH, expand=True)
        self.group_list.bind("<<ListboxSelect>>", lambda e: self.refresh_classes())
        gbtns = tk.Frame(left)
        gbtns.pack(fill=tk.X, pady=4)
        tk.Button(gbtns, text="New Group", width=12, command=self.new_group).pack(side=tk.LEFT, padx=2)
        tk.Button(gbtns, text="Delete Group", width=12, command=self.delete_group).pack(side=tk.LEFT, padx=2)

        right = tk.Frame(self)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 12), pady=12)
        tk.Label(right, text="Classes").pack(anchor=tk.W)
        self.class_list = tk.Listbox(right, height=14)
        self.class_list.pack(fill=tk.BOTH, expand=True)
        cbtns = tk.Frame(right)
        cbtns.pack(fill=tk.X, pady=4)
        tk.Button(cbtns, text="Add Class", width=12, command=self.add_class).pack(side=tk.LEFT, padx=2)
        tk.Button(cbtns, text="Remove Class", width=12, command=self.remove_class).pack(side=tk.LEFT, padx=2)

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
        else:
            self.staged = output_dir / "._staged"
            self.staged.mkdir(parents=True, exist_ok=True)

        self.existing = self._scan_existing()
        self.class_buttons = {}
        self._photo = None
        self._base_photo = None
        self._img_item = None
        self._staged_current = False

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

        toolbar = tk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)
        tk.Button(toolbar, text="Groups...", command=self.manage_groups).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="◀ Prev (←)", command=self.prev).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Next (→)", command=self.next_image).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Rotate (r)", command=self.rotate).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Skip (s)", command=self.skip).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Undo (u)", command=self.undo).pack(side=tk.LEFT, padx=2)
        if self.mode == "yolo":
            tk.Button(toolbar, text="Close Polygon (c)", command=self.close_polygon).pack(side=tk.LEFT, padx=2)
            tk.Button(toolbar, text="Whole Image (w)", command=self.annotate_whole_image).pack(side=tk.LEFT, padx=2)
            tk.Button(toolbar, text="Save & Next (Enter)", command=self.save_next).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Next Unlabeled (n)", command=self.next_unlabeled).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Quit (q)", command=self.quit).pack(side=tk.RIGHT, padx=2)

        self.display = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.display.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.display.bind("<Configure>", lambda e: self._redraw_overlay())

        if self.mode == "yolo":
            self.display.bind("<Button-1>", self.on_click)
            self.display.bind("<Button-3>", self.on_close_polygon)
            self.display.bind("<B1-Motion>", self.on_motion)

        self.class_bar = tk.Frame(self.root)
        self._rebuild_class_bar()

        self.status = tk.Label(self.root, anchor=tk.W, relief=tk.SUNKEN, bd=1)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self.class_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=6)

    def _rebuild_class_bar(self):
        for w in self.class_bar.winfo_children():
            w.destroy()
        self.class_buttons = {}
        for cls in self.classes:
            key = self.class_keys[cls]
            btn = tk.Button(self.class_bar, text=f"[{key}] {cls}", width=16,
                            command=lambda c=cls: self._on_class_press(c))
            btn.pack(side=tk.LEFT, padx=2)
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
            if self.mode == "yolo" and cls == self.current_cls:
                btn.configure(relief=tk.SUNKEN)
            else:
                btn.configure(relief=tk.RAISED)

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
            parts.append("left: add point  right/click 1st point/c: close  w: whole image  "
                         "Bksp: remove  Esc: cancel  Enter: save&next")
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
        if self.mode == "yolo":
            self.polygons = []
            self.current = []
            self.mouse_pos = None
            self._load_existing_polygons()
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
        self._base_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(self._base_bgr, cv2.COLOR_BGR2RGB)))
        self._photo = self._base_photo
        self._redraw_overlay()
        path = self.files[self.i]
        key = self._existing_key(path)
        existing = self.existing.get(key)
        if existing:
            label_info = "annotated" if self.mode == "yolo" else f"label: {existing}"
            self.status.configure(fg="#1a7f37")
        else:
            label_info = "label: —"
            self.status.configure(fg="#333333")
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
        self._disp_scale = min(1.0, cw / dw, ch / dh)
        sw, sh = max(1, round(dw * self._disp_scale)), max(1, round(dh * self._disp_scale))
        if self._disp_scale < 1.0:
            img = Image.fromarray(self._base_bgr).resize((sw, sh), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
        else:
            self._photo = self._base_photo
        iw, ih = self._photo.width(), self._photo.height()
        x0 = (cw - iw) // 2
        y0 = (ch - ih) // 2
        if self._img_item is None:
            self._img_item = c.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            c.itemconfig(self._img_item, image=self._photo)
        c.coords(self._img_item, x0, y0)
        c.tag_lower(self._img_item)
        if self.mode != "yolo":
            return
        scale = self._disp_scale
        lb_w, lb_h = self.lb_w, self.lb_h
        ow, oh = self._orig_dims
        for idx, poly in enumerate(self.polygons):
            color = COLORS[idx % len(COLORS)]
            tk_color = "#%02x%02x%02x" % (color[2], color[1], color[0])
            pts = [(x0 + dx, y0 + dy) for dx, dy in (
                norm_to_disp(nx, ny, self.rot, lb_w, lb_h, ow, oh, scale) for nx, ny in poly["pts"])]
            fill = "" if poly.get("whole") else tk_color
            c.create_polygon(pts, outline=tk_color, width=2, fill=fill, stipple="gray50", tags="overlay")
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

    def _event_to_disp(self, event):
        if self._base_photo is None:
            return None
        bbox = self._canvas_img_pos()
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox
        x = event.x - x0
        y = event.y - y0
        dw, dh = disp_dims(self.lb_w, self.lb_h, self.rot)
        sw, sh = round(dw * self._disp_scale), round(dh * self._disp_scale)
        if x < 0 or y < 0 or x > sw - 1 or y > sh - 1:
            return None
        return x, y

    def on_click(self, event):
        p = self._event_to_disp(event)
        if p is None or self.current_cls is None:
            return
        scale = self._disp_scale
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

    def on_motion(self, event):
        p = self._event_to_disp(event)
        if p is None:
            return
        self.mouse_pos = p
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
        if self.current:
            self.current.pop()
            self._redraw_overlay()

    def cancel_polygon(self):
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
        self.polygons.append({"cls": self.current_cls, "whole": True,
                              "pts": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]})
        self._redraw_overlay()

    def save_next(self):
        if self.i >= len(self.files):
            return
        if self.current:
            self.close_polygon()
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
