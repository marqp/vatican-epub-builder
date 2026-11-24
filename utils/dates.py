"""Convert the human-readable promulgation dates found on vatican.va to ISO 8601."""

import re
import unicodedata

_MONTHS = {
    1: ["january", "janeiro", "gennaio", "enero", "janvier", "ianuarii", "januarii", "ianuarius"],
    2: ["february", "fevereiro", "febbraio", "febrero", "fevrier", "februarii", "februarius"],
    3: ["march", "marco", "marzo", "mars", "martii", "martius"],
    4: ["april", "abril", "aprile", "avril", "aprilis"],
    5: ["may", "maio", "maggio", "mayo", "mai", "maii", "maius"],
    6: ["june", "junho", "giugno", "junio", "juin", "iunii", "junii", "iunius"],
    7: ["july", "julho", "luglio", "julio", "juillet", "iulii", "julii", "iulius"],
    8: ["august", "agosto", "aout", "augusti", "augustus"],
    9: ["september", "setembro", "settembre", "septiembre", "setiembre", "septembre", "septembris"],
    10: ["october", "outubro", "ottobre", "octubre", "octobre", "octobris"],
    11: ["november", "novembro", "novembre", "noviembre", "novembris"],
    12: ["december", "dezembro", "dicembre", "diciembre", "decembre", "decembris"],
}
_MONTH_LOOKUP = {name: num for num, names in _MONTHS.items() for name in names}
_MONTH_RE = "|".join(sorted(_MONTH_LOOKUP, key=len, reverse=True))

# "14 giugno 1751", "29 de Junho de 1958", "1er janvier 1900", "14 de mayo, 1751"
_DAY_MONTH_YEAR = re.compile(
    r"\b(\d{1,2})(?:o|er|st|nd|rd|th)?\.?\s+(?:de\s+|mensis\s+)?(" + _MONTH_RE + r")\.?,?\s+(?:de\s+)?(\d{4})\b"
)
# "September 29, 1932"
_MONTH_DAY_YEAR = re.compile(
    r"\b(" + _MONTH_RE + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
)
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower()


def to_iso_date(text: str) -> str | None:
    """
    Return ``YYYY-MM-DD`` for a recognisable date, ``YYYY`` when only a year
    is present, or None when no date can be found.
    """
    if not text:
        return None
    folded = _fold(text)

    m = _DAY_MONTH_YEAR.search(folded)
    if m:
        day, month, year = int(m.group(1)), _MONTH_LOOKUP[m.group(2)], m.group(3)
    else:
        m = _MONTH_DAY_YEAR.search(folded)
        if m:
            month, day, year = _MONTH_LOOKUP[m.group(1)], int(m.group(2)), m.group(3)
        else:
            y = _YEAR.search(folded)
            return y.group(1) if y else None

    if not 1 <= day <= 31:
        return year
    return f"{year}-{month:02d}-{day:02d}"
