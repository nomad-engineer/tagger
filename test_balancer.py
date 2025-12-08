#!/usr/bin/env python3

# Simple test script to check dataset balancer logic
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


# Mock the GUI components we don't need
class MockQSpinBox:
    def __init__(self, value=1):
        self.value = value

    def setValue(self, value):
        self.value = value


class MockAppManager:
    def __init__(self):
        self.project = None

    def get_project(self):
        return self.project

    def update_project(self, save=False):
        pass


# Import and test the dataset balancer logic
from src.plugins.dataset_balancer import DatasetBalancerPlugin

# Create a mock instance
app_manager = MockAppManager()
balancer = DatasetBalancerPlugin(app_manager)

# Mock the UI setup
balancer.global_mult_spin = MockQSpinBox()

print("=== Dataset Balancer Test ===")
print(f"Initial concept_multipliers: {balancer.concept_multipliers}")
print(f"Initial global_multiplier: {balancer.global_multiplier}")

# Test loading configuration
print("\n=== Testing _load_configuration ===")
balancer._load_configuration()
print(f"After load concept_multipliers: {balancer.concept_multipliers}")
print(f"After load global_multiplier: {balancer.global_multiplier}")

# Test with some mock multipliers
print("\n=== Testing with mock multipliers ===")
balancer.concept_multipliers = {"rating": 2, "pose": -1}
balancer.global_multiplier = 2


# Mock image data
class MockImageData:
    def __init__(self, tags):
        self.tags = tags


class MockImageList:
    def __init__(self):
        self.images = [
            MockImageData(["rating", "character:alice"]),
            MockImageData(["pose", "character:bob"]),
            MockImageData(["background:city"]),
        ]

    def get_all_paths(self):
        return ["image1.jpg", "image2.jpg", "image3.jpg"]


# Test preview calculation
print("\n=== Testing preview calculation ===")
image_list = MockImageList()
preview_data = []

for img_path in image_list.get_all_paths():
    # Simulate the preview calculation logic
    img_data = image_list.images[image_list.get_all_paths().index(img_path)]
    img_tags = [str(tag) for tag in img_data.tags]

    repeats = 1
    matching_tags = []

    for tag_str in img_tags:
        if tag_str in balancer.concept_multipliers:
            extra = balancer.concept_multipliers[tag_str]
            repeats += extra
            if extra != 0:
                matching_tags.append(f"{tag_str} ({'+' if extra > 0 else ''}{extra})")

    repeats *= balancer.global_multiplier
    repeats = max(1, repeats)

    preview_data.append(
        {"path": img_path, "repeats": repeats, "matching_tags": matching_tags}
    )

for item in preview_data:
    print(f"{item['path']}: {item['repeats']} repeats - {item['matching_tags']}")

print("\n=== Test Complete ===")
