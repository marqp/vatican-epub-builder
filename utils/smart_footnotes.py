import re
import json
import os

# Globals for caching the encyclicals dictionary
_ENCYCLICALS_DICT = None


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
            basename = url.split("/")[-1].replace(".html", "")

            # Clean basename to extract the title
            clean = re.sub(r"^papa-francesco_\d{8}_enciclica-", "", basename)
            clean = re.sub(r"^hf_[a-z0-9-]+_enc_\d{8}_", "", clean)
            clean = re.sub(r"^(enciclica|encyclica)-", "", clean)
            clean = re.sub(r"-\d{1,2}-[a-z]+-\d{4}$", "", clean)
            clean = clean.replace("-", " ")

            # Skip very short or generic titles
            if len(clean) < 4 or clean in ["carta", "lettera"]:
                continue

            _ENCYCLICALS_DICT[clean.lower()] = url

    except Exception as e:
        print(f"Warning: could not load encyclicals dict for smart footnotes: {e}")

    return _ENCYCLICALS_DICT


def make_accent_insensitive_regex(title):
    pattern = ""
    for char in title:
        c = char.lower()
        if c in "aáàãâä":
            pattern += r"[aAáÁàÀãÃâÂäÄ]"
        elif c in "eéèêë":
            pattern += r"[eEéÉèÈêÊëË]"
        elif c in "iíìîï":
            pattern += r"[iIíÍìÌîÎïÏ]"
        elif c in "oóòõôö":
            pattern += r"[oOóÓòÒõÕôÔöÖ]"
        elif c in "uúùûü":
            pattern += r"[uUúÚùÙûÛüÜ]"
        elif c in "cç":
            pattern += r"[cCçÇ]"
        elif c.isalpha():
            pattern += f"[{c.lower()}{c.upper()}]"
        elif c == " ":
            pattern += r"\s+"
        else:
            pattern += re.escape(char)
    return r"\b(" + pattern + r")\b"


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
                    pattern_str = make_accent_insensitive_regex(title)
                    pattern = re.compile(pattern_str)
                    if pattern.search(parts[i]):
                        url = encyclicals[title]
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
