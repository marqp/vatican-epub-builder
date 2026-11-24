"""
Structural checks for built EPUBs (a lightweight stand-in for epubcheck).

Usage: python -m utils.check_epubs [EPUB_DIR]   (default: epubs)
Exits with status 1 if any problem is found.
"""

import collections
import glob
import os
import re
import sys
import zipfile

from lxml import etree

NS = {
    "x": "http://www.w3.org/1999/xhtml",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_ISO_DATE = re.compile(r"^\d{4}(-\d\d(-\d\d)?)?$")
_INVALID_TAGS = ("font", "center")


def check_epub(path: str) -> list[str]:
    issues: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        docs = {}
        for name in sorted(n for n in names if n.endswith((".xhtml", ".opf", ".ncx"))):
            try:
                docs[name] = etree.fromstring(z.read(name))
            except etree.XMLSyntaxError as e:
                issues.append(f"{name}: not well-formed XML ({e})")

    content = docs.get("OEBPS/text/content.xhtml")
    if content is None:
        return issues or ["missing OEBPS/text/content.xhtml"]

    ids = [el.get("id") for el in content.iter() if el.get("id")]
    dups = sorted(i for i, c in collections.Counter(ids).items() if c > 1)
    if dups:
        issues.append(f"duplicate ids: {dups[:5]}")
    id_set = set(ids)

    broken = [
        a.get("href")
        for a in content.iter(f"{{{NS['x']}}}a")
        if (a.get("href") or "").startswith("#") and a.get("href")[1:] not in id_set
    ]
    if broken:
        issues.append(f"{len(broken)} internal links with no target: {broken[:5]}")

    for tag in _INVALID_TAGS:
        n = len(content.findall(f".//{{{NS['x']}}}{tag}"))
        if n:
            issues.append(f"{n} <{tag}> elements")

    nav = docs.get("OEBPS/nav.xhtml")
    if nav is not None:
        for a in nav.iter(f"{{{NS['x']}}}a"):
            href = a.get("href", "")
            if href.startswith("text/content.xhtml#") and href.split("#", 1)[1] not in id_set:
                issues.append(f"nav link with no target: {href}")

    opf = docs.get("OEBPS/content.opf")
    if opf is not None:
        date = opf.findtext(".//dc:date", namespaces=NS)
        if date is not None and not _ISO_DATE.match(date):
            issues.append(f"dc:date not ISO 8601: {date!r}")

    return issues


def main() -> int:
    epub_dir = sys.argv[1] if len(sys.argv) > 1 else "epubs"
    paths = sorted(glob.glob(os.path.join(epub_dir, "*.epub")))
    failing = 0
    for path in paths:
        issues = check_epub(path)
        if issues:
            failing += 1
            print(f"=== {os.path.basename(path)} ===")
            for issue in issues:
                print(f"  - {issue}")
    print(f"\n{failing} of {len(paths)} EPUBs have problems.")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
