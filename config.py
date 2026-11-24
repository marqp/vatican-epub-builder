from pathlib import Path

UI_LABELS = {
    "en": {
        "cover_kicker": "ENCYCLICAL LETTER",
        "title_page_label": "ENCYCLICAL LETTER",
        "title_page_nav": "Title Page",
        "contents_label": "Contents",
        "notes_label": "Notes",
    },
    "fr": {
        "cover_kicker": "LETTRE ENCYCLIQUE",
        "title_page_label": "LETTRE ENCYCLIQUE",
        "title_page_nav": "Page de titre",
        "contents_label": "Sommaire",
        "notes_label": "Notes",
    },
    "pt": {
        "cover_kicker": "CARTA ENCÍCLICA",
        "title_page_label": "CARTA ENCÍCLICA",
        "title_page_nav": "Página de título",
        "contents_label": "Índice",
        "notes_label": "Notas",
    },
    "es": {
        "cover_kicker": "CARTA ENCÍCLICA",
        "title_page_label": "CARTA ENCÍCLICA",
        "title_page_nav": "Página de título",
        "contents_label": "Índice",
        "notes_label": "Notas",
    },
    "it": {
        "cover_kicker": "LETTERA ENCICLICA",
        "title_page_label": "LETTERA ENCICLICA",
        "title_page_nav": "Frontespizio",
        "contents_label": "Indice",
        "notes_label": "Note",
    },
}

SOURCE_URL = ""
SOURCE_HTML = Path()
BUILD_DIR = Path()
OUTPUT_EPUB = Path()

TITLE = ""
SUBTITLE = ""
AUTHOR = ""
PUBLISHER = ""
DATE = ""
DATE_ISO: str | None = None
LANG = "pt"
COVER_KICKER = ""
COVER_DATE = ""
TITLE_PAGE_LABEL = ""
TITLE_PAGE_NAV = ""
CONTENTS_LABEL = ""
NOTES_LABEL = ""
