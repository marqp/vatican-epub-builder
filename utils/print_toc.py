import sys
import zipfile
from lxml import etree

with zipfile.ZipFile(sys.argv[1], "r") as z:
    toc_data = z.read("OEBPS/toc.ncx")

root = etree.fromstring(toc_data)
ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}


def print_nav(node, depth):
    text_node = node.find("ncx:navLabel/ncx:text", ns)
    if text_node is not None:
        print("  " * depth + text_node.text)
    for child in node.findall("ncx:navPoint", ns):
        print_nav(child, depth + 1)


navMap = root.find("ncx:navMap", ns)
for child in navMap.findall("ncx:navPoint", ns):
    print_nav(child, 0)
