# AGENTS.md

Single-file Tkinter image labeling app. Everything lives in `main.py` (~1750 lines). No tests, lint, CI, or build system. Requirements: `opencv-python`, `Pillow` (`requirements.txt`).

## Environment

- Must use the venv interpreter: `.venv/bin/python` (Python 3.11.4). System `/usr/bin/python3` PIL lacks `ImageTk` and will fail on `import main`.
- GUI cannot be runtime-tested (no display/xvfb here). Verify changes with:
  - `.venv/bin/python -m py_compile main.py`
  - `.venv/bin/python -c "import main"`
  - For icon/photo changes, also render `build_icons` and `rounded_photo` via PIL and check non-empty sizes.

## App architecture

- `main()` → `SetupDialog` (choose group/mode/input/output) → `LabelerApp`.
- Two modes on `self.mode`:
  - `classification`: `assign(cls)` moves image into `output_dir/<cls>/`, keeps uncommitted file in `output_dir/._staged/`, writes orientation copy to `output_dir/../orientation/rot_<k>/` for classes flagged `front` in config. `undo` restores from staged. `_cleanup` moves remaining staged files back on quit.
  - `yolo`: no file moves; `save_next` writes `output_dir/<stem>.txt`. Format per line: `cid x y x y ...` (normalized [0,1] polygon), or a bare `cid` line for whole-image annotation. Lines always have 6 decimals.
- Config: `groups.json` (`CONFIG_PATH`), `{"groups": {name: {cls: {"key": "1", "front": bool}}}}`. `load_config` regenerates `DEFAULT_GROUPS` if missing. Keys come from the `KEYS` list (1-9, a-z).

## Coordinate & display system

- Polygons stored normalized `(nx, ny) ∈ [0,1]`. Image pipeline: letterbox → rotate (`self.rot`) → display. Helpers: `letterbox`, `rot_cw`, `lb_to_disp`/`disp_to_lb`, `norm_to_disp`/`disp_to_norm`. When editing transforms/zoom/pan, keep these consistent.
- Zoom/pan state: `self.zoom`, `self._pan_x/y`. `_redraw_overlay` caches the rescaled photo on `self._scaled_scale`; invalidate with `self._scaled_scale=None` in `_render`. New image via `_show_current` resets zoom/pan to 1.0/0.

## UI conventions

- Use the custom widgets (NO plain `tk.Button` anywhere): `ModernButton` (rounded, hover/press states; pass `icon_active=self._icons_white[...]`, `style="accent"/"danger"`), `Pill`, `ProgressBar`, `ToolTip`, `rounded_photo`. Colors from the module-level `UI` dict.
- Icons: 13 PIL-drawn icons via `build_icons` + `ICON_DRAWS`. Two sets are built per app: `self._icons` (normal) and `self._icons_white` (active state). New icons must be added to both and both `ICON_DRAWS`/`build_icons` names.
- `theme_tree` is used by dialogs only; `LabelerApp._build_ui` sets colors explicitly.
- Keyboard shortcuts in `_bind_keys`; class keys derive from the active group's `key` fields.

## Repo hygiene

- Large user data lives in untracked dirs/tarballs (`data/`, `yolo_labled_images/`, `vertical_text_data*`, `yolo_classified/`, `*.tar.gz`, `__pycache__/`, `.venv/`). Never `git add` them or edit their contents as code.
- Only `main.py` and `groups.json` are meaningful source files; `groups.json` is user config, edit carefully.
- Do not add comments to code.