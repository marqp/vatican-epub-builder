import glob
from lxml import html
import parser
import config
import epub

files = glob.glob("sources/*.source.html")
for src in files:
    try:
        import importlib

        importlib.reload(config)
        with open(src, "rb") as f:
            doc = html.parse(f).getroot()
        canonical = doc.xpath('//link[@rel="canonical"]/@href')
        if not canonical:
            continue
        url = canonical[0]
        parser.scrape_metadata(doc, url)
        nodes = doc.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " documento ")]')
        if not nodes:
            continue
        content = nodes[0]
        parser.normalize_footnotes(content)
        parser.wrap_loose_text(content)
        id_map = parser.build_id_map(content)
        body, notes, toc = parser.build_content_fragments(content, id_map)
        epub.write_epub_files(body, notes, toc)
        epub.validate_xml()
        epub.create_epub()
    except Exception as e:
        print(f"Error on {src}: {e}")
print("Rebuild complete!")
