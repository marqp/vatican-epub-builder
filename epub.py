import uuid
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree
from PIL import Image, ImageDraw, ImageFont

import config
from utils import escape
from utils.integrity import repair_links_and_ids


_FONT_CANDIDATES = {
    False: [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
    True: [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf",
        "C:/Windows/Fonts/georgiab.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES[bold]:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    # Pillow >= 10.1 ships a scalable default font; honour the requested size
    return ImageFont.load_default(size=size)


def wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.ImageFont, max_width: int
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font_obj)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font_obj: ImageFont.ImageFont,
    y: int,
    fill: str,
    line_gap: int,
    width: int,
) -> int:
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_obj)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def create_cover(path: Path) -> None:
    width, height = 1600, 2400
    image = Image.new("RGB", (width, height), "#f7f1e6")
    draw = ImageDraw.Draw(image)
    burgundy = "#6d1726"
    graphite = "#262626"
    gold = "#b9965d"

    margin = 110
    draw.rectangle((margin, margin, width - margin, height - margin), outline=burgundy, width=8)
    draw.rectangle(
        (margin + 32, margin + 32, width - margin - 32, height - margin - 32), outline=gold, width=3
    )

    y = 360
    y = draw_centered_lines(draw, [config.COVER_KICKER], font(54), y, graphite, 18, width)
    y += 120

    title_lines = wrap_text(draw, config.TITLE.upper(), font(126, bold=True), width - 360)
    y = draw_centered_lines(draw, title_lines, font(126, bold=True), y, burgundy, 34, width)
    y += 120

    if config.SUBTITLE:
        subtitle_lines = wrap_text(draw, config.SUBTITLE.upper(), font(48), width - 360)
        y = draw_centered_lines(draw, subtitle_lines, font(48), y, graphite, 22, width)
        y += 190

    draw.line((width // 2 - 210, y, width // 2 + 210, y), fill=gold, width=6)
    y += 110
    y = draw_centered_lines(
        draw, [config.AUTHOR.upper()], font(58, bold=True), y, graphite, 18, width
    )
    y += 48
    draw_centered_lines(draw, [config.COVER_DATE], font(44), y, graphite, 14, width)

    image.save(path, "PNG", optimize=True)


def make_xhtml(title: str, body: str, css_href: str = "../styles/book.css") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{config.LANG}" lang="{config.LANG}">
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="{escape(css_href)}" />
</head>
<body>
{body}
</body>
</html>
"""


def render_nav_tree(entries: list[dict[str, str | int]]) -> str:
    root: list[dict[str, object]] = []
    stack: list[tuple[int, list[dict[str, object]]]] = [(0, root)]

    for entry in entries:
        level = int(entry.get("level", 1))
        level = max(1, min(level, 6))
        while stack and level <= stack[-1][0]:
            stack.pop()
        node: dict[str, object] = {
            "href": entry["href"],
            "text": entry["text"],
            "children": [],
        }
        stack[-1][1].append(node)
        stack.append((level, node["children"]))

    def render(nodes: list[dict[str, object]]) -> str:
        items = ["<ol>"]
        for node in nodes:
            items.append(
                f'<li><a href="{escape(str(node["href"]))}">{escape(str(node["text"]))}</a>'
            )
            children = node["children"]
            if children:
                items.append(render(children))
            items.append("</li>")
        items.append("</ol>")
        return "\n".join(items)

    return render(root)


def write_epub_files(
    body_fragments: list[str], notes: list[str], toc_entries: list[dict[str, str | int]]
) -> None:
    if config.BUILD_DIR.exists():
        shutil.rmtree(config.BUILD_DIR)

    (config.BUILD_DIR / "META-INF").mkdir(parents=True)
    (config.BUILD_DIR / "OEBPS" / "text").mkdir(parents=True)
    (config.BUILD_DIR / "OEBPS" / "styles").mkdir(parents=True)
    (config.BUILD_DIR / "OEBPS" / "images").mkdir(parents=True)

    (config.BUILD_DIR / "mimetype").write_text("application/epub+zip", encoding="utf-8")
    (config.BUILD_DIR / "META-INF" / "container.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
""",
        encoding="utf-8",
    )

    create_cover(config.BUILD_DIR / "OEBPS" / "images" / "cover.png")

    css = """
body {
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.45;
  margin: 5%;
  color: #1f1f1f;
}
a {
  color: #6d1726;
  text-decoration: none;
}
h1, h2, h3 {
  font-family: Georgia, "Times New Roman", serif;
  color: #5f1320;
  line-height: 1.2;
  margin-top: 1.6em;
}
h1 {
  font-size: 1.7em;
  text-align: center;
}
h2 {
  font-size: 1.3em;
}
h3 {
  font-size: 1.08em;
  font-style: italic;
}
p {
  margin: 0 0 0.85em;
  text-align: justify;
}
.center {
  text-align: center;
}
.title-page {
  text-align: center;
  margin-top: 18%;
}
.title-page p {
  text-align: center;
}
.book-title {
  font-size: 2.2em;
  color: #5f1320;
  margin: 0.6em 0 0.2em;
}
.subtitle {
  font-size: 1.1em;
}
.source {
  font-size: 0.85em;
  margin-top: 3em;
}
.footnote {
  font-size: 0.88em;
  text-align: left;
}
#notes {
  border-top: 1px solid #b9965d;
  margin-top: 2em;
  padding-top: 1em;
}
img.cover {
  display: block;
  height: auto;
  margin: 0 auto;
  max-width: 100%;
}
""".strip()
    (config.BUILD_DIR / "OEBPS" / "styles" / "book.css").write_text(css + "\n", encoding="utf-8")

    cover_body = f'<section class="cover"><img class="cover" src="../images/cover.png" alt="{escape(config.TITLE)} cover" /></section>'
    (config.BUILD_DIR / "OEBPS" / "text" / "cover.xhtml").write_text(
        make_xhtml("Cover", cover_body), encoding="utf-8"
    )

    title_body = f"""
<section class="title-page">
  <p>{escape(config.TITLE_PAGE_LABEL)}</p>
  <h1 class="book-title">{escape(config.TITLE)}</h1>
  <p class="subtitle">{escape(config.SUBTITLE)}</p>
  <p>{escape(config.AUTHOR)}</p>
  <p>{escape(config.DATE)}</p>
  <p class="source">Source: <a href="{escape(config.SOURCE_URL)}">{escape(config.PUBLISHER)}</a></p>
</section>
""".strip()
    (config.BUILD_DIR / "OEBPS" / "text" / "title.xhtml").write_text(
        make_xhtml(config.TITLE, title_body), encoding="utf-8"
    )

    notes_section = ""
    if notes:
        nl_indent = "\n  "
        notes_section = f"""
<section id="notes" epub:type="footnotes">
  <h1>{escape(config.NOTES_LABEL)}</h1>
  {nl_indent.join(notes)}
</section>
""".strip()

    nl_indent = "\n  "
    content_body = f"""
<section id="encyclical">
  {nl_indent.join(body_fragments)}
</section>
{notes_section}
""".strip()
    content_body = repair_links_and_ids(content_body)
    (config.BUILD_DIR / "OEBPS" / "text" / "content.xhtml").write_text(
        make_xhtml(config.TITLE, content_body), encoding="utf-8"
    )

    nav_entries = [
        {"href": "text/title.xhtml", "text": config.TITLE_PAGE_NAV, "level": 1},
        *[
            {
                "href": f"text/content.xhtml#{entry['id']}",
                "text": str(entry["text"]),
                "level": int(entry["level"]),
            }
            for entry in toc_entries
        ],
    ]
    if notes:
        nav_entries.append(
            {"href": "text/content.xhtml#notes", "text": config.NOTES_LABEL, "level": 1}
        )

    nav_body = f"""
<nav epub:type="toc" id="toc">
  <h1>{escape(config.CONTENTS_LABEL)}</h1>
  {render_nav_tree(nav_entries)}
</nav>
""".strip()
    (config.BUILD_DIR / "OEBPS" / "nav.xhtml").write_text(
        make_xhtml("Contents", nav_body, "styles/book.css"), encoding="utf-8"
    )

    def toc_depth(entries: list[dict[str, str | int]]) -> int:
        # Same nesting rules as the trees below
        depth, stack = 1, [0]
        for entry in entries:
            level = max(1, min(int(entry.get("level", 1)), 6))
            while stack and level <= stack[-1]:
                stack.pop()
            stack.append(level)
            depth = max(depth, len(stack) - 1)
        return depth

    def render_ncx_tree(entries: list[dict[str, str | int]]) -> str:
        root: list[dict[str, object]] = []
        stack: list[tuple[int, list[dict[str, object]]]] = [(0, root)]

        for entry in entries:
            level = int(entry.get("level", 1))
            level = max(1, min(level, 6))
            while stack and level <= stack[-1][0]:
                stack.pop()
            node: dict[str, object] = {
                "href": entry["href"],
                "text": entry["text"],
                "children": [],
            }
            stack[-1][1].append(node)
            stack.append((level, node["children"]))

        play_order_counter = 1

        def render_nodes(nodes: list[dict[str, object]], depth: int = 1) -> str:
            nonlocal play_order_counter
            lines = []
            indent = "  " * depth
            for node in nodes:
                lines.append(
                    f'{indent}<navPoint id="navPoint-{play_order_counter}" playOrder="{play_order_counter}">'
                )
                lines.append(
                    f"{indent}  <navLabel><text>{escape(str(node['text']))}</text></navLabel>"
                )
                lines.append(f'{indent}  <content src="{escape(str(node["href"]))}" />')
                play_order_counter += 1
                if node["children"]:
                    lines.append(render_nodes(node["children"], depth + 1))
                lines.append(f"{indent}</navPoint>")
            return "\n".join(lines)

        return render_nodes(root, 2)

    ncx_points_str = render_ncx_tree(nav_entries)

    identifier = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, config.SOURCE_URL)}"
    (config.BUILD_DIR / "OEBPS" / "toc.ncx").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{identifier}" />
    <meta name="dtb:depth" content="{toc_depth(nav_entries)}" />
    <meta name="dtb:totalPageCount" content="0" />
    <meta name="dtb:maxPageNumber" content="0" />
  </head>
  <docTitle><text>{escape(config.TITLE)}</text></docTitle>
  <docAuthor><text>{escape(config.AUTHOR)}</text></docAuthor>
  <navMap>
{ncx_points_str}
  </navMap>
</ncx>
""",
        encoding="utf-8",
    )

    date_line = f"    <dc:date>{config.DATE_ISO}</dc:date>\n" if config.DATE_ISO else ""
    (config.BUILD_DIR / "OEBPS" / "content.opf").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{config.LANG}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{identifier}</dc:identifier>
    <dc:title>{escape(config.TITLE)}</dc:title>
    <dc:creator>{escape(config.AUTHOR)}</dc:creator>
    <dc:language>{config.LANG}</dc:language>
    <dc:publisher>{escape(config.PUBLISHER)}</dc:publisher>
{date_line}    <dc:source>{escape(config.SOURCE_URL)}</dc:source>
    <dc:description>{escape(config.SUBTITLE)}</dc:description>
    <meta property="dcterms:modified">{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>
    <meta name="cover" content="cover-image" />
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />
    <item id="style" href="styles/book.css" media-type="text/css" />
    <item id="cover-image" href="images/cover.png" media-type="image/png" properties="cover-image" />
    <item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml" />
    <item id="title-page" href="text/title.xhtml" media-type="application/xhtml+xml" />
    <item id="content" href="text/content.xhtml" media-type="application/xhtml+xml" />
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover" />
    <itemref idref="title-page" />
    <itemref idref="content" />
  </spine>
</package>
""",
        encoding="utf-8",
    )


def create_epub() -> None:
    if config.OUTPUT_EPUB.exists():
        config.OUTPUT_EPUB.unlink()

    with zipfile.ZipFile(config.OUTPUT_EPUB, "w") as epub:
        epub.write(config.BUILD_DIR / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(config.BUILD_DIR.rglob("*")):
            if path.is_dir() or path.name == "mimetype":
                continue
            epub.write(
                path,
                path.relative_to(config.BUILD_DIR).as_posix(),
                compress_type=zipfile.ZIP_DEFLATED,
            )


def validate_xml() -> None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    for path in [
        config.BUILD_DIR / "META-INF" / "container.xml",
        config.BUILD_DIR / "OEBPS" / "content.opf",
        config.BUILD_DIR / "OEBPS" / "toc.ncx",
        config.BUILD_DIR / "OEBPS" / "nav.xhtml",
        config.BUILD_DIR / "OEBPS" / "text" / "cover.xhtml",
        config.BUILD_DIR / "OEBPS" / "text" / "title.xhtml",
        config.BUILD_DIR / "OEBPS" / "text" / "content.xhtml",
    ]:
        etree.parse(str(path), parser)
