# Current Tasks

## Completed Simplification Refactor
- [x] Removed tag overlay system (diff-based tagging)
- [x] Updated tag operations to always modify base library images
- [x] Renamed "projects" to "datasets" throughout codebase
- [x] Updated dataset structure (image_selection, caption_profile, repeats, balancing)
- [x] Updated API endpoints (`datasets.py`, `hf.py`)
- [x] Updated frontend (`store.ts`, `App.tsx`, `Gallery.tsx`)

## Next Steps
- [x] Create `start_dev.sh` script to start dev servers
- [ ] Test simplified implementation
- [ ] Implement dataset-specific features (repeats, balancing)
- [ ] Add caption profile functionality
- [ ] Async database operations
