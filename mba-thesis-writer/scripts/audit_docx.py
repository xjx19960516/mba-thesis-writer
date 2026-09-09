#!/usr/bin/env python3
"""Read-only OOXML risk checks; cannot certify pagination or inherited formatting."""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def audit(path, profile=None):
    report = {"errors": [], "warnings": [], "manual_checks": [
        "Render and inspect every page: fonts, overflow, table continuation, headings, page numbers",
        "Check effective formatting through defaults, styles and direct overrides",
        "Verify numeric and author-year citations against the source/claim ledger",
        "Check captions, first mentions, footnotes, equations, table totals and anonymous-review requirements"], "visual_verified": False}
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            report["errors"].append("Corrupt ZIP entry: " + bad)
        root = ET.fromstring(archive.read("word/document.xml"))
        styles = ET.fromstring(archive.read("word/styles.xml"))
        texts = []
        for name in archive.namelist():
            if name.startswith("word/") and name.endswith(".xml") and not any(x in name for x in ("styles", "numbering", "settings", "fontTable", "theme/")):
                part = ET.fromstring(archive.read(name))
                texts.extend("".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in part.findall(".//w:p", NS))
        if any("comments" in n for n in archive.namelist()):
            report["warnings"].append("Comments present: review author identities and resolve as appropriate")
    body = root.find("w:body", NS)
    paragraphs = root.findall(".//w:p", NS)
    tables = root.findall(".//w:tbl", NS)
    report["counts"] = {"paragraphs_including_tables": len(paragraphs), "tables_including_layout_tables": len(tables), "sections": len(root.findall(".//w:sectPr", NS))}
    combined = "\n".join(texts)
    for marker in [r"【待补充[^】]*】", r"\bTODO\b", r"【说明[：:]", r"【注[：:]", r"博士/硕士", r"学术/专业"]:
        matches = re.findall(marker, combined)
        if matches:
            report["warnings"].append({"template_or_pending_text": marker, "count": len(matches)})
    declaration_texts = {re.sub(r"\s+", "", text) for text in texts}
    used_declaration = any(re.fullmatch(r".*(?<!未)使用人工智能工具声明", t) for t in declaration_texts)
    unused_declaration = any(re.fullmatch(r".*未使用人工智能工具声明", t) for t in declaration_texts)
    if used_declaration and unused_declaration:
        report["warnings"].append("Both AI declaration variants/mentions detected; inspect selected actual declaration")
    for marker in ["创新性及应用性说明", "此部分内容为我校博士学位论文模板要求"]:
        if marker in combined:
            report["warnings"].append("Doctoral-template content detected: " + marker)
    if root.findall(".//w:ins", NS) or root.findall(".//w:del", NS):
        report["warnings"].append("Tracked revisions remain; inspect intended delivery version")
    if any(x in combined for x in ["Error! Reference source not found", "错误!未找到引用源", "错误！未找到引用源"]):
        report["errors"].append("Broken reference field display")
    fields = [t.text or "" for t in root.findall(".//w:instrText", NS)]
    if any("TOC" in text for text in fields):
        report["warnings"].append("TOC fields present: update in a field-capable editor then inspect cached page numbers")
    # Explicit numbering check only on likely caption paragraphs, not every mention.
    captions = []
    if body is not None:
        top_ps = [p for p in body if p.tag == W + "p"]
        for index, p in enumerate(top_ps, 1):
            text = "".join(t.text or "" for t in p.findall(".//w:t", NS))
            match = re.match(r"^(续?)(表|图)\s*((?:\d+|[A-Z])\.\d+)\s+(.+)$", text.strip())
            if match:
                captions.append((index, *match.groups()))
    seen = set()
    groups = {}
    for index, continued, kind, number, title in captions:
        key = (kind, number)
        if continued:
            if key not in seen:
                report["warnings"].append(f"Caption paragraph {index}: continuation has no earlier base caption")
        else:
            if key in seen:
                report["warnings"].append(f"Possible duplicate caption {kind}{number}; exclude list-of-tables entries manually")
            seen.add(key)
            chapter, item = number.split(".")
            groups.setdefault((kind, chapter), set()).add(int(item))
    for (kind, chapter), values in groups.items():
        if values and values != set(range(1, max(values) + 1)):
            report["warnings"].append(f"Possible caption numbering gap: {kind} chapter {chapter}")
    for i, table in enumerate(tables, 1):
        first = table.find("w:tr", NS)
        if first is not None and first.find("w:trPr/w:tblHeader", NS) is None:
            report["warnings"].append(f"Table {i}: no repeat-header flag (may be a layout table)")
        sizes = {int(el.get(W + "val")) / 2 for el in table.findall(".//w:rPr/w:sz", NS) if el.get(W + "val", "").isdigit()}
        if profile and any(abs(s - profile["table"]["size_pt"]) > .01 for s in sizes):
            report["warnings"].append(f"Table {i}: explicit text sizes {sorted(sizes)} differ from table profile; distinguish layout tables")
    if profile:
        pg = profile["page"]
        for i, section in enumerate(root.findall(".//w:sectPr", NS), 1):
            margins = section.find("w:pgMar", NS)
            if margins is not None:
                for name, prop in [("top", "top_cm"), ("bottom", "bottom_cm"), ("left", "left_cm"), ("right", "right_cm"), ("header", "header_cm"), ("footer", "footer_cm")]:
                    raw = margins.get(W + name)
                    if raw is not None and abs(int(raw) - pg[prop] * 1440 / 2.54) > 3:
                        report["warnings"].append(f"Section {i}: {name} differs from profile; verify section purpose")
        # Include used paragraph styles and their ancestors, not unrelated defaults.
        style_by_id = {s.get(W + "styleId"): s for s in styles.findall("w:style", NS)}
        default_style = next((sid for sid, s in style_by_id.items() if s.get(W + "type") == "paragraph" and s.get(W + "default") == "1"), None)
        used_styles = set()
        for paragraph in paragraphs:
            selected = paragraph.find("w:pPr/w:pStyle", NS)
            sid = selected.get(W + "val") if selected is not None else default_style
            while sid and sid not in used_styles:
                used_styles.add(sid)
                style = style_by_id.get(sid)
                parent = style.find("w:basedOn", NS) if style is not None else None
                sid = parent.get(W + "val") if parent is not None else None
        # Record used style formatting without treating all Normal text as body.
        for s in styles.findall("w:style", NS):
            sid = s.get(W + "styleId")
            if sid not in used_styles:
                continue
            name = s.find("w:name", NS)
            size = s.find("w:rPr/w:sz", NS)
            if name is not None and name.get(W + "val", "").lower() in ("normal", "heading 1", "body text indent") and size is not None:
                report["warnings"].append({"style_id": sid, "style": name.get(W + "val"), "explicit_size_pt": float(size.get(W + "val")) / 2, "action": "Compare effective role formatting against template instructions"})
    return report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--profile", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.out and args.out.resolve() == args.input.resolve():
        p.error("Output must not overwrite input")
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig")) if args.profile else None
        result = audit(args.input, profile)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 1 if result["errors"] else 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(json.dumps({"input_error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
