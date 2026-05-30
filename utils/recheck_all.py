"""Re-process ALL cached source files and print TOC for each."""

import os
import glob
import importlib
import json
from lxml import html
import parser
import config

STATE_FILE = "crawler_state.json"
SOURCES_DIR = "sources"

with open(STATE_FILE) as f:
    state = json.load(f)

# Build a map from source filename slug to the original URL
url_map = {}
for url in state["queue"][:65]:
    # Extract slug from URL to match source files
    parts = url.split("/")
    doc_name = parts[-1].replace(".html", "")
    # The source files are named like vatican-{slug}.source.html
    # but slug comes from config.TITLE which we don't know yet.
    # Instead, match by document name in URL
    url_map[doc_name] = url

source_files = sorted(glob.glob(os.path.join(SOURCES_DIR, "*.source.html")))
print(f"Found {len(source_files)} cached source files.\n")

for src in source_files:
    importlib.reload(config)
    basename = os.path.basename(src)

    # Find matching URL from state
    matching_url = None
    for doc_name, url in url_map.items():
        if doc_name.split("_")[-1].replace("-", "") in basename.replace("-", "").replace(
            "vatican", ""
        ).replace(".source.html", ""):
            matching_url = url
            break

    # If no match, try to find URL by reading the source and looking at breadcrumbs
    # For simplicity, construct a plausible URL from the file
    try:
        with open(src, "rb") as f:
            doc = html.parse(f).getroot()

        # Try to find the canonical URL from the page itself
        canonical = doc.xpath('//link[@rel="canonical"]/@href')
        og_url = doc.xpath('//meta[@property="og:url"]/@content')
        actual_url = None
        if canonical:
            actual_url = canonical[0]
        elif og_url:
            actual_url = og_url[0]

        if not actual_url:
            print(f"⚠ {basename}: No URL found, skipping")
            continue

        importlib.reload(config)
        parser.scrape_metadata(doc, actual_url)

        nodes = doc.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " documento ")]')
        if not nodes:
            print(f"=== {config.TITLE} ===  ({basename})")
            print("  ⚠ No document body found\n")
            continue

        content = nodes[0]
        parser.normalize_footnotes(content)
        parser.wrap_loose_text(content)
        id_map = parser.build_id_map(content)
        body, notes, toc = parser.build_content_fragments(content, id_map)

        print(f"=== {config.TITLE} ===  ({basename})")
        if toc:
            for t in toc:
                prefix = "  " * (t["level"] - 1)
                print(f"  {prefix}L{t['level']}: {t['text']}")
        else:
            print("  (no TOC entries)")
        print()

    except Exception as e:
        print(f"✗ {basename}: Error: {e}\n")
