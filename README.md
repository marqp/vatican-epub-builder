# Vatican EPUB Builder

A Python tool to automatically generate clean, beautifully formatted EPUB versions of Encyclicals and other documents directly from the Holy See's website (`vatican.va`).

The builder scrapes the page to extract the title, subtitle, author (Pope), date, and body content, injecting dynamic footnotes, smart-links, and a generated interactive Table of Contents.

The generated EPUBs include:
- Cover image (dynamically generated with title, author, and date)
- Interactive Table of Contents
- Smart Footnotes (cross-referencing other encyclicals)
- Clean, standard formatting with beautiful fonts

All outputs validate with `epubcheck` 5.3.0 with zero errors or warnings.

## Setup

Install the required dependencies inside a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

## Usage

**Single Document:**
Pass the `--url` argument with a link to any Vatican document:
```sh
python3 vatican_epub_builder.py --url https://www.vatican.va/content/leo-xiv/pt/encyclicals/documents/20260515-magnifica-humanitas.html
```

**Bulk Generation:**
The crawler can automatically fetch and build all encyclicals across all popes:
```sh
python3 crawler.py
```

EPUB files are saved to the `epubs/` directory.

## Core Features

- **Smart Headings**: Uses advanced heuristics (detecting typographic signals and rejecting false positives) to reconstruct chapter divisions on older, unstructured encyclicals.
- **Smart Footnotes**: Automatically detects citations to other encyclicals inside footnotes and converts them to clickable external links.
- **Auto Anchors**: Reconstructs broken or missing footnote anchors from plain-text numbers.
- **Dynamic Metadata**: Accurately extracts the Pope's name and infers the language from the URL to localize UI elements (like "Table of Contents" or "Carta Encíclica").

## Legal Disclaimer

This project is independent and is not affiliated with, endorsed by, or sponsored by the Holy See. All original encyclical texts, documents, and content are the property of the *Libreria Editrice Vaticana*. 

This tool was created exclusively for educational, pastoral, and personal use to facilitate the reading of these important public documents in standard EPUB format. No commercial use is intended, permitted, or encouraged.
