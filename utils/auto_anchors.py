import re
import sys

from lxml import etree

from utils import serialize_element

_LEADING_NUMBER = re.compile(r"^[\(\[]?(\d+)[\)\]\.]?\s+")
_TAG_SPLIT = re.compile(r"(<[^>]+>)")


def _anchor(num: str) -> str:
    return f'<a name="ftnref{num}" href="#ftn{num}">[{num}]</a>'


def _note_anchor(num: str) -> etree._Element:
    a_elem = etree.Element("a")
    a_elem.set("id", f"ftn{num}")
    a_elem.set("href", f"#ftnref{num}")
    a_elem.text = f"[{num}] "
    return a_elem


def _anchor_note(note_html: str) -> tuple[str, str | None]:
    """
    If *note_html* is a footnote without an anchor that starts with a number
    (e.g. "1 Some text"), prepend an ``ftnN`` anchor.
    Returns (html, number) — number is None when nothing was changed.
    """
    root = etree.fromstring(note_html, etree.HTMLParser())
    if root is None:
        return note_html, None
    paragraphs = root.xpath("//p")
    if not paragraphs:
        return note_html, None
    p = paragraphs[0]

    if p.xpath(".//a[@id or @name]"):
        return note_html, None

    if p.text and p.text.strip():
        match = _LEADING_NUMBER.match(p.text.lstrip())
        if not match:
            return note_html, None
        num = match.group(1)
        p.text = re.sub(r"^\s*[\(\[]?" + num + r"[\)\]\.]?\s*", "", p.text)
    else:
        # Number may sit inside a nested tag; prepend without deleting it
        match = _LEADING_NUMBER.match("".join(p.itertext()).strip())
        if not match:
            return note_html, None
        num = match.group(1)

    p.insert(0, _note_anchor(num))
    # Serialize as XML so void elements like <br/> stay well-formed XHTML
    return serialize_element(p), num


def _patterns(num: str):
    """Patterns for a body reference to note *num*, in priority order."""
    whole_html = [
        (re.compile(r"<sup>\s*0*" + num + r"\s*</sup>"), f"<sup>{_anchor(num)}</sup>"),
        (
            re.compile(r"<span[^>]*>\s*0*" + num + r"\s*</span>"),
            f'<span class="note-ref">{_anchor(num)}</span>',
        ),
    ]
    text_only = [
        # (12) or [12]
        re.compile(r"[\(\[]0*" + num + r"[\)\]]"),
        # word12 / word. 12 — but not a day in a date such as "February 6, 1694"
        re.compile(
            r"(?<=[^\W\d_]|[.,;:!?])\s*0*" + num + r"(?!\d)(?!\s*,\s*\d{4})"
        ),
    ]
    return whole_html, text_only


def _replace_first(html_str: str, start: int, num: str) -> tuple[str, int] | None:
    """
    Replace the first reference to note *num* found at or after *start*.
    Returns (new_html, end_offset_of_inserted_anchor) or None.
    """
    head, tail = html_str[:start], html_str[start:]
    whole_html, text_only = _patterns(num)

    candidates: list[tuple[int, int, str]] = []
    for pattern, replacement in whole_html:
        m = pattern.search(tail)
        if m:
            candidates.append((m.start(), m.end(), replacement))

    # Text-only patterns: never look inside tags or existing <a> elements
    parts = _TAG_SPLIT.split(tail)
    offset = 0
    in_a = False
    for i, part in enumerate(parts):
        if i % 2:
            low = part.lower()
            if low.startswith("<a ") or low == "<a>":
                in_a = True
            elif low == "</a>":
                in_a = False
        elif part and not in_a:
            for pattern in text_only:
                m = pattern.search(part)
                if m:
                    candidates.append((offset + m.start(), offset + m.end(), _anchor(num)))
                    break
        offset += len(part)

    if not candidates:
        return None
    s, e, replacement = min(candidates, key=lambda c: c[0])
    new_tail = tail[:s] + replacement + tail[e:]
    return head + new_tail, len(head) + s + len(replacement)


def inject_missing_anchors(fragments, notes):
    """
    Scans notes for unanchored footnote items (e.g. "1 Some text").
    If found, injects ftnN anchors into the notes and ftnrefN anchors into the
    body fragments. Body references are searched in note order, each note
    anchored at most once, and never before the previous note's reference.
    Returns (modified_fragments, modified_notes).
    """
    unanchored: list[str] = []
    modified_notes = []

    # Pass 1: anchor the notes themselves
    for note_html in notes:
        try:
            new_html, num = _anchor_note(note_html)
        except Exception as e:
            print(f"Error processing note: {e}", file=sys.stderr)
            new_html, num = note_html, None
        modified_notes.append(new_html)
        if num is not None and num not in unanchored:
            unanchored.append(num)

    if not unanchored:
        return fragments, modified_notes

    # Pass 2: find each body reference, in order, with a moving cursor
    html_cache: dict[int, str] = {}
    changed: set[int] = set()

    def html_of(idx: int) -> str:
        if idx not in html_cache:
            html_cache[idx] = etree.tostring(
                fragments[idx]["element"], encoding="unicode", method="html", with_tail=False
            )
        return html_cache[idx]

    paragraph_idx = [i for i, f in enumerate(fragments) if f["type"] == "paragraph"]
    cursor_pos = 0  # index into paragraph_idx
    cursor_off = 0  # character offset inside that paragraph's HTML

    for num in sorted(unanchored, key=int):
        for k in range(cursor_pos, len(paragraph_idx)):
            idx = paragraph_idx[k]
            start = cursor_off if k == cursor_pos else 0
            result = _replace_first(html_of(idx), start, num)
            if result:
                html_cache[idx], end = result
                changed.add(idx)
                cursor_pos, cursor_off = k, end
                break

    for idx in changed:
        try:
            tree = etree.fromstring(html_cache[idx], etree.HTMLParser())
            body_elems = tree.xpath("//body/*")
            if body_elems:
                fragments[idx]["element"] = body_elems[0]
        except Exception as e:
            print(f"Error re-parsing fragment: {e}", file=sys.stderr)

    return fragments, modified_notes
