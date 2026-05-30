"""
Metadata scraper for Vatican encyclical HTML pages.

Extracts title, author (pope name), subtitle, date, language,
and derives filesystem paths from the encyclical URL structure.
"""

import re
from pathlib import Path

from lxml import etree

import config
from utils import normspace

# ---------------------------------------------------------------------------
# Localised label maps
# ---------------------------------------------------------------------------

_POPE_PREFIXES = {
    "pt": "Papa ",
    "en": "Pope ",
    "fr": "Pape ",
    "es": "Papa ",
    "it": "Papa ",
}

_FALLBACK_AUTHOR = {
    "pt": "Sumo Pontífice",
    "en": "Supreme Pontiff",
    "fr": "Souverain Pontife",
    "es": "Sumo Pontífice",
    "it": "Sommo Pontefice",
}

# Prefixes to strip from the <title> tag (multilingual)
_ENCYCLICAL_PREFIXES = [
    r"^(Carta\s+Encíclica|Encíclica|Carta\s+Enciclica|Enciclica)\s+",
    r"^(Encyclical\s+Letter|Encyclical)\s+",
    r"^(Lettre\s+Encyclique|Encyclique)\s+",
    r"^(Lettera\s+Enciclica|Enciclica)\s+",
]

# Same prefixes but including "do/del Santo Padre {pope}" variants
_POPE_TITLE_PATTERNS = [
    r"^(Carta\s+Encíclica|Encíclica|Carta\s+Enciclica|Enciclica)\s+(do|del)\s+Santo\s+Padre\s+{pope}\s+",
    r"^(Encyclical\s+Letter|Encyclical)\s+of\s+the\s+Holy\s+Father\s+{pope}\s+",
    r"^(Lettre\s+Encyclique|Encyclique)\s+du\s+Saint-Père\s+{pope}\s+",
    r"^(Lettera\s+Enciclica|Enciclica)\s+del\s+Santo\s+Padre\s+{pope}\s+",
]

# Strings to strip when extracting the bare pope name
_AUTHOR_PREFIXES_TO_STRIP = [
    "Papa ",
    "Pope ",
    "Pape ",
    "Sumo Pontífice",
    "Supreme Pontiff",
    "Souverain Pontife",
    "Sommo Pontefice",
]


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def scrape_metadata(root: etree._Element, url: str) -> None:
    """
    Parse the Vatican HTML tree at *url* and populate ``config.*`` fields
    with the encyclical's metadata (title, author, date, paths, etc.).
    """
    config.SOURCE_URL = url
    parts = url.strip("/").split("/")

    # --- Language ---
    lang_candidate = parts[5] if len(parts) > 5 else "pt"
    config.LANG = lang_candidate if len(lang_candidate) == 2 else "pt"

    labels = config.UI_LABELS.get(config.LANG, config.UI_LABELS["pt"])
    config.COVER_KICKER = labels["cover_kicker"]
    config.TITLE_PAGE_LABEL = labels["title_page_label"]
    config.TITLE_PAGE_NAV = labels["title_page_nav"]
    config.CONTENTS_LABEL = labels["contents_label"]
    config.NOTES_LABEL = labels["notes_label"]

    # --- Author (pope name) ---
    title_node = root.xpath("//head/title")
    head_title = title_node[0].text_content().strip() if title_node else "Encyclical"

    parts = url.split("/")
    if "content" in parts:
        idx = parts.index("content")
        if idx + 2 < len(parts):
            slug = parts[idx + 1]
            lang = parts[idx + 2]
            config.LANG = lang

            nodes = root.xpath(
                f'//*[contains(@class, "breadcrumb")]//a[@href="/content/{slug}/{lang}.html"]'
            )
            if not nodes:
                nodes = root.xpath(f'.//a[@href="/content/{slug}/{lang}.html"]')

            nodes = [
                n
                for n in nodes
                if normspace(n.text_content()).lower()
                not in ("magisterium", "calendário", "calendar", "calendario")
            ]

            if nodes:
                name = normspace(nodes[0].text_content())
                prefix = _POPE_PREFIXES.get(lang, "Papa ")
                if not name.upper().startswith(prefix.upper().strip()):
                    name = prefix + name
                config.AUTHOR = name
            else:
                config.AUTHOR = _FALLBACK_AUTHOR.get(config.LANG, "Sumo Pontífice")
    else:
        config.AUTHOR = _FALLBACK_AUTHOR.get(config.LANG, "Sumo Pontífice")

    # --- Title ---
    pope_name = config.AUTHOR
    for p in _AUTHOR_PREFIXES_TO_STRIP:
        pope_name = pope_name.replace(p, "")
    pope_name = pope_name.strip()

    title_main = head_title.split("(")[0].strip()
    # Sanitize control characters that can appear in Vatican HTML titles
    title_main = re.sub(r"[\r\n\t]+", " ", title_main).strip()
    title_main = re.sub(r"\s+", " ", title_main)

    # Strip "Encíclica do Santo Padre {Pope}..." from the title
    if pope_name:
        pope_escaped = re.escape(pope_name)
        for pattern_template in _POPE_TITLE_PATTERNS:
            pattern = pattern_template.format(pope=pope_escaped)
            title_main = re.sub(pattern, "", title_main, flags=re.IGNORECASE).strip()

    # Strip generic encyclical prefixes
    for pattern in _ENCYCLICAL_PREFIXES:
        title_main = re.sub(pattern, "", title_main, flags=re.IGNORECASE).strip()

    # Split title : subtitle
    if ":" in title_main:
        ts = title_main.split(":", 1)
        config.TITLE = ts[0].strip()
        config.SUBTITLE = ts[1].strip()
    else:
        config.TITLE = title_main
        config.SUBTITLE = ""

    # --- Date ---
    date_match = re.search(r"\((.*?)\)", head_title)
    config.DATE = date_match.group(1).strip() if date_match else ""
    config.COVER_DATE = config.DATE.upper()

    # --- Subtitle fallback (scan document for "SOBRE..." / "ON..." lines) ---
    if not config.SUBTITLE:
        content_nodes = root.xpath(
            '//*[contains(concat(" ", normalize-space(@class), " "), " documento ")]'
        )
        if content_nodes:
            for p in content_nodes[0].xpath(".//*"):
                text = " ".join(t.strip() for t in p.xpath(".//text()") if t.strip())
                if len(text) > 300:
                    continue
                match = re.search(
                    r"\b(SOBRE\s+.*|ON\s+.*|SUR\s+.*|SULLA\s+.*)",
                    text,
                    re.IGNORECASE,
                )
                if match:
                    sub = match.group(1).strip()
                    if len(sub) < 200:
                        sub = re.sub(r"\[.*?\]|_", "", sub).strip()
                        config.SUBTITLE = sub
                        break

    # --- Derived paths ---
    author_slug = config.AUTHOR.lower().replace(" ", "-").replace(".", "")
    slug = f"{config.TITLE.lower().replace(' ', '-').replace(':', '')}-{author_slug}"

    config.SOURCE_HTML = Path("sources") / f"vatican-{slug}.source.html"
    config.SOURCE_HTML.parent.mkdir(parents=True, exist_ok=True)

    config.BUILD_DIR = Path(f"build/{slug}-epub-{config.LANG}")

    config.OUTPUT_EPUB = Path("epubs") / f"{config.TITLE} - {config.AUTHOR} ({config.LANG}).epub"
    config.OUTPUT_EPUB.parent.mkdir(parents=True, exist_ok=True)

    config.PUBLISHER = "A Santa Sé" if config.LANG == "pt" else "The Holy See"
