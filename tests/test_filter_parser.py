"""
Tests for the filter parser
"""
import pytest
from src.filter_parser import parse_filter, evaluate_filter, FilterParser


def test_exact_match():
    """Test exact tag matching"""
    tags = ['class:lake', 'setting:mountain', 'class:river']

    # Should match
    assert evaluate_filter('class:lake', tags) == True
    assert evaluate_filter('setting:mountain', tags) == True

    # Should NOT match (not exact)
    assert evaluate_filter('class:lakeside', tags) == False
    assert evaluate_filter('lake', tags) == False  # No category


def test_wildcard_match():
    """Test wildcard matching"""
    tags = ['class:lakeside', 'class:riverside', 'setting:mountain']

    # Wildcard should match
    assert evaluate_filter('class:lake*', tags) == True
    assert evaluate_filter('class:*side', tags) == True
    assert evaluate_filter('class:*', tags) == True

    # Should NOT match
    assert evaluate_filter('class:ocean*', tags) == False


def test_and_operator():
    """Test AND operator"""
    tags = ['class:lake', 'class:river', 'setting:mountain']

    # Both present - should match
    assert evaluate_filter('class:lake AND class:river', tags) == True
    assert evaluate_filter('class:lake AND setting:mountain', tags) == True

    # One missing - should NOT match
    tags2 = ['class:lake', 'setting:mountain']
    assert evaluate_filter('class:lake AND class:river', tags2) == False

    # Both missing - should NOT match
    tags3 = ['setting:mountain', 'camera:wide']
    assert evaluate_filter('class:lake AND class:river', tags3) == False


def test_or_operator():
    """Test OR operator"""
    tags = ['class:lake', 'setting:mountain']

    # One present - should match
    assert evaluate_filter('class:lake OR class:river', tags) == True
    assert evaluate_filter('class:river OR class:lake', tags) == True
    assert evaluate_filter('class:ocean OR setting:mountain', tags) == True

    # Both present - should match
    tags2 = ['class:lake', 'class:river']
    assert evaluate_filter('class:lake OR class:river', tags2) == True

    # Neither present - should NOT match
    tags3 = ['setting:desert', 'camera:wide']
    assert evaluate_filter('class:lake OR class:river', tags3) == False


def test_not_operator():
    """Test NOT operator"""
    tags = ['class:lake', 'setting:mountain']

    # Tag not present - should match
    assert evaluate_filter('NOT meta:deleted', tags) == True
    assert evaluate_filter('NOT class:river', tags) == True

    # Tag present - should NOT match
    assert evaluate_filter('NOT class:lake', tags) == False


def test_complex_expressions():
    """Test complex expressions with multiple operators"""
    tags = ['class:lake', 'class:river', 'setting:mountain']

    # (A OR B) AND C
    assert evaluate_filter('(class:lake OR class:ocean) AND setting:mountain', tags) == True
    assert evaluate_filter('(class:ocean OR class:desert) AND setting:mountain', tags) == False

    # A AND B AND C
    assert evaluate_filter('class:lake AND class:river AND setting:mountain', tags) == True
    assert evaluate_filter('class:lake AND class:river AND camera:wide', tags) == False

    # A AND NOT B
    assert evaluate_filter('class:lake AND NOT meta:deleted', tags) == True
    tags2 = ['class:lake', 'meta:deleted']
    assert evaluate_filter('class:lake AND NOT meta:deleted', tags2) == False

    # (A OR B) AND NOT C
    assert evaluate_filter('(class:lake OR class:river) AND NOT meta:deleted', tags) == True


def test_empty_tags():
    """Test filtering with empty tag list"""
    tags = []

    # Should NOT match (no tags to match)
    assert evaluate_filter('class:lake', tags) == False
    assert evaluate_filter('class:lake AND class:river', tags) == False

    # NOT should match (tag not present)
    assert evaluate_filter('NOT class:lake', tags) == True


def test_case_insensitivity():
    """Test case insensitive matching"""
    tags = ['Class:Lake', 'SETTING:MOUNTAIN']

    assert evaluate_filter('class:lake', tags) == True
    assert evaluate_filter('CLASS:LAKE', tags) == True
    assert evaluate_filter('setting:mountain', tags) == True
    assert evaluate_filter('class:lake AND setting:mountain', tags) == True


def test_special_characters():
    """Test tags with special characters"""
    tags = ['class:big-lake', 'setting:mountain_view', 'meta:test_123']

    assert evaluate_filter('class:big-lake', tags) == True
    assert evaluate_filter('setting:mountain_view', tags) == True
    assert evaluate_filter('meta:test_123', tags) == True

    # Wildcard with special chars
    assert evaluate_filter('class:big-*', tags) == True
    assert evaluate_filter('setting:mountain*', tags) == True


def test_exact_vs_substring():
    """Test that exact match doesn't do substring matching"""
    tags = ['class:lakeside', 'class:riverside']

    # Should NOT match - we want exact match, not substring
    assert evaluate_filter('class:lake', tags) == False
    assert evaluate_filter('class:river', tags) == False
    assert evaluate_filter('lake', tags) == False

    # But wildcard should match
    assert evaluate_filter('class:lake*', tags) == True
    assert evaluate_filter('class:river*', tags) == True


def test_duplicate_tags():
    """Test handling of duplicate tags"""
    tags = ['class:lake', 'class:lake', 'setting:mountain']

    # Should still match correctly
    assert evaluate_filter('class:lake', tags) == True
    assert evaluate_filter('class:lake AND setting:mountain', tags) == True


def test_invalid_expression():
    """Test handling of invalid expressions"""
    tags = ['class:lake']

    # These should raise ValueError
    with pytest.raises(ValueError):
        evaluate_filter('AND class:lake', tags)  # Missing operand

    with pytest.raises(ValueError):
        evaluate_filter('class:lake AND', tags)  # Missing operand


def test_empty_expression():
    """Test empty filter expression"""
    tags = ['class:lake', 'setting:mountain']

    # Empty expression should match everything
    assert evaluate_filter('', tags) == True
    assert evaluate_filter('   ', tags) == True


def test_quoted_strings():
    """Test tags with spaces using quoted strings"""
    tags = ['class:big lake', 'setting:mountain view']

    # Quoted strings should work
    assert evaluate_filter('"class:big lake"', tags) == True
    assert evaluate_filter('"setting:mountain view"', tags) == True

    # Should NOT match without quotes
    # (pyparsing will treat as separate tokens)
    # This is expected behavior


def test_operator_precedence():
    """Test that operators have correct precedence (NOT > AND > OR)"""
    tags = ['class:lake', 'setting:mountain']

    # NOT has highest precedence
    # "class:lake AND NOT setting:desert OR meta:deleted" should be:
    # (class:lake AND (NOT setting:desert)) OR meta:deleted
    assert evaluate_filter('class:lake AND NOT setting:desert OR meta:deleted', tags) == True

    # Without NOT, it's: (class:lake AND setting:mountain) OR meta:deleted
    assert evaluate_filter('class:lake AND setting:mountain OR meta:deleted', tags) == True
    assert evaluate_filter('class:ocean AND setting:mountain OR meta:deleted', tags) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
