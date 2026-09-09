#!/usr/bin/env python3
"""Local paragraph similarity and style review hints; not a plagiarism/AI score."""
import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


def paragraphs(path):
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return [(i + 1, "".join(t.text or "" for t in p.findall(".//w:t", ns))) for i, p in enumerate(root.findall(".//w:p", ns))]
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if path.suffix.lower() not in {".md", ".markdown"}:
        return [(i + 1, line.strip()) for i, line in enumerate(lines) if line.strip()]
    # Markdown soft wrapping does not start a new paragraph. Preserve first-line
    # locators, keep block boundaries and exclude fenced implementation examples.
    result, pending = [], []
    start, fence = None, None
    def flush():
        nonlocal start
        if pending:
            result.append((start, " ".join(pending)))
            pending.clear()
        start = None
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        marker = re.match(r"^(`{3,}|~{3,})(.*)$", line)
        if marker:
            if fence is None:
                flush()
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence) and not marker.group(2).strip():
                fence = None
            continue
        if fence is not None:
            continue
        if not line:
            flush()
        elif re.match(r"^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)", line):
            flush()
            result.append((i, line))
        else:
            if start is None:
                start = i
            pending.append(line)
    flush()
    return result


def analyze(lines, minimum=60, threshold=.86):
    candidates = []
    style = []
    patterns = ["随着时代的发展", "具有十分重要的意义", "填补了.*空白", "首次提出", "作为AI", "作为人工智能"]
    for loc, text in lines:
        normalized = re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text)).lower()
        if len(normalized) >= minimum:
            candidates.append((loc, text, normalized))
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                style.append({"location": loc, "pattern": pattern, "text": text[:180], "action": "Review context and evidence; do not auto-delete"})
    matches = []
    for index, a in enumerate(candidates):
        for b in candidates[index + 1:]:
            if 2 * min(len(a[2]), len(b[2])) / (len(a[2]) + len(b[2])) < threshold:
                continue
            matcher = SequenceMatcher(None, a[2], b[2], autojunk=False)
            if matcher.quick_ratio() < threshold:
                continue
            ratio = matcher.ratio()
            if ratio >= threshold:
                matches.append({"first": a[0], "second": b[0], "kind": "exact" if a[2] == b[2] else "near", "character_similarity": round(ratio, 4), "excerpt": a[1][:180]})
    return {"paragraph_count": len(lines), "compared_paragraphs": len(candidates), "matches": matches, "style_review": style,
            "limits": ["Character overlap is not semantic plagiarism", "No external database or AI detector used", "Keep legitimate summaries, standard declarations and necessary terminology", "DOCX excludes headers/footnotes here; review them separately"]}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--min-chars", type=int, default=60)
    p.add_argument("--threshold", type=float, default=.86)
    args = p.parse_args()
    if args.min_chars < 1 or not 0 < args.threshold <= 1:
        p.error("min-chars >= 1 and 0 < threshold <= 1 required")
    if args.out and args.out.resolve() == args.input.resolve():
        p.error("Output must not overwrite input")
    try:
        result = analyze(paragraphs(args.input), args.min_chars, args.threshold)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        print(json.dumps({"input_error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
