#!/usr/bin/env python3
"""Read actual DOCX/TXT/Markdown citation labels; does not validate GB/T syntax or source truth."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"
BRACKET = re.compile(r"\[\s*(\d+(?:\s*[,，、;；\-–—]\s*\d+)*)\s*\]")
ENTRY = re.compile(r"^\s*\[\s*([1-9]\d*)\s*\]\s*(.*)$")
END = re.compile(r"^(?:致谢|附录(?:\s*[A-Z0-9一二三四五六七八九十].*)?|acknowledgements?|acknowledgments?|appendix(?:\s+[A-Z](?:\s.*)?)?)$", re.I)


def normalize(text):
    return text.replace("［", "[").replace("］", "]")


def read_paragraphs(path):
    rows, notes, warnings = [], [], []
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            styles = ET.fromstring(archive.read("word/styles.xml")) if "word/styles.xml" in archive.namelist() else None
            style_map = {s.get(W + "styleId"): s for s in styles.findall("w:style", NS)} if styles is not None else {}
            default_style = next((sid for sid, s in style_map.items() if s.get(W + "type") == "paragraph" and s.get(W + "default") == "1"), None)
            def auto_numbered(paragraph):
                # A numId of zero explicitly cancels inherited numbering.
                number = paragraph.find("w:pPr/w:numPr/w:numId", NS)
                if number is not None:
                    return number.get(W + "val") != "0"
                unresolved = paragraph.find("w:pPr/w:numPr", NS) is not None
                selected = paragraph.find("w:pPr/w:pStyle", NS)
                sid = selected.get(W + "val") if selected is not None else default_style
                seen = set()
                while sid and sid not in seen:
                    seen.add(sid)
                    style = style_map.get(sid)
                    if style is None:
                        break
                    number = style.find("w:pPr/w:numPr/w:numId", NS)
                    if number is not None:
                        return number.get(W + "val") != "0"
                    unresolved |= style.find("w:pPr/w:numPr", NS) is not None
                    parent = style.find("w:basedOn", NS)
                    sid = parent.get(W + "val") if parent is not None else None
                return unresolved
            for index, paragraph in enumerate(document.findall(".//w:p", NS), 1):
                text = "".join(t.text or "" for t in paragraph.findall(".//w:t", NS))
                rows.append({"text": normalize(text), "location": f"paragraph:{index}",
                             "auto_numbered": auto_numbered(paragraph)})
            for name in ["word/footnotes.xml", "word/endnotes.xml"]:
                if name in archive.namelist():
                    part = ET.fromstring(archive.read(name))
                    for index, paragraph in enumerate(part.findall(".//w:p", NS), 1):
                        notes.append({"text": normalize("".join(t.text or "" for t in paragraph.findall(".//w:t", NS))),
                                      "location": f"{name}:paragraph:{index}"})
            if document.findall(".//w:ins", NS) or document.findall(".//w:del", NS):
                warnings.append("Tracked changes present; resolve the intended reading version before final citation review")
    elif path.suffix.lower() in {".txt", ".md", ".markdown"}:
        fence = None
        for index, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if path.suffix.lower() != ".txt":
                marker = re.match(r"^\s*(`{3,}|~{3,})", line)
                if marker:
                    if fence is None:
                        fence = marker.group(1)[0]
                    elif marker.group(1)[0] == fence:
                        fence = None
                    continue
                if fence:
                    continue
                line = re.sub(r"^\s*#{1,6}\s+", "", line)
            rows.append({"text": normalize(line), "location": f"line:{index}", "auto_numbered": False})
    else:
        raise ValueError("Input must be DOCX, TXT or Markdown")
    return rows, notes, warnings


def labels(text):
    values = []
    for match in BRACKET.finditer(text):
        for group in re.split(r"[,，、;；]", match.group(1)):
            limits = re.split(r"[\-–—]", group)
            if len(limits) == 1:
                value = int(limits[0])
                if not 1 <= value <= 10000:
                    raise ValueError("Citation label must be in 1..10000; inspect whether this is actually a citation")
                values.append(value)
            elif len(limits) == 2:
                start, end = map(int, limits)
                if not 1 <= start <= end <= 10000:
                    raise ValueError("Invalid or unsupported citation range")
                values.extend(range(start, end + 1))
            else:
                raise ValueError("Ambiguous citation range")
    return values


def audit(path, style, bibliography_heading=None):
    rows, notes, warnings = read_paragraphs(path)
    report = {"input": str(path.resolve()), "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "style": style, "status": "needs_manual_review", "errors": [], "warnings": warnings,
              "manual_checks": ["Verify source identities, metadata, current GB/T rules and semantic support",
                "Bracketed numbers may be formulas, sample IDs or non-citation labels; inspect findings in context",
                "Word automatic numbering, text boxes, field refresh, detached superscript ranges and appendix-local numbering need manual review",
                "First-use order here follows document paragraph order then notes; check the actual placement of notes"],
              "visual_verified": False}
    headings = {re.sub(r"\s+", "", bibliography_heading).casefold()} if bibliography_heading else {"参考文献", "references"}
    starts = [i for i, row in enumerate(rows) if re.sub(r"\s+", "", row["text"]).casefold() in headings]
    if len(starts) != 1:
        report["errors"].append("Exactly one bibliography heading required; specify --bibliography-heading or remove ambiguous copies from a working export")
        report["status"] = "issues_found"
        return report
    start = starts[0]
    end = next((i for i in range(start + 1, len(rows)) if END.fullmatch(rows[i]["text"].strip())), len(rows))
    bib_rows = rows[start + 1:end]
    if style == "author_year":
        report["warnings"].append("Author-year matching requires manual source/author/year review; numeric checking was not performed")
        return report
    entries = {}
    auto_numbering = False
    for row in bib_rows:
        auto_numbering |= row.get("auto_numbered", False)
        match = ENTRY.match(row["text"])
        if match:
            number = int(match.group(1))
            if number in entries:
                report["errors"].append(f"Duplicate bibliography label [{number}] at {row['location']}")
            if not match.group(2).strip():
                report["warnings"].append(f"No entry text following [{number}] at {row['location']}; inspect wrapped text")
            entries[number] = row["location"]
        elif row["text"].strip() and not row.get("auto_numbered"):
            report["warnings"].append(f"Unlabelled bibliography text at {row['location']}; inspect whether continuation text or an unnumbered entry")
    if auto_numbering or not entries:
        report["warnings"].append("Bibliography labels cannot be fully read as literal [n]; export displayed labels or review manually")
        if report["errors"]:
            report["status"] = "issues_found"
        return report
    citations, first_order, usage = set(), [], {}
    for row in rows[:start] + rows[end:] + notes:
        try:
            found = labels(row["text"])
        except ValueError as exc:
            report["errors"].append(f"{row['location']}: {exc}")
            continue
        for number in found:
            if number not in citations:
                first_order.append(number)
            citations.add(number)
            usage.setdefault(str(number), []).append(row["location"])
    missing = sorted(citations - entries.keys())
    unused = sorted(entries.keys() - citations)
    if missing:
        report["errors"].append("Cited labels missing from bibliography: " + ", ".join(map(str, missing)))
    if unused:
        report["warnings"].append("Bibliography entries without detected use: " + ", ".join(map(str, unused)))
    expected = list(range(1, len(entries) + 1))
    if sorted(entries) != expected:
        report["errors"].append("Bibliography labels are not consecutive starting at 1")
    if list(entries) != sorted(entries):
        report["errors"].append("Bibliography entries are not in numeric order")
    if first_order != sorted(citations):
        report["warnings"].append("First-use order is not ascending; inspect notes, grouped citations and numbering")
    report.update(bibliography_count=len(entries), cited_count=len(citations), citation_locations=usage,
                  missing_labels=missing, unused_labels=unused, first_use_order=first_order)
    report["status"] = "issues_found" if report["errors"] else "review_findings" if report["warnings"] else "no_label_issues_found"
    return report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--style", choices=["numeric", "author_year"], required=True)
    parser.add_argument("--bibliography-heading")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and (args.out.exists() or args.out.resolve() == args.input.resolve()):
        parser.error("Choose a new output report; input and existing files must remain unchanged")
    try:
        report = audit(args.input, args.style, args.bibliography_heading)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            with args.out.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        print(rendered)
        return 1 if report["errors"] else 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(json.dumps({"input_error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
