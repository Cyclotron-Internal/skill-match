"""Ingest resumes: read file -> analyze with Azure OpenAI -> store in SQLite.

Usage:
    python ingest.py path/to/resume.pdf
    python ingest.py path/to/folder_of_resumes
    python ingest.py path/to/resume.docx --json
"""
import argparse
import json
import sys
from pathlib import Path

from config import level_label
from db import get_all_skill_names, get_connection, init_db, save_employee
from extractor import analyze_resume
from resume_parser import SUPPORTED_EXTENSIONS, read_resume


def ingest_resume(path: str) -> dict:
    """Process one resume end-to-end. Returns the saved employee summary (UI-friendly dict)."""
    init_db()
    text = read_resume(path)
    with get_connection() as conn:
        existing = get_all_skill_names(conn)
    analysis = analyze_resume(text, existing)
    return save_employee(analysis, resume_path=str(Path(path).resolve()))


def find_resumes(path: str) -> list[Path]:
    p = Path(path)
    if p.is_dir():
        return sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS)
    return [p]


def print_result(result: dict) -> None:
    print(f"\nSaved: {result['name']} (employee id {result['employee_id']})")
    for original, canonical in result["corrections"]:
        print(f"  corrected skill: {original} -> {canonical}")
    print(f"  {'Skill':<28}{'Domain':<27}Level")
    print(f"  {'-' * 28}{'-' * 27}{'-' * 20}")
    for s in result["skills"]:
        print(f"  {s['skill']:<28}{s['domain']:<27}{level_label(s['level'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest resume(s) into the skills database")
    parser.add_argument("path", help="Resume file (.pdf/.docx/.txt) or a folder of resumes")
    parser.add_argument("--json", action="store_true", help="Print results as JSON")
    args = parser.parse_args()

    results, failed = [], 0
    for file in find_resumes(args.path):
        try:
            if not args.json:
                print(f"Analyzing {file.name} ...")
            result = ingest_resume(str(file))
            results.append(result)
            if not args.json:
                print_result(result)
        except Exception as exc:  # keep going with the next resume
            failed += 1
            print(f"  ERROR processing {file}: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(results, indent=2))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
