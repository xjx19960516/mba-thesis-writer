#!/usr/bin/env python3
"""Generate explicitly labelled synthetic survey data from exact option/group quotas."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def generate(spec):
    require(isinstance(spec, dict), "Specification must be an object")
    require(not (set(spec) - {"data_origin", "purpose", "sample_size", "seed", "questions"}), "Unsupported specification fields; do not assume unimplemented targets were satisfied")
    require(spec.get("data_origin") == "SIMULATED", "data_origin must be SIMULATED")
    require(isinstance(spec.get("purpose"), str) and spec["purpose"].strip(), "State the simulation purpose and assumptions")
    n, seed, questions = spec.get("sample_size"), spec.get("seed"), spec.get("questions")
    require(type(n) is int and 1 <= n <= 100000, "sample_size must be an integer in 1..100000")
    require(type(seed) is int, "An integer seed is required")
    require(isinstance(questions, list) and 1 <= len(questions) <= 200 and n * len(questions) <= 2000000, "Provide 1..200 questions within 2 million cells")
    rng = random.Random(seed)
    rows = [{"record_id": f"SIM-{i + 1:06d}", "data_origin": "SIMULATED"} for i in range(n)]
    known = {}
    summary = {"data_origin": "SIMULATED", "sample_size": n, "seed": seed, "purpose": spec["purpose"], "questions": []}
    for q in questions:
        require(isinstance(q, dict), "Question must be an object")
        require(not (set(q) - {"id", "text", "kind", "options", "reverse", "counts", "condition_on", "counts_by_group"}), "Unsupported question fields")
        qid = q.get("id")
        require(isinstance(qid, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", qid) and qid not in known and qid not in {"record_id", "data_origin"}, "Question IDs must be unique safe column names")
        require(isinstance(q.get("text"), str) and q["text"].strip(), f"{qid}: question text required")
        require(q.get("kind") in {"single", "likert"}, f"{qid}: supported kinds are single and likert")
        options = q.get("options")
        require(isinstance(options, list) and 2 <= len(options) <= 100, f"{qid}: provide 2..100 options")
        values = []
        for option in options:
            require(isinstance(option, dict) and isinstance(option.get("label"), str) and option["label"].strip(), f"{qid}: option label required")
            value = option.get("value")
            require(set(option) == {"value", "label"}, f"{qid}: option fields must be value and label")
            valid = type(value) is int and -100 <= value <= 100 if q["kind"] == "likert" else isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", value)
            require(valid and value not in values, f"{qid}: invalid or duplicate option value")
            values.append(value)
        if q["kind"] == "likert":
            require(sorted(values) == list(range(min(values), max(values) + 1)), f"{qid}: this tool supports contiguous integer Likert scores only")
        reverse = q.get("reverse", False)
        require(type(reverse) is bool and (not reverse or q["kind"] == "likert"), f"{qid}: reverse applies only to Likert scoring")
        parent = q.get("condition_on")
        if parent is None:
            require("counts" in q and "counts_by_group" not in q, f"{qid}: specify counts only")
            groups = [(None, list(range(n)), q["counts"])]
        else:
            require(isinstance(parent, str) and parent in known and "counts" not in q, f"{qid}: condition_on must refer to an earlier question; do not also set counts")
            quotas = q.get("counts_by_group")
            require(isinstance(quotas, dict) and set(quotas) == {str(v) for v in known[parent]}, f"{qid}: quotas must cover exactly every parent option")
            groups = [(value, [i for i, row in enumerate(rows) if row[parent] == value], quotas[str(value)]) for value in known[parent]]
        for group, indices, counts in groups:
            require(isinstance(counts, list) and len(counts) == len(values) and all(type(c) is int and c >= 0 for c in counts), f"{qid}/{group}: counts must be nonnegative integers matching options")
            require(sum(counts) == len(indices), f"{qid}/{group}: quota total {sum(counts)} does not match group size {len(indices)}")
            assigned = [value for value, count in zip(values, counts) for _ in range(count)]
            rng.shuffle(assigned)
            for i, value in zip(indices, assigned):
                rows[i][qid] = value
        known[qid] = values
        def describe(indices):
            observed = [rows[i][qid] for i in indices]
            freq = Counter(observed)
            result = {"n": len(observed), "options": [{"value": v, "label": option["label"], "count": freq[v], "percent": 100 * freq[v] / len(observed) if observed else None} for v, option in zip(values, options)]}
            if q["kind"] == "likert":
                scored = [min(values) + max(values) - v if reverse else v for v in observed]
                result.update(raw_mean=math.fsum(observed) / len(observed) if observed else None,
                              scored_mean=math.fsum(scored) / len(scored) if scored else None)
            return result
        entry = {"id": qid, "text": q["text"], "kind": q["kind"], "reverse": reverse,
                 "overall": describe(list(range(n)))}
        if parent is not None:
            entry.update(condition_on=parent, groups=[{"value": value, **describe(indices)} for value, indices, _ in groups])
        summary["questions"].append(entry)
    return rows, summary


def outputs(spec, rows, summary):
    def encoded(value):
        return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    def md(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=["record_id", "data_origin"] + [q["id"] for q in spec["questions"]])
    writer.writeheader()
    writer.writerows(rows)
    lines = ["# 模拟问卷分析报告", "", "**数据性质：全部为程序生成的模拟记录；未实际发放或回收问卷。**", "",
             "用途与假设：" + md(spec["purpose"]), "", f"生成记录数：{len(rows)}；随机种子：{spec['seed']}。", "",
             "选项人数和分组差异由配置设定；随机打乱只决定记录分配。结果描述这些设定，不验证现实企业状况或因果关系。"]
    for q in summary["questions"]:
        lines += ["", f"## {md(q['id'])}：{md(q['text'])}"]
        sections = [("总体", q["overall"])] + [(f"{q.get('condition_on')}={g['value']}", g) for g in q.get("groups", [])]
        for label, stats in sections:
            lines += ["", f"{md(label)}（模拟记录数 {stats['n']}）", "", "|选项|模拟人数|模拟比例|", "|---|---:|---:|"]
            for option in stats["options"]:
                percent = "—" if option["percent"] is None else f"{option['percent']:.2f}%"
                lines.append(f"|{md(option['label'])}|{option['count']}|{percent}|")
            if stats.get("raw_mean") is not None:
                lines += ["", f"原始编码均值：{stats['raw_mean']:.4f}；计分均值：{stats['scored_mean']:.4f}（反向计分：{'是' if q['reverse'] else '否'}）。"]
            lines += ["", "来源：本次模拟生成记录；比例按本表模拟记录数计算，展示舍入可能使合计略有差异。"]
    lines += ["", "## 解释范围", "", "本报告提供描述统计，不报告真实回收率、实测信效度、显著性或因果效果。复杂量表、跳转、多选、相关结构与推断方法需使用适用分析工具另行建模和核验。模拟报告不替代真实调查；可用于保留临时标识及替换任务的研究工作稿。作为正式模拟研究内容时须符合已确认的研究方案并保留模拟标识。", ""]
    files = {"simulated-responses.csv": csv_buffer.getvalue().encode("utf-8-sig"),
             "simulated-summary.json": encoded(summary), "simulation-spec.json": encoded(spec),
             "simulated-report.md": "\n".join(lines).encode("utf-8")}
    files["provenance.json"] = encoded({"data_origin": "SIMULATED", "generator": "simulate_survey.py", "python": sys.version.split()[0],
        "algorithm": "Exact option quotas, shuffled sequentially per question/group using Python Random(seed)",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}})
    return files


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
        rows, summary = generate(spec)
        files = outputs(spec, rows, summary)
        # Validate and render everything before creating the new output directory.
        args.out_dir.mkdir(exist_ok=False)
        for name, data in files.items():
            with (args.out_dir / name).open("xb") as handle:
                handle.write(data)
        print(json.dumps({"status": "simulated_generated", "data_origin": "SIMULATED", "sample_size": len(rows), "files": list(files)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"input_or_output_error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
