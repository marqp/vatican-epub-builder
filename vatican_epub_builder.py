#!/usr/bin/env python3
import argparse
from urllib.request import Request, urlopen
from lxml import html

import config
import parser
import epub


def main() -> None:
    arg_parser = argparse.ArgumentParser(
        description="Build an EPUB from a Vatican Encyclical HTML."
    )
    arg_parser.add_argument("--url", required=True, help="Vatican encyclical URL to package")
    args = arg_parser.parse_args()

    request = Request(args.url, headers={"User-Agent": "magnifica-humanitas-epub/1.0"})
    with urlopen(request, timeout=30) as response:
        html_bytes = response.read()

    document = html.fromstring(html_bytes)
    parser.scrape_metadata(document, args.url)
    config.SOURCE_HTML.write_bytes(html_bytes)

    content_nodes = document.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " documento ")]'
    )
    if not content_nodes:
        raise RuntimeError("Could not find the Vatican document text (class 'documento').")

    content = content_nodes[0]
    parser.normalize_footnotes(content)
    parser.wrap_loose_text(content)
    id_map = parser.build_id_map(content)
    body_fragments, notes, toc_entries = parser.build_content_fragments(content, id_map)

    epub.write_epub_files(body_fragments, notes, toc_entries)
    epub.validate_xml()
    epub.create_epub()

    print(f"Wrote {config.OUTPUT_EPUB}")
    print(f"Body fragments: {len(body_fragments)}")
    print(f"Notes: {len(notes)}")
    print(f"TOC entries: {len(toc_entries)}")


if __name__ == "__main__":
    main()
