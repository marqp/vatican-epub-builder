import pytest
from lxml import etree
import config
from parser.heuristics import extract_heading_metadata


@pytest.fixture(autouse=True)
def setup_config():
    """Reset the global config before each test to ensure isolation."""
    config.TITLE = ""
    yield


def make_p(text, is_bold=False, is_centered=False):
    """Helper to create an lxml paragraph element."""
    p = etree.Element("p")
    if is_centered:
        p.set("style", "text-align: center")

    if is_bold:
        b = etree.Element("b")
        b.text = text
        p.append(b)
    else:
        p.text = text

    # Inject a dummy anchor as heuristics.py expects it for ID generation
    a = etree.Element("a")
    a.set("name", "test_anchor")
    p.append(a)

    return p


def test_explicit_intro_heading():
    """Test that a bold INTRODUÇÃO line is detected as a heading."""
    p = make_p("INTRODUÇÃO", is_bold=True)
    id_map = {}
    meta = extract_heading_metadata(p, id_map)

    assert meta is not None
    assert meta["text"] == "INTRODUÇÃO"
    # Bold (+1) + ALL CAPS (+5) + Intro (+100) = 106
    assert meta["weight"] >= 100


def test_numbered_heading():
    """Test that a standard numbered section is detected as a heading."""
    p = make_p("1. O Mistério da Fé", is_bold=True)
    id_map = {}
    meta = extract_heading_metadata(p, id_map)

    assert meta is not None
    assert meta["text"] == "1. O Mistério da Fé"
    # Bold (+1) + Numbered (+5) = 6
    assert meta["weight"] >= 6


def test_rejection_pope_name():
    """Test that a lone Pope name is correctly rejected as a false positive."""
    # Sometimes pages have "PAPA FRANCISCO" centered and bolded at the top
    p = make_p("PAPA FRANCISCO", is_bold=True, is_centered=True)
    id_map = {}
    meta = extract_heading_metadata(p, id_map)

    assert meta is None


def test_rejection_salutation():
    """Test that salutations are rejected."""
    p = make_p("Aos veneráveis irmãos no episcopado", is_bold=True)
    id_map = {}
    meta = extract_heading_metadata(p, id_map)

    assert meta is None


def test_rejection_date_location():
    """Test that the promulgation date is rejected."""
    p = make_p("Dado em Roma, junto a São Pedro, no dia 15 de maio.", is_bold=True)
    id_map = {}
    meta = extract_heading_metadata(p, id_map)

    assert meta is None


def test_rejection_notes_header():
    """Test that the word 'NOTAS' is rejected (handled elsewhere)."""
    p = make_p("NOTAS", is_bold=True)
    id_map = {}
    meta = extract_heading_metadata(p, id_map)

    assert meta is None
