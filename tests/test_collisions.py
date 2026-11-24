import zipfile

import pytest
from pathlib import Path
from lxml import html

import config
from crawler import merge_new_urls
from parser.metadata import scrape_metadata

BASE = "https://www.vatican.va/content/pius-ix/it/documents/"
URL_1847 = BASE + "enciclica-ubi-primum-17-giugno-1847.html"
URL_1849 = BASE + "enciclica-ubi-primum-2-febbraio-1849.html"


def page(date: str):
    return html.fromstring(
        f"<html><head><title>Ubi primum ({date})</title></head><body>"
        '<div class="breadcrumb"><a href="/content/pius-ix/it.html">Pio IX</a></div>'
        '<div class="documento"><p>1. Testo.</p></div></body></html>'
    )


def fake_epub(path, source_url):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:source>{source_url}</dc:source></metadata></package>",
        )


@pytest.fixture(autouse=True)
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_first_document_gets_the_plain_name():
    scrape_metadata(page("17 giugno 1847"), URL_1847)
    assert config.OUTPUT_EPUB.name == "Ubi primum - Papa Pio IX (it).epub"


def test_rebuilding_the_same_document_keeps_its_name():
    fake_epub(Path("epubs/Ubi primum - Papa Pio IX (it).epub"), URL_1847)
    scrape_metadata(page("17 giugno 1847"), URL_1847.replace("https", "http"))
    assert config.OUTPUT_EPUB.name == "Ubi primum - Papa Pio IX (it).epub"


def test_same_title_and_pope_gets_the_year():
    fake_epub(Path("epubs/Ubi primum - Papa Pio IX (it).epub"), URL_1847)
    scrape_metadata(page("2 febbraio 1849"), URL_1849)
    assert config.OUTPUT_EPUB.name == "Ubi primum (1849) - Papa Pio IX (it).epub"
    assert config.SOURCE_HTML.name == "vatican-ubi-primum-1849-papa-pio-ix.source.html"
    assert config.TITLE == "Ubi primum"  # the book title itself is unchanged


def test_merge_new_urls_appends_only_unseen():
    state = {"queue": ["https://a/1.html", "https://a/2.html"], "processed": 2}
    added = merge_new_urls(state, ["http://a/1.html", "https://a/3.html", "https://a/2.html"])
    assert added == ["https://a/3.html"]
    assert state["queue"] == ["https://a/1.html", "https://a/2.html", "https://a/3.html"]
    assert state["processed"] == 2
