#!/usr/bin/env python3
"""Check a relocated skill without network, installation, or writes to the skill folder."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def inspect(self_test=False):
    report = {"skill_root": str(ROOT), "python": sys.version.split()[0],
              "python_supported": sys.version_info >= (3, 10), "checks": [],
              "optional": {}, "errors": [], "visual_review": "not_performed"}
    if not report["python_supported"]:
        report["errors"].append("Python 3.10+ required for supported script execution")
    manifest = ROOT / "manifest.json"
    if manifest.is_file():
        try:
            inventory = json.loads(manifest.read_text(encoding="utf-8"))["files"]
            for name, expected in inventory.items():
                path = (ROOT / name).resolve()
                if not path.is_relative_to(ROOT) or not path.is_file():
                    report["errors"].append(f"Missing or unsafe manifest path: {name}")
                elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    report["errors"].append(f"Checksum mismatch: {name}")
            report["checks"].append({"manifest_files": len(inventory)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report["errors"].append(f"Invalid manifest: {exc}")
    else:
        report["errors"].append("manifest.json missing from baseline package")
    docx_available = importlib.util.find_spec("docx") is not None
    report["optional"]["python_docx"] = "available" if docx_available else "missing; audits still work"
    report["optional"]["renderer_candidates_on_path"] = {
        name: shutil.which(name) for name in ("soffice", "libreoffice", "winword")}
    report["optional"]["renderer_note"] = "PATH discovery only; native/API renderers may exist elsewhere. No renderer has been launched."
    if not self_test:
        return report
    with tempfile.TemporaryDirectory(prefix="mba skill 自检 ") as temp:
        workspace = Path(temp)
        def run(name, args, expected=0):
            interpreter_flags = ["-S"] if sys.flags.no_site else []
            process = subprocess.run([sys.executable, *interpreter_flags, str(ROOT / "scripts" / name), *map(str, args)],
                                     cwd=workspace, capture_output=True, timeout=60,
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            stdout = process.stdout.decode("utf-8")
            if process.returncode != expected:
                raise ValueError(f"{name} exit {process.returncode}: {stdout[:500]} {process.stderr.decode('utf-8', errors='replace')[:300]}")
            payload = json.loads(stdout)
            report["checks"].append({"script": name, "exit": process.returncode})
            return payload
        try:
            project = workspace / "项目.json"
            project.write_text(json.dumps({"schema_version": 1, "project": {
                "title": "SYNTHETIC self-test", "mode": "topic_to_thesis", "stage": "research_draft"}}, ensure_ascii=False), encoding="utf-8")
            assert not run("audit_project.py", [project])["errors"], "Draft rejected"
            paragraph = "这是临时安装自检使用的模拟段落，内容用于核验重复扫描是否能够按实际段落运行，不代表任何企业事实或论文结论。" * 2
            prose = workspace / "测试.md"
            prose.write_text(paragraph + "\n\n" + paragraph, encoding="utf-8")
            result = run("audit_text.py", [prose])
            assert any(x["kind"] == "exact" for x in result["matches"]), "Duplicate missed"
            if docx_available:
                from docx import Document
                spec = workspace / "表.json"
                spec.write_text(json.dumps({"number": "3.1", "title": "安装自检模拟表", "headers": ["类别", "值"],
                    "rows": [["模拟A", 1], ["模拟B", None]], "source": "临时生成的自检材料，非研究数据"}, ensure_ascii=False), encoding="utf-8")
                output = workspace / "表.docx"
                run("build_table.py", [spec, "--out", output])
                doc = Document(output)
                assert len(doc.tables) == 1 and doc.tables[0].cell(2, 1).text == "—", "Editable table or missing value failed"
                assert any("不表示零" in p.text for p in doc.paragraphs), "Missing value note omitted"
                result = run("audit_docx.py", [output, "--profile", ROOT / "assets/ustc-format.json"])
                assert not result["errors"], "Generated table has structural errors"
                original = output.read_bytes()
                run("build_table.py", [spec, "--out", output], expected=2)
                assert output.read_bytes() == original, "Existing output changed"
            else:
                # The standard-library audit can inspect the bundled DOCX without python-docx.
                run("audit_docx.py", [ROOT / "assets/ustc-thesis-template.docx"])
                report["checks"].append({"table_generation": "skipped: optional python-docx unavailable"})
        except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as exc:
            report["errors"].append(str(exc))
    return report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    result = inspect(args.self_test)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
