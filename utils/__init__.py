import re
import html as html_lib
import unicodedata
from lxml import etree


def normspace(value: str) -> str:
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def escape(value: str) -> str:
    return html_lib.escape(value, quote=True)


def safe_id(value: str, used: set[str]) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized).strip("_")
    normalized = normalized or "section"
    if normalized[0].isdigit():
        normalized = f"id_{normalized}"

    candidate = normalized
    i = 2
    while candidate in used:
        candidate = f"{normalized}_{i}"
        i += 1
    used.add(candidate)
    return candidate


def remove_preserving_tail(parent: etree._Element, child: etree._Element) -> None:
    tail = child.tail
    previous = child.getprevious()
    parent.remove(child)
    if tail:
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail


def serialize_element(element: etree._Element) -> str:
    return etree.tostring(element, encoding="unicode", method="xml", with_tail=False)
