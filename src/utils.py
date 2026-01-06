"""
Utility functions for image tagging application
"""

import hashlib
import re
import os
from pathlib import Path
from typing import List, Tuple, Optional
from difflib import SequenceMatcher


def hash_image(image_path: Path, hash_length: int = 16) -> str:
    """
    Generate a hash from image pixel data (including alpha channel)

    Args:
        image_path: Path to image file
        hash_length: Length of hash string to return

    Returns:
        Hash string of specified length
    """
    try:
        from PIL import Image

        hasher = hashlib.sha256()
        with Image.open(image_path) as img:
            # Ensure consistent mode for hashing
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            hasher.update(img.tobytes())
        return hasher.hexdigest()[:hash_length]
    except Exception:
        # Fallback to file hashing if PIL fails
        hasher = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:hash_length]


def hash_video_first_frame(
    video_path: Path, hash_length: int = 16, include_file_size: bool = True
) -> str:
    """
    Generate a hash from the first frame of a video file and its size

    Args:
        video_path: Path to video file
        hash_length: Length of hash string to return
        include_file_size: Whether to include file size in hash

    Returns:
        Hash string of specified length
    """
    try:
        import cv2
    except ImportError:
        # Fallback to standard file hashing if cv2 not available
        return hash_image(video_path, hash_length)

    hasher = hashlib.sha256()

    # Capture first frame
    cap = cv2.VideoCapture(str(video_path))
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            hasher.update(frame.tobytes())
    cap.release()

    # Add file size to hash to improve uniqueness
    if include_file_size:
        file_size = os.path.getsize(video_path)
        hasher.update(str(file_size).encode())

    full_hash = hasher.hexdigest()
    return full_hash[:hash_length]


def split_sequential_filename(filename: str) -> Tuple[str, Optional[int]]:
    """
    Split a filename into base name and sequential number

    Supports patterns like:
    - image-001.png -> ("image", 1)
    - image_02.jpg -> ("image", 2)
    - image (3).webp -> ("image", 3)
    - image004.png -> ("image", 4)

    Returns:
        Tuple of (base_name, sequence_number)
    """
    stem = Path(filename).stem

    # Common patterns for sequential numbers
    # 1. Separator (- or _) followed by digits at the end
    # 2. Space and parentheses with digits
    # 3. Just digits at the end
    patterns = [r"^(.*?)[-_](\d+)$", r"^(.*?) \((\d+)\)$", r"^(.*?)(\d+)$"]

    for pattern in patterns:
        match = re.match(pattern, stem)
        if match:
            base_name = match.group(1).strip()
            seq_num_str = match.group(2)
            if seq_num_str:
                seq_num = int(seq_num_str)
                # Don't treat very short base names as valid if they are just separators
                if base_name:
                    return base_name, seq_num

    return stem, None


def fuzzy_search(
    query: str, candidates: List[str], threshold: float = 0.3
) -> List[Tuple[str, float]]:
    """
    Fuzzy search for matching strings with intelligent scoring

    Args:
        query: Search query
        candidates: List of candidate strings
        threshold: Minimum similarity ratio (0-1) to include in results

    Returns:
        List of (candidate, similarity_score) tuples, sorted by score descending
    """
    if not query:
        return [(c, 1.0) for c in candidates]

    results = []
    query_lower = query.lower()

    # Check if query has a category (contains colon)
    query_parts = query_lower.split(":", 1)
    query_has_category = len(query_parts) > 1
    query_category = query_parts[0] if query_has_category else ""
    query_value = query_parts[1] if query_has_category else query_lower

    for candidate in candidates:
        candidate_lower = candidate.lower()

        # Extract category and value from candidate
        parts = candidate_lower.split(":", 1)
        has_category = len(parts) > 1
        category = parts[0] if has_category else ""
        value_part = parts[1] if has_category else candidate_lower

        # If query has a category, only match candidates from same category
        if query_has_category and has_category:
            if category != query_category:
                continue  # Skip candidates from different categories
            # Match on the value part only
            match_target = value_part
            query_match = query_value
        elif query_has_category and not has_category:
            # Query has category but candidate doesn't, skip
            continue
        else:
            # Query doesn't have category, match against both full tag and value
            match_target = candidate_lower
            query_match = query_lower

        # Calculate similarity ratio
        ratio = SequenceMatcher(None, query_match, match_target).ratio()

        # Also check value part separately if not already doing so
        if not query_has_category and has_category:
            value_ratio = SequenceMatcher(None, query_match, value_part).ratio()
            ratio = max(ratio, value_ratio)

        # High priority: exact match
        if query_match == match_target or (
            not query_has_category and query_match == value_part
        ):
            ratio = 2.0
        # High priority: starts with
        elif match_target.startswith(query_match) or (
            not query_has_category and value_part.startswith(query_match)
        ):
            ratio = 1.5
        # Medium priority: contains
        elif query_match in match_target or (
            not query_has_category and query_match in value_part
        ):
            ratio = 1.0 + ratio * 0.5
        # Low priority: fuzzy match only if ratio is good (>= 0.6)
        elif ratio < 0.6:
            # Skip weak fuzzy matches
            continue

        if ratio >= threshold:
            results.append((candidate, ratio))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def parse_filter_expression(expression: str) -> dict:
    """
    Parse a filter expression into a structured format

    Supports: tag1 AND tag2 NOT tag3, or tag1 OR tag2 NOT tag3

    Args:
        expression: Filter expression string

    Returns:
        Dict with 'include' and 'exclude' tag lists, and 'operator' (AND/OR)
    """
    tokens = expression.split()
    include_tags = []
    exclude_tags = []
    operator = "AND"  # Default to AND

    # Detect if OR is used in the expression
    for token in tokens:
        if token.upper() == "OR":
            operator = "OR"
            break

    i = 0
    while i < len(tokens):
        token = tokens[i].strip()

        if token.upper() == "NOT" and i + 1 < len(tokens):
            exclude_tags.append(tokens[i + 1].strip())
            i += 2
        elif token.upper() in ["AND", "OR"]:
            i += 1
        elif token:
            include_tags.append(token)
            i += 1
        else:
            i += 1

    return {"include": include_tags, "exclude": exclude_tags, "operator": operator}


def parse_export_template(template: str) -> List[dict]:
    """
    Parse export template into structured format

    Example: "trigger, {class}, {camera}, {details}[0:3]"

    Args:
        template: Export template string

    Returns:
        List of template parts with type and parameters
    """
    parts = []
    segments = [s.strip() for s in template.split(",")]

    for segment in segments:
        if not segment:
            continue

        # Check if it's a placeholder {category} or {category}[range]
        if segment.startswith("{") and "}" in segment:
            bracket_end = segment.index("}")
            category = segment[1:bracket_end]

            # Check for range specifier
            range_spec = None
            if bracket_end + 1 < len(segment) and segment[bracket_end + 1] == "[":
                range_str = segment[
                    bracket_end + 2 : -1
                ]  # Extract content between [ and ]
                range_spec = range_str

            parts.append(
                {"type": "category", "category": category, "range": range_spec}
            )
        else:
            # Literal text
            parts.append({"type": "literal", "value": segment})

    return parts


def apply_export_template(
    template_parts: List[dict],
    image_data,
    remove_duplicates: bool = False,
    max_tags: Optional[int] = None,
) -> str:
    """
    Apply export template to image data to generate caption

    Args:
        template_parts: Parsed template parts from parse_export_template
        image_data: ImageData instance
        remove_duplicates: If True, remove duplicate tag values (keeps first occurrence)
        max_tags: If specified, limit total number of tags in caption (keeps first N)

    Returns:
        Generated caption string
    """
    result = []
    seen_tags = set()
    tag_count = 0

    for part in template_parts:
        if part["type"] == "literal":
            result.append(part["value"])
        elif part["type"] == "category":
            category = part["category"]
            range_spec = part["range"]

            # Get tags for this category
            tags = image_data.get_tags_by_category(category)

            # Apply range if specified
            if range_spec:
                try:
                    # Parse Python slice notation
                    if ":" in range_spec:
                        range_parts = range_spec.split(":")
                        start_str = range_parts[0]
                        end_str = range_parts[1] if len(range_parts) > 1 else ""
                        start = int(start_str) if start_str else 0
                        end = int(end_str) if end_str else len(tags)
                        tags = tags[start:end]
                    else:
                        # Single index
                        idx = int(range_spec)
                        tags = [tags[idx]] if 0 <= idx < len(tags) else []
                except (ValueError, IndexError):
                    tags = []

            # Add tag values to result
            for tag in tags:
                # Check if we've reached max tags limit
                if max_tags is not None and tag_count >= max_tags:
                    break

                tag_value = tag.value
                # Skip duplicates if remove_duplicates is enabled
                if remove_duplicates:
                    if tag_value in seen_tags:
                        continue
                    seen_tags.add(tag_value)
                result.append(tag_value)
                tag_count += 1

    return ", ".join(result)
