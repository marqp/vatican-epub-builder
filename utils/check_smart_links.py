import os
import glob
import zipfile
import re
from lxml import etree

EPUB_DIR = "epubs"
ns = {"xhtml": "http://www.w3.org/1999/xhtml"}


def check_epub_smart_links(epub_path):
    issues = []
    stats = {"total_footnotes": 0, "smart_links": 0, "missed_citations": []}

    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            if "OEBPS/text/content.xhtml" not in z.namelist():
                return stats, ["Missing OEBPS/text/content.xhtml"]
            content_data = z.read("OEBPS/text/content.xhtml")
    except Exception as e:
        return stats, [f"Error reading zip: {e}"]

    try:
        # We use HTML parser because XHTML might have entities or not be perfectly strict
        parser = etree.HTMLParser()
        root = etree.fromstring(content_data, parser)
    except Exception as e:
        return stats, [f"Error parsing HTML: {e}"]

    # Find footnotes
    footnotes = root.xpath('//p[@class="footnote"]')
    stats["total_footnotes"] = len(footnotes)

    # Common citation keywords, excluding offline journals like AAS and Acta
    citation_keywords = re.compile(
        r"\b(Enc\.|Lett\.|Epist\.|Syllabus|Conc\.|Const\.|Bula|Constituição)\b", re.IGNORECASE
    )

    for fn in footnotes:
        text_content = "".join(fn.itertext())
        html_str = etree.tostring(fn, encoding="unicode")

        has_smart_link = 'target="_blank"' in html_str

        if has_smart_link:
            stats["smart_links"] += 1
        else:
            # Check if it looks like a citation but wasn't linked
            if citation_keywords.search(text_content):
                # Clean up text for printing
                clean_text = re.sub(r"\s+", " ", text_content).strip()
                # Limit length
                if len(clean_text) > 200:
                    clean_text = clean_text[:197] + "..."
                stats["missed_citations"].append(clean_text)

    if stats["missed_citations"]:
        issues.append(f"Found {len(stats['missed_citations'])} potential missed citations")

    return stats, issues


def main():
    epubs = sorted(glob.glob(os.path.join(EPUB_DIR, "*.epub")))
    print(f"Checking {len(epubs)} EPUBs for smart links...\n")

    files_with_misses = 0
    total_smart_links = 0

    for epub in epubs:
        basename = os.path.basename(epub)
        stats, issues = check_epub_smart_links(epub)
        total_smart_links += stats["smart_links"]

        if stats["missed_citations"] or issues:
            files_with_misses += 1
            print(f"=== {basename} ===")
            print(f"  Footnotes: {stats['total_footnotes']} | Smart Links: {stats['smart_links']}")
            for issue in issues:
                print(f"  - {issue}")

            # Print a sample of missed citations (up to 3)
            for miss in stats["missed_citations"][:3]:
                print(f"    [?] Missed: {miss}")
            if len(stats["missed_citations"]) > 3:
                print(f"    ... and {len(stats['missed_citations']) - 3} more.")
            print()

    print(f"Total smart links injected across all EPUBs: {total_smart_links}")
    print(f"Total files with potential missed citations: {files_with_misses} out of {len(epubs)}")


if __name__ == "__main__":
    main()
