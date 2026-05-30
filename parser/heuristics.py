"""
Heading detection heuristics for Vatican encyclical HTML.

Uses a weighted scoring system to determine whether a <p> element
is a section heading or body text. Scores are based on typographic
signals (bold, italic, centering, ALL CAPS, explicit h1-h6 tags)
and a battery of rejection filters to exclude false positives like
papal titles, salutations, dates, and bibliographic citations.
"""

import re
from lxml import etree

import config
from utils import normspace, safe_id
from parser.cleaner import get_element_text

# ---------------------------------------------------------------------------
# Rejection patterns — compiled once at module level
# ---------------------------------------------------------------------------

# Papal names that appear in encyclical headers (not section headings)
_POPE_NAMES = (
    r"\b(?:"
    r"PAPA|PP|PONT[IÍE]FICE|PONTIFF|"
    r"FRANCISCUS|FRANCISCO|FRANCOIS|"
    r"BENEDICTUS|BENEDICT|BENTO|BENEDETTO|BENOIT|"
    r"PAULUS|PAULO|PAUL|PABLO|"
    r"IOANNES|JO[AÃ]O|JUAN|GIOVANNI|JEAN|"
    r"PIUS|PIUX|PIO|PIE|"
    r"LEO|LE[AÃ]O|LEON|LEONE"
    r")\b"
)

_ENCYCLICAL_TYPE = r"(?:CARTA\s+ENC[IÍ]CLICA|ENCYCLICAL|ENCICLICA|ENCYCLIQUE)"

# Matches "Encíclica do Papa XYZ" style text
_RE_ENCYCLICAL_HEADER = re.compile(
    _POPE_NAMES + r".*" + _ENCYCLICAL_TYPE + r"|" + _ENCYCLICAL_TYPE + r".*" + _POPE_NAMES,
    re.IGNORECASE,
)

# Pope name alone (no encyclical keyword required)
_RE_POPE_NAME_ALONE = re.compile(_POPE_NAMES, re.IGNORECASE)

# Dates of promulgation ("Dado em Roma...", "Given at the Vatican...")
_RE_DATE_LOCATION = re.compile(
    r"^(?:Dado|Dada|Given|Donné|Dato|Datum|Da|Dal)\b"
    r".*\b(?:Roma|Rome|Romae|Vatican|Vaticano|Castel Gandolfo"
    r"|S\.\s*Pietro|San Pietro|St\.\s*Peter|Quirinale)\b",
    re.IGNORECASE,
)
_RE_PONTIFICATE = re.compile(r"\b(?:anno|year).*pontificat[oe]\b", re.IGNORECASE)
_RE_ROME_YEAR = re.compile(
    r"^(?:Roma|Rome|Romae|Vaticano|Castel Gandolfo"
    r"|From\s+the\s+Vatican)\b.*\b(?:ano|year|pontificado|pontificate|\d{4})\b",
    re.IGNORECASE,
)
_RE_FROM_VATICAN = re.compile(r"^(?:From\s+the\s+Vatican)[, ]*\d+", re.IGNORECASE)

# Salutations and addressees
_RE_SALUTATION = re.compile(
    r"^(?:"
    r"carta\s+enc[ií]clica|encyclical\s+letter|lettera\s+enciclica|"
    r"vener[aá]veis\s+irm[aã]os|venerable\s+brethren|venerable\s+brothers|"
    r"venerabili\s+fratelli|venerables\s+hermanos|beloved\s+sons|"
    r"to\s+the\s+.*(?:archbishops|bishops|patriarchs|clergy)|"
    r"to\s+(?:our\s+)?venerable\s+(?:brothers|brethren)|"
    r"to\s+(?:\w+\s+)?cardinal|"
    r"aos\s+(?:vener[aá]veis|bispos|arcebispos)|"
    r"a\s+tutti\s+(?:i|gli)\s+(?:patriarchi|sudditi|fedeli|arcivescovi|vescovi|primati)|"
    r"ai\s+(?:venerabili|vescovi|patriarchi)|"
    r"al\s+(?:primate|patriarca)|"
    r"agli\s+(?:arcivescovi|vescovi)"
    r")\b",
    re.IGNORECASE,
)
_RE_BLESSING = re.compile(
    r"(?:"
    r"greetings\s+and\s+(?:the\s+)?apostolic\s+blessing|"
    r"health\s+and\s+(?:the\s+)?apostolic\s+benediction|"
    r"sauda[cç][aã]o\s+e\s+b[eê]n[cç][aã]o\s+apost[oó]lica|"
    r"salute\s+e\s+apostolica\s+benedizione"
    r")",
    re.IGNORECASE,
)

# Bibliographic abbreviations
_RE_ABBREVIATION = re.compile(
    r"^(?:Alloc\.|Encicl\.|Lett\.|Epist\.|Epistola\s+encicl\."
    r"|Allocutio\b|Litt\.\s+Apost\.|Lett\.\s+Apost\.)\s",
    re.IGNORECASE,
)

# Citation patterns inside numbered paragraphs
_RE_CITATION_MARKERS = re.compile(
    r"\b(?:"
    r"AAS|Acta|Serm\.|Epis\.|Matt\.|Marc\.|Luc\.|Ioan\.|Cor\.|Rom\."
    r"|Hebr\.|Ibid\.|Id\.|cf\.|cfr\.|S\.\s*Thom\."
    r"|loc\.?\s*cit|op\.?\s*cit|sqq?\."
    r"|Annales|Monumenta"
    r"|\bp\.\s*\d|\bpp\.\s*\d|\bvol\.\s*[IVXLCDM0-9]"
    r"|\bCol\.\s*[IVXLCDMivxlcdm0-9]"
    r"|Luke\b|Matthew\b|Eph\.\s|Soph\.\s|Gen\.\s|Exod?\.\s"
    r"|Psalm\b|Deut\.\s|Levit\.\s|Numb?\.\s|Josue?\b"
    r"|Apoc\.\s|Philipp?\.\s|Coloss?\.\s|Thessal\.\s"
    r"|Apostolic\s+Letter|Encyclical\s+Letter"
    r"|Encycl\.|Concord\.|Catech\.|Const\.\s*Apost"
    r"|Summ?\.\s*theol|De\s+\w+\s+coniug|De\s+nupt"
    r"|Homii?\.\s|Enarrat\.|cap\.\s*[IVXLCDM0-9]"
    r"|\bart\.\s*[0-9]|\bn\.\s*[0-9]|\bq\.\s*[0-9]"
    r"|Conc\.\s*Trid|Sess\.\s|Cod\.\s*iur"
    r"|\blib\.\s*[IVXLCDM0-9]|\bprop\.\s*[0-9]"
    r"|Decr\.\s*S\.\s*Offic|Act\.\s*Apost"
    r"|\bFebr\.\s|\bMay\s|\bApril\s|\bDec\.\s|\bJuly\s"
    r"|\bpag\.\s*[0-9]"
    r")\b",
    re.IGNORECASE,
)

# Subtitle-like lines ("SOBRE ...", "ON ...", etc.)
_RE_SUBTITLE_PREFIX = re.compile(
    r"^(?:SOBRE|ON|SUR|SUL|SULLA|SULL\'|SULLO|SUI|SUGLI|SULLE|DE|ACERCA\s+DE)\b",
    re.IGNORECASE,
)

# Section-end markers
_NOTES_MARKERS = {"notas", "notes", "referências", "references", "note"}

# Roman numeral validator
_RE_ROMAN_NUMERAL = re.compile(
    r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})$",
    re.IGNORECASE,
)

# Numbered heading patterns
_RE_NUMBERED_START = re.compile(r"^(?:[0-9]+\s*(?:\.|-)|[IVXLCDM]+(?:\.| -|\s*-))")
_RE_CAPITULO_START = re.compile(
    r"^Cap[ií]tulo\s+[IVXLCDM0-9]+",
    re.IGNORECASE,
)
_RE_PARTE_START = re.compile(
    r"^(?:[a-zA-Z]+|Primeira|Segunda|Terceira|Quarta|Quinta"
    r"|Sexta|S[eé]tima|Oitava|Nona|D[eé]cima)\s+PARTE"
    r"|PARTE\s+(?:[IVXLCDM]+|[0-9]+)\b",
    re.IGNORECASE,
)
_RE_INTRO_CONCLUSION = re.compile(
    r"^(?:INTRODU[ÇC][AÃ]O|INTRODUCTION|INTRODUCCIÓN"
    r"|CONCLUS[AÃ]O|CONCLUSION|CONCLUSIÓN)$",
    re.IGNORECASE,
)

# HTML heading tag weights
_HEADING_TAG_WEIGHTS = {
    "h1": 1000,
    "h2": 900,
    "h3": 800,
    "h4": 700,
    "h5": 600,
    "h6": 500,
}


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def extract_heading_metadata(
    paragraph: etree._Element,
    id_map: dict[str, str],
) -> dict[str, object] | None:
    """
    Analyse a DOM element and return heading metadata if it looks like
    a section heading, or None if it's regular body text.

    Returns a dict with keys: ``id``, ``text``, ``weight``.
    """
    text = normspace(get_element_text(paragraph))
    if not text or len(text) > 220:
        return None

    # Skip elements that contain internal anchor links (e.g. footnote refs)
    if paragraph.xpath('.//a[starts-with(@href, "#") and not(starts-with(@href, "#_ftn"))]'):
        return None

    # --- Typographic signals ---
    tag = paragraph.tag.lower()
    has_bold = tag in ("b", "strong") or bool(paragraph.xpath(".//b | .//strong"))
    has_italic = tag in ("i", "em") or bool(paragraph.xpath(".//i | .//em"))
    is_centered = (
        "text-align: center" in paragraph.get("style", "").lower()
        or paragraph.get("align", "").lower() == "center"
    )
    starts_with_num = bool(_RE_NUMBERED_START.match(text))
    starts_with_capitulo = bool(_RE_CAPITULO_START.match(text))
    is_all_caps = text.replace("ª", "").replace("º", "").isupper() and len(text.strip()) > 0
    is_explicit_heading = tag in _HEADING_TAG_WEIGHTS

    # --- Very short ALL-CAPS rejection (language codes like "EN", "IT") ---
    if is_all_caps and len(text.strip()) <= 3 and not is_explicit_heading and not starts_with_num:
        if not _RE_ROMAN_NUMERAL.match(text.strip()):
            return None

    # --- Main qualification gate ---
    if not (
        (
            is_explicit_heading
            or has_bold
            or has_italic
            or is_centered
            or is_all_caps
            or starts_with_capitulo
        )
        and len(text) < 150
    ):
        return None

    # --- Rejection filters ---

    # 1. Encyclical header ("Encíclica do Papa Francisco")
    if _RE_POPE_NAME_ALONE.search(text) and re.search(_ENCYCLICAL_TYPE, text, re.IGNORECASE):
        return None

    # 2. Pope name alone (without encyclical keyword)
    if (
        len(text) < 120
        and not starts_with_num
        and not starts_with_capitulo
        and _RE_POPE_NAME_ALONE.search(text.upper())
    ):
        return None

    # 3. Date/location of promulgation
    if (
        _RE_DATE_LOCATION.search(text)
        or _RE_PONTIFICATE.search(text)
        or _RE_ROME_YEAR.search(text)
        or _RE_FROM_VATICAN.search(text)
    ):
        return None

    # 4. Exact title match
    if config.TITLE and text.strip().upper() == config.TITLE.strip().upper():
        return None

    # 5. Salutations and blessings
    if _RE_SALUTATION.search(text) or _RE_BLESSING.search(text):
        return None

    # 6. Bibliographic abbreviations
    if _RE_ABBREVIATION.search(text):
        return None

    # 7. Copyright / source markers
    if len(text) < 100:
        text_lower = text.lower()
        if "copyright" in text_lower or "fonti francescane" in text_lower:
            return None

    # 8. Notes section headers
    if text.upper() in {"NOTAS", "NOTES", "REFERÊNCIAS", "REFERENCES", "NOTE"}:
        return None

    # 9. Subtitle-like lines
    if is_all_caps and _RE_SUBTITLE_PREFIX.search(text):
        return None

    # --- Weight calculation ---
    weight = _HEADING_TAG_WEIGHTS.get(tag, 0)

    starts_with_parte = bool(_RE_PARTE_START.match(text))
    is_intro_conclusion = bool(_RE_INTRO_CONCLUSION.match(text.strip()))

    if starts_with_capitulo or starts_with_parte or is_intro_conclusion:
        weight += 100
    if is_centered:
        weight += 10
    if is_all_caps:
        weight += 5
    if has_bold:
        weight += 1
    if has_italic and not is_all_caps:
        weight += 1

    # --- Post-weight rejection filters ---

    # Long paragraphs without strong typographic signals
    if len(text) > 80 and not (has_bold or is_centered or is_all_caps):
        if starts_with_num:
            return None
        if text.strip().endswith("."):
            return None

    # Numbered paragraphs that start with a quote
    if starts_with_num and re.search(r'^[0-9]+\s*\.\s*["\'\xab\u201c]', text):
        return None

    # Numbered paragraphs that are bibliographic citations
    if starts_with_num and _RE_CITATION_MARKERS.search(text):
        return None

    # Numbered headings bonus
    if starts_with_num and not is_all_caps:
        weight += 5

    # Alphabetical bullets penalty (a), b), etc.)
    if re.match(r"^[a-zA-Z]\)", text.strip()) and not is_all_caps:
        weight -= 5

    # Dash bullets penalty (- item)
    if re.match(r"^[-\u2013\u2014]\s*", text.strip()) and not is_all_caps:
        weight -= 6

    # --- ID generation ---
    anchors = paragraph.xpath('.//a[@name and not(starts-with(@name, "_ftn"))]')
    old_id = anchors[0].get("name") if anchors else None
    new_id = id_map.get(old_id, old_id) if old_id else None

    if not new_id:
        new_id = safe_id(text[:30], set(id_map.values()))
        id_map[text] = new_id

    return {"id": new_id, "text": text, "weight": weight}
