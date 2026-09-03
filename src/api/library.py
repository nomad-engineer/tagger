from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import tempfile
import asyncio

from src.main import app_manager

router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryCreateRequest(BaseModel):
    name: str
    path: str = ""


class LibraryLoadRequest(BaseModel):
    path: str


class FilterRequest(BaseModel):
    expression: str = ""


class SaveFilterRequest(BaseModel):
    name: str
    expression: str = ""


class RenameFilterRequest(BaseModel):
    name: str


class ImportRequest(BaseModel):
    folder_path: str
    recursive: bool = True


class RenameLibraryRequest(BaseModel):
    path: str
    new_name: str


class DeleteLibraryRequest(BaseModel):
    path: str


class DuplicateLibraryRequest(BaseModel):
    path: str
    new_name: str


def _pick_folder_sync() -> str:
    """Open the native OS folder-picker dialog."""
    import subprocess, platform
    system = platform.system()

    if system == "Linux":
        # Try zenity (GTK-native), then kdialog (KDE-native)
        for cmd in [
            ["zenity", "--file-selection", "--directory", "--title=Select Folder"],
            ["kdialog", "--getexistingdirectory", "."],
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except FileNotFoundError:
                continue
    elif system == "Darwin":
        # macOS: use osascript
        try:
            result = subprocess.run(
                ["osascript", "-e", 'POSIX path of (choose folder with prompt "Select Folder")'],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().rstrip("/")
        except FileNotFoundError:
            pass

    # Fallback: tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Select Folder")
        root.destroy()
        return folder or ""
    except Exception:
        return ""


# -----------------------------------------------------------------------

@router.get("/browse-folder")
async def browse_folder():
    """Open a native OS folder picker and return the selected path."""
    path = await asyncio.to_thread(_pick_folder_sync)
    return {"path": path}


@router.get("/config")
async def get_library_config():
    """Return server-side library configuration for the UI."""
    return {
        "libraries_root": app_manager.global_config.libraries_root,
        "managed": app_manager.managed_mode,
    }


@router.get("/root")
async def get_libraries_root():
    return {"root": app_manager.global_config.libraries_root}


@router.get("/available")
async def get_available_libraries():
    return {"libraries": app_manager.list_available_libraries()}


@router.get("/current")
async def get_current_library():
    info = app_manager.get_library_info()
    if not info:
        return None
    return info


@router.post("/create-new")
async def create_new_library(req: LibraryCreateRequest):
    success = app_manager.create_new_library(req.name, req.path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create library")
    return {"status": "success", "name": req.name, "path": req.path, "count": 0}


@router.post("/load")
async def load_library(req: LibraryLoadRequest):
    lib_path = Path(req.path)
    if not lib_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    try:
        success = app_manager.load_library(lib_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to load library")
    info = app_manager.get_library_info()
    return {"status": "success", **(info or {})}


@router.post("/filter")
async def set_filter(req: FilterRequest):
    app_manager.set_filter(req.expression)
    return {"status": "success", "expression": req.expression}


@router.post("/clear-filter")
async def clear_filter():
    app_manager.clear_filter()
    return {"status": "success"}


@router.get("/filters/saved")
async def get_saved_filters():
    return {"filters": app_manager.get_saved_filters()}


@router.post("/filters/save")
async def save_filter(req: SaveFilterRequest):
    result = app_manager.save_filter(req.name, req.expression)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to save filter")
    return {"status": "success", "filter": result}


@router.delete("/filters/{filter_id}")
async def delete_saved_filter(filter_id: int):
    ok = app_manager.delete_saved_filter(filter_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete filter")
    return {"status": "success"}


@router.patch("/filters/{filter_id}")
async def rename_saved_filter(filter_id: int, req: RenameFilterRequest):
    ok = app_manager.rename_saved_filter(filter_id, req.name)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to rename filter")
    return {"status": "success"}


@router.post("/rename")
async def rename_library(req: RenameLibraryRequest):
    ok = app_manager.rename_library(req.path, req.new_name)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to rename library")
    return {"status": "success"}


@router.post("/duplicate")
async def duplicate_library(req: DuplicateLibraryRequest):
    new_path = await asyncio.to_thread(
        app_manager.duplicate_library, req.path, req.new_name
    )
    if not new_path:
        raise HTTPException(status_code=500, detail="Failed to duplicate library")
    return {"status": "success", "path": new_path}


@router.post("/delete")
async def delete_library(req: DeleteLibraryRequest):
    ok = app_manager.delete_library(req.path)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete library")
    return {"status": "success"}


@router.post("/scan")
async def scan_library():
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    added = app_manager.scan_and_add_new_files()
    return {"status": "success", "added": added}


@router.post("/import")
async def import_from_folder(req: ImportRequest):
    """Start a folder import in a background thread."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    # Run in thread so we don't block the event loop
    result = await asyncio.to_thread(
        app_manager.import_from_folder, req.folder_path, req.recursive
    )
    return {"status": "success", **result}


class LegacyImportRequest(BaseModel):
    folder_path: str


@router.post("/import-legacy")
async def import_legacy_folder(req: LegacyImportRequest):
    """Start a legacy folder import in a background thread."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    result = await asyncio.to_thread(
        app_manager.import_legacy_folder, req.folder_path
    )
    return {"status": "success", **result}


@router.get("/import-status")
async def get_import_status():
    """Poll current import progress."""
    status = app_manager.get_import_status()
    if status is None:
        return {"running": False}
    return status


@router.get("/backfill-status")
async def get_backfill_status():
    """Poll background metadata backfill progress (runs after library open)."""
    status = app_manager.get_backfill_status()
    if status is None:
        return {"running": False}
    return status


@router.post("/import-cancel")
async def cancel_import():
    """Cancel a running import."""
    cancelled = app_manager.cancel_import()
    return {"status": "cancelled" if cancelled else "no_import_running"}


async def _save_uploads(files: List[UploadFile], tmp: Path) -> None:
    """Stream each uploaded file to disk without loading all content into memory at once."""
    import shutil
    for f in files:
        filename = f.filename or "upload"
        dest = tmp / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        # f.file is a SpooledTemporaryFile — copy in chunks, no full-RAM buffer
        with open(dest, "wb") as out:
            await asyncio.to_thread(shutil.copyfileobj, f.file, out)
        await f.close()


@router.post("/upload-import")
async def upload_import(files: List[UploadFile] = File(...)):
    """Receive a batch of files from the browser file picker and import images."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    with tempfile.TemporaryDirectory() as tmp_dir:
        await _save_uploads(files, Path(tmp_dir))
        result = await asyncio.to_thread(
            app_manager.import_from_folder, tmp_dir, True
        )
    return {"status": "success", **result}


@router.post("/upload-legacy")
async def upload_legacy(files: List[UploadFile] = File(...)):
    """Receive a batch of legacy-library files from the browser file picker."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    with tempfile.TemporaryDirectory() as tmp_dir:
        await _save_uploads(files, Path(tmp_dir))
        result = await asyncio.to_thread(
            app_manager.import_legacy_folder, tmp_dir
        )
    return {"status": "success", **result}


# -----------------------------------------------------------------------
# Deleted image browser / restore
# -----------------------------------------------------------------------

@router.get("/deleted")
async def list_deleted():
    """List all files in the library's deleted/ folder with metadata."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    items = app_manager.list_deleted_images()
    return {"items": items}


@router.get("/deleted-thumbnail/{filename}")
async def get_deleted_thumbnail(filename: str, size: int = 200):
    """Generate and return a thumbnail for a file in deleted/."""
    if not app_manager.is_open:
        raise HTTPException(status_code=404, detail="No library loaded")

    # Prevent path traversal
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    deleted_path = app_manager.fs.deleted_dir / filename
    if not deleted_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    def make_thumb(path: Path, max_edge: int) -> bytes:
        from PIL import Image
        from io import BytesIO
        img = Image.open(path)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, 'WEBP', quality=70)
        return buf.getvalue()

    try:
        data = await asyncio.to_thread(make_thumb, deleted_path, size)
        return Response(content=data, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=60"})
    except Exception:
        from fastapi.responses import FileResponse
        return FileResponse(deleted_path)


class RestoreRequest(BaseModel):
    filenames: List[str]
    dataset_id: Optional[int] = None


@router.post("/restore-deleted")
async def restore_deleted(req: RestoreRequest):
    """Restore deleted images back to the library."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    result = await asyncio.to_thread(
        app_manager.restore_deleted_images, req.filenames, req.dataset_id
    )
    return {"status": "success", **result}
