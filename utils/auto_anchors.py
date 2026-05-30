import re
from lxml import etree
import sys


def inject_missing_anchors(fragments, notes):
    """
    Scans notes for unanchored footnote items (e.g. "1 Some text").
    If found, injects the ftn1 and ftnref1 anchors into the notes and the fragments.
    Returns (modified_fragments, modified_notes)
    """
    unanchored = {}  # mapping of number -> bool (whether it was found in fragments)
    modified_notes = []

    # Pass 1: Parse notes and find unanchored ones
    for note_html in notes:
        try:
            parser = etree.HTMLParser()
            root = etree.fromstring(note_html, parser)

            p = root.xpath("//p")
            if not p:
                modified_notes.append(note_html)
                continue

            p = p[0]

            # Check if it already has an anchor
            has_anchor = bool(p.xpath(".//a[@id or @name]"))
            if has_anchor:
                modified_notes.append(note_html)
                continue

            # It has no anchor. Does it start with a number?
            if p.text and p.text.strip():
                match = re.match(r"^[\(\[]?(\d+)[\)\]\.]?\s+", p.text.lstrip())
                if match:
                    num = match.group(1)
                    original_text = p.text

                    # Strip leading spaces and the number pattern
                    stripped_text = re.sub(
                        r"^\s*[\(\[]?" + num + r"[\)\]\.]?\s*", "", original_text
                    )
                    p.text = stripped_text

                    # Create the anchor element
                    a_elem = etree.Element("a")
                    a_elem.set("id", f"ftn{num}")
                    a_elem.set("href", f"#ftnref{num}")
                    a_elem.text = f"[{num}] "

                    # Insert the anchor at the beginning of the <p>
                    p.insert(0, a_elem)

                    new_note_html = etree.tostring(p, encoding="unicode", method="html")
                    modified_notes.append(new_note_html)
                    unanchored[num] = False
                else:
                    modified_notes.append(note_html)
            else:
                # Number might be in a span or b tag at the start
                text_content = "".join(p.itertext()).strip()
                match = re.match(r"^[\(\[]?(\d+)[\)\]\.]?\s+", text_content)
                if match:
                    num = match.group(1)
                    # We will simply prepend the anchor and not try to delete the old number
                    # if it's deeply nested, to avoid breaking HTML.
                    # But if it's just text, it would be caught above.
                    # For safety, just prepend.
                    a_elem = etree.Element("a")
                    a_elem.set("id", f"ftn{num}")
                    a_elem.set("href", f"#ftnref{num}")
                    a_elem.text = f"[{num}] "
                    p.insert(0, a_elem)

                    new_note_html = etree.tostring(p, encoding="unicode", method="html")
                    modified_notes.append(new_note_html)
                    unanchored[num] = False
                else:
                    modified_notes.append(note_html)

        except Exception as e:
            print(f"Error processing note: {e}", file=sys.stderr)
            modified_notes.append(note_html)

    if not unanchored:
        return fragments, modified_notes

    # Pass 2: Search for the missing numbers in the fragments
    modified_fragments = []

    for frag in fragments:
        if frag["type"] != "paragraph":
            modified_fragments.append(frag)
            continue

        element = frag["element"]
        html_str = etree.tostring(element, encoding="unicode", method="html")

        # We need to split HTML into text nodes and tags to avoid replacing inside tags
        parts = re.split(r"(<[^>]+>)", html_str)

        for num in unanchored.keys():
            sup_pattern = re.compile(r"<sup>\s*0*" + num + r"\s*</sup>")
            span_pattern = re.compile(r"<span[^>]*>\s*0*" + num + r"\s*</span>")
            br_pattern = re.compile(r"([\(\[])0*" + num + r"([\)\]])")
            post_word_pattern = re.compile(r"(?<=[A-Za-z\.\,\;\:\!\?])\s*0*" + num + r"(?!\d)")

            def replace_br(match):
                unanchored[num] = True
                return f'<a name="ftnref{num}" href="#ftn{num}">[{num}]</a>'

            def replace_post_word(match):
                unanchored[num] = True
                return f'<a name="ftnref{num}" href="#ftn{num}">[{num}]</a>'

            for i in range(0, len(parts), 2):  # Even indices are text
                # Try brackets first
                old_part = parts[i]
                parts[i] = br_pattern.sub(replace_br, parts[i])

                # If brackets didn't match, try post word pattern (e.g. word1 or word.1)
                if old_part == parts[i]:
                    parts[i] = post_word_pattern.sub(replace_post_word, parts[i])

            html_str = "".join(parts)

            # Now run sup_pattern on the whole HTML safely, since <sup> is a tag structure
            if sup_pattern.search(html_str):
                html_str = sup_pattern.sub(
                    f'<sup><a name="ftnref{num}" href="#ftn{num}">[{num}]</a></sup>', html_str
                )
                unanchored[num] = True

            if span_pattern.search(html_str):
                html_str = span_pattern.sub(
                    f'<span class="note-ref"><a name="ftnref{num}" href="#ftn{num}">[{num}]</a></span>',
                    html_str,
                )
                unanchored[num] = True

        try:
            # Parse back
            new_elem_tree = etree.fromstring(html_str, etree.HTMLParser())
            body_elems = new_elem_tree.xpath("//body/*")
            if body_elems:
                frag["element"] = body_elems[0]
            modified_fragments.append(frag)
        except Exception:
            modified_fragments.append(frag)

    return modified_fragments, modified_notes
