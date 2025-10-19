"""
Test script to reproduce the filtered view bug
"""
from pathlib import Path
from src.data_models import ImageList

# Simulate the filter window scenario
test_project_dir = Path("/home/adam/Nextcloud/Projects/tagger2/test_project")

# Get all images (simulate main image list)
all_images = list(test_project_dir.glob("*.png")) + list(test_project_dir.glob("*.jpg"))
print(f"All images in project: {len(all_images)}")
for img in all_images:
    print(f"  - {img.name}")

# Create main image list
main_image_list = ImageList(test_project_dir)
for img_path in all_images:
    main_image_list.add_image(img_path)

print(f"\nMain ImageList has {len(main_image_list.get_all_paths())} images")

# Simulate filter returning 0 matches
filtered = []
print(f"\nFilter matched images: {len(filtered)}")

# Create filtered view (this is what filter_window.py does)
filtered_view = ImageList.create_filtered(test_project_dir, filtered)

print(f"\nFiltered view has {len(filtered_view.get_all_paths())} images")
if filtered_view.get_all_paths():
    print("ERROR: Filtered view should be empty but contains:")
    for img in filtered_view.get_all_paths():
        print(f"  - {img.name}")
else:
    print("SUCCESS: Filtered view is empty as expected")

# Test with some images
print("\n" + "="*50)
print("Testing with 2 images")
filtered2 = [all_images[0], all_images[1]] if len(all_images) >= 2 else []
filtered_view2 = ImageList.create_filtered(test_project_dir, filtered2)
print(f"Filtered view has {len(filtered_view2.get_all_paths())} images (expected 2)")
for img in filtered_view2.get_all_paths():
    print(f"  - {img.name}")
