# Image Tagger Architecture

## Overview

The Image Tagger uses a **file-first architecture** with a **rebuildable database layer** for performance. This ensures your data is always safe in human-readable files while providing fast queries through SQLite.

## Core Principles

1. **Files = Source of Truth** - All data stored in readable JSON files
2. **Database = Rebuildable Cache** - SQLite provides fast queries but can be regenerated
3. **Dual-Write Pattern** - Writes go to files first, then database
4. **Cache = Safe to Delete** - Thumbnails and computed data regenerated on demand

---

## File Structure

```
library/
├── library.json              # Library metadata
├── library.db                # SQLite index (REBUILDABLE - ignored by git)
├── images/                   # Source data (human-readable)
│   ├── abc123def456.png     # Original image (perceptual hash as filename)
│   ├── abc123def456.json    # Metadata: tags, caption, relationships
│   ├── abc123def456.txt     # ML training caption
│   ├── mask_xyz789.png      # Mask image (first-class citizen)
│   ├── mask_xyz789.json     # Mask metadata + source_image reference
│   └── ...
├── cache/                    # SAFE TO DELETE - regenerated automatically
│   ├── thumbnails/           # 150x150 thumbnails
│   │   ├── abc123def456.jpg
│   │   └── ...
│   └── lowres/               # 1024px previews
│       └── abc123def456_1024.jpg
├── deleted/                  # Soft-deleted images (move here instead of permanent delete)
└── projects/                 # Project definitions
    ├── project1.json        # References images from library
    └── project2.json
```

---

## Data Models

### MediaData (Base Class)

All media types inherit from `MediaData`:

```python
@dataclass
class MediaData:
    type: str              # "image", "mask", "video_frame"
    name: str
    caption: str
    tags: List[Tag]
    related: Dict[str, List[str]]  # {"similar": [...], "masks": [...]}
    metadata: Dict[str, Any]       # Extensible metadata
```

### ImageData

Standard images:

```python
@dataclass
class ImageData(MediaData):
    type: str = "image"
```

**JSON Format** (`abc123.json`):
```json
{
  "name": "mountain_sunset",
  "caption": "mountains, sunset, natural lighting",
  "tags": [
    {"category": "class", "value": "landscape", "position": 0},
    {"category": "details", "value": "sunset", "position": 1}
  ],
  "related": {
    "similar": ["xyz789"],
    "masks": ["mask_def456"]
  },
  "metadata": {
    "created": "2025-01-15T10:30:00Z",
    "width": 1920,
    "height": 1080
  }
}
```

### MaskData

Segmentation masks (first-class citizens):

```python
@dataclass
class MaskData(MediaData):
    type: str = "mask"
    source_image: str      # Hash of parent image
    mask_category: str     # What this masks ("person", "background", etc.)
```

**JSON Format** (`mask_xyz.json`):
```json
{
  "type": "mask",
  "source_image": "abc123def456",
  "mask_category": "person",
  "name": "person_mask",
  "tags": [
    {"category": "mask_type", "value": "person"}
  ],
  "related": {},
  "metadata": {}
}
```

### VideoFrameData

Video frames (future support):

```python
@dataclass
class VideoFrameData(MediaData):
    type: str = "video_frame"
    source_video: str      # Hash of source video
    frame_index: int       # Frame number
    timestamp: float       # Timestamp in seconds
```

---

## Repository Layer

The repository pattern abstracts data access into three specialized classes:

### 1. FileSystemRepository

**Purpose**: Reads/writes JSON files (source of truth)

**Key Methods**:
```python
fs_repo = FileSystemRepository(library_dir)

# Save media data to JSON
fs_repo.save_media_data(hash, image_data)

# Load media data from JSON
media_data = fs_repo.load_media_data(hash)

# Save caption file
fs_repo.save_caption_file(hash, caption)

# Soft delete (move to deleted/ folder)
fs_repo.delete_media(hash)

# Scan all media in library
hashes = fs_repo.scan_all_media()
```

### 2. DatabaseRepository

**Purpose**: SQLite operations for fast queries (rebuildable)

**Key Methods**:
```python
db_repo = DatabaseRepository(db_path)
db_repo.connect()

# Insert or update media
db_repo.upsert_media(hash, image_data)

# Load from database
media_data = db_repo.load_media(hash)

# Query all media
hashes = db_repo.get_all_media_hashes(media_type='image')

# Find similar images
similar = db_repo.get_similar_media(hash, threshold=0.8)

# Cache perceptual hash
db_repo.save_perceptual_hash(hash, 'phash', hash_value)
```

### 3. CacheRepository

**Purpose**: Manages thumbnails and computed data (safe to delete)

**Key Methods**:
```python
cache_repo = CacheRepository(library_dir, thumbnail_size=150)

# Get thumbnail (generates if not cached)
thumb_path = cache_repo.get_thumbnail(hash, source_path)

# Get low-res preview
lowres_path = cache_repo.get_lowres(hash, source_path, max_size=1024)

# Clear entire cache
cache_repo.clear_cache()

# Get cache size
size_bytes = cache_repo.get_cache_size()
```

---

## Database Schema

The SQLite database is a **rebuildable performance layer**. It can be deleted and regenerated from JSON files.

### Tables

#### media
```sql
CREATE TABLE media (
    hash TEXT PRIMARY KEY,
    type TEXT NOT NULL,           -- 'image', 'mask', 'video_frame'
    source_media TEXT,            -- For masks/frames: hash of source
    name TEXT,
    caption TEXT,
    created DATETIME,
    modified DATETIME,
    metadata_json TEXT            -- JSON blob
);
```

#### tags
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    media_hash TEXT NOT NULL,
    category TEXT NOT NULL,
    value TEXT NOT NULL,
    position INTEGER NOT NULL,    -- Order/importance
    FOREIGN KEY (media_hash) REFERENCES media(hash) ON DELETE CASCADE
);
```

#### tags_fts (Full-Text Search)
```sql
CREATE VIRTUAL TABLE tags_fts USING fts5(
    category,
    value,
    media_hash UNINDEXED
);
```

#### relationships
```sql
CREATE TABLE relationships (
    from_hash TEXT NOT NULL,
    to_hash TEXT NOT NULL,
    type TEXT NOT NULL,           -- 'similar', 'mask_of', 'video_sequence'
    strength REAL,                -- Similarity score (0-1) or NULL
    PRIMARY KEY (from_hash, to_hash, type)
);
```

#### perceptual_hashes
```sql
CREATE TABLE perceptual_hashes (
    media_hash TEXT NOT NULL,
    algorithm TEXT NOT NULL,      -- 'phash', 'dhash', 'ahash', 'whash'
    hash_value TEXT NOT NULL,
    computed DATETIME,
    PRIMARY KEY (media_hash, algorithm)
);
```

---

## Dual-Write Pattern

All writes follow this pattern to ensure data safety:

```python
# Example: Saving image data
def save_image_data(hash, data):
    # 1. Write to filesystem FIRST (source of truth)
    fs_repo.save_media_data(hash, data)
    if data.caption:
        fs_repo.save_caption_file(hash, data.caption)

    # 2. Then write to database (for performance)
    try:
        db_repo.upsert_media(hash, data)
    except Exception as e:
        # Log warning but don't fail - filesystem is the source
        print(f"Warning: Database update failed: {e}")
```

**Benefits**:
- Data never lost (always in JSON files)
- Database corruption won't cause data loss
- Can work offline with just files
- Other tools can read/modify JSON directly

---

## Database Rebuild

If the database is corrupted or missing, it can be rebuilt from JSON files:

### Automatic Rebuild

When opening a library:
1. App checks if `library.db` exists
2. If missing or corrupted, prompts user: "Rebuild from files?"
3. Shows progress dialog during rebuild
4. Scans all `*.json` files in `images/`
5. Populates database from JSON data

### Manual Rebuild

```python
from src.database import rebuild_database

db = rebuild_database(db_path, images_dir)
# Scans all JSON files and rebuilds database
```

---

## Data Flow

### Read Operations

**Fast path (cache hit)**:
```
User requests image
    ↓
Check database (fast)
    ↓
Return data
```

**Slow path (cache miss)**:
```
User requests image
    ↓
Database miss
    ↓
Read JSON file (slower but accurate)
    ↓
Update database cache
    ↓
Return data
```

### Write Operations

**Dual-write for safety**:
```
User edits tags
    ↓
Mark as pending change
    ↓
User presses Ctrl+S
    ↓
1. Write to JSON file (source of truth)
    ↓
2. Write to database (for fast queries)
    ↓
3. Emit signals to update UI
```

---

## Migration from Old Format

The new architecture is **100% backward compatible**:

### Existing Libraries

1. Open existing library → database will be missing
2. App prompts: "Rebuild database from files?"
3. Click "Yes" → database generated from existing JSON files
4. Library works exactly as before, but faster!

### JSON Format

- Old format (without `type` field) → interpreted as `"image"`
- Old `similar_images` → converted to `related["similar"]`
- New fields (`metadata`, `type`) optional → backward compatible

---

## Performance Characteristics

| Operation | Without Database | With Database | Speedup |
|-----------|-----------------|---------------|---------|
| Filter by tag | O(n) file reads | O(1) SQL query | 100-1000x |
| Load image data | File read | Database row | 10-50x |
| Find similar | O(n²) comparisons | O(log n) index lookup | 100-10000x |
| Full-text search | Linear scan | FTS5 index | 1000x+ |

**Scalability**:
- **1K images**: Works great without database
- **10K images**: Database provides noticeable speedup
- **100K+ images**: Database essential for good performance

---

## Cache Management

### Automatic Cache

Thumbnails and previews generated on-demand:

```python
# First access: generates and caches
thumb = cache_repo.get_thumbnail(hash, source_path)

# Subsequent access: instant (cached)
thumb = cache_repo.get_thumbnail(hash, source_path)
```

### Cache Invalidation

Cache files deleted when:
- Source image modified
- User manually clears cache
- Cache directory deleted (safe!)

Regeneration is automatic on next access.

---

## Extending the System

### Adding New Media Types

1. Create new data model inheriting from `MediaData`
2. Add type to database enum
3. Update `MediaData.from_dict()` routing
4. Implement plugin for import/export

Example:
```python
@dataclass
class AudioData(MediaData):
    type: str = "audio"
    duration: float = 0.0
    sample_rate: int = 44100
```

### Adding New Relationships

Just add to `related` dict:
```python
image_data.related["variations"] = [hash1, hash2, hash3]
```

Database schema supports arbitrary relationship types!

---

## Best Practices

### For Developers

1. **Always dual-write**: Filesystem first, database second
2. **Treat database as cache**: Don't rely on it exclusively
3. **Graceful degradation**: If database fails, fall back to files
4. **Test with database missing**: Ensure rebuild works

### For Users

1. **Backup `images/` directory**: That's your data!
2. **Ignore `library.db` in backups**: It's rebuildable
3. **Delete `cache/` to save space**: Regenerates automatically
4. **Keep JSON files readable**: Don't corrupt them!

---

## Troubleshooting

### Database Corruption

**Symptom**: App crashes on library open

**Solution**:
1. Delete `library.db`
2. Reopen library
3. Click "Yes" when prompted to rebuild

### Missing Images

**Symptom**: Images don't appear in gallery

**Solution**:
1. Check `images/` directory for `*.json` files
2. Rebuild database (File → Rebuild Database)
3. Check `deleted/` folder for moved files

### Slow Performance

**Symptom**: Gallery lags with many images

**Solution**:
1. Ensure `library.db` exists and is current
2. Clear cache if it's huge (`cache/` directory)
3. Rebuild database to optimize indexes

---

## Future Enhancements

### Planned Features

- **Virtualized gallery**: Lazy loading for 100K+ images
- **Background workers**: Parallel import and processing
- **AI tagging integration**: Plugin-based model support
- **Video support**: Frame extraction and tagging
- **Collaborative editing**: Multi-user libraries with sync

### Database Migrations

Future schema changes will use versioning:

```sql
SELECT value_json FROM library_metadata WHERE key = 'schema_version'
```

Migration scripts will update database while preserving JSON files.
