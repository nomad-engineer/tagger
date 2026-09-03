# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the app (development)
```bash
./start_dev.sh
# Backend: http://127.0.0.1:8000   Frontend: http://localhost:3000
```

Or manually:
```bash
# Backend
./venv/bin/python -m uvicorn src.main:app --port 8000 --reload

# Frontend (separate terminal)
cd frontend && npm run dev -- --port 3000
```

### Electron desktop app
```bash
cd frontend && npm run start   # Vite + Electron together
cd frontend && npm run electron  # Electron only (requires Vite already running)
```

### Build frontend for production
```bash
cd frontend && npm run build   # outputs to frontend/dist/
```

### Tests
```bash
# Run all tests
pytest tests/

# Single file, verbose
pytest tests/test_utils.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Linting (frontend)
```bash
cd frontend && npm run lint
```

### Python dependencies
```bash
python -m venv venv
./venv/bin/pip install fastapi uvicorn pillow platformdirs pyparsing pydantic python-multipart
# For ML/model tagging plugin: torch torchvision transformers imagehash
```

## Architecture

This is a **desktop image tagging application** for ML training datasets. It has two layers:

1. **Python backend** (`src/`) — FastAPI REST API, runs on port 8000
2. **React/Electron frontend** (`frontend/src/`) — Vite + React, runs on port 3000, wraps in Electron for desktop

The frontend is served as static files from `frontend/dist/` in production. In dev, Vite proxies to the FastAPI backend.

### Backend structure (`src/`)

- **`main.py`** — FastAPI app entry point. Creates `WebAppManager`, registers API routers, mounts `frontend/dist/` as static files.
- **`web_app_manager.py`** — Central headless controller. Holds all application state (current library, datasets, tag index, image cache). No PyQt5 dependency. This is what the API routes call.
- **`app_manager.py`** — Legacy PyQt5-based manager (the old desktop-only version). Kept for backwards compat with the Qt UI code. Uses signals for change notification.
- **`config_manager.py`** + **`global_config.py`** — Persists user config at `~/.config/image_tagger/global.json` via `platformdirs`.
- **`repository.py`** — Data access layer with three classes: `FileSystemRepository` (source of truth — JSON files), `DatabaseRepository` (SQLite rebuildable cache), `CacheRepository` (thumbnails).
- **`database.py`** — SQLite wrapper.
- **`data_models.py`** — Core dataclasses: `Tag`, `MediaData`, `ImageData`, `MaskData`, `VideoFrameData`, `ProjectData`, `ImageLibrary`, etc. Also re-exports `GlobalConfig`.
- **`commands.py`** + **`command_manager.py`** — Command pattern for undo/redo. `BatchAddTagsCommand`, `BatchRemoveTagsCommand` are the main commands. `CommandManager` holds a 100-item undo/redo stack.
- **`filter_parser.py`** — Parses tag filter expressions using `pyparsing`. Supports `AND`, `OR`, `NOT`, wildcards, parentheses, quoted strings.
- **`plugin_base.py`** + **`plugin_manager.py`** — Plugin system. `PluginBase` for headless plugins, `PluginWindow(QWidget, PluginBase)` for Qt UI plugins.
- **`plugins/`** — Built-in plugins: `model_tagging.py`, `remove_duplicates.py`, `caption_profile.py`, `dataset_balancer.py`, `export_captions.py`, `spell_checker.py`.
- **`api/`** — FastAPI routers: `library.py`, `images.py`, `tags.py`, `datasets.py`, `hf.py` (Hugging Face).

### Frontend structure (`frontend/src/`)

- **`store.ts`** — Zustand global state (selected images, active image, status toasts).
- **`App.tsx`** — Main app shell. Handles library open/create dialogs, import dialog, layout split between gallery and tag editor. Detects Electron via `window.electronAPI`.
- **`Gallery.tsx`** — Virtualized image grid using TanStack Virtual. Handles 100k+ images via lazy-loaded thumbnails from `/api/images/{hash}/thumbnail`.
- **`TagEditor.tsx`** — Tag sidebar for viewing/editing tags on the selected image.

### Data storage format

A **library** is a directory containing:
```
library.json         # manifest: name, image list, dataset references
images/
  {hash}.jpeg        # image file (named by content hash, 16-char default)
  {hash}.json        # metadata: name, caption, tags [{category, value}], related, media_type
deleted/             # soft-deleted images moved here
cache/
  thumbnails/        # auto-generated thumbnails
datasets/
  {name}.json        # dataset: image_selection[], caption_profile, repeats, balancing, saved_filters
```

Tags are structured as `{category: str, value: str}` and displayed as `category:value`. All tags live on the base library image JSON — no overlay/diff system.

### Two parallel UI systems

The codebase has **two UIs in parallel**: the old PyQt5 desktop app (files like `main_window.py`, `gallery.py`, `tag_window.py`, `image_viewer.py`, etc.) and the new Electron+React app. The `refactor` branch is focused on the new web-based architecture. The `WebAppManager` is the new headless version of `AppManager`.
