"""
Utility functions for image tagging application
"""
from pathlib import Path
from typing import List, Tuple
import hashlib
from difflib import SequenceMatcher


def hash_image(image_path: Path, hash_length: int = 16) -> str:
    """
    Generate a hash from image file content

    Args:
        image_path: Path to image file
        hash_length: Length of hash string to return

    Returns:
        Hash string of specified length
    """
    hasher = hashlib.sha256()
    with open(image_path, 'rb') as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)

    full_hash = hasher.hexdigest()
    return full_hash[:hash_length]


def fuzzy_search(query: str, candidates: List[str], threshold: float = 0.3) -> List[Tuple[str, float]]:
    """
    Fuzzy search for matching strings

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

    for candidate in candidates:
        candidate_lower = candidate.lower()

        # Calculate similarity ratio
        ratio = SequenceMatcher(None, query_lower, candidate_lower).ratio()

        # Bonus for starts with
        if candidate_lower.startswith(query_lower):
            ratio += 0.3

        # Bonus for contains
        elif query_lower in candidate_lower:
            ratio += 0.2

        if ratio >= threshold:
            results.append((candidate, ratio))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def parse_filter_expression(expression: str) -> dict:
    """
    Parse a filter expression into a structured format

    Supports: tag1 AND tag2 NOT tag3

    Args:
        expression: Filter expression string

    Returns:
        Dict with 'include' and 'exclude' tag lists
    """
    tokens = expression.split()
    include_tags = []
    exclude_tags = []

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

    return {
        "include": include_tags,
        "exclude": exclude_tags
    }


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
    segments = [s.strip() for s in template.split(',')]

    for segment in segments:
        if not segment:
            continue

        # Check if it's a placeholder {category} or {category}[range]
        if segment.startswith('{') and '}' in segment:
            bracket_end = segment.index('}')
            category = segment[1:bracket_end]

            # Check for range specifier
            range_spec = None
            if bracket_end + 1 < len(segment) and segment[bracket_end + 1] == '[':
                range_str = segment[bracket_end + 2:-1]  # Extract content between [ and ]
                range_spec = range_str

            parts.append({
                "type": "category",
                "category": category,
                "range": range_spec
            })
        else:
            # Literal text
            parts.append({
                "type": "literal",
                "value": segment
            })

    return parts


def apply_export_template(template_parts: List[dict], image_data) -> str:
    """
    Apply export template to image data to generate caption

    Args:
        template_parts: Parsed template parts from parse_export_template
        image_data: ImageData instance

    Returns:
        Generated caption string
    """
    result = []

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
                    if ':' in range_spec:
                        parts = range_spec.split(':')
                        start = int(parts[0]) if parts[0] else 0
                        end = int(parts[1]) if parts[1] else len(tags)
                        tags = tags[start:end]
                    else:
                        # Single index
                        idx = int(range_spec)
                        tags = [tags[idx]] if 0 <= idx < len(tags) else []
                except (ValueError, IndexError):
                    tags = []

            # Add tag values to result
            for tag in tags:
                result.append(tag.value)

    return ", ".join(result)
