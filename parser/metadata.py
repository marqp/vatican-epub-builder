"""
Metadata scraper for Vatican encyclical HTML pages.

Extracts title, author (pope name), subtitle, date, language,
and derives filesystem paths from the encyclical URL structure.
"""

import re
import zipfile
from pathlib import Path

from lxml import etree

import config
from utils import normspace
from utils.dates import to_iso_date

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

_PUBLISHER = {
    "pt": "A Santa Sé",
    "en": "The Holy See",
    "fr": "Le Saint-Siège",
    "es": "La Santa Sede",
    "it": "La Santa Sede",
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

    # --- Language (from /content/{pope}/{lang}/...) ---
    parts = url.split("/")
    slug = lang = None
    if "content" in parts:
        idx = parts.index("content")
        if idx + 2 < len(parts):
            slug, lang = parts[idx + 1], parts[idx + 2]
    config.LANG = lang if lang and re.fullmatch(r"[a-z]{2}", lang) else "pt"

    labels = config.UI_LABELS.get(config.LANG, config.UI_LABELS["en"])
    config.COVER_KICKER = labels["cover_kicker"]
    config.TITLE_PAGE_LABEL = labels["title_page_label"]
    config.TITLE_PAGE_NAV = labels["title_page_nav"]
    config.CONTENTS_LABEL = labels["contents_label"]
    config.NOTES_LABEL = labels["notes_label"]

    # --- Author (pope name) ---
    title_node = root.xpath("//head/title")
    head_title = title_node[0].text_content().strip() if title_node else "Encyclical"

    # Always reset, so a previous document's author never leaks through
    config.AUTHOR = _FALLBACK_AUTHOR.get(config.LANG, _FALLBACK_AUTHOR["en"])
    if slug:
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
            prefix = _POPE_PREFIXES.get(config.LANG, "Papa ")
            if not name.upper().startswith(prefix.upper().strip()):
                name = prefix + name
            config.AUTHOR = name

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
    config.DATE_ISO = to_iso_date(config.DATE)
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
                # Real subtitles are set in capitals ("ON THE MORALITY OF DUELING");
                # a case-insensitive match picked up body text ("... on the 23rd December")
                match = re.search(r"\b((?:SOBRE|ON|SUR|SULLA)\s.*)", text)
                if match:
                    sub = normspace(match.group(1))
                    if len(sub) < 200 and sub == sub.upper():
                        sub = re.sub(r"\[.*?\]|_", "", sub).strip()
                        config.SUBTITLE = sub
                        break

    # --- Derived paths ---
    # Two documents can share a title and pope (Pius IX wrote two "Ubi primum"),
    # so if the EPUB name is already taken by a different source URL, add the
    # year (or the full date) to keep both.
    epub_dir = Path("epubs")
    label = config.TITLE
    for suffix in ["", (config.DATE_ISO or "")[:4], config.DATE_ISO or ""]:
        if suffix and suffix in label:
            continue
        candidate = f"{config.TITLE} ({suffix})" if suffix else config.TITLE
        existing = _epub_source_url(
            epub_dir / f"{candidate} - {config.AUTHOR} ({config.LANG}).epub"
        )
        if existing is None or _same_url(existing, url):
            label = candidate
            break

    author_slug = config.AUTHOR.lower().replace(" ", "-").replace(".", "")
    title_slug = re.sub(r"[()]", "", label).lower().replace(" ", "-").replace(":", "")
    slug = f"{title_slug}-{author_slug}"

    config.SOURCE_HTML = Path("sources") / f"vatican-{slug}.source.html"
    config.SOURCE_HTML.parent.mkdir(parents=True, exist_ok=True)

    config.BUILD_DIR = Path(f"build/{slug}-epub-{config.LANG}")

    config.OUTPUT_EPUB = epub_dir / f"{label} - {config.AUTHOR} ({config.LANG}).epub"
    config.OUTPUT_EPUB.parent.mkdir(parents=True, exist_ok=True)

    config.PUBLISHER = _PUBLISHER.get(config.LANG, _PUBLISHER["en"])


def _same_url(a: str, b: str) -> bool:
    return a.replace("http://", "https://").rstrip("/") == b.replace("http://", "https://").rstrip("/")


def _epub_source_url(path: Path) -> str | None:
    """Return the dc:source URL of an existing EPUB, or None if there is none."""
    if not path.exists():
        return None
    try:
        with zipfile.ZipFile(path) as z:
            opf = etree.fromstring(z.read("OEBPS/content.opf"))
        return opf.findtext(".//{http://purl.org/dc/elements/1.1/}source") or ""
    except Exception:
        return ""
