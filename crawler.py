import sys
import json
import argparse
import os
import subprocess
from urllib.request import Request, urlopen
from lxml import html

STATE_FILE = "crawler_state.json"
BASE_URL = "https://www.vatican.va"


def get_html(url: str) -> html.HtmlElement:
    req = Request(url, headers={"User-Agent": "vatican-epub-crawler/1.0"})
    with urlopen(req, timeout=30) as resp:
        return html.fromstring(resp.read())


def fetch_all_encyclicals() -> list[str]:
    popes = [
        "leo-xiv",
        "francesco",
        "benedict-xvi",
        "john-paul-ii",
        "john-paul-i",
        "paul-vi",
        "john-xxiii",
        "pius-xii",
        "pius-xi",
        "benedict-xv",
        "pius-x",
        "leo-xiii",
        "pius-ix",
        "gregorius-xvi",
        "pius-viii",
        "leo-xii",
        "pius-vii",
        "pius-vi",
        "clemens-xiv",
        "clemens-xiii",
        "benedictus-xiv",
    ]

    # Languages to try for index and fallback pages (in priority order)
    LANGUAGES = ["en", "pt", "it", "la"]

    encyclical_urls = []

    for pope in popes:
        all_links = []
        found = False

        # Strategy 1: Try the dedicated encyclicals index page in each language
        for lang in LANGUAGES:
            if found:
                break
            index_url = f"{BASE_URL}/content/{pope}/{lang}/encyclicals.index.html"
            try:
                index_doc = get_html(index_url)
                all_links = index_doc.xpath('//a[contains(@href, "/encyclicals/documents/")]')
                if all_links:
                    found = True
            except Exception:
                continue

        # Strategy 2: Try the main pope page with h2 "Encyclical"/"Enciclica" headings
        fallback_doc = None
        fallback_lang = None
        if not found:
            for lang in LANGUAGES:
                if found:
                    break
                fallback_url = f"{BASE_URL}/content/{pope}/{lang}.html"
                try:
                    fallback_doc = get_html(fallback_url)
                    fallback_lang = lang
                    # Match English "encyclical" and Italian "enciclica"
                    all_links = fallback_doc.xpath(
                        '//h2[contains(translate(text(), "ENCYCLICAL", "encyclical"), "encyclical")'
                        ' or contains(translate(text(), "ENCICLICA", "enciclica"), "enciclica")]'
                        '/following-sibling::div[1][contains(@class, "translation-field")]//a'
                    )
                    if all_links:
                        found = True
                except Exception:
                    continue

        # Strategy 3: Scan the main page for links whose href contains
        # "enciclica" or "encyclica". This supplements Strategy 2 to catch
        # encyclicals filed under different heading classifications.
        # Only needed for popes not found via Strategy 1 (the dedicated index).
        strategy1_found = found and fallback_doc is None
        if not strategy1_found:
            for lang in LANGUAGES:
                main_url = f"{BASE_URL}/content/{pope}/{lang}.html"
                try:
                    # Reuse already-loaded doc if same language
                    if fallback_doc is not None and fallback_lang == lang:
                        main_doc = fallback_doc
                    else:
                        main_doc = get_html(main_url)
                    extra_links = main_doc.xpath(
                        '//a[contains(@href, "/documents/") and '
                        '(contains(@href, "enciclica") or contains(@href, "encyclica"))]'
                    )
                    if extra_links:
                        all_links = list(all_links) + extra_links
                        found = True
                        break
                except Exception:
                    continue

        if not all_links:
            continue

        # Deduplicate links and group by document basename across languages
        doc_groups = {}
        seen_hrefs = set()
        for link in all_links:
            href = link.get("href")
            if not href or not href.endswith(".html"):
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            basename = href.split("/")[-1]
            parts = href.split("/")
            lang_code = parts[3] if len(parts) > 3 else ""

            if basename not in doc_groups:
                doc_groups[basename] = {}
            full_url = BASE_URL + href if href.startswith("/") else href
            doc_groups[basename][lang_code.upper()] = full_url

        for basename, langs in doc_groups.items():
            if "PT" in langs:
                url = langs["PT"]
            elif "EN" in langs:
                url = langs["EN"]
            elif "IT" in langs:
                url = langs["IT"]
            else:
                url = list(langs.values())[0]

            if url not in encyclical_urls:
                encyclical_urls.append(url)

    return encyclical_urls


def merge_new_urls(state: dict, urls: list[str]) -> list[str]:
    """
    Append URLs not yet in the queue to its end. Already-processed entries keep
    their positions, so the next run builds only the new documents.
    Returns the list of URLs that were added.
    """
    known = {u.replace("http://", "https://") for u in state["queue"]}
    added = [u for u in urls if u.replace("http://", "https://") not in known]
    state["queue"].extend(added)
    return added


def main():
    arg_parser = argparse.ArgumentParser(description="Crawl vatican.va and build all encyclicals.")
    arg_parser.add_argument(
        "--refresh",
        action="store_true",
        help="search vatican.va again and queue encyclicals not seen before",
    )
    args = arg_parser.parse_args()

    if not os.path.exists(STATE_FILE):
        print("Scraping Vatican index for all encyclicals...")
        urls = fetch_all_encyclicals()
        state = {"queue": urls, "processed": 0}
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        print(f"Found {len(urls)} encyclicals across all popes.")
    else:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        if args.refresh:
            print("Searching vatican.va for new encyclicals...")
            added = merge_new_urls(state, fetch_all_encyclicals())
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
            print(f"Queued {len(added)} new encyclical(s).")
            for url in added:
                print(f"  + {url}")

    queue = state["queue"]
    processed = state["processed"]
    BATCH_SIZE = 300

    if processed >= len(queue):
        print("All encyclicals processed! Run with --refresh to look for new ones.")
        return

    print(f"Resuming from index {processed}/{len(queue)}")

    batch = queue[processed : processed + BATCH_SIZE]
    for url in batch:
        print(f"\nProcessing {url}...")
        try:
            import parser
            import config

            doc = get_html(url)
            parser.scrape_metadata(doc, url)
            nodes = doc.xpath(
                '//*[contains(concat(" ", normalize-space(@class), " "), " documento ")]'
            )
            if nodes:
                content = nodes[0]
                parser.normalize_footnotes(content)
                parser.wrap_loose_text(content)
                id_map = parser.build_id_map(content)
                body, notes, toc = parser.build_content_fragments(content, id_map)

                print(f"=== {config.TITLE} ===")
                for t in toc:
                    prefix = "  " * (t["level"] - 1)
                    print(f"{prefix}L{t['level']}: {t['text']}")

                result = subprocess.run(
                    [sys.executable, "vatican_epub_builder.py", "--url", url],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f"Error building EPUB for {url}:\n{result.stderr.strip()}")
                    continue
                print(f"-> Successfully built EPUB for {config.TITLE}")
            else:
                print(f"Failed to find document body for {url}")
        except Exception as e:
            print(f"Error processing {url}: {e}")

    state["processed"] += len(batch)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

    print(f"\nBatch complete. Next batch will start at index {state['processed']}")


if __name__ == "__main__":
    main()
