from collections.abc import Iterator
from typing import Any

from selectolax.lexbor import LexborHTMLParser as html

allowed_tags: dict[str, dict[str, Any]] = {
    "card-body": {
        "allowed-children": {
            "p",
            "code",
            "table",
            "h1",
            "h2",
            "h3",
            "h4",
            "ul",
            "ol",
            "dl",
            "formula",
            "strong",
            "em",
            "i",
        }
    },
    "card-title": {},
    "p": {
        "allowed-children": {"b", "i", "s", "code", "strong", "em", "inline-formula"},
    },
    "code": {
        "allowed-attributes": {"class"},
    },
    "table": {
        "allowed-attributes": {"class"},
        "allowed-children": {"thead", "tbody", "tr"},
    },
    "thead": {"allowed-children": {"tr"}},
    "tbody": {"allowed-children": {"tr"}},
    "tr": {
        "allowed-children": {"td", "th"},
    },
    "td": {
        "allowed-attributes": {"colspan", "rowspan"},
        "allowed-children": {
            "p",
            "div",
            "span",
            "ul",
            "i",
            "ol",
            "formula",
            "inline-formula",
        },
    },
    "th": {
        "allowed-attributes": {"colspan", "rowspan"},
        "allowed-children": {"inline-formula"},
    },
    "h1": {},
    "h2": {},
    "h3": {},
    "h4": {},
    "ul": {"allowed-children": {"li"}},
    "ol": {"allowed-children": {"li"}},
    "li": {"allowed-children": {"ul", "ol", "inline-formula", "strong", "em", "i"}},
    "dl": {"allowed-children": {"dt", "dd"}},
    "dt": {"allowed-children": {"inline-formula"}},
    "dd": {"allowed-children": {"inline-formula", "strong", "em", "i"}},
    "formula": {},
    "inline-formula": {},
    "strong": {},
    "em": {},
    "i": {},
}


def validate(html_text: str) -> bool:
    """
    Validate the given HTML layout for a card.
    Strictly checks for allowed tags, structure and classes
    """

    try:
        tree = html(html_text)
    except (TypeError, ValueError):
        return False

    root = tree.root
    head = tree.css_first("head")
    body = tree.css_first("body")
    if root is None or body is None or root.attributes or body.attributes:
        return False

    # Lexbor wraps fragments in <html><head/><body>...</body></html>.
    # Content in <head> is not part of a layout and must not bypass validation.
    if head is not None and any(_element_children(head)):
        return False

    body_children = list(_element_children(body))
    if len(body_children) != 2:
        return False
    title, card_body = body_children

    if title.tag != "card-title" or card_body.tag != "card-body":
        return False

    def _validate_node(node: Any) -> bool:
        if node.tag not in allowed_tags:
            return False

        allowed_attributes = allowed_tags[node.tag].get("allowed-attributes", set())
        for attr in node.attributes:
            if attr not in allowed_attributes:
                return False

        allowed_children = allowed_tags[node.tag].get("allowed-children", set())
        for child in _element_children(node):
            if child.tag not in allowed_children:
                return False
            if not _validate_node(child):
                return False

        return True

    return _validate_node(title) and _validate_node(card_body)


def _element_children(node: Any) -> Iterator[Any]:
    """Yield a node's direct element children, excluding text and comments."""
    child = node.child
    while child is not None:
        if child.is_element_node:
            yield child
        child = child.next
