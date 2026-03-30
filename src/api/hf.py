from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import os
import asyncio
from datasets import Dataset, Features, Image, Value, load_dataset

from src.main import app_manager

router = APIRouter(prefix="/api/hf", tags=["huggingface"])

class PushRequest(BaseModel):
    repo_id: str
    token: Optional[str] = None
    private: bool = True

class PullRequest(BaseModel):
    repo_id: str
    dataset_name: Optional[str] = None
    token: Optional[str] = None

@router.post("/push")
async def push_to_hub(req: PushRequest, background_tasks: BackgroundTasks):
    current_view = app_manager.get_current_view()
    if not current_view:
        raise HTTPException(status_code=400, detail="No active view to push")
        
    token = req.token or os.environ.get("HF_TOKEN")
    if not token:
        # Check if logged in via CLI
        try:
            from huggingface_hub import HfFolder
            token = HfFolder.get_token()
        except ImportError:
            pass
            
    if not token:
        raise HTTPException(status_code=401, detail="HuggingFace token required")
        
    # Kick off background push to avoid blocking UI
    background_tasks.add_task(_do_push, current_view, req.repo_id, token, req.private)
    return {"status": "success", "message": f"Pushing to {req.repo_id} in background"}

def _do_push(image_hashes: List[str], repo_id: str, token: str, private: bool):
    try:
        print(f"Starting push to {repo_id}...")
        
        data = {
            "image": [],
            "text": []
        }
        
        images_dir = app_manager.get_images_directory()
        if not images_dir:
            print("Error: No images directory found")
            return

        for img_hash in image_hashes:
            img_data = app_manager.load_image_data(img_hash)
            if img_data:
                # Try to find the image file
                found_path = None
                for ext in ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif']:
                    p = images_dir / f"{img_hash}.{ext}"
                    if p.exists():
                        found_path = p
                        break
                
                if found_path:
                    data["image"].append(str(found_path))
                    data["text"].append(img_data.get("caption", ""))
                
        if not data["image"]:
            print("Error: No images found to push")
            return

        features = Features({
            "image": Image(),
            "text": Value("string")
        })
        
        ds = Dataset.from_dict(data, features=features)
        ds.push_to_hub(repo_id, token=token, private=private)
        print(f"Successfully pushed to {repo_id}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error pushing to HuggingFace: {e}")

@router.post("/pull")
async def pull_from_hub(req: PullRequest, background_tasks: BackgroundTasks):
    """Pull a dataset from Hugging Face and import it."""
    token = req.token or os.environ.get("HF_TOKEN")
    
    # Start background task for pulling
    background_tasks.add_task(_do_pull, req.repo_id, req.dataset_name, token)

    return {
        "status": "success",
        "message": f"Dataset {req.repo_id} is being pulled in the background."
    }

def _do_pull(repo_id: str, dataset_name: Optional[str], token: Optional[str]):
    try:
        print(f"Pulling dataset {repo_id}...")
        # Load dataset
        # We assume common image-text naming like 'train' split and 'image'/'text' or 'image'/'caption' columns
        dataset = load_dataset(repo_id, token=token, split='train')
        
        # Check column names
        cols = dataset.column_names
        img_col = 'image' if 'image' in cols else None
        text_col = 'text' if 'text' in cols else ('caption' if 'caption' in cols else None)
        
        if not img_col:
            print(f"Error: No image column found in {repo_id}")
            return

        # Prepare data for import_hf_dataset
        data_dict = {
            "image": dataset[img_col],
            "text": dataset[text_col] if text_col else [""] * len(dataset)
        }
        
        success = app_manager.import_hf_dataset(repo_id, data_dict, dataset_name)
        if success:
            print(f"Successfully imported {repo_id}")
        else:
            print(f"Import failed for {repo_id}")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error pulling from HuggingFace: {e}")
