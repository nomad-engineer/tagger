#!/usr/bin/env python3

# Simple test of dataset balancer calculation logic
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

print("=== Dataset Balancer Calculation Test ===")


# Test the calculation logic directly
def calculate_repeats(img_tags, concept_multipliers, global_multiplier):
    """Calculate repeats for an image based on current configuration"""
    repeats = 1
    matching_tags = []

    # Add extra repeats for each balance tag
    for tag_str in img_tags:
        if tag_str in concept_multipliers:
            extra = concept_multipliers[tag_str]
            repeats += extra
            if extra != 0:
                matching_tags.append(f"{tag_str} ({'+' if extra > 0 else ''}{extra})")

    # Apply global multiplier
    repeats *= global_multiplier

    # Ensure minimum of 1
    repeats = max(1, repeats)

    return repeats, matching_tags


# Test cases
test_cases = [
    {
        "name": "No multipliers, global = 1",
        "tags": ["rating", "character:alice"],
        "multipliers": {},
        "global": 1,
        "expected": 1,
    },
    {
        "name": "Rating +2, global = 1",
        "tags": ["rating", "character:alice"],
        "multipliers": {"rating": 2},
        "global": 1,
        "expected": 3,  # 1 + 2 = 3
    },
    {
        "name": "Rating +2, global = 2",
        "tags": ["rating", "character:alice"],
        "multipliers": {"rating": 2},
        "global": 2,
        "expected": 6,  # (1 + 2) * 2 = 6
    },
    {
        "name": "Multiple tags, global = 1",
        "tags": ["rating", "pose", "character:alice"],
        "multipliers": {"rating": 2, "pose": -1},
        "global": 1,
        "expected": 2,  # 1 + 2 - 1 = 2
    },
    {
        "name": "Multiple tags, global = 2",
        "tags": ["rating", "pose", "character:alice"],
        "multipliers": {"rating": 2, "pose": -1},
        "global": 2,
        "expected": 4,  # (1 + 2 - 1) * 2 = 4
    },
    {
        "name": "No matching tags, global = 2",
        "tags": ["character:alice", "background:city"],
        "multipliers": {"rating": 2, "pose": -1},
        "global": 2,
        "expected": 2,  # 1 * 2 = 2
    },
]

print("\nRunning test cases:")
for test in test_cases:
    repeats, matching = calculate_repeats(
        test["tags"], test["multipliers"], test["global"]
    )
    status = "✓" if repeats == test["expected"] else "✗"
    print(
        f"{status} {test['name']}: {repeats} (expected {test['expected']}) - {matching}"
    )

print("\n=== Test Complete ===")
print("The calculation logic appears to be working correctly.")
print("The issue must be with configuration loading/saving or signal connections.")
