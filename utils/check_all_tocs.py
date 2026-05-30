import os
import glob
import zipfile
from lxml import etree

EPUB_DIR = "epubs"
ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}


def check_epub_toc(epub_path):
    issues = []

    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            if "OEBPS/toc.ncx" not in z.namelist():
                return ["Missing OEBPS/toc.ncx"]
            toc_data = z.read("OEBPS/toc.ncx")
    except Exception as e:
        return [f"Error reading zip: {e}"]

    try:
        root = etree.fromstring(toc_data)
    except Exception as e:
        return [f"Error parsing XML: {e}"]

    navMap = root.find("ncx:navMap", ns)
    if navMap is None:
        return ["No navMap found"]

    entries = []

    def extract_entries(node, depth):
        text_node = node.find("ncx:navLabel/ncx:text", ns)
        if text_node is not None and text_node.text:
            text = text_node.text.strip()
            # Ignore standard nodes
            if text.lower() not in [
                "página de título",
                "title page",
                "frontespizio",
                "page de titre",
                "página del título",
                "notas",
                "notes",
                "note",
                "referências",
                "references",
            ]:
                entries.append((depth, text))

        for child in node.findall("ncx:navPoint", ns):
            extract_entries(child, depth + 1)

    for child in navMap.findall("ncx:navPoint", ns):
        extract_entries(child, 1)

    if len(entries) == 0:
        issues.append("No TOC entries (excluding Title/Notes).")
    elif len(entries) == 1:
        issues.append(f"Solitary L1 (only one entry in TOC): '{entries[0][1]}'")

    if len(entries) > 150:
        issues.append(f"Unusually high number of TOC entries: {len(entries)}")

    prev_depth = 0
    for depth, text in entries:
        if depth > prev_depth + 1:
            issues.append(
                f"Skipped depth level: went from L{prev_depth} to L{depth} at '{text[:30]}...'"
            )

        if len(text) > 150:
            issues.append(f"Very long entry ({len(text)} chars): '{text[:50]}...'")

        if text.isupper() and len(text) > 80:
            issues.append(f"Long ALL-CAPS entry: '{text[:50]}...'")

        prev_depth = depth

    return issues


def main():
    epubs = sorted(glob.glob(os.path.join(EPUB_DIR, "*.epub")))
    print(f"Checking {len(epubs)} EPUBs...\n")

    files_with_issues = 0
    for epub in epubs:
        basename = os.path.basename(epub)
        issues = check_epub_toc(epub)
        if issues:
            files_with_issues += 1
            print(f"=== {basename} ===")
            for issue in issues:
                print(f"  - {issue}")
            print()

    print(f"Total files with potential issues: {files_with_issues} out of {len(epubs)}")


if __name__ == "__main__":
    main()
