from lxml import etree

from utils.auto_anchors import inject_missing_anchors


def para(html: str) -> dict:
    return {"type": "paragraph", "element": etree.fromstring(html)}


def body_html(fragments) -> str:
    return "".join(etree.tostring(f["element"], encoding="unicode") for f in fragments)


def test_date_number_is_not_a_note_reference():
    fragments = [
        para("<p>a stepping stone to the Christian faith,6 sometimes the prelude.</p>"),
        para("<p>addressed to that university on February 6, 1694, and Benedict.</p>"),
    ]
    notes = ['<p class="footnote">6 Cf. Clement of Alexandria.</p>']
    fragments, notes = inject_missing_anchors(fragments, notes)

    html = body_html(fragments)
    assert html.count('name="ftnref6"') == 1
    assert "faith,<a" in html
    assert "February 6, 1694" in html


def test_each_note_is_anchored_once_and_in_order():
    fragments = [
        para("<p>First claim.1 Second claim.2 Repeated number 1 here.</p>"),
        para("<p>Later text mentions 2 again.</p>"),
    ]
    notes = ['<p class="footnote">1 Note one.</p>', '<p class="footnote">2 Note two.</p>']
    fragments, notes = inject_missing_anchors(fragments, notes)

    html = body_html(fragments)
    assert html.count('name="ftnref1"') == 1
    assert html.count('name="ftnref2"') == 1
    assert html.index("ftnref1") < html.index("ftnref2")
    assert 'id="ftn1"' in notes[0] and 'id="ftn2"' in notes[1]


def test_reference_inside_sup():
    fragments = [para("<p>Some text<sup>3</sup> continues.</p>")]
    notes = ['<p class="footnote">3 A note.</p>']
    fragments, _ = inject_missing_anchors(fragments, notes)
    assert '<sup><a name="ftnref3" href="#ftn3">[3]</a></sup>' in body_html(fragments)


def test_notes_stay_well_formed_xml():
    notes = ['<p class="footnote">4 First line<br/>second line.</p>']
    _, notes = inject_missing_anchors([], notes)
    # Must parse as XML (the old HTML serialization emitted a bare <br>)
    etree.fromstring(notes[0])
    assert "<br/>" in notes[0]


def test_already_anchored_notes_are_untouched():
    note = '<p class="footnote"><a id="ftn1" href="#ftnref1">[1]</a> Note.</p>'
    fragments = [para("<p>Text.1</p>")]
    new_fragments, notes = inject_missing_anchors(fragments, [note])
    assert notes == [note]
    assert "ftnref1" not in body_html(new_fragments)
