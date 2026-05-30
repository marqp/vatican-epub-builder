"""
HTML cleaning utilities for Vatican encyclical source pages.

Handles DOM normalisation, whitespace cleanup, footnote anchor repair,
loose-text wrapping, and attribute sanitisation for EPUB-ready XHTML.
"""

import re
from copy import deepcopy
from urllib.parse import urljoin

from lxml import etree

import config
from utils import normspace, safe_id, remove_preserving_tail

# Language codes commonly found in Vatican translation switcher bars
_COMMON_LANG_CODES = frozenset(
    {
        "PT",
        "EN",
        "ES",
        "IT",
        "FR",
        "DE",
        "LA",
        "PL",
        "HU",
        "ZH",
        "RU",
        "AR",
        "BY",
        "HR",
        "CS",
        "FI",
        "EL",
        "KO",
        "LV",
        "LT",
        "NO",
        "RO",
        "SK",
        "SL",
        "SV",
        "TR",
    }
)

_BLOCK_TAGS = frozenset(
    {
        "p",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "blockquote",
        "div",
        "table",
        "center",
    }
)


def get_element_text(element: etree._Element) -> str:
    """Recursively extract all text from an element, treating <br> as space."""
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        if isinstance(child.tag, str) and child.tag.lower() == "br":
            parts.append(" ")
        parts.append(get_element_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def is_language_switcher_bar(text: str) -> bool:
    """Return True if *text* looks like a Vatican language-switcher bar (e.g. 'PT EN ES IT')."""
    text = normspace(text)
    if not text:
        return False
    words = re.findall(r"\b\w+\b", text)
    if len(words) < 2:
        return False
    if all(len(w) in (1, 2, 3) and w.isupper() for w in words):
        if sum(1 for w in words if w in _COMMON_LANG_CODES) >= 2:
            return True
    return False


def build_id_map(content: etree._Element) -> dict[str, str]:
    """Build a mapping from original anchor names to EPUB-safe IDs."""
    used: set[str] = set()
    ids: dict[str, str] = {}
    for anchor in content.xpath(".//a[@name]"):
        old = anchor.get("name")
        if old and old not in ids:
            ids[old] = safe_id(old, used)
    return ids


def sanitize_element(
    element: etree._Element,
    id_map: dict[str, str],
) -> etree._Element:
    """
    Deep-copy *element* and clean it for EPUB output:
    normalise tags, strip attributes, fix links, and preserve centering.
    """
    cleaned = deepcopy(element)

    def _clean(node: etree._Element) -> None:
        if not isinstance(node.tag, str):
            return

        # Normalise presentational tags to semantic ones
        tag = node.tag.lower()
        if tag == "b":
            node.tag = "strong"
        elif tag == "i":
            node.tag = "em"

        # Collapse whitespace
        if node.text:
            node.text = re.sub(r"\s+", " ", node.text.replace("\xa0", " "))
        if node.tail:
            node.tail = re.sub(r"\s+", " ", node.tail.replace("\xa0", " "))

        # Recurse into children
        for child in list(node):
            if not isinstance(child.tag, str):
                remove_preserving_tail(node, child)
                continue
            _clean(child)

        # Preserve only the attributes we care about
        original_style = node.get("style", "")
        name = node.get("name")
        href = node.get("href")
        text_align_center = "text-align: center" in original_style.lower()

        for attr in list(node.attrib):
            del node.attrib[attr]

        if name:
            node.set("id", id_map.get(name, name))

        if node.tag == "a" and href:
            if href.startswith("#"):
                node.set("href", f"#{id_map.get(href[1:], href[1:])}")
            else:
                full_url = urljoin(config.SOURCE_URL, href)
                node.set(
                    "href", full_url.replace("http://www.vatican.va", "https://www.vatican.va")
                )

        if text_align_center and node.tag in {"p", "div"}:
            node.set("class", "center")

    _clean(cleaned)
    return cleaned


def normalize_footnotes(content: etree._Element) -> None:
    """Ensure every footnote anchor sits inside a <p> wrapper."""
    for a in content.xpath(
        './/a[starts-with(@name, "_ft") and not(starts-with(@name, "_ftnref"))]'
    ):
        parent = a.getparent()
        if parent is not None and parent.tag.lower() != "p":
            tail = a.tail
            a.tail = None
            new_p = etree.Element("p")
            parent.replace(a, new_p)
            new_p.append(a)
            a.tail = tail


def has_block_elements(element: etree._Element, block_tags: frozenset) -> bool:
    """Return True if any descendant of *element* is a block-level tag."""
    for child in element.iterdescendants():
        if isinstance(child.tag, str) and child.tag.lower() in block_tags:
            return True
    return False


def wrap_loose_text(content: etree._Element) -> None:
    """
    Wrap inline children and bare text nodes into <p> elements
    so the content is valid block-level HTML.
    """
    # Recurse into container elements first
    for child in list(content):
        if isinstance(child.tag, str) and child.tag.lower() in {"div", "blockquote", "center"}:
            wrap_loose_text(child)

    new_children: list[etree._Element] = []
    current_p: etree._Element | None = None

    def _get_or_create_p() -> etree._Element:
        nonlocal current_p
        if current_p is None:
            current_p = etree.Element("p")
            new_children.append(current_p)
        return current_p

    if content.text and content.text.strip():
        _get_or_create_p().text = content.text
        content.text = None

    for child in list(content):
        if not isinstance(child.tag, str):
            if current_p is not None:
                current_p.append(child)
            else:
                new_children.append(child)
        elif child.tag.lower() in _BLOCK_TAGS or has_block_elements(child, _BLOCK_TAGS):
            current_p = None
            new_children.append(child)
        else:
            _get_or_create_p().append(child)

        if child.tail and child.tail.strip():
            if isinstance(child.tag, str) and child.tag.lower() in _BLOCK_TAGS:
                current_p = etree.Element("p")
                current_p.text = child.tail
                child.tail = None
                new_children.append(current_p)

    for child in list(content):
        content.remove(child)
    for child in new_children:
        content.append(child)
