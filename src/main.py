from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .web_app_manager import WebAppManager

# Global app manager instance (imported by routers)
app_manager = WebAppManager()

app = FastAPI(title="Image Tagger API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from .api import library, images, tags, datasets, taxonomy, export

app.include_router(library.router)
app.include_router(images.router)
app.include_router(tags.router)
app.include_router(datasets.router)
app.include_router(taxonomy.router)
app.include_router(export.router)

# Try to include HF router if it doesn't have PyQt5 deps
try:
    from .api import hf
    app.include_router(hf.router)
except Exception:
    pass


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# Mount frontend static files LAST — catch-all "/" must come after all API routes
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:
    print(f"Warning: Frontend dist not found at {frontend_dist}. Run 'npm run build' first.")
