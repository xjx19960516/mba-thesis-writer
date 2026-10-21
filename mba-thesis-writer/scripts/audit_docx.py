#!/usr/bin/env python3
"""Read-only OOXML risk checks; cannot certify pagination or inherited formatting."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from types import ModuleType
import xml.etree.ElementTree as ET
import zipfile

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def audit(path, profile=None, expected_headings=None, full_thesis=False, citation_style="numeric"):
    path = Path(path)
    if citation_style not in {"numeric", "author_year"}:
        raise ValueError("citation_style must be numeric or author_year")
    report = {"input": str(path.resolve()), "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "errors": [], "warnings": [], "manual_checks": [
        "Render and inspect every page: fonts, overflow, table continuation, headings, page numbers",
        "Check effective formatting through defaults, styles and direct overrides",
        "Verify numeric and author-year citations against the source/claim ledger",
        "Check captions, first mentions, footnotes, equations, table totals and anonymous-review requirements"], "visual_verified": False}
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            report["errors"].append("Corrupt ZIP entry: " + bad)
        root = ET.fromstring(archive.read("word/document.xml"))
        styles = ET.fromstring(archive.read("word/styles.xml")) if "word/styles.xml" in archive.namelist() else ET.Element(W + "styles")
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
    # Explicit user/project chapter expectations avoid imposing a fixed thesis outline.
    style_map = {s.get(W + "styleId"): s for s in styles.findall("w:style", NS)}
    parent_map = {child: parent for parent in root.iter() for child in parent}
    def ancestors(element):
        current = parent_map.get(element)
        while current is not None:
            yield current
            current = parent_map.get(current)
    def owned_elements(paragraph, tags):
        # Text boxes contain nested paragraphs; count their text only once.
        return [element for element in paragraph.iter() if element.tag in tags and
                next((parent for parent in ancestors(element) if parent.tag == W + "p"), None) is paragraph]
    paragraph_ancestors = [list(ancestors(p)) for p in paragraphs]
    in_table = [any(parent.tag == W + "tbl" for parent in parents) for parents in paragraph_ancestors]
    in_textbox = [any(parent.tag == W + "txbxContent" for parent in parents) for parents in paragraph_ancestors]
    def heading_level(paragraph):
        direct = paragraph.find("w:pPr/w:outlineLvl", NS)
        if direct is not None:
            value = direct.get(W + "val", "9")
            return int(value) if value.isdigit() and int(value) < 9 else None
        selected = paragraph.find("w:pPr/w:pStyle", NS)
        sid = selected.get(W + "val") if selected is not None else None
        seen_styles = set()
        while sid and sid not in seen_styles:
            seen_styles.add(sid)
            style = style_map.get(sid)
            if style is None:
                break
            outline = style.find("w:pPr/w:outlineLvl", NS)
            if outline is not None:
                value = outline.get(W + "val", "9")
                return int(value) if value.isdigit() and int(value) < 9 else None
            parent = style.find("w:basedOn", NS)
            sid = parent.get(W + "val") if parent is not None else None
        return None
    levels = [heading_level(p) if not in_table[i] and not in_textbox[i] else None
              for i, p in enumerate(paragraphs)]
    paragraph_texts = ["".join(t.text or "" for t in owned_elements(p, {W + "t"})).strip()
                       for p in paragraphs]
    def is_caption(paragraph, text):
        if re.match(r"^(?:续?表|续?图)\s*(?:\d+|[A-Z])(?:[.．\-－–]\d+)?(?:\s+|[：:])\S", text):
            return True
        selected = paragraph.find("w:pPr/w:pStyle", NS)
        sid = selected.get(W + "val") if selected is not None else None
        visited = set()
        while sid and sid not in visited:
            visited.add(sid)
            style = style_map.get(sid)
            if style is None:
                break
            name = style.find("w:name", NS)
            if name is not None and name.get(W + "val", "").strip().lower() in {"caption", "题注"}:
                return True
            parent = style.find("w:basedOn", NS)
            sid = parent.get(W + "val") if parent is not None else None
        return False
    def is_display_note(text):
        return bool(re.match(r"^(?:资料来源|数据来源|来源|注|注释)\s*[：:]\s*\S", text))
    roles = ["heading" if levels[i] is not None else "table" if in_table[i] else
             "textbox" if in_textbox[i] else "caption" if is_caption(p, paragraph_texts[i]) else
             "display_note" if is_display_note(paragraph_texts[i]) else "narrative"
             for i, p in enumerate(paragraphs)]
    characters = [len(re.sub(r"\s+", "", text)) for text in paragraph_texts]
    object_tags = {W + "drawing", W + "pict", "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"}
    objects = [owned_elements(p, object_tags) for p in paragraphs]
    def metrics(start, end):
        indices = range(start, end)
        result = {role + "_characters": sum(characters[i] for i in indices if roles[i] == role)
                  for role in ["narrative", "table", "caption", "display_note", "textbox"]}
        result["non_heading_characters"] = sum(result.values())
        result["nonempty_narrative_paragraphs"] = sum(1 for i in indices if roles[i] == "narrative" and characters[i])
        result["table_count"] = len({parent for i in indices for parent in paragraph_ancestors[i] if parent.tag == W + "tbl"})
        result["figure_count"] = sum(1 for i in indices for element in objects[i] if element.tag in {W + "drawing", W + "pict"})
        result["equation_count"] = sum(1 for i in indices for element in objects[i] if element.tag not in {W + "drawing", W + "pict"})
        return result
    def section_record(start):
        end = next((i for i in range(start + 1, len(paragraphs))
                    if levels[i] is not None and levels[i] <= levels[start]), len(paragraphs))
        record = {"heading": paragraph_texts[start], "paragraph": start + 1,
                  "end_paragraph": end, "outline_level": levels[start],
                  "is_leaf": not any(levels[i] is not None for i in range(start + 1, end))}
        record.update(metrics(start + 1, end))
        has_content = bool(record["non_heading_characters"] or record["table_count"] or record["figure_count"] or record["equation_count"])
        record["status"] = "text_present" if record["non_heading_characters"] else "content_present" if has_content else "empty"
        record["coverage_state"] = "narrative_present" if record["narrative_characters"] else "nonprose_only" if has_content else "empty"
        return record
    section_records = {i: section_record(i) for i, level in enumerate(levels) if level is not None}
    report["document_text_metrics"] = metrics(0, len(paragraphs))
    report["document_text_metrics"]["character_count_definition"] = (
        "Non-whitespace OOXML w:t characters in the main document, counted once per paragraph; "
        "excludes heading text and does not represent the school's body-word-count definition")
    coverage = []
    expected_indices = set()
    for title in expected_headings or []:
        matches = [i for i, text in enumerate(paragraph_texts) if text == title and levels[i] is not None]
        if len(matches) != 1:
            report["errors"].append(f"Expected heading not uniquely located as an outline heading: {title}")
            coverage.append({"heading": title, "status": "missing_or_ambiguous"})
            continue
        start = matches[0]
        expected_indices.add(start)
        record = dict(section_records[start])
        coverage.append(record)
        if record["coverage_state"] == "empty":
            report["errors"].append(f"Expected section has no text, table, figure or equation: {title} (paragraph {start + 1})")
        elif record["coverage_state"] == "nonprose_only":
            report["warnings"].append({"section_without_narrative": title, "paragraph": start + 1,
                                       "action": "Inspect whether its tables, captions, source notes, figures or equations need accompanying analysis for this section's purpose"})
    report["chapter_coverage"] = coverage
    report["section_coverage"] = list(section_records.values())
    for start, record in section_records.items():
        if start not in expected_indices and record["outline_level"] > 0 and record["is_leaf"] and record["coverage_state"] == "empty":
            report["warnings"].append({"empty_leaf_section": record["heading"], "paragraph": start + 1,
                                       "action": "Check this subsection's intended analysis and complete or remove it as appropriate"})
    report["manual_checks"].append("Coverage records describe text, tables and objects, not evidence or analytical depth; review each section against its research purpose and apply the school's word-count rules")
    for marker in [r"【待补充[^】]*】", r"\bTODO\b", r"【说明[：:]", r"【注[：:]", r"博士/硕士", r"学术/专业", r"此处(?:补充|填写|插入)", r"待(?:补充|填写|核实|完善)(?:原因|数据|结果|内容|访谈|问卷)?", r"临时演示", r"待真实数据替换"]:
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
    if full_thesis:
        _audit_required_content(root, styles, paragraphs, paragraph_texts, levels, in_table, in_textbox,
                                report, citation_style)
    return report


def _audit_required_content(root, styles, paragraphs, texts, levels, in_table, in_textbox, report, citation_style):
    """Check actual main-story components, never certify their meaning or pagination."""
    # Import by this script's location: no dependency or caller-cwd assumptions.
    citation_path = Path(__file__).with_name("audit_citations.py")
    citations = ModuleType("_thesis_citation_labels")
    citations.__file__ = str(citation_path)
    # Source compilation avoids __pycache__ writes without changing caller flags.
    exec(compile(citation_path.read_bytes(), str(citation_path), "exec"), citations.__dict__)
    compact = lambda text: re.sub(r"\s+", "", text).casefold()
    content_size = lambda text: sum(c.isalnum() for c in text)
    parent_map = {child: parent for parent in root.iter() for child in parent}
    p_index = {p: i for i, p in enumerate(paragraphs)}
    def owner(element):
        while element is not None and element.tag != W + "p":
            element = parent_map.get(element)
        return p_index.get(element)
    style_map = {s.get(W + "styleId"): s for s in styles.findall("w:style", NS)}
    default_style = next((sid for sid, s in style_map.items() if s.get(W + "type") == "paragraph" and s.get(W + "default") == "1"), None)
    def style_chain(paragraph):
        selected = paragraph.find("w:pPr/w:pStyle", NS)
        sid = selected.get(W + "val") if selected is not None else default_style
        seen = set()
        while sid and sid not in seen:
            seen.add(sid)
            style = style_map.get(sid)
            yield sid, style
            parent = style.find("w:basedOn", NS) if style is not None else None
            sid = parent.get(W + "val") if parent is not None else None
    def auto_numbered(i):
        for element in [paragraphs[i]] + [style for _, style in style_chain(paragraphs[i]) if style is not None]:
            num = element.find("w:pPr/w:numPr", NS)
            if num is not None:
                number = num.find("w:numId", NS)
                return number is None or number.get(W + "val") != "0"
        return False
    eligible = {i for i in range(len(paragraphs)) if not in_table[i] and not in_textbox[i]}
    toc_rows, toc_fields, cached_rows, listing_rows = set(), [], set(), set()
    def contents_field(instruction):
        return not re.search(r"\\[ca](?:\s|$)", instruction, re.I)
    for i in eligible:
        for sid, style in style_chain(paragraphs[i]):
            name = style.find("w:name", NS) if style is not None else None
            if any(re.fullmatch(r"(?:toc|目录)\d+", compact(value)) for value in [sid, name.get(W + "val", "") if name is not None else ""]):
                toc_rows.add(i)
    # Complex TOC fields can span paragraphs and be wrapped in a w:sdt content control.
    stack = []
    for element in root.iter():
        i = owner(element)
        if element.tag == W + "fldChar":
            kind = element.get(W + "fldCharType")
            if kind == "begin":
                stack.append({"instruction": "", "start": i, "rows": set(), "cached": set(), "result": False})
            elif kind == "separate" and stack:
                stack[-1]["result"] = True
            elif kind == "end" and stack:
                field = stack.pop()
                if re.match(r"^\s*TOC(?:\s|$)", field["instruction"], re.I):
                    toc_rows.update(field["rows"])
                    if contents_field(field["instruction"]):
                        toc_fields.append(field)
                        cached_rows.update(field["cached"])
                    else:
                        listing_rows.update(field["rows"])
        elif element.tag == W + "instrText" and stack and not stack[-1]["result"]:
            stack[-1]["instruction"] += element.text or ""
        for field in stack:
            if i in eligible:
                field["rows"].add(i)
                if element.tag == W + "t" and field["result"] and content_size(element.text or ""):
                    field["cached"].add(i)
    # fldSimple uses an attribute rather than the begin/separate/end token sequence.
    for field in root.findall(".//w:fldSimple", NS):
        if re.match(r"^\s*TOC(?:\s|$)", field.get(W + "instr", ""), re.I):
            rows = {owner(t) for t in field.findall(".//w:t", NS)} & eligible
            cached = {owner(t) for t in field.findall(".//w:t", NS) if content_size(t.text or "")} & eligible
            toc_rows.update(rows)
            if contents_field(field.get(W + "instr", "")):
                toc_fields.append({"start": owner(field), "rows": rows, "cached": cached})
                cached_rows.update(cached)
            else:
                listing_rows.update(rows)
    # An unterminated TOC field is never a validated automatic table of contents.
    for field in stack:
        if re.match(r"^\s*TOC(?:\s|$)", field["instruction"], re.I):
            toc_rows.update(field["rows"])
            report["manual_checks"].append("Unterminated TOC field: inspect its cached result and field boundaries")
    headings = {"abstract_zh": {"摘要", "中文摘要"}, "abstract_en": {"abstract", "英文摘要"},
                "table_of_contents": {"目录", "contents", "tableofcontents"}, "bibliography": {"参考文献", "references", "bibliography"}}
    def special(i):
        return next((key for key, titles in headings.items() if compact(texts[i]) in titles), None)
    keyword_re = {"keywords_zh": re.compile(r"^\s*关\s*键\s*[词字]\s*[：:]?\s*(.*)$", re.I),
                  "keywords_en": re.compile(r"^\s*key\s*words?\b\s*[：:]?\s*(.*)$", re.I)}
    def keyword(i):
        return next(((key, match.group(1)) for key, pattern in keyword_re.items() if (match := pattern.fullmatch(texts[i]))), None)
    def chapter_heading(i):
        return bool(re.match(r"^(?:第\s*[一二三四五六七八九十百\d]+\s*章|[1-9]\d*(?:\.[0-9]+)*\s+|introduction\b)", texts[i], re.I))
    # Recognize manual TOC copies as a region, so their special-title entries cannot
    # substitute for missing actual abstracts/references. A chapter outline ends it.
    toc_titles = [i for i in sorted(eligible - toc_rows) if special(i) == "table_of_contents"]
    listing_titles = [i for i in sorted(eligible - toc_rows) if compact(texts[i]) in {"图表清单", "图表目录", "图目录", "表目录", "插图目录", "表格目录", "图清单", "表清单", "listoffigures", "listoftables"}]
    manual_rows = set()
    toc_line = lambda i: bool(re.search(r"(?:\t|[.．·…]{2,}|\s)\s*(?:\d+|[ivxlcdm]+)\s*$", texts[i], re.I)) or any(t.tag == W + "tab" for t in paragraphs[i].iter())
    for title in toc_titles + listing_titles:
        if title in toc_titles and any(i > title for i in toc_rows):
            first = next((i for i in sorted(eligible) if i > title and texts[i]), None)
            if first in toc_rows:
                continue
        for i in sorted(eligible):
            if i <= title:
                continue
            if not texts[i]:
                if manual_rows and paragraphs[i].find("w:pPr/w:sectPr", NS) is not None:
                    break
                continue
            if special(i) == "table_of_contents" or i in listing_titles:
                break
            if levels[i] is not None and special(i) is None and not toc_line(i):
                break
            if chapter_heading(i) and not toc_line(i):
                break
            manual_rows.add(i)
            if title in listing_titles:
                listing_rows.add(i)
    toc_rows.update(manual_rows)
    actual = sorted(eligible - toc_rows)
    required = {}
    def record(key, indices, status, detail, **counts):
        required[key] = {"status": status, "location": [f"paragraph:{i + 1}" for i in indices], "detail": detail, **counts}
        if status in {"missing", "empty"}:
            report["errors"].append(f"Required full-thesis component {key}: {status}")
        elif status == "needs_manual_review":
            report["manual_checks"].append(f"Required component {key}: {detail}")
    starts = {key: [i for i in actual if special(i) == key] for key in headings}
    def section_end(start):
        return next((i for i in actual if i > start and (special(i) is not None or keyword(i) is not None or levels[i] is not None or chapter_heading(i))), len(paragraphs))
    front_ends = []
    for key in ["abstract_zh", "abstract_en"]:
        found = starts[key]
        if not found:
            record(key, [], "missing", "No actual main-story abstract heading outside TOC, tables and text boxes")
            continue
        content = []
        for start in found:
            end = section_end(start)
            front_ends.append(end - 1)
            content.extend(i for i in actual if start < i < end and content_size(texts[i]))
        size = sum(content_size(texts[i]) for i in content)
        record(key, found, "needs_manual_review" if len(found) > 1 and size else "present" if size else "empty",
               "Actual abstract text detected; manually compare meaning and numbers across languages" if size else "Heading has no abstract text before the next component/outline heading",
               characters=size, content_paragraphs=len(content))
    for key, abstract_key in [("keywords_zh", "abstract_zh"), ("keywords_en", "abstract_en")]:
        found, payloads = [], []
        for i in actual:
            match = keyword(i)
            if match is None or match[0] != key:
                continue
            # A label is not an abstract title, and must be in the front matter.
            earlier = [start for start in starts[abstract_key] if start < i]
            if earlier and any(j for j in actual if max(earlier) < j < i and (special(j) is not None or levels[j] is not None or chapter_heading(j))):
                continue
            found.append(i)
            payload = match[1]
            if not content_size(payload):
                nxt = next((j for j in actual if j > i and texts[j]), None)
                if nxt is not None and special(nxt) is None and keyword(nxt) is None and levels[nxt] is None and not chapter_heading(nxt):
                    payload = texts[nxt]
                    front_ends.append(nxt)
            payloads.append(payload)
            front_ends.append(i)
        size = sum(content_size(value) for value in payloads)
        record(key, found, "present" if size else "empty" if found else "missing",
               "Keyword payload detected; manually compare both language lists" if size else "No nonempty keyword payload after its label", characters=size)
    toc_content = [i for i in sorted(toc_rows - listing_rows) if any(c.isalpha() for c in texts[i]) and special(i) != "table_of_contents"]
    # Title text and field instructions alone are not cached entries.
    cached_content = [i for i in sorted(cached_rows) if any(c.isalpha() for c in texts[i]) and special(i) != "table_of_contents"]
    locations = toc_titles or [f["start"] for f in toc_fields if f["start"] is not None] or sorted(toc_rows - listing_rows)[:1]
    toc_status = "present" if toc_fields and cached_content else "needs_manual_review" if toc_content and not toc_fields else "empty" if locations else "missing"
    record("table_of_contents", locations, toc_status,
           "Automatic TOC has cached text entries; refresh and inspect displayed titles/page numbers manually" if toc_status == "present" else
           "Nonempty manual/styled TOC text detected; completeness and page mapping require manual review" if toc_status == "needs_manual_review" else
           "No cached TOC entries or nonempty manual contents detected", entries=len(cached_content) if toc_fields else len(toc_content))
    front_ends.extend(toc_rows)
    front_ends.extend(toc_titles)
    front_ends.extend(listing_titles)
    bib_starts = starts["bibliography"]
    bib_indices = []
    if bib_starts:
        start = bib_starts[-1]
        end = next((i for i in actual if i > start and (special(i) is not None or citations.END.fullmatch(texts[i].strip()) or levels[i] is not None)), len(paragraphs))
        bib_indices = [i for i in actual if start < i < end and content_size(texts[i])]
    entries, entry_order, empty_labels, duplicate_labels = {}, [], [], []
    automatic = any(auto_numbered(i) for i in bib_indices)
    for pos, i in enumerate(bib_indices):
        match = citations.ENTRY.match(citations.normalize(texts[i]))
        if match:
            number = int(match.group(1))
            payload = match.group(2)
            if not content_size(payload) and pos + 1 < len(bib_indices) and not citations.ENTRY.match(citations.normalize(texts[bib_indices[pos + 1]])):
                payload = texts[bib_indices[pos + 1]]
            if not content_size(payload):
                empty_labels.append(number)
                continue
            if number in entries:
                duplicate_labels.append(number)
            entries[number] = i
            entry_order.append(number)
    unlabelled_content = any(not citations.ENTRY.match(citations.normalize(texts[i])) for i in bib_indices)
    bib_nonempty = bool(entries or unlabelled_content)
    bib_status = "missing" if not bib_starts else "empty" if not bib_nonempty else "needs_manual_review" if automatic or citation_style == "author_year" or not entries or len(bib_starts) > 1 else "present"
    record("bibliography", bib_starts, bib_status,
           "Literal reference labels with nonempty entry text detected" if bib_status == "present" else
           "Reference text exists; automatic numbering, author-year/unlabelled entries or multiple headings require manual review" if bib_status == "needs_manual_review" else
           "No actual bibliography heading and nonempty reference entries", entries=len(entries), content_paragraphs=len(bib_indices), empty_labels=empty_labels)
    # Only main-body rows before the actual bibliography count as body citations.
    body_start = max(front_ends, default=-1) + 1
    body_end = min(bib_starts) if bib_starts else len(paragraphs)
    # Source notes in normal body tables can carry citations; their cells still
    # cannot serve as the required abstract/TOC/bibliography headings above.
    body_indices = [i for i in range(len(paragraphs)) if not in_textbox[i] and i not in toc_rows and
                    body_start <= i < body_end and special(i) is None and keyword(i) is None]
    usage, first_order, label_errors = {}, [], []
    for i in body_indices:
        try:
            found = citations.labels(citations.normalize(texts[i]))
        except ValueError as exc:
            label_errors.append(f"paragraph:{i + 1}: {exc}")
            continue
        for number in found:
            if number not in usage:
                first_order.append(number)
            usage.setdefault(number, []).append(i)
    year_pattern = re.compile(r"[（(][^()（）\n]{1,100}(?:19|20)\d{2}[a-z]?[^()（）\n]*[）)]|[A-Za-z\u4e00-\u9fff][^。！？；;\n]{0,35}[（(](?:19|20)\d{2}[a-z]?[）)]", re.I)
    indirect = [i for i in body_indices if year_pattern.search(texts[i]) or paragraphs[i].find(".//w:footnoteReference", NS) is not None or paragraphs[i].find(".//w:endnoteReference", NS) is not None or
                any(re.search(r"\b(?:CITATION|NOTEREF)\b", t.text or "", re.I) for t in paragraphs[i].findall(".//w:instrText", NS)) or
                any(re.search(r"\b(?:CITATION|NOTEREF)\b", f.get(W + "instr", ""), re.I) for f in paragraphs[i].findall(".//w:fldSimple", NS))]
    citation_status = "needs_manual_review" if citation_style == "author_year" or (not usage and (indirect or label_errors)) else "present" if usage else "missing"
    citation_locations = sorted({i for values in usage.values() for i in values})
    record("body_citations", citation_locations[:8] or indirect[:8], citation_status,
           "Literal numeric markers detected in the main body; marker meaning and source support require manual review" if citation_status == "present" else
           "Author-year, notes, citation fields or unsupported labels require manual inspection; body citation coverage is not verified" if citation_status == "needs_manual_review" else
           "No body citation markers detected before the bibliography; the bibliography list alone does not establish citation use",
           detected_labels=sorted(usage), location_count=len(citation_locations))
    if citation_style == "numeric":
        report["errors"].extend(label_errors)
        if empty_labels:
            report["warnings"].append("Bibliography labels without detected entry text: " + ", ".join(map(str, empty_labels)) + "; inspect wrapped entries and complete any empty reference")
        if duplicate_labels:
            report["errors"].append("Duplicate bibliography labels: " + ", ".join(map(str, sorted(set(duplicate_labels)))))
        if entries and not automatic:
            missing = sorted(set(usage) - set(entries))
            unused = sorted(set(entries) - set(usage))
            report["citation_analysis"] = {"style": citation_style, "missing_labels": missing, "unused_labels": unused, "first_use_order": first_order}
            if missing:
                report["errors"].append("Cited labels missing from bibliography: " + ", ".join(map(str, missing)))
            if sorted(entries) != list(range(1, len(entries) + 1)):
                report["errors"].append("Bibliography labels are not consecutive starting at 1")
            if entry_order != sorted(entry_order):
                report["errors"].append("Bibliography entries are not in numeric order")
            if unused:
                report["warnings"].append("Bibliography entries without detected body use: " + ", ".join(map(str, unused)))
            if first_order != sorted(usage):
                report["warnings"].append("First body use of reference labels is not ascending; inspect grouped citations and notes")
    report["required_content"] = required
    report["full_thesis"] = True
    report["citation_style"] = citation_style
    report["manual_checks"].extend([
        "Required-content presence is an OOXML structure/content check; no pagination, whole-standard compliance or research-content quality is certified",
        "Compare Chinese/English abstract meaning, findings and numbers; compare their keyword lists",
        "Refresh the table of contents in a field-capable editor and check every displayed title and page number",
        "Verify each body citation, reference metadata and source/claim semantic support; numeric brackets may have another meaning"])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--profile", type=Path)
    p.add_argument("--expect-heading", action="append", default=[], help="Exact displayed paragraph text of an expected outline heading; repeat per chapter")
    p.add_argument("--full-thesis", action="store_true", help="Require nonempty bilingual abstracts/keywords, TOC, body citations and bibliography for a complete thesis")
    p.add_argument("--citation-style", choices=["numeric", "author_year"], default="numeric", help="Citation checks in --full-thesis mode; author-year matching remains manual")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.out and args.out.resolve() == args.input.resolve():
        p.error("Output must not overwrite input")
    if args.out and args.profile and args.out.resolve() == args.profile.resolve():
        p.error("Output must not overwrite the format profile")
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig")) if args.profile else None
        result = audit(args.input, profile, args.expect_heading, args.full_thesis, args.citation_style)
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
