from lxml import etree

from parser.cleaner import sanitize_element
from utils.integrity import repair_links_and_ids


def test_duplicate_ids_keep_first():
    out = repair_links_and_ids('<p><a id="x" href="#y">1</a></p><p id="y">a</p><p id="x">b</p>')
    assert out.count('id="x"') == 1
    assert out.index('id="x"') < out.index('id="y"')


def test_links_without_target_are_unlinked():
    out = repair_links_and_ids(
        '<p><a href="#missing">[7]</a> <a href="#here">ok</a> '
        '<a href="https://example.org">ext</a></p><p id="here">t</p>'
    )
    assert 'href="#missing"' not in out
    assert "[7]" in out
    assert 'href="#here"' in out
    assert 'href="https://example.org"' in out


def test_output_has_no_namespace_noise():
    out = repair_links_and_ids('<section id="a"><p>x</p></section>')
    assert out == '<section id="a"><p>x</p></section>'


def test_epub_namespace_attributes_survive():
    out = repair_links_and_ids('<section id="notes" epub:type="footnotes"><p>x</p></section>')
    assert 'epub:type="footnotes"' in out


def test_sanitize_strips_font_and_center():
    el = etree.fromstring(
        '<p><font size="3"><b>45</b></font> text <center>c</center></p>'
    )
    out = etree.tostring(sanitize_element(el, {}), encoding="unicode")
    assert "<font" not in out and "<center" not in out
    assert "<strong>45</strong>" in out
    assert '<div class="center">c</div>' in out
