# Features — New Electron App

## Desktop Experience
- [x] Electron desktop wrapper (native OS window, not browser)
- [x] Multi-window support (pop-out Tag Editor into separate window)
- [x] Native OS file dialogs for opening libraries and folders
- [x] GPU acceleration toggle (disabled by default for Linux compatibility)

## Backend (FastAPI)
- [x] Library loading, creation, and scanning via API
- [x] Project listing and loading
- [x] Image serving by hash (full resolution + thumbnails)
- [x] Per-image metadata endpoint (tags, caption, related, metadata)
- [x] Batch tag add/remove with Command pattern
- [x] Undo/Redo action history (Command stack, 100-action limit)
- [x] Hugging Face Hub push endpoint
- [x] CORS enabled for development

## Frontend (React + Vite)
- [x] Virtualized image gallery grid (TanStack Virtual) — handles 100k+ images
- [x] Lazy-loaded image thumbnails from backend API
- [x] Image selection with visual checkmark indicators
- [x] Tag Editor sidebar for viewing and adding tags
- [x] Undo/Redo buttons wired to backend
- [x] Scan for new files button
- [x] Open Library via native OS file dialog
- [x] Zustand state management for selections and active image

## Simplified Architecture (Refactored)
- [x] Removed diff-based tagging (tag overlays)
- [x] All tags stored on base library images
- [x] Datasets are now selections of images with metadata
- [x] Dataset structure includes: image selection, caption profiles, repeats, balancing, saved filters

## Remaining / In Progress
- [x] Hugging Face pull (download datasets)
- [x] Dataset system (simplified from projects)
- [x] Filter/search functionality (basic implementation)
- [ ] Async database operations
- [ ] Auto-save with atomic file writes
- [ ] Dataset-specific features (repeats, balancing, caption profiles)
