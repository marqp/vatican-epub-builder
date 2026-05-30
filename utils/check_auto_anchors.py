import glob
from lxml import etree
import os


def check_auto_anchors():
    epub_files = glob.glob("build/*/OEBPS/text/content.xhtml")

    total_epubs_with_auto = 0
    total_auto_anchors = 0
    mismatches = 0
    false_positives_candidates = []

    print("=" * 60)
    print("Verifying Auto-Anchors (ftn and ftnref)...")
    print("=" * 60)

    for f_path in epub_files:
        with open(f_path, "r", encoding="utf-8") as f:
            content = f.read().encode("utf-8")

        parser = etree.HTMLParser()
        try:
            root = etree.fromstring(content, parser)
        except Exception:
            continue

        auto_ftn = root.xpath('//a[starts-with(@id, "ftn") and not(starts-with(@id, "ftnref"))]')
        auto_ftnref = root.xpath('//a[starts-with(@id, "ftnref")]')

        if not auto_ftn and not auto_ftnref:
            continue

        total_epubs_with_auto += 1

        ftn_ids = {a.get("id").replace("ftn", "") for a in auto_ftn if a.get("id")}
        ftnref_ids = {a.get("id").replace("ftnref", "") for a in auto_ftnref if a.get("id")}

        missing_in_body = ftn_ids - ftnref_ids
        missing_in_notes = ftnref_ids - ftn_ids

        total_auto_anchors += len(ftnref_ids)

        epub_name = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(f_path))))

        print(f"\n[{epub_name}]")
        print(f"  Notes auto-anchored: {len(ftn_ids)}")
        print(f"  Body refs auto-anchored: {len(ftnref_ids)}")

        if missing_in_body:
            print(f"  [!] Missing body refs for notes: {sorted(list(missing_in_body))}")
            mismatches += len(missing_in_body)
        if missing_in_notes:
            print(f"  [!] Missing notes for body refs: {sorted(list(missing_in_notes))}")
            mismatches += len(missing_in_notes)

        # Extract context for false positive review
        for ref in auto_ftnref:
            parent = ref.getparent()
            while parent is not None and parent.tag != "p":
                parent = parent.getparent()

            if parent is not None:
                text = "".join(parent.itertext()).strip()
                ref_text = "".join(ref.itertext())
                idx = text.find(ref_text)
                if idx != -1:
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(ref_text) + 40)
                    context = text[start:end].replace("\n", " ")
                    false_positives_candidates.append(
                        f"{epub_name} | {ref.get('id')}: ...{context}..."
                    )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total EPUBs with auto-anchors: {total_epubs_with_auto}")
    print(f"Total body references injected: {total_auto_anchors}")
    print(f"Total unlinked/mismatched notes: {mismatches}")

    print("\n" + "=" * 60)
    print("FALSE POSITIVE REVIEW (Context of injected anchors)")
    print("=" * 60)
    for c in false_positives_candidates:
        print(c)


if __name__ == "__main__":
    check_auto_anchors()
