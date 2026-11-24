"""
Final link/ID integrity pass for the assembled content document.

Vatican source pages (and footnote auto-anchoring) can produce duplicate IDs
and internal links whose target doesn't exist. Both are epubcheck errors, so
they are repaired here just before the XHTML is written.
"""

from lxml import etree

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"


def repair_links_and_ids(body_xhtml: str) -> str:
    """
    Take the inner XHTML of <body> and return it with:
      - duplicate ``id`` attributes removed (the first occurrence is kept);
      - internal ``href="#x"`` links without a matching ``id`` unlinked
        (the ``href`` is dropped, the text is kept).
    """
    wrapper = etree.fromstring(
        f'<body xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}">{body_xhtml}</body>'
    )

    seen: set[str] = set()
    for el in wrapper.iter():
        el_id = el.get("id")
        if el_id is None:
            continue
        if el_id in seen:
            del el.attrib["id"]
        else:
            seen.add(el_id)

    for el in wrapper.iter(f"{{{XHTML_NS}}}a"):
        href = el.get("href")
        if href is not None and href.startswith("#") and href[1:] not in seen:
            del el.attrib["href"]

    parts = [wrapper.text or ""]
    for child in wrapper:
        parts.append(etree.tostring(child, encoding="unicode", with_tail=True))
    # Drop the namespace declarations lxml re-adds on top-level children
    out = "".join(parts)
    out = out.replace(f' xmlns="{XHTML_NS}"', "").replace(f' xmlns:epub="{EPUB_NS}"', "")
    return out
