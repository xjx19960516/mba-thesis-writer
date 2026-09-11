#!/usr/bin/env python3
"""Check traceability records, not source truth or research validity. Stdlib only."""
import argparse
import copy
import datetime as dt
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


def audit(data):
    result = {"errors": [], "warnings": [], "manual_checks": [
        "Return to each source to verify truth, scope and claim support.",
        "Recompute numbers from original inputs; confirm source independence.",
        "Verify the current national standard on the official platform.",
        "Read the thesis and inspect all rendered pages; records are not proof of review."]}
    def issue(msg, hard=True):
        result["errors" if hard else "warnings"].append(msg)
    def filled(value):
        return isinstance(value, str) and bool(value.strip())
    def past_date(value, loc):
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            parsed = dt.date.fromisoformat(value)
            if parsed > dt.date.today():
                raise ValueError()
            return parsed
        except ValueError:
            issue(f"{loc}: valid ISO YYYY-MM-DD date no later than today required")
            return None
    def enum(obj, key, choices, loc, required=True):
        if not required and obj.get(key) is None:
            return
        if not isinstance(obj.get(key), str) or obj.get(key) not in choices:
            issue(f"{loc}.{key}: expected one of {', '.join(sorted(choices))}")
            obj[key] = None
    def require(obj, keys, loc):
        for key in keys:
            if not filled(obj.get(key)):
                issue(f"{loc}.{key}: substantive text required")
    if not isinstance(data, dict):
        issue("Root must be an object")
        return result
    # Normalize invalid enums only on a private copy; never mutate caller data.
    data = copy.deepcopy(data)
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        issue("schema_version must be 1")
    project = data.get("project", {})
    if not isinstance(project, dict):
        issue("project must be an object")
        return result
    require(project, ["title"], "project")
    enum(project, "mode", {"topic_to_thesis", "proposal_to_thesis", "thesis_revision", "finalization"}, "project")
    enum(project, "stage", {"research_draft", "research_ready", "full_draft", "review_ready", "submission_candidate"}, "project")
    enum(project, "thesis_type", {"topic_research", "case_descriptive", "case_problem", "other"}, "project", False)
    enum(project, "citation_style", {"numeric", "author_year"}, "project", False)
    final = project.get("stage") == "submission_candidate"
    temporary = project.get("contains_temporary_results")
    if temporary is not None and type(temporary) is not bool:
        issue("project.contains_temporary_results: boolean required when provided")
    if temporary is True:
        issue("project.contains_temporary_results: replace or resolve temporary results before submission", final)
    revision = project.get("content_revision")
    if revision is not None and not filled(revision):
        issue("project.content_revision: nonempty text required when provided")
    if final:
        require(project, ["thesis_type", "citation_style", "citation_standard", "template", "research_period", "delivery_variant"], "project")
        enum(project, "delivery_variant", {"review", "archive"}, "project")
        standard = project.get("standard_verification", {})
        if not isinstance(standard, dict):
            standard = {}
        require(standard, ["number", "status", "effective_on", "checked_on", "official_url"], "standard_verification")
        if standard.get("number") != project.get("citation_standard") or standard.get("status") != "current":
            issue("Current verified standard must match citation_standard")
        official_url = standard.get("official_url")
        parsed = urlparse(official_url) if isinstance(official_url, str) else urlparse("")
        if parsed.scheme not in {"https", "http"} or not (parsed.hostname == "samr.gov.cn" or (parsed.hostname or "").endswith(".samr.gov.cn")):
            issue("standard_verification.official_url: use the SAMR official standard record")
        try:
            effective = dt.date.fromisoformat(standard.get("effective_on", ""))
            checked = dt.date.fromisoformat(standard.get("checked_on", ""))
            if effective > checked or checked > dt.date.today():
                issue("Standard effective/verification dates are inconsistent")
        except (ValueError, TypeError):
            issue("Standard dates must be ISO YYYY-MM-DD")
        if project.get("mode") == "proposal_to_thesis" and (not isinstance(data.get("proposal_baseline"), dict) or not data.get("proposal_baseline")):
            issue("Proposal baseline is required for a proposal-derived submission")
        if project.get("thesis_type") == "other" and not filled(project.get("type_authority")):
            issue("Other thesis forms require a cultivation-unit authority")

    collections = {}
    all_ids = set()
    for key in ["sources", "claims", "data_items", "displays", "research_questions", "changes", "tasks"]:
        items = data.get(key, [])
        if not isinstance(items, list):
            issue(f"{key}: array required")
            items = []
        collections[key] = {}
        for n, item in enumerate(items):
            if not isinstance(item, dict) or not filled(item.get("id")):
                issue(f"{key}[{n}]: object with a nonempty id required")
                continue
            if item["id"] in all_ids:
                issue(f"Duplicate ID: {item['id']}")
            all_ids.add(item["id"])
            collections[key][item["id"]] = item
    src = collections["sources"]
    nums = collections["data_items"]
    for key in ["sources", "claims", "research_questions"]:
        if not collections[key]:
            issue(f"No {key} registered", final)

    def refs(item, key, allowed, required=False):
        ids = item.get(key, [])
        if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
            issue(f"{item['id']}.{key}: string array required")
            return []
        if required and not ids:
            issue(f"{item['id']}.{key}: evidence required")
        for value in ids:
            if value not in allowed:
                issue(f"{item['id']}.{key}: unresolved ID {value}")
        return ids

    def source_ready(sid):
        item = src.get(sid, {})
        return item.get("verification") == "verified" and item.get("eligibility") == "accepted" and item.get("access_scope") in {"abstract", "full_text", "dataset"}

    bibliography_keys = {}
    for sid, source in src.items():
        enum(source, "kind", {"official", "academic", "third_party", "internal", "auxiliary"}, sid)
        enum(source, "verification", {"verified", "unverified"}, sid)
        enum(source, "eligibility", {"accepted", "reference_only", "rejected"}, sid)
        enum(source, "access_scope", {"metadata_only", "abstract", "full_text", "dataset"}, sid)
        if source.get("eligibility") == "accepted":
            require(source, ["title", "publisher", "origin", "accessed_on", "locator"], sid)
            past_date(source.get("accessed_on"), f"{sid}.accessed_on")
            if source.get("verification") != "verified":
                issue(f"{sid}: accepted source is unverified")
            if source.get("kind") == "third_party":
                qual = source.get("qualification", {})
                if not isinstance(qual, dict):
                    qual = {}
                require(qual, ["traceable_origin", "period", "population", "definition", "method", "research_fit"], f"{sid}.qualification")
        if "used_in_bibliography" in source and type(source["used_in_bibliography"]) is not bool:
            issue(f"{sid}.used_in_bibliography: boolean required")
        if source.get("used_in_bibliography") is True:
            if not source_ready(sid):
                issue(f"{sid}: bibliography source is not eligible for substantive use")
            require(source, ["bibliography_key"], sid)
            key = source.get("bibliography_key")
            if filled(key):
                if key in bibliography_keys:
                    issue(f"{sid}: duplicate bibliography key {key} with {bibliography_keys[key]}")
                bibliography_keys[key] = sid

    for did, item in nums.items():
        enum(item, "status", {"observed", "calculated", "scenario", "pending"}, did)
        used = refs(item, "source_ids", src, item.get("status") in {"observed", "calculated"})
        for sid in used:
            if not source_ready(sid):
                issue(f"{did}: unsuitable data source {sid}", item.get("status") != "pending")
        if item.get("status") != "pending":
            require(item, ["indicator", "unit", "period", "definition", "population"], did)
            if item.get("value") is None:
                issue(f"{did}: actual/scenario value is absent")
            elif type(item["value"]) not in (str, int, float) or (isinstance(item["value"], float) and not math.isfinite(item["value"])) or (isinstance(item["value"], str) and not item["value"].strip()):
                issue(f"{did}.value: nonempty text or finite number required, not boolean")
        if item.get("status") == "calculated":
            refs(item, "input_ids", nums, True)
            require(item, ["formula", "analysis_path"], did)
        elif item.get("status") == "observed" and item.get("input_ids"):
            issue(f"{did}: observed data cannot have derived inputs; classify as calculated or scenario")
    # Derived data must not launder scenario/pending values or form cycles.
    visited = set()
    def visit(did, stack):
        if did in stack:
            issue("Cyclic data dependencies: " + " -> ".join(stack + [did]))
            return
        if did in visited:
            return
        item = nums.get(did, {})
        for parent in item.get("input_ids", []) if isinstance(item.get("input_ids", []), list) else []:
            if not isinstance(parent, str) or parent not in nums:
                continue
            if item.get("status") == "calculated" and nums[parent].get("status") in {"scenario", "pending"}:
                issue(f"{did}: calculated empirical data depends on {nums[parent].get('status')} {parent}")
            visit(parent, stack + [did])
        visited.add(did)
    for did in nums:
        visit(did, [])

    used_source_ids = set()
    def check_evidence(owner, ids, factual=False):
        for eid in ids:
            if eid in src:
                used_source_ids.add(eid)
                if not source_ready(eid):
                    issue(f"{owner}: source {eid} cannot support substantive evidence")
            elif eid in nums:
                item = nums[eid]
                if item.get("status") not in {"observed", "calculated", "scenario"} or (factual and item.get("status") == "scenario"):
                    issue(f"{owner}: unsuitable data status for {eid}")
                pending = [eid]
                seen_data = set()
                while pending:
                    current = pending.pop()
                    if current in seen_data:
                        continue
                    seen_data.add(current)
                    raw = nums[current]
                    source_ids = refs(raw, "source_ids", src)
                    for sid in source_ids:
                        used_source_ids.add(sid)
                        if not source_ready(sid):
                            issue(f"{owner}: data {current} has unsuitable source {sid}")
                    inputs = refs(raw, "input_ids", nums)
                    pending.extend(x for x in inputs if x in nums)

    for cid, claim in collections["claims"].items():
        enum(claim, "status", {"supported", "pending", "withdrawn"}, cid)
        enum(claim, "kind", {"factual", "interpretation", "proposal", "scenario"}, cid)
        used = refs(claim, "evidence_ids", set(src) | set(nums), claim.get("status") == "supported")
        require(claim, ["text", "section"], cid)
        if claim.get("status") == "supported":
            require(claim, ["locator"], cid)
            check_evidence(cid, used, claim.get("kind") == "factual")
        if final and claim.get("status") == "pending":
            issue(f"{cid}: unresolved claim in submission candidate")

    for rid, question in collections["research_questions"].items():
        enum(question, "status", {"planned", "in_progress", "answered"}, rid)
        ids = refs(question, "evidence_ids", set(src) | set(nums), question.get("status") == "answered")
        if question.get("status") == "answered":
            check_evidence(rid, ids)
        require(question, ["question", "unit", "inference_goal", "method", "output"], rid)
        chapters = question.get("chapters")
        if not isinstance(chapters, list) or not chapters or any(not filled(x) for x in chapters):
            issue(f"{rid}: chapters not mapped", final)
        if final and question.get("status") != "answered":
            issue(f"{rid}: research question not answered")
    display_numbers = set()
    for did, display in collections["displays"].items():
        enum(display, "kind", {"table", "figure"}, did)
        enum(display, "status", {"planned", "included"}, did, False)
        display_state = display.get("status") or "included"
        require(display, ["number", "title"], did)
        if display_state == "included" or final:
            require(display, ["first_mention"], did)
        if not isinstance(display.get("number"), str) or not re.fullmatch(r"(?:[1-9]\d*|[A-Z])\.[1-9]\d*", display["number"]):
            issue(f"{did}.number: chapter.index or appendix.index required")
        ids = refs(display, "source_ids", src)
        data_ids = refs(display, "data_ids", nums)
        if not ids and not data_ids and (display_state == "included" or final):
            issue(f"{did}: no traceable source or data")
        if not isinstance(display.get("research_question_id"), str) or display.get("research_question_id") not in collections["research_questions"]:
            issue(f"{did}: research question missing")
        key = (display.get("kind"), str(display.get("number")))
        if key in display_numbers:
            issue(f"{did}: duplicate display number")
        display_numbers.add(key)
        if display_state == "included" or final:
            check_evidence(did, ids + data_ids)
        if final and display_state != "included":
            issue(f"{did}: planned display is unfinished in submission candidate")
        for flag in ["calculation_checked", "format_checked"]:
            if flag == "calculation_checked" and display.get(flag) == "not_applicable":
                require(display, ["calculation_note"], did)
                pending = list(data_ids)
                visited_data = set()
                while pending:
                    data_id = pending.pop()
                    if data_id in visited_data or data_id not in nums:
                        continue
                    visited_data.add(data_id)
                    datum = nums[data_id]
                    if datum.get("status") == "calculated" or type(datum.get("value")) in (int, float):
                        issue(f"{did}.calculation_checked: numeric or calculated data {data_id} requires numeric review, not not_applicable")
                        break
                    parents = datum.get("input_ids", [])
                    if isinstance(parents, list):
                        pending.extend(x for x in parents if isinstance(x, str))
                continue
            if flag in display and type(display[flag]) is not bool:
                issue(f"{did}.{flag}: boolean required")
            if final and display.get(flag) is not True:
                issue(f"{did}.{flag}: must be true after actual review")
    for cid, change in collections["changes"].items():
        enum(change, "status", {"proposed", "approved", "implemented", "declined"}, cid)
        if type(change.get("substantive")) is not bool:
            issue(f"{cid}.substantive: boolean required")
        if change.get("substantive") and change.get("status") == "implemented" and not filled(change.get("authorization")):
            issue(f"{cid}: implemented substantive change lacks authorization record")
    for tid, task in collections["tasks"].items():
        enum(task, "status", {"open", "done", "waived"}, tid)
        if type(task.get("blocking")) is not bool:
            issue(f"{tid}.blocking: boolean required")
        if final and task.get("blocking") and task.get("status") == "open":
            issue(f"{tid}: blocking task remains open")
        if task.get("status") == "waived" and not filled(task.get("reason")):
            issue(f"{tid}: waived task needs reason/alternative")
    if final:
        if not any(c.get("status") == "supported" for c in collections["claims"].values()):
            issue("Submission candidate has no supported claims")
        for sid, source in src.items():
            if source.get("used_in_bibliography") is True and sid not in used_source_ids:
                issue(f"{sid}: bibliography entry has no substantive use in claims/questions/displays")
            if sid in used_source_ids and source.get("kind") in {"official", "academic", "third_party", "auxiliary"} and source.get("used_in_bibliography") is not True:
                issue(f"{sid}: used public evidence is missing from the bibliography")
        qa = data.get("qa", {})
        if not isinstance(qa, dict):
            qa = {}
        for key in ["evidence_semantics", "calculations", "citations", "repetition", "academic_style", "consistency", "docx_structure", "visual_pages"]:
            record = qa.get(key, {})
            if not isinstance(record, dict):
                record = {}
            allowed = {"pass", "not_applicable"} if key == "calculations" and not nums else {"pass"}
            if record.get("status") not in allowed or not filled(record.get("evidence")):
                issue(f"qa.{key}: completed review and evidence required")
            if filled(revision) and record.get("reviewed_revision") != revision:
                issue(f"qa.{key}.reviewed_revision: must cover current content_revision {revision}")
            if key == "visual_pages":
                total = record.get("total_pages")
                pages = record.get("checked_pages")
                if type(total) is not int or total < 1 or not isinstance(pages, list) or any(type(p) is not int for p in pages) or set(pages) != set(range(1, total + 1)):
                    issue("qa.visual_pages: coverage must be every page 1..total_pages")
                if not filled(record.get("rendered_file")):
                    issue("qa.visual_pages.rendered_file required")
    result["counts"] = {key: len(value) for key, value in collections.items()}
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and args.out.resolve() == args.input.resolve():
        parser.error("Output must not overwrite input")
    try:
        result = audit(json.loads(args.input.read_text(encoding="utf-8-sig")))
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(rendered, encoding="utf-8")
        print(rendered)
        return 1 if result["errors"] else 0
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"input_error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
