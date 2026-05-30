"""
Content builder — orchestrates the transformation of raw Vatican HTML
into structured body fragments, footnotes, and a table-of-contents.

Pipeline passes:
  1. **Collect** — walk DOM nodes, separate body paragraphs from footnotes
  1.5. **Merge** — fuse bare Roman-numeral headings with their successor
  2. **Rank** — compute dynamic heading hierarchy from weight scores
  3. **Generate** — emit final XHTML strings and TOC entries
"""

import re
from lxml import etree

from utils import normspace, serialize_element
from utils.auto_anchors import inject_missing_anchors
from utils.smart_footnotes import inject_smart_links
from parser.cleaner import get_element_text, sanitize_element, is_language_switcher_bar
from parser.heuristics import extract_heading_metadata

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Text markers that signal the start of the main content
_INTRO_MARKERS = {
    "INTRODUÇÃO",
    "INTRODUCTION",
    "I INTRODUÇÃO",
    "I. INTRODUÇÃO",
    "I - INTRODUÇÃO",
}

# Text markers that signal the end of the main content / start of notes
_SECTION_END_MARKERS = {"notas", "notes", "referências", "references", "note"}


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def build_content_fragments(
    content: etree._Element,
    id_map: dict[str, str],
) -> tuple[list[str], list[str], list[dict[str, str | int]]]:
    """
    Parse a Vatican ``documento`` element into three outputs:

    Returns:
        body:  list of XHTML fragment strings
        notes: list of XHTML footnote strings
        toc:   list of dicts with ``id``, ``text``, ``level``
    """
    # --- Gather top-level content nodes ---
    xpath_query = (
        ".//p | .//hr | .//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6"
        " | .//ul | .//ol | .//blockquote"
        " | .//*[self::b or self::strong or self::i or self::em]"
    )
    raw_children = content.xpath(xpath_query)

    children = []
    for c in raw_children:
        # Skip nodes whose ancestor is already in our list (avoid duplication)
        if any(anc in raw_children for anc in c.iterancestors()):
            continue
        # Skip copyright sections
        if any(
            anc.get("class") and "doc-copyright" in anc.get("class") for anc in c.iterancestors()
        ):
            continue
        # Skip language switcher bars
        if any(
            anc.get("class") and "translation-field" in anc.get("class", "")
            for anc in c.iterancestors()
        ):
            continue
        if is_language_switcher_bar(get_element_text(c)):
            continue
        children.append(c)

    # --- Detect where the actual encyclical text begins ---
    start_index = _find_start_index(children)

    # --- Pass 1: Collect body fragments and footnotes ---
    fragments, notes = _collect_fragments(children[start_index:], id_map)

    # --- Pass 1.5: Merge bare Roman-numeral headings with next heading ---
    fragments = _merge_roman_numeral_headings(fragments)

    # --- Pass 2: Dynamic heading hierarchy + solitary-heading demotion ---
    heading_count = sum(1 for f in fragments if f["type"] == "heading")

    # A single heading is almost certainly a false positive — demote it
    if heading_count == 1:
        for f in fragments:
            if f["type"] == "heading":
                f["type"] = "paragraph"

    unique_weights = sorted(
        {f["meta"]["weight"] for f in fragments if f["type"] == "heading"},
        reverse=True,
    )
    weight_to_level = {w: min(i + 1, 6) for i, w in enumerate(unique_weights)}

    # Inject missing footnote anchors
    fragments, notes = inject_missing_anchors(fragments, notes)

    # --- Pass 3: HTML generation ---
    body: list[str] = []
    toc_entries: list[dict[str, str | int]] = []

    for f in fragments:
        if f["type"] == "heading":
            meta = f["meta"]
            level = weight_to_level[meta["weight"]]
            tag = f"h{level}"

            heading_el = etree.Element(tag)
            heading_el.set("id", str(meta["id"]))
            heading_el.text = str(meta["text"])

            body.append(serialize_element(heading_el))

            if not str(meta["id"]).startswith("ftn"):
                toc_entries.append(
                    {
                        "id": meta["id"],
                        "text": meta["text"],
                        "level": level,
                    }
                )
        else:
            cleaned = sanitize_element(f["element"], id_map)
            body.append(serialize_element(cleaned))

    return body, notes, toc_entries


# ---------------------------------------------------------------------------
# Helper: find where the encyclical body text starts
# ---------------------------------------------------------------------------


def _find_start_index(children: list[etree._Element]) -> int:
    """Scan children for the first 'Introduction' or '1. ...' marker."""
    start_index = 0

    for i, child in enumerate(children):
        if not isinstance(child.tag, str):
            continue
        if child.tag.lower() == "hr":
            continue

        if child.xpath('.//a[starts-with(@href, "#") and not(starts-with(@href, "#_ftn"))]'):
            continue

        text = normspace(get_element_text(child))
        if text.upper() in _INTRO_MARKERS or text.startswith("1. ") or text.startswith("2. "):
            start_index = i

            # Backtrack to include preceding section headings
            if text.startswith("1. ") or text.startswith("2. "):
                if text.startswith("2. ") and i > 0:
                    start_index = i - 1

                for j in range(start_index - 1, max(start_index - 5, -1), -1):
                    prev = children[j]
                    if not isinstance(prev.tag, str):
                        continue
                    prev_text = normspace(get_element_text(prev))
                    if (
                        prev_text
                        and (re.match(r"^[IVXLCDM]+\.", prev_text) or prev_text.isupper())
                        and len(prev_text) < 150
                    ):
                        is_centered = (
                            "text-align: center" in prev.get("style", "").lower()
                            or prev.get("align", "").lower() == "center"
                        )
                        has_bold = prev.tag.lower() in ("b", "strong") or bool(
                            prev.xpath(".//b | .//strong")
                        )
                        if is_centered or has_bold or prev_text.isupper():
                            start_index = j
                            break
            break

    return start_index


# ---------------------------------------------------------------------------
# Helper: collect body fragments and footnotes (Pass 1)
# ---------------------------------------------------------------------------


def _collect_fragments(
    children: list[etree._Element],
    id_map: dict[str, str],
) -> tuple[list[dict], list[str]]:
    """Walk children, classifying each as heading, paragraph, or footnote."""
    notes: list[str] = []
    fragments: list[dict] = []
    has_reached_end = False

    for child in children:
        if not isinstance(child.tag, str):
            continue

        # <hr> separates body from footnotes
        if child.tag.lower() == "hr":
            if fragments and not has_reached_end:
                has_reached_end = True
            continue

        # <hr> wrapped inside another tag
        if child.xpath(".//hr") and not normspace(get_element_text(child)):
            if fragments and not has_reached_end:
                has_reached_end = True
            continue

        text = normspace(get_element_text(child))
        if not text:
            continue

        # Detect end-of-body markers
        if not has_reached_end:
            text_lower = text.lower()
            if (
                text_lower in _SECTION_END_MARKERS
                or "copyright" in text_lower
                or "fonti francescane" in text_lower
            ):
                has_reached_end = True

        # Determine if this element is a footnote
        is_footnote = bool(
            child.xpath('.//a[starts-with(@name, "_ft") and not(starts-with(@name, "_ftnref"))]')
        )
        if not is_footnote:
            is_footnote = " MsoFootnoteText " in f" {child.get('class', '')} "

        # Everything after the end marker is a footnote
        if has_reached_end and text.lower() not in _SECTION_END_MARKERS:
            if "copyright" not in text.lower() and "fonti francescane" not in text.lower():
                is_footnote = True

        if is_footnote:
            cleaned = sanitize_element(child, id_map)
            etree.strip_tags(cleaned, "font", "span", "p", "div", "center")
            cleaned.tag = "p"
            cleaned.set("class", "footnote")
            if cleaned.text:
                cleaned.text = cleaned.text.lstrip()
            if normspace(get_element_text(cleaned)):
                notes.append(inject_smart_links(serialize_element(cleaned)))
        else:
            if has_reached_end:
                continue

            meta = extract_heading_metadata(child, id_map)
            if meta:
                fragments.append({"type": "heading", "element": child, "meta": meta})
            else:
                fragments.append({"type": "paragraph", "element": child})

        # Handle tail text
        tail_text = normspace(child.tail) if child.tail else ""
        if tail_text:
            p_tail = etree.Element("p")
            p_tail.text = tail_text
            fragments.append({"type": "paragraph", "element": p_tail})

    return fragments, notes


# ---------------------------------------------------------------------------
# Helper: merge bare Roman-numeral headings (Pass 1.5)
# ---------------------------------------------------------------------------


def _merge_roman_numeral_headings(
    fragments: list[dict],
) -> list[dict]:
    """
    Fuse consecutive headings where the first is a bare Roman numeral
    (e.g. ``II.`` followed by ``THE ACTUAL TITLE``).
    """
    merged = []
    i = 0
    while i < len(fragments):
        f = fragments[i]
        if (
            f["type"] == "heading"
            and i + 1 < len(fragments)
            and re.match(r"^[IVXLCDM]+\.\s*$", f["meta"]["text"].strip())
        ):
            next_f = fragments[i + 1]
            if next_f["type"] == "heading":
                merged_text = f["meta"]["text"].rstrip() + " " + next_f["meta"]["text"]
                next_f["meta"]["text"] = merged_text
                next_f["meta"]["weight"] = max(f["meta"]["weight"], next_f["meta"]["weight"])
                merged.append(next_f)
                i += 2
                continue
        merged.append(f)
        i += 1
    return merged
