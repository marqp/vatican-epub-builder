import re

import pytest

from utils import smart_footnotes
from utils.smart_footnotes import _clean_title, inject_smart_links, make_accent_insensitive_regex

URLS = {
    # Keys come from URL slugs, so they never contain the apostrophe
    "laudato si": "https://www.vatican.va/laudato",
    "caritatis": "https://www.vatican.va/caritatis",
    "rerum novarum": "https://www.vatican.va/rerum",
    "humanae vitae": "https://www.vatican.va/hv",
}


@pytest.fixture(autouse=True)
def fake_dict(monkeypatch):
    d = {
        t: (u, re.compile(make_accent_insensitive_regex(t, first_upper=" " not in t)))
        for t, u in URLS.items()
    }
    monkeypatch.setattr(smart_footnotes, "_ENCYCLICALS_DICT", d)


def test_title_followed_by_apostrophe_is_linked():
    out = inject_smart_links("<p>Cf. Laudato si' (2015), 12.</p>")
    assert '<a href="https://www.vatican.va/laudato" target="_blank">Laudato si</a>\'' in out


def test_title_ending_in_apostrophe_matches():
    # Titles that do end in an apostrophe must not need a word character after it
    pattern = re.compile(make_accent_insensitive_regex("laudato si'"))
    assert pattern.search("Cf. Laudato si' (2015)")


def test_curly_apostrophe_is_linked():
    out = inject_smart_links("<p>Cf. Laudato si’, 12.</p>")
    assert 'href="https://www.vatican.va/laudato"' in out


def test_lowercase_common_word_is_not_linked():
    out = inject_smart_links("<p>Opus caritatis est.</p>")
    assert "href" not in out


def test_lowercase_multiword_title_is_linked():
    out = inject_smart_links("<p>Pio XII, Enc. humani generis, 12.</p>")
    assert "href" not in out  # not in the fixture dict
    out = inject_smart_links("<p>Paulo VI, Enc. humanae vitae, 12.</p>")
    assert 'href="https://www.vatican.va/hv"' in out


def test_capitalised_title_with_accents_and_case():
    assert 'href="https://www.vatican.va/rerum"' in inject_smart_links(
        "<p>Leão XIII, Rerum Novarum, 15.</p>"
    )
    assert 'href="https://www.vatican.va/caritatis"' in inject_smart_links(
        "<p>Cf. Caritatis, 3.</p>"
    )


def test_no_nested_links():
    html = '<p><a href="https://example.org/x">Humanae vitae</a>, 10.</p>'
    out = inject_smart_links(html)
    assert out.count("<a ") == 1


@pytest.mark.parametrize(
    "basename, expected",
    [
        ("hf_l-xiii_enc_15051891_rerum-novarum", "rerum novarum"),
        ("papa-francesco_20150524_enciclica-laudato-si", "laudato si"),
        ("<i>quod-provinciale</i>--1-agosto-1754-cristiani-che", None),
        ("carta", None),
    ],
)
def test_clean_title(basename, expected):
    assert _clean_title(basename) == expected
