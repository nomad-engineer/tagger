"""
Advanced filter parser using pyparsing for robust tag filtering

Supports:
- Exact matching: class:lake (matches only "class:lake")
- Wildcard matching: class:lake* (matches "class:lake", "class:lakeside", etc.)
- Logical operators: AND, OR, NOT
- Parentheses for grouping: (class:lake OR class:river) AND NOT meta:deleted
- Quoted strings: "class:big lake" for tags with spaces
"""
from typing import List, Set
from fnmatch import fnmatch
from pyparsing import (
    Word, alphanums, alphas, Keyword, Group, Forward,
    QuotedString, Suppress, opAssoc, infix_notation,
    pyparsing_common, ParseException
)
from dataclasses import dataclass
from abc import ABC, abstractmethod


# Abstract base class for filter nodes
class FilterNode(ABC):
    """Base class for filter expression nodes"""

    @abstractmethod
    def evaluate(self, tags: List[str]) -> bool:
        """Evaluate this node against a list of tag strings"""
        pass


@dataclass
class TagPattern(FilterNode):
    """A tag pattern that can be exact or wildcard"""
    pattern: str

    def evaluate(self, tags: List[str]) -> bool:
        """Check if any tag matches this pattern"""
        pattern_lower = self.pattern.lower()

        for tag in tags:
            tag_lower = tag.lower()

            # Exact match if no wildcard
            if '*' not in pattern_lower:
                if pattern_lower == tag_lower:
                    return True
            else:
                # Wildcard match
                if fnmatch(tag_lower, pattern_lower):
                    return True

        return False

    def __repr__(self):
        return f"TagPattern({self.pattern})"


@dataclass
class NotNode(FilterNode):
    """NOT operator node"""
    operand: FilterNode

    def evaluate(self, tags: List[str]) -> bool:
        return not self.operand.evaluate(tags)

    def __repr__(self):
        return f"NOT({self.operand})"


@dataclass
class AndNode(FilterNode):
    """AND operator node"""
    left: FilterNode
    right: FilterNode

    def evaluate(self, tags: List[str]) -> bool:
        return self.left.evaluate(tags) and self.right.evaluate(tags)

    def __repr__(self):
        return f"AND({self.left}, {self.right})"


@dataclass
class OrNode(FilterNode):
    """OR operator node"""
    left: FilterNode
    right: FilterNode

    def evaluate(self, tags: List[str]) -> bool:
        return self.left.evaluate(tags) or self.right.evaluate(tags)

    def __repr__(self):
        return f"OR({self.left}, {self.right})"


class FilterParser:
    """Parse filter expressions into an expression tree"""

    def __init__(self):
        self._grammar = self._build_grammar()

    def _build_grammar(self):
        """Build the pyparsing grammar for filter expressions"""

        # Define tag pattern: word characters, colons, asterisks, hyphens
        # Examples: class:lake, class:lake*, setting:big-mountain
        tag_chars = alphanums + ":*-_"
        tag_pattern = Word(tag_chars)

        # Also support quoted strings for tags with spaces
        quoted_tag = QuotedString('"', esc_char='\\')

        # A tag is either a regular pattern or quoted string
        tag = (quoted_tag | tag_pattern).set_parse_action(lambda t: TagPattern(t[0]))

        # Define logical operators
        AND = Keyword("AND", caseless=True)
        OR = Keyword("OR", caseless=True)
        NOT = Keyword("NOT", caseless=True)

        # Build expression with operator precedence
        # NOT has highest precedence, then AND, then OR

        def make_and_node(tokens):
            """Create AND nodes, handling multiple consecutive ANDs"""
            t = tokens[0]
            # t will be [operand, AND, operand, AND, operand, ...]
            # Build left-associative tree
            if len(t) == 1:
                return t[0]
            result = t[0]
            for i in range(2, len(t), 2):
                result = AndNode(result, t[i])
            return result

        def make_or_node(tokens):
            """Create OR nodes, handling multiple consecutive ORs"""
            t = tokens[0]
            # t will be [operand, OR, operand, OR, operand, ...]
            # Build left-associative tree
            if len(t) == 1:
                return t[0]
            result = t[0]
            for i in range(2, len(t), 2):
                result = OrNode(result, t[i])
            return result

        expr = Forward()
        expr <<= infix_notation(
            tag,
            [
                (NOT, 1, opAssoc.RIGHT, lambda t: NotNode(t[0][1])),
                (AND, 2, opAssoc.LEFT, make_and_node),
                (OR, 2, opAssoc.LEFT, make_or_node),
            ]
        )

        return expr

    def parse(self, expression: str) -> FilterNode:
        """
        Parse a filter expression into an expression tree

        Args:
            expression: Filter expression string

        Returns:
            Root FilterNode of the expression tree

        Raises:
            ParseException: If expression is invalid
        """
        if not expression or not expression.strip():
            # Empty expression matches everything
            return TagPattern("*")

        try:
            result = self._grammar.parse_string(expression, parse_all=True)
            return result[0]
        except ParseException as e:
            raise ValueError(f"Invalid filter expression: {e}")

    def evaluate(self, expression: str, tags: List[str]) -> bool:
        """
        Parse and evaluate a filter expression against a list of tags

        Args:
            expression: Filter expression string
            tags: List of tag strings (e.g., ["class:lake", "setting:mountain"])

        Returns:
            True if tags match the expression, False otherwise
        """
        tree = self.parse(expression)
        return tree.evaluate(tags)


# Singleton instance
_parser = FilterParser()


def parse_filter(expression: str) -> FilterNode:
    """
    Parse a filter expression into an expression tree

    Args:
        expression: Filter expression string

    Returns:
        Root FilterNode of the expression tree
    """
    return _parser.parse(expression)


def evaluate_filter(expression: str, tags: List[str]) -> bool:
    """
    Evaluate a filter expression against a list of tags

    Args:
        expression: Filter expression string
        tags: List of tag strings

    Returns:
        True if tags match the expression, False otherwise
    """
    return _parser.evaluate(expression, tags)


from typing import Tuple

def filter_node_to_sql(node: FilterNode) -> Tuple[str, list]:
    """
    Convert a FilterNode tree to a SQL WHERE clause fragment.

    The clause references alias 'm' for the media table.
    Returns (sql_fragment, params_list).
    """
    if isinstance(node, TagPattern):
        pattern = node.pattern.lower()
        if '*' in pattern:
            sql_pattern = pattern.replace('*', '%')
            return (
                "EXISTS (SELECT 1 FROM tags _t WHERE _t.media_hash = m.hash AND LOWER(_t.value) LIKE ?)",
                [sql_pattern],
            )
        else:
            return (
                "EXISTS (SELECT 1 FROM tags _t WHERE _t.media_hash = m.hash AND LOWER(_t.value) = ?)",
                [pattern],
            )
    elif isinstance(node, NotNode):
        clause, params = filter_node_to_sql(node.operand)
        return f"NOT ({clause})", params
    elif isinstance(node, AndNode):
        lc, lp = filter_node_to_sql(node.left)
        rc, rp = filter_node_to_sql(node.right)
        return f"({lc} AND {rc})", lp + rp
    elif isinstance(node, OrNode):
        lc, lp = filter_node_to_sql(node.left)
        rc, rp = filter_node_to_sql(node.right)
        return f"({lc} OR {rc})", lp + rp
    else:
        return "1=1", []
