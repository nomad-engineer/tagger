"""
Model Tagging Plugin - Generate tags using captioning models
"""
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar,
    QTextEdit, QWidget, QFormLayout, QScrollArea, QProgressDialog,
    QApplication
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QProcess
from PIL import Image
import sys
import subprocess

from ..plugin_base import PluginWindow


# Pre-defined model configurations
PREDEFINED_MODELS = {
    "BLIP Base": {
        "model_id": "Salesforce/blip-image-captioning-base",
        "processor_id": "Salesforce/blip-image-captioning-base",
        "model_type": "blip",
        "task": "captioning",
        "max_length": 50,
        "num_beams": 3,
        "temperature": 1.0,
        "top_p": 0.9,
    },
    "BLIP Large": {
        "model_id": "Salesforce/blip-image-captioning-large",
        "processor_id": "Salesforce/blip-image-captioning-large",
        "model_type": "blip",
        "task": "captioning",
        "max_length": 50,
        "num_beams": 3,
        "temperature": 1.0,
        "top_p": 0.9,
    },
    "BLIP-2 OPT 2.7B": {
        "model_id": "Salesforce/blip2-opt-2.7b",
        "processor_id": "Salesforce/blip2-opt-2.7b",
        "model_type": "blip2",
        "task": "captioning",
        "max_length": 50,
        "num_beams": 3,
        "temperature": 1.0,
        "top_p": 0.9,
    },
    "GIT Base": {
        "model_id": "microsoft/git-base",
        "processor_id": "microsoft/git-base",
        "model_type": "git",
        "task": "captioning",
        "max_length": 50,
        "num_beams": 3,
        "temperature": 1.0,
        "top_p": 0.9,
    },
    "ViT-GPT2": {
        "model_id": "nlpconnect/vit-gpt2-image-captioning",
        "processor_id": "nlpconnect/vit-gpt2-image-captioning",
        "model_type": "vision-encoder-decoder",
        "task": "captioning",
        "max_length": 50,
        "num_beams": 3,
        "temperature": 1.0,
        "top_p": 0.9,
    },
    "WD Tagger v3 (SmilingWolf)": {
        "model_id": "SmilingWolf/wd-vit-tagger-v3",
        "processor_id": "SmilingWolf/wd-vit-tagger-v3",
        "model_type": "image-classification",
        "task": "tagging",
        "threshold": 0.35,
    },
    "WD Tagger v3 (wd-eva02-large-tagger-v3)": {
        "model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
        "processor_id": "SmilingWolf/wd-eva02-large-tagger-v3",
        "model_type": "image-classification",
        "task": "tagging",
        "threshold": 0.35,
    },
    "WD SwinV2 Tagger v3": {
        "model_id": "SmilingWolf/wd-swinv2-tagger-v3",
        "processor_id": "SmilingWolf/wd-swinv2-tagger-v3",
        "model_type": "image-classification",
        "task": "tagging",
        "threshold": 0.35,
    },
    "WD ConvNext Tagger v3": {
        "model_id": "SmilingWolf/wd-convnext-tagger-v3",
        "processor_id": "SmilingWolf/wd-convnext-tagger-v3",
        "model_type": "image-classification",
        "task": "tagging",
        "threshold": 0.35,
    },
    "CLIP ViT-B/32 (Zero-shot)": {
        "model_id": "openai/clip-vit-base-patch32",
        "processor_id": "openai/clip-vit-base-patch32",
        "model_type": "zero-shot",
        "task": "zero-shot",
        "threshold": 0.25,
    },
    "CLIP ViT-L/14 (Zero-shot)": {
        "model_id": "openai/clip-vit-large-patch14",
        "processor_id": "openai/clip-vit-large-patch14",
        "model_type": "zero-shot",
        "task": "zero-shot",
        "threshold": 0.25,
    },
    "SigLIP Base (Zero-shot)": {
        "model_id": "google/siglip-base-patch16-224",
        "processor_id": "google/siglip-base-patch16-224",
        "model_type": "zero-shot",
        "task": "zero-shot",
        "threshold": 0.25,
    },
    "SigLIP Large (Zero-shot)": {
        "model_id": "google/siglip-large-patch16-256",
        "processor_id": "google/siglip-large-patch16-256",
        "model_type": "zero-shot",
        "task": "zero-shot",
        "threshold": 0.25,
    },
}


class PackageInstallThread(QThread):
    """Thread for installing Python packages with progress"""

    output = pyqtSignal(str)  # Output line
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, packages: List[str]):
        super().__init__()
        self.packages = packages

    def run(self):
        """Install packages using pip"""
        try:
            # Run pip install with real-time output
            process = subprocess.Popen(
                [sys.executable, "-m", "pip", "install"] + self.packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Stream output
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.output.emit(line.strip())

            process.stdout.close()
            return_code = process.wait()

            if return_code == 0:
                self.finished.emit(True, "Installation successful!")
            else:
                self.finished.emit(False, f"Installation failed with code {return_code}")

        except Exception as e:
            self.finished.emit(False, f"Installation error: {str(e)}")


class ModelInferenceThread(QThread):
    """Thread for running model inference on images"""

    progress = pyqtSignal(int, int)  # current, total
    result = pyqtSignal(Path, str, bool)  # image_path, caption, success
    finished = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)  # status message (e.g., "Loading model...")

    def __init__(self, image_paths: List[Path], model_config: Dict[str, Any],
                 device: str = "cpu"):
        super().__init__()
        self.image_paths = image_paths
        self.model_config = model_config
        self.device = device
        self.model = None
        self.processor = None
        self._stop_requested = False

    def stop(self):
        """Request thread to stop"""
        self._stop_requested = True

    def run(self):
        """Run inference on all images"""
        try:
            # Import here to avoid loading at startup
            from transformers import (
                BlipProcessor, BlipForConditionalGeneration,
                Blip2Processor, Blip2ForConditionalGeneration,
                AutoProcessor, AutoModelForCausalLM,
                VisionEncoderDecoderModel, ViTImageProcessor, AutoTokenizer,
                AutoModelForImageClassification, pipeline,
                CLIPProcessor, CLIPModel, AutoModel
            )
            import torch

            # Load model and processor based on model type
            model_type = self.model_config.get("model_type", "blip")
            task = self.model_config.get("task", "captioning")
            model_id = self.model_config["model_id"]
            processor_id = self.model_config.get("processor_id", model_id)

            # For zero-shot, get custom tags
            if task == "zero-shot":
                self.custom_tags = self.model_config.get("custom_tags", [])
                if not self.custom_tags:
                    self.error.emit("No custom tags provided for zero-shot classification")
                    return
                self.status.emit(f"Using {len(self.custom_tags)} custom tags for zero-shot classification")

            try:
                if task == "tagging":
                    # For image classification/tagging models
                    self.status.emit(f"Loading tagging model from {model_id}...")

                    # Try to use AutoImageProcessor for better compatibility
                    try:
                        from transformers import AutoImageProcessor
                        self.processor = AutoImageProcessor.from_pretrained(processor_id, trust_remote_code=True)
                    except:
                        # Fallback to AutoProcessor
                        self.processor = AutoProcessor.from_pretrained(processor_id, trust_remote_code=True)

                    self.model = AutoModelForImageClassification.from_pretrained(
                        model_id, trust_remote_code=True
                    )

                    # Load proper tag labels for SmilingWolf models
                    self.id2label = self.model.config.id2label

                    # Check if we have generic LABEL_X labels (check both int and str keys)
                    has_generic_labels = False
                    if self.id2label:
                        # Try different key formats
                        first_label = self.id2label.get(0) or self.id2label.get("0") or self.id2label.get(1) or self.id2label.get("1")
                        if first_label and first_label.startswith("LABEL_"):
                            has_generic_labels = True
                            self.status.emit(f"Detected generic labels: {first_label}")

                    if has_generic_labels:
                        try:
                            from huggingface_hub import hf_hub_download
                            import csv

                            self.status.emit("Loading tag label names from CSV...")
                            csv_path = hf_hub_download(
                                repo_id=model_id,
                                filename="selected_tags.csv"
                            )

                            # Read the CSV to get tag names
                            tag_names = []
                            with open(csv_path, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    tag_names.append(row['name'])

                            # Create proper id2label mapping (use int keys)
                            self.id2label = {i: name for i, name in enumerate(tag_names)}
                            self.status.emit(f"Loaded {len(tag_names)} tag labels (e.g., {tag_names[0]}, {tag_names[1]})")
                        except Exception as e:
                            self.status.emit(f"ERROR loading tag labels: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        self.status.emit(f"Using existing labels from model config")
                elif task == "zero-shot" or model_type == "zero-shot":
                    # Zero-shot classification with CLIP or SigLIP models
                    self.status.emit(f"Loading zero-shot model from {model_id}...")
                    self.processor = AutoProcessor.from_pretrained(processor_id)

                    # Use AutoModel for SigLIP, CLIPModel for CLIP
                    if "siglip" in model_id.lower():
                        self.model = AutoModel.from_pretrained(model_id)
                        self.status.emit(f"Loaded SigLIP model with {len(self.custom_tags)} custom tags")
                    else:
                        self.model = CLIPModel.from_pretrained(model_id)
                        self.status.emit(f"Loaded CLIP model with {len(self.custom_tags)} custom tags")
                elif model_type == "blip":
                    self.status.emit(f"Loading processor from {processor_id}...")
                    self.processor = BlipProcessor.from_pretrained(processor_id)
                    self.status.emit(f"Loading model from {model_id}...")
                    self.model = BlipForConditionalGeneration.from_pretrained(model_id)
                elif model_type == "blip2":
                    self.status.emit(f"Loading processor from {processor_id}...")
                    self.processor = Blip2Processor.from_pretrained(processor_id)
                    self.status.emit(f"Loading model from {model_id}...")
                    self.model = Blip2ForConditionalGeneration.from_pretrained(model_id)
                elif model_type == "git":
                    self.status.emit(f"Loading processor from {processor_id}...")
                    self.processor = AutoProcessor.from_pretrained(processor_id)
                    self.status.emit(f"Loading model from {model_id}...")
                    self.model = AutoModelForCausalLM.from_pretrained(model_id)
                elif model_type == "vision-encoder-decoder":
                    self.status.emit(f"Loading model from {model_id}...")
                    self.model = VisionEncoderDecoderModel.from_pretrained(model_id)
                    self.status.emit(f"Loading feature extractor...")
                    feature_extractor = ViTImageProcessor.from_pretrained(processor_id)
                    self.status.emit(f"Loading tokenizer...")
                    tokenizer = AutoTokenizer.from_pretrained(processor_id)
                    # For vision-encoder-decoder, we need both
                    self.processor = (feature_extractor, tokenizer)
                else:
                    # Generic auto-loading for captioning
                    self.status.emit(f"Loading processor from {processor_id}...")
                    self.processor = AutoProcessor.from_pretrained(processor_id)
                    self.status.emit(f"Loading model from {model_id}...")
                    self.model = AutoModelForCausalLM.from_pretrained(model_id)

                self.status.emit("Model loaded successfully!")

            except Exception as e:
                self.error.emit(f"Failed to load model: {str(e)}")
                return

            # Move model to device
            self.model.to(self.device)
            self.model.eval()

            # Process each image
            total = len(self.image_paths)
            for idx, img_path in enumerate(self.image_paths):
                if self._stop_requested:
                    break

                try:
                    # Load image
                    image = Image.open(img_path).convert("RGB")

                    if task == "zero-shot":
                        # Zero-shot classification with CLIP/SigLIP
                        # Prepare text inputs (custom tags)
                        text_inputs = self.processor(
                            text=self.custom_tags,
                            return_tensors="pt",
                            padding=True
                        )
                        text_inputs = {k: v.to(self.device) for k, v in text_inputs.items()}

                        # Prepare image inputs
                        image_inputs = self.processor(
                            images=image,
                            return_tensors="pt"
                        )
                        image_inputs = {k: v.to(self.device) for k, v in image_inputs.items()}

                        # Get predictions
                        with torch.no_grad():
                            # Get image and text embeddings
                            image_features = self.model.get_image_features(**image_inputs)
                            text_features = self.model.get_text_features(**text_inputs)

                            # Normalize features
                            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                            # Calculate cosine similarity
                            similarity = (image_features @ text_features.T).squeeze(0)
                            probs = similarity.cpu().numpy()

                        # Get threshold
                        threshold = self.model_config.get("threshold", 0.25)

                        # Get tags above threshold
                        import numpy as np
                        tags_with_probs = []
                        for idx, (tag, prob) in enumerate(zip(self.custom_tags, probs)):
                            if prob >= threshold:
                                tags_with_probs.append((tag, float(prob)))

                        # Sort by probability (highest first)
                        tags_with_probs.sort(key=lambda x: x[1], reverse=True)

                        # Extract tag names
                        tags = [tag for tag, _ in tags_with_probs]

                        # Create caption
                        if tags:
                            caption = ", ".join(tags)
                        else:
                            max_prob = np.max(probs) if len(probs) > 0 else 0.0
                            caption = f"no tags above threshold (max similarity: {max_prob:.4f})"

                    elif task == "tagging":
                        # Image classification/tagging task
                        inputs = self.processor(images=image, return_tensors="pt")
                        inputs = {k: v.to(self.device) for k, v in inputs.items()}

                        # Get predictions
                        with torch.no_grad():
                            outputs = self.model(**inputs)
                            logits = outputs.logits[0]
                            probs = torch.sigmoid(logits).cpu().numpy()

                        # Get tag labels and filter by threshold
                        threshold = self.model_config.get("threshold", 0.35)

                        # Debug: Check max probability
                        import numpy as np
                        max_prob = np.max(probs)
                        self.status.emit(f"Max probability: {max_prob:.4f}, Threshold: {threshold}")

                        # Get tags above threshold with their probabilities
                        tags_with_probs = []
                        debug_first_few = []  # For debugging
                        for idx_label, prob in enumerate(probs):
                            if prob >= threshold:
                                # Try int key first, then string key
                                label = self.id2label.get(idx_label, self.id2label.get(str(idx_label), f"unknown_{idx_label}"))

                                # Debug: collect first few for inspection
                                if len(debug_first_few) < 3:
                                    debug_first_few.append(f"{label}({prob:.3f})")

                                # Skip generic LABEL_X labels (shouldn't happen after we load proper labels)
                                if not label.startswith("LABEL_"):
                                    tags_with_probs.append((label, prob))

                        # Debug: Show what we found
                        if debug_first_few:
                            self.status.emit(f"First tags found: {', '.join(debug_first_few)}")

                        # Sort by probability (highest first)
                        tags_with_probs.sort(key=lambda x: x[1], reverse=True)

                        # Extract just the tag names
                        tags = [tag for tag, _ in tags_with_probs]

                        # Debug: Show count
                        self.status.emit(f"Found {len(tags)} tags above threshold (after filtering)")

                        # Join tags with commas
                        if tags:
                            caption = ", ".join(tags)
                        else:
                            caption = f"no tags above threshold (max prob: {max_prob:.4f})"

                    elif model_type == "vision-encoder-decoder":
                        # Vision-encoder-decoder captioning
                        feature_extractor, tokenizer = self.processor
                        pixel_values = feature_extractor(
                            images=image, return_tensors="pt"
                        ).pixel_values
                        pixel_values = pixel_values.to(self.device)

                        # Generate caption
                        with torch.no_grad():
                            output_ids = self.model.generate(
                                pixel_values,
                                max_length=self.model_config.get("max_length", 50),
                                num_beams=self.model_config.get("num_beams", 3),
                                temperature=self.model_config.get("temperature", 1.0),
                                top_p=self.model_config.get("top_p", 0.9),
                            )

                        caption = tokenizer.decode(output_ids[0], skip_special_tokens=True)
                    else:
                        # Standard captioning models
                        inputs = self.processor(images=image, return_tensors="pt")
                        inputs = {k: v.to(self.device) for k, v in inputs.items()}

                        # Generate caption
                        with torch.no_grad():
                            output_ids = self.model.generate(
                                **inputs,
                                max_length=self.model_config.get("max_length", 50),
                                num_beams=self.model_config.get("num_beams", 3),
                                temperature=self.model_config.get("temperature", 1.0),
                                top_p=self.model_config.get("top_p", 0.9),
                            )

                        caption = self.processor.decode(output_ids[0], skip_special_tokens=True)

                    # Clean up caption
                    caption = caption.strip()

                    # Emit result
                    self.result.emit(img_path, caption, True)

                except Exception as e:
                    self.result.emit(img_path, f"Error: {str(e)}", False)

                # Update progress
                self.progress.emit(idx + 1, total)

        except Exception as e:
            self.error.emit(f"Inference error: {str(e)}")
        finally:
            self.finished.emit()


class ModelTaggingPlugin(PluginWindow):
    """Plugin to generate tags using captioning models"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Model Tagging"
        self.description = "Generate tags using captioning models"
        self.shortcut = "Ctrl+M"

        self.setWindowTitle(self.name)
        self.resize(800, 700)

        self.inference_thread = None
        self.results = {}  # image_path -> caption

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Instructions
        instructions = QLabel(
            "Generate captions/tags using AI models from Hugging Face.\n"
            "Select a model, configure parameters, and run inference on selected images."
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Model selection section
        model_group = QGroupBox("Model Selection")
        model_layout = QVBoxLayout(model_group)

        # Predefined models dropdown
        predefined_layout = QHBoxLayout()
        predefined_layout.addWidget(QLabel("Preset Models:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(list(PREDEFINED_MODELS.keys()) + ["Custom"])
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        predefined_layout.addWidget(self.model_combo)
        model_layout.addLayout(predefined_layout)

        # Custom model inputs
        self.custom_model_widget = QWidget()
        custom_layout = QFormLayout(self.custom_model_widget)

        self.model_id_input = QLineEdit()
        self.model_id_input.setPlaceholderText("e.g., Salesforce/blip-image-captioning-base")
        custom_layout.addRow("Model ID:", self.model_id_input)

        self.processor_id_input = QLineEdit()
        self.processor_id_input.setPlaceholderText("Leave empty to use model ID")
        custom_layout.addRow("Processor ID:", self.processor_id_input)

        self.model_type_combo = QComboBox()
        self.model_type_combo.addItems(["blip", "blip2", "git", "vision-encoder-decoder", "auto"])
        custom_layout.addRow("Model Type:", self.model_type_combo)

        self.custom_model_widget.setVisible(False)
        model_layout.addWidget(self.custom_model_widget)

        layout.addWidget(model_group)

        # Parameters section
        params_group = QGroupBox("Model Parameters")
        params_layout = QFormLayout(params_group)

        # Captioning parameters (hidden for tagging models)
        self.captioning_params = []

        self.max_length_spin = QSpinBox()
        self.max_length_spin.setRange(10, 200)
        self.max_length_spin.setValue(50)
        self.max_length_label = QLabel("Max Length:")
        params_layout.addRow(self.max_length_label, self.max_length_spin)
        self.captioning_params.extend([self.max_length_label, self.max_length_spin])

        self.num_beams_spin = QSpinBox()
        self.num_beams_spin.setRange(1, 10)
        self.num_beams_spin.setValue(3)
        self.num_beams_label = QLabel("Num Beams:")
        params_layout.addRow(self.num_beams_label, self.num_beams_spin)
        self.captioning_params.extend([self.num_beams_label, self.num_beams_spin])

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.1, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(1.0)
        self.temperature_label = QLabel("Temperature:")
        params_layout.addRow(self.temperature_label, self.temperature_spin)
        self.captioning_params.extend([self.temperature_label, self.temperature_spin])

        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.1, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setValue(0.9)
        self.top_p_label = QLabel("Top P:")
        params_layout.addRow(self.top_p_label, self.top_p_spin)
        self.captioning_params.extend([self.top_p_label, self.top_p_spin])

        # Tagging parameters (hidden for captioning models)
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setValue(0.35)
        self.threshold_label = QLabel("Threshold:")
        params_layout.addRow(self.threshold_label, self.threshold_spin)
        self.tagging_params = [self.threshold_label, self.threshold_spin]

        # Initially hide tagging params
        for widget in self.tagging_params:
            widget.setVisible(False)

        layout.addWidget(params_group)

        # Zero-shot custom tags section (hidden for other models)
        self.zeroshot_group = QGroupBox("Custom Tags (Zero-shot)")
        zeroshot_layout = QVBoxLayout(self.zeroshot_group)

        # Instructions
        zeroshot_help = QLabel(
            "Enter the tags you want to detect (one per line or comma-separated).\n"
            "The model will classify the image against these custom tags."
        )
        zeroshot_help.setStyleSheet("color: gray; font-size: 9px;")
        zeroshot_layout.addWidget(zeroshot_help)

        # Custom tags input
        self.custom_tags_input = QTextEdit()
        self.custom_tags_input.setPlaceholderText(
            "Examples:\n"
            "person\n"
            "cat\n"
            "dog\n"
            "indoor scene\n"
            "outdoor scene\n"
            "daytime\n"
            "nighttime\n"
            "portrait\n"
            "landscape"
        )
        self.custom_tags_input.setMaximumHeight(150)
        zeroshot_layout.addWidget(self.custom_tags_input)

        self.zeroshot_group.setVisible(False)
        layout.addWidget(self.zeroshot_group)

        # Device selection
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Device:"))
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cpu", "cuda"])
        device_layout.addWidget(self.device_combo)
        device_layout.addStretch()
        layout.addLayout(device_layout)

        # Tag configuration section
        tag_group = QGroupBox("Tag Configuration")
        tag_layout = QVBoxLayout(tag_group)

        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Tag Category:"))
        self.tag_category_input = QLineEdit()
        self.tag_category_input.setText("caption")
        self.tag_category_input.setPlaceholderText("e.g., caption, ai_caption, description")
        category_layout.addWidget(self.tag_category_input)
        tag_layout.addLayout(category_layout)

        # Option to split caption into tags
        self.split_caption_check = QCheckBox("Split caption into individual tags (comma/space separated)")
        tag_layout.addWidget(self.split_caption_check)

        # Option to keep existing tags
        self.keep_existing_check = QCheckBox("Keep existing tags in this category")
        self.keep_existing_check.setChecked(True)
        tag_layout.addWidget(self.keep_existing_check)

        layout.addWidget(tag_group)

        # Run button
        run_layout = QHBoxLayout()
        run_layout.addStretch()

        self.run_btn = QPushButton("Run Inference on Selected Images")
        self.run_btn.clicked.connect(self._run_inference)
        run_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop_inference)
        self.stop_btn.setEnabled(False)
        run_layout.addWidget(self.stop_btn)

        layout.addLayout(run_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Results section
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(200)
        results_layout.addWidget(self.results_text)

        # Apply tags button
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()

        self.apply_btn = QPushButton("Apply Tags to Images")
        self.apply_btn.clicked.connect(self._apply_tags)
        self.apply_btn.setEnabled(False)
        apply_layout.addWidget(self.apply_btn)

        results_layout.addLayout(apply_layout)

        layout.addWidget(results_group)

        # Set initial model config
        self._on_model_changed(self.model_combo.currentText())

    def _on_model_changed(self, model_name: str):
        """Handle model selection change"""
        if model_name == "Custom":
            self.custom_model_widget.setVisible(True)
            # Default to captioning params for custom models
            for widget in self.captioning_params:
                widget.setVisible(True)
            for widget in self.tagging_params:
                widget.setVisible(False)
            self.zeroshot_group.setVisible(False)
        else:
            self.custom_model_widget.setVisible(False)

            # Load predefined config
            if model_name in PREDEFINED_MODELS:
                config = PREDEFINED_MODELS[model_name]
                task = config.get("task", "captioning")

                # Show/hide appropriate parameters based on task
                is_tagging = (task == "tagging")
                is_zeroshot = (task == "zero-shot")

                for widget in self.captioning_params:
                    widget.setVisible(not is_tagging and not is_zeroshot)
                for widget in self.tagging_params:
                    widget.setVisible(is_tagging or is_zeroshot)
                self.zeroshot_group.setVisible(is_zeroshot)

                # Load parameter values
                if is_tagging or is_zeroshot:
                    self.threshold_spin.setValue(config.get("threshold", 0.35))
                else:
                    self.max_length_spin.setValue(config.get("max_length", 50))
                    self.num_beams_spin.setValue(config.get("num_beams", 3))
                    self.temperature_spin.setValue(config.get("temperature", 1.0))
                    self.top_p_spin.setValue(config.get("top_p", 0.9))

    def _get_model_config(self) -> Dict[str, Any]:
        """Get current model configuration"""
        model_name = self.model_combo.currentText()

        if model_name == "Custom":
            config = {
                "model_id": self.model_id_input.text().strip(),
                "processor_id": self.processor_id_input.text().strip() or self.model_id_input.text().strip(),
                "model_type": self.model_type_combo.currentText(),
                "task": "captioning",  # Default for custom
            }
        else:
            config = PREDEFINED_MODELS[model_name].copy()

        # Add task-specific parameters
        task = config.get("task", "captioning")
        if task == "tagging":
            config["threshold"] = self.threshold_spin.value()
        elif task == "zero-shot":
            config["threshold"] = self.threshold_spin.value()
            # Parse custom tags from text input
            custom_tags_text = self.custom_tags_input.toPlainText().strip()
            if ',' in custom_tags_text:
                # Comma-separated
                custom_tags = [t.strip() for t in custom_tags_text.split(',') if t.strip()]
            else:
                # Newline-separated
                custom_tags = [t.strip() for t in custom_tags_text.split('\n') if t.strip()]
            config["custom_tags"] = custom_tags
        else:
            config.update({
                "max_length": self.max_length_spin.value(),
                "num_beams": self.num_beams_spin.value(),
                "temperature": self.temperature_spin.value(),
                "top_p": self.top_p_spin.value(),
            })

        return config

    def _run_inference(self):
        """Run inference on selected images"""
        # Get selected images
        selected_images = self.get_selected_images()

        if not selected_images:
            QMessageBox.warning(self, "No Images", "No images selected for inference.")
            return

        # Get model config
        model_config = self._get_model_config()

        if not model_config.get("model_id"):
            QMessageBox.warning(self, "No Model", "Please select or specify a model.")
            return

        # Validate custom tags for zero-shot models
        if model_config.get("task") == "zero-shot":
            custom_tags = model_config.get("custom_tags", [])
            if not custom_tags:
                QMessageBox.warning(
                    self,
                    "No Custom Tags",
                    "Please enter at least one custom tag for zero-shot classification."
                )
                return

        # Check if transformers is installed
        try:
            import transformers
        except ImportError:
            reply = QMessageBox.question(
                self,
                "Install transformers?",
                "The 'transformers' library is not installed.\n\n"
                "Would you like to install it now? This may take a few minutes.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                self._install_dependencies()
            return

        # Clear previous results
        self.results = {}
        self.results_text.clear()

        # Setup progress bar
        self.progress_bar.setMaximum(len(selected_images))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # Disable run button, enable stop button
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(False)

        # Create and start inference thread
        device = self.device_combo.currentText()
        self.inference_thread = ModelInferenceThread(
            selected_images, model_config, device
        )
        self.inference_thread.progress.connect(self._on_progress)
        self.inference_thread.result.connect(self._on_result)
        self.inference_thread.finished.connect(self._on_inference_finished)
        self.inference_thread.error.connect(self._on_error)
        self.inference_thread.status.connect(self._on_status)
        self.inference_thread.start()

        self.results_text.append(f"Running inference on {len(selected_images)} images...\n")
        self.results_text.append(f"Model: {model_config['model_id']}\n")
        self.results_text.append(f"Device: {device}\n")
        self.results_text.append("-" * 50 + "\n")

    def _install_dependencies(self):
        """Install transformers and dependencies with progress dialog"""
        # Create progress dialog
        progress = QProgressDialog("Installing dependencies...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Installing Packages")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)  # Can't cancel pip install easily

        # Create text area for output
        output_text = QTextEdit()
        output_text.setReadOnly(True)
        output_text.setMaximumHeight(300)
        progress.setLabel(output_text)

        progress.show()
        QApplication.processEvents()

        # Start installation thread
        packages = ["transformers", "torch", "torchvision", "accelerate"]
        self.install_thread = PackageInstallThread(packages)

        def on_output(line):
            output_text.append(line)
            QApplication.processEvents()

        def on_finished(success, message):
            progress.close()
            if success:
                QMessageBox.information(
                    self,
                    "Success",
                    "Dependencies installed successfully!\n\n"
                    "Please try running inference again."
                )
            else:
                QMessageBox.critical(
                    self,
                    "Installation Failed",
                    f"Failed to install dependencies:\n\n{message}"
                )

        self.install_thread.output.connect(on_output)
        self.install_thread.finished.connect(on_finished)
        self.install_thread.start()

    def _stop_inference(self):
        """Stop inference thread"""
        if self.inference_thread:
            self.inference_thread.stop()
            self.results_text.append("\nStopping inference...\n")

    def _on_progress(self, current: int, total: int):
        """Handle progress update"""
        self.progress_bar.setValue(current)

    def _on_result(self, img_path: Path, caption: str, success: bool):
        """Handle inference result"""
        if success:
            self.results[img_path] = caption
            self.results_text.append(f"{img_path.name}: {caption}\n")
        else:
            self.results_text.append(f"{img_path.name}: FAILED - {caption}\n")

    def _on_status(self, status_msg: str):
        """Handle status update (e.g., model loading)"""
        self.results_text.append(f"{status_msg}\n")
        QApplication.processEvents()  # Update UI immediately

    def _on_error(self, error_msg: str):
        """Handle error from inference thread"""
        QMessageBox.critical(self, "Inference Error", error_msg)
        self.results_text.append(f"\nERROR: {error_msg}\n")

    def _on_inference_finished(self):
        """Handle inference completion"""
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self.results:
            self.apply_btn.setEnabled(True)
            self.results_text.append(f"\nCompleted! Generated {len(self.results)} captions.\n")
        else:
            self.results_text.append("\nNo results generated.\n")

    def _apply_tags(self):
        """Apply generated captions as tags to images"""
        if not self.results:
            QMessageBox.warning(self, "No Results", "No captions to apply.")
            return

        category = self.tag_category_input.text().strip()
        if not category:
            QMessageBox.warning(self, "No Category", "Please specify a tag category.")
            return

        split_caption = self.split_caption_check.isChecked()
        keep_existing = self.keep_existing_check.isChecked()

        tags_added = 0

        for img_path, caption in self.results.items():
            # Load image data
            img_data = self.app_manager.load_image_data(img_path)

            # Remove existing tags in this category if not keeping
            if not keep_existing:
                tags_to_remove = [tag for tag in img_data.tags if tag.category == category]
                for tag in tags_to_remove:
                    img_data.remove_tag(tag)

            # Add new tags
            if split_caption:
                # Split caption into individual tags
                # Try comma-separated first, then space-separated
                if ',' in caption:
                    tags = [t.strip() for t in caption.split(',') if t.strip()]
                else:
                    tags = [t.strip() for t in caption.split() if t.strip()]

                for tag_value in tags:
                    # Check if tag already exists
                    tag_str = f"{category}:{tag_value}"
                    tag_exists = any(str(tag) == tag_str for tag in img_data.tags)

                    if not tag_exists:
                        img_data.add_tag(category, tag_value)
                        tags_added += 1
            else:
                # Add whole caption as single tag
                tag_str = f"{category}:{caption}"
                tag_exists = any(str(tag) == tag_str for tag in img_data.tags)

                if not tag_exists:
                    img_data.add_tag(category, caption)
                    tags_added += 1

            # Save image data (marks as modified in pending changes - NOT written to disk yet)
            self.app_manager.save_image_data(img_path, img_data)

        # Update project (marks project as modified - NOT written to disk yet)
        self.app_manager.update_project(save=True)

        QMessageBox.information(
            self,
            "Tags Applied",
            f"Applied {tags_added} tags to {len(self.results)} images.\n\n"
            "Remember to save the library/project to persist changes to disk."
        )

        self.results_text.append(f"\nApplied {tags_added} tags!\n")
