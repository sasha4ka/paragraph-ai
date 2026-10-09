from typing import Any

from lxml import html

allowed_tags: dict[str, dict[str, Any]] = {
    "div": {
        "allowed-attributes": {"class"},
        "allowed-children": {
            "div",
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "ul",
            "ol",
            "table",
            "formula",
            "inline-formula",
        },
    },
    "section": {
        "allowed-attributes": {"class"},
        "allowed-children": {
            "div",
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "ul",
            "ol",
            "table",
            "formula",
            "inline-formula",
        },
    },
    "span": {
        "allowed-attributes": {"class"},
        "allowed-children": {"b", "i", "s", "code", "strong", "em", "inline-formula"},
    },
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
        parser = html.HTMLParser(remove_comments=True, recover=False)
        tree = html.fromstring(html_text, parser=parser)
    except Exception:
        return False

    for element in tree.iter():
        tag = element.tag
        if tag not in allowed_tags:
            return False

        allowed_attributes = allowed_tags[tag].get("allowed-attributes", set())
        for attr in element.attrib:
            if attr not in allowed_attributes:
                return False

        allowed_children = allowed_tags[tag].get("allowed-children", set())
        for child in element:
            if child.tag not in allowed_children:
                return False

    return True
