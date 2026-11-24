import re
import json
import os

# Cache: title (lowercase) -> (url, compiled pattern)
_ENCYCLICALS_DICT = None

# A usable title is plain words: letters, apostrophes and single spaces
_VALID_TITLE = re.compile(r"^[a-z']+(?: [a-z']+)*$")


def _clean_title(basename: str) -> str | None:
    clean = re.sub(r"^papa-francesco_\d{8}_enciclica-", "", basename)
    clean = re.sub(r"^hf_[a-z0-9-]+_enc_\d{8}_", "", clean)
    clean = re.sub(r"^(enciclica|encyclica)-", "", clean)
    clean = re.sub(r"-\d{1,2}-[a-z]+-\d{4}$", "", clean)
    clean = re.sub(r"\s+", " ", clean.replace("-", " ")).strip().lower()

    # Skip leftovers of odd basenames (digits, markup, dates) and generic words
    if not _VALID_TITLE.match(clean):
        return None
    if len(clean) < 4 or clean in ("carta", "lettera"):
        return None
    return clean


def load_encyclicals_dict():
    global _ENCYCLICALS_DICT
    if _ENCYCLICALS_DICT is not None:
        return _ENCYCLICALS_DICT

    _ENCYCLICALS_DICT = {}
    state_file = os.path.join(os.path.dirname(__file__), "..", "crawler_state.json")
    if not os.path.exists(state_file):
        return _ENCYCLICALS_DICT

    try:
        with open(state_file, "r") as f:
            state = json.load(f)

        for url in state.get("queue", []):
            title = _clean_title(url.split("/")[-1].replace(".html", ""))
            if title:
                # Single words ("caritatis", "arcanum") must be capitalised to count as a
                # title; multi-word titles are distinctive enough in any case
                pattern = make_accent_insensitive_regex(title, first_upper=" " not in title)
                _ENCYCLICALS_DICT[title] = (url, re.compile(pattern))

    except Exception as e:
        print(f"Warning: could not load encyclicals dict for smart footnotes: {e}")

    return _ENCYCLICALS_DICT


_ACCENT_CLASSES = {
    "a": "aáàãâä",
    "e": "eéèêë",
    "i": "iíìîï",
    "o": "oóòõôö",
    "u": "uúùûü",
    "c": "cç",
}
_ACCENT_BASE = {ch: base for base, chars in _ACCENT_CLASSES.items() for ch in chars}


def make_accent_insensitive_regex(title, first_upper: bool = False):
    """
    Build a regex matching *title* regardless of accents and case — except the
    first letter, which must be uppercase when *first_upper* is set (used for
    single-word titles, which are otherwise ordinary Latin words).
    """
    pattern = ""
    first = True
    for char in title:
        c = char.lower()
        if c.isalpha():
            variants = _ACCENT_CLASSES.get(_ACCENT_BASE.get(c, c), c)
            if first and first_upper:
                pattern += f"[{variants.upper()}]"
            else:
                pattern += f"[{variants}{variants.upper()}]"
            first = False
        elif c == " ":
            pattern += r"\s+"
        elif c in "'’":
            pattern += "['’]"
        else:
            pattern += re.escape(char)
    # \b would fail after a trailing apostrophe ("Laudato si'"), so use lookarounds
    return r"(?<!\w)(" + pattern + r")(?!\w)"


def inject_smart_links(html_text: str) -> str:
    """
    Given a footnote HTML string, scans the text for encyclical titles and replaces
    them with smart links. Also standardizes the initial numbering spacing.
    """
    # Standardize numbering spacing after the anchor
    # E.g. <a id="fn1" href="#fnref1">1</a>   - becomes <a ...>1</a>
    html_text = re.sub(r"(</a>)[\s\-\.\)]+", r"\1 ", html_text)

    encyclicals = load_encyclicals_dict()
    if not encyclicals:
        return html_text

    # Sort titles by length descending so we match longer titles first (e.g. "Rerum Novarum" before "Rerum")
    sorted_titles = sorted(encyclicals.keys(), key=len, reverse=True)

    # We only want to replace text outside of HTML tags, AND outside of <a>/<em>/<i> tag contents
    # that are themselves inside an <a>.
    # Strategy: split by tags, track <a> nesting, only replace in text nodes outside <a>.
    # CRITICAL: After each replacement, we must re-split the HTML because the replacement
    # introduces new <a> tags that must be treated as TAG parts, not text.

    def _split_and_inject_target_blank(parts):
        """First pass: add target='_blank' to external <a> tags."""
        for i in range(len(parts)):
            if i % 2 != 0:
                tag = parts[i].lower()
                if tag.startswith("<a ") or tag == "<a>":
                    if "href=" in tag and 'target="_blank"' not in tag and "target=" not in tag:
                        if 'href="#' not in tag:
                            parts[i] = parts[i].replace("<a ", '<a target="_blank" ')
        return parts

    parts = re.split(r"(<[^>]+>)", html_text)
    parts = _split_and_inject_target_blank(parts)
    html_text = "".join(parts)

    # Second pass: inject smart links title by title.
    # After each title match, re-split so new <a> tags are properly recognized.
    for title in sorted_titles:
        parts = re.split(r"(<[^>]+>)", html_text)

        in_a_tag = False
        modified = False
        for i in range(len(parts)):
            if i % 2 != 0:
                tag = parts[i].lower()
                if tag.startswith("<a ") or tag == "<a>":
                    in_a_tag = True
                elif tag == "</a>":
                    in_a_tag = False
            else:
                if parts[i].strip() and not in_a_tag:
                    url, pattern = encyclicals[title]
                    if pattern.search(parts[i]):
                        parts[i] = pattern.sub(rf'<a href="{url}" target="_blank">\1</a>', parts[i])
                        modified = True

        if modified:
            # Re-join and the next title iteration will re-split cleanly
            html_text = "".join(parts)

    # Final sanitizer: remove any nested <a> tags that might have slipped through.
    # A nested <a> looks like: <a ...>...<a ...>...</a>...</a>
    # We detect this by tracking depth and stripping inner <a> tags.
    parts = re.split(r"(<[^>]+>)", html_text)
    a_depth = 0
    sanitized = []
    for i, part in enumerate(parts):
        if i % 2 != 0:
            tag_lower = part.lower()
            if tag_lower.startswith("<a ") or tag_lower == "<a>":
                a_depth += 1
                if a_depth > 1:
                    # Skip this nested <a> opening tag
                    continue
            elif tag_lower == "</a>":
                if a_depth > 1:
                    a_depth -= 1
                    # Skip this nested </a> closing tag
                    continue
                a_depth = max(0, a_depth - 1)
        sanitized.append(part)

    return "".join(sanitized)
