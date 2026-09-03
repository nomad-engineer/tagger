"""
Advanced filter parser using pyparsing for robust tag filtering

Supports:
- Exact matching: class:lake (matches only "class:lake")
- Wildcard matching: class:lake* (matches "class:lake", "class:lakeside", etc.)
- Logical operators: AND, OR, NOT
- Parentheses for grouping: (class:lake OR class:river) AND NOT meta:deleted
- Quoted strings: "class:big lake" for tags with spaces
- Special predicates:
    type:image / type:video     — filter by media type
    has:alpha                   — images with variable alpha (transparency)
    has:caption                 — images that have a caption
    has:tags                    — images that have at least one tag
    untagged                    — images with zero tags
    tag_count>N / tag_count<N / tag_count=N  — filter by tag count
"""
from typing import List, Set, Tuple
from fnmatch import fnmatch
from pyparsing import (
    Word, alphanums, alphas, Keyword, Group, Forward,
    QuotedString, Suppress, opAssoc, infix_notation,
    pyparsing_common, ParseException, Regex
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
class MediaTypePredicate(FilterNode):
    """Filter by media type (image, video)"""
    media_type: str

    def evaluate(self, tags: List[str]) -> bool:
        # In-memory evaluation not supported for media predicates
        return True

    def __repr__(self):
        return f"MediaType({self.media_type})"


@dataclass
class HasPredicate(FilterNode):
    """Filter by property: alpha, caption, tags"""
    property: str

    def evaluate(self, tags: List[str]) -> bool:
        if self.property == "tags":
            return len(tags) > 0
        return True

    def __repr__(self):
        return f"Has({self.property})"


@dataclass
class UntaggedPredicate(FilterNode):
    """Match images with zero tags"""

    def evaluate(self, tags: List[str]) -> bool:
        return len(tags) == 0

    def __repr__(self):
        return "Untagged()"


@dataclass
class TagCountPredicate(FilterNode):
    """Filter by tag count: tag_count>N, tag_count<N, tag_count=N"""
    operator: str  # '>', '<', '=', '>=', '<='
    count: int

    def evaluate(self, tags: List[str]) -> bool:
        n = len(tags)
        if self.operator == '>':
            return n > self.count
        elif self.operator == '<':
            return n < self.count
        elif self.operator == '=':
            return n == self.count
        elif self.operator == '>=':
            return n >= self.count
        elif self.operator == '<=':
            return n <= self.count
        return True

    def __repr__(self):
        return f"TagCount({self.operator}{self.count})"


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

        # Special predicates — must be checked before general tag pattern
        # type:image, type:video
        media_type = Regex(r"type:(image|video)", re_flags=0).set_parse_action(
            lambda t: MediaTypePredicate(t[0].split(":")[1].lower())
        )

        # has:alpha, has:caption, has:tags
        has_pred = Regex(r"has:(alpha|caption|tags)", re_flags=0).set_parse_action(
            lambda t: HasPredicate(t[0].split(":")[1].lower())
        )

        # untagged
        untagged = Keyword("untagged", caseless=True).set_parse_action(
            lambda t: UntaggedPredicate()
        )

        # tag_count>N, tag_count<N, tag_count=N, tag_count>=N, tag_count<=N
        tag_count = Regex(r"tag_count\s*(>=|<=|>|<|=)\s*(\d+)").set_parse_action(
            lambda t: TagCountPredicate(
                operator=t[0].replace("tag_count", "").strip().split(str(int(''.join(c for c in t[0] if c.isdigit()))))[0].strip(),
                count=int(''.join(c for c in t[0] if c.isdigit()))
            )
        )

        # Simpler tag_count parsing
        def parse_tag_count(t):
            import re
            m = re.match(r"tag_count\s*(>=|<=|>|<|=)\s*(\d+)", t[0])
            if m:
                return TagCountPredicate(operator=m.group(1), count=int(m.group(2)))
        tag_count = Regex(r"tag_count\s*(>=|<=|>|<|=)\s*\d+").set_parse_action(parse_tag_count)

        # Define tag pattern: word characters, colons, asterisks, hyphens
        tag_chars = alphanums + ":*-_."
        tag_pattern = Word(tag_chars)

        # Also support quoted strings for tags with spaces
        quoted_tag = QuotedString('"', esc_char='\\')

        # A tag is either a special predicate or a regular pattern or quoted string
        tag = (
            media_type | has_pred | untagged | tag_count |
            quoted_tag.set_parse_action(lambda t: TagPattern(t[0])) |
            tag_pattern.set_parse_action(lambda t: TagPattern(t[0]))
        )

        # Define logical operators
        AND = Keyword("AND", caseless=True)
        OR = Keyword("OR", caseless=True)
        NOT = Keyword("NOT", caseless=True)

        # Build expression with operator precedence
        # NOT has highest precedence, then AND, then OR

        def make_and_node(tokens):
            """Create AND nodes, handling multiple consecutive ANDs"""
            t = tokens[0]
            if len(t) == 1:
                return t[0]
            result = t[0]
            for i in range(2, len(t), 2):
                result = AndNode(result, t[i])
            return result

        def make_or_node(tokens):
            """Create OR nodes, handling multiple consecutive ORs"""
            t = tokens[0]
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
    elif isinstance(node, MediaTypePredicate):
        return "m.media_type = ?", [node.media_type]
    elif isinstance(node, HasPredicate):
        if node.property == "alpha":
            return "m.has_alpha = 1", []
        elif node.property == "caption":
            return "EXISTS (SELECT 1 FROM captions _c WHERE _c.media_hash = m.hash AND _c.content != '')", []
        elif node.property == "tags":
            return "EXISTS (SELECT 1 FROM tags _t WHERE _t.media_hash = m.hash)", []
        else:
            return "1=1", []
    elif isinstance(node, UntaggedPredicate):
        return "NOT EXISTS (SELECT 1 FROM tags _t WHERE _t.media_hash = m.hash)", []
    elif isinstance(node, TagCountPredicate):
        return (
            f"(SELECT COUNT(*) FROM tags _t WHERE _t.media_hash = m.hash) {node.operator} ?",
            [node.count],
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
