# Import Dialog Changes for Library Architecture

## Summary
The Import Dialog has been completely updated to work with the new library/projects architecture.

## ✅ What Changed

### Removed Features
- ❌ **Import Mode Selection** (Copy and link / Link only) - Always copies to library now
- ❌ **Destination Directory Selection** - Images always go to library's `images/` directory
- ❌ **Retain Relative Paths** - Library uses flat structure with hash-based filenames

### New Features
- ✅ **Add to Project Dropdown** - Optionally add imported images to a project
  - Options: "(None - Library only)" or any existing project
  - Default to current project if in project view
  - Images are copied to library AND linked to selected project

### Kept Features
- ✅ Source directory selection
- ✅ Paste image paths
- ✅ Add import tag (e.g., `meta:imported: 2025-01-15`)
- ✅ Import caption.txt files
- ✅ Select images after import
- ✅ Duplicate detection (by perceptual hash)

## 🔄 New Import Flow

1. **User selects source** (directory or pasted paths)
2. **User selects project** (optional) from dropdown
3. **Import process:**
   - Each image is hashed (perceptual hash)
   - Image copied to `library/images/` with hash-based filename (e.g., `abc123def.jpg`)
   - JSON file created/updated next to image
   - Image added to library's image list
   - If project selected, also added to that project's image list
   - Caption .txt files imported if enabled
   - Import tag added if specified

4. **Results:**
   - Library.json updated with new images
   - Project.json updated (if project selected)
   - All changes saved immediately
   - Selection updated to show imported images

## 📝 Usage Examples

### Example 1: Import to Library Only
1. File → Import Images
2. Select source directory
3. Leave "Add to project" as "(None - Library only)"
4. Click Import
5. ✅ Images copied to library, available across all projects

### Example 2: Import to Library + Specific Project
1. File → Import Images
2. Select source directory
3. Select project from "Add to project" dropdown (e.g., "Character Art")
4. Click Import
5. ✅ Images in library AND in "Character Art" project

### Example 3: Import with Caption Tags
1. File → Import Images
2. Select source directory
3. Check "Import caption.txt"
4. Set caption category (e.g., "tags")
5. Select project if desired
6. Click Import
7. ✅ Images imported with tags from .txt files

## 🔍 Technical Details

### File Structure After Import

**Before Import:**
```
source/
  ├── image1.jpg
  ├── image1.txt (optional caption file)
  ├── image2.png
  └── subfolder/
      └── image3.jpg
```

**After Import to Library:**
```
library/
  ├── library.json (updated)
  ├── images/
  │   ├── a1b2c3d4.jpg (was image1.jpg)
  │   ├── a1b2c3d4.json
  │   ├── e5f6g7h8.png (was image2.png)
  │   ├── e5f6g7h8.json
  │   ├── i9j0k1l2.jpg (was subfolder/image3.jpg)
  │   └── i9j0k1l2.json
  └── projects/
      └── my_project.json (updated if project selected)
```

### Perceptual Hashing
- Images are renamed based on perceptual hash
- Same visual content = same hash (even if different files)
- Duplicates automatically detected and skipped
- Flat directory structure in library/images/

### Project Linking
- Projects reference images from library by path
- Multiple projects can reference same image
- Deleting from project doesn't delete from library
- Image data (tags, etc.) shared across projects

## 🧪 Testing Checklist

- [ ] Import to library only (no project selected)
- [ ] Import to library + current project
- [ ] Import to library + different project
- [ ] Import with caption.txt files
- [ ] Import with custom import tag
- [ ] Duplicate detection works
- [ ] Pasted paths import
- [ ] Selection after import works
- [ ] Library.json and project.json updated correctly
- [ ] Images renamed with hash-based filenames
- [ ] JSON files created alongside images

## 🐛 Known Limitations

1. **No Undo** - Import cannot be undone (files are copied)
2. **Flat Structure** - Library uses flat structure only (no subdirectories)
3. **Hash Collisions** - Extremely rare, but possible with perceptual hashing
4. **File Overwrite** - If hash already exists in library, file is not copied (assumes same image)

## 💡 Future Enhancements

- Progress bar for large imports
- Bulk tag editing after import
- Import preview before copying
- Import from URLs
- Auto-organize by metadata
