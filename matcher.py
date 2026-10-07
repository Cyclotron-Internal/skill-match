"""Skill matching and search over SQLite - no AI involved.

Every public function returns plain lists/dicts, so any UI or API can call them directly.

CLI usage:
    python matcher.py search  --skills "Python, Azure" --min-level 3
    python matcher.py project --file sample_project.json
    python matcher.py domain  --name "Cloud"
    python matcher.py profile --name "Jane Doe"
    python matcher.py domains
    python matcher.py employees
Add --json to any command for machine-readable output.
"""
import argparse
import json
import sys

from config import LEVELS, level_label
from db import get_all_skill_names, get_connection, init_db
from skill_normalizer import resolve_skill


# ---------------------------------------------------------------- helpers

def _resolve(conn, names: list[str]) -> dict[str, str]:
    """Map user input (possibly misspelled) -> canonical skill name stored in DB."""
    known = get_all_skill_names(conn)
    return {n.strip(): resolve_skill(n, known) for n in names if n.strip()}


def _skill_rows(conn, skill_names: list[str]):
    """All employee_skills rows for the given canonical skill names."""
    if not skill_names:
        return []
    marks = ",".join("?" * len(skill_names))
    return conn.execute(
        f"""
        SELECT e.id AS employee_id, e.name, e.current_role, e.email,
               s.name AS skill, s.domain, es.level, es.years_used, es.evidence
        FROM employee_skills es
        JOIN employees e ON e.id = es.employee_id
        JOIN skills s    ON s.id = es.skill_id
        WHERE s.name IN ({marks})
        """,
        skill_names,
    ).fetchall()


def _skill_dict(row) -> dict:
    return {
        "skill": row["skill"],
        "domain": row["domain"],
        "level": row["level"],
        "level_label": LEVELS[row["level"]],
        "years_used": row["years_used"],
        "evidence": row["evidence"],
    }


# ---------------------------------------------------------------- service functions

def search_skills(skills: list[str], min_level: int = 1) -> dict:
    """Employees having any of `skills` at >= min_level.

    Ranked by: number of matched skills, then total level, then name.
    """
    init_db()
    with get_connection() as conn:
        resolved = _resolve(conn, skills)
        rows = _skill_rows(conn, list(set(resolved.values())))

    people: dict[int, dict] = {}
    for r in rows:
        if r["level"] < min_level:
            continue
        p = people.setdefault(
            r["employee_id"],
            {"employee_id": r["employee_id"], "name": r["name"], "current_role": r["current_role"],
             "email": r["email"], "matched_skills": [], "total_level": 0},
        )
        p["matched_skills"].append(_skill_dict(r))
        p["total_level"] += r["level"]

    results = sorted(people.values(), key=lambda p: (-len(p["matched_skills"]), -p["total_level"], p["name"]))
    for p in results:
        p["matched_skills"].sort(key=lambda s: -s["level"])
    return {"searched": resolved, "min_level": min_level, "results": results}


def match_project(requirements: dict[str, int], project_name: str = "") -> dict:
    """Rank employees against a project's required skills {skill: minimum level}.

    coverage = % of required skills met at the minimum level
    score    = sum of the employee's levels on the requirements they meet
    """
    init_db()
    with get_connection() as conn:
        resolved = _resolve(conn, list(requirements))
        required = {resolved[k.strip()]: int(v) for k, v in requirements.items() if k.strip()}
        rows = _skill_rows(conn, list(required))

    people: dict[int, dict] = {}
    for r in rows:
        p = people.setdefault(
            r["employee_id"],
            {"employee_id": r["employee_id"], "name": r["name"], "current_role": r["current_role"],
             "email": r["email"], "met": [], "below_required_level": [], "score": 0},
        )
        need = next(lvl for name, lvl in required.items() if name.lower() == r["skill"].lower())
        item = {**_skill_dict(r), "required_level": need}
        if r["level"] >= need:
            p["met"].append(item)
            p["score"] += r["level"]
        else:
            p["below_required_level"].append(item)

    for p in people.values():
        have = {s["skill"].lower() for s in p["met"] + p["below_required_level"]}
        p["missing"] = [s for s in required if s.lower() not in have]
        p["coverage_pct"] = round(100 * len(p["met"]) / len(required)) if required else 0

    results = sorted(people.values(), key=lambda p: (-p["coverage_pct"], -p["score"], p["name"]))
    return {"project": project_name, "requirements": required, "searched": resolved, "results": results}


def list_domains() -> list[dict]:
    """Every domain with its skills and how many employees have each skill."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.domain, s.name AS skill, COUNT(es.employee_id) AS employees
            FROM skills s LEFT JOIN employee_skills es ON es.skill_id = s.id
            GROUP BY s.id ORDER BY s.domain, s.name
            """
        ).fetchall()
    domains: dict[str, list] = {}
    for r in rows:
        domains.setdefault(r["domain"], []).append({"skill": r["skill"], "employees": r["employees"]})
    return [{"domain": d, "skills": s} for d, s in domains.items()]


def employees_by_domain(domain: str) -> dict:
    """Employees with skills in a domain (partial, case-insensitive name: 'cloud' finds 'Cloud & DevOps')."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.id AS employee_id, e.name, e.current_role, e.email,
                   s.name AS skill, s.domain, es.level, es.years_used, es.evidence
            FROM employee_skills es
            JOIN employees e ON e.id = es.employee_id
            JOIN skills s    ON s.id = es.skill_id
            WHERE s.domain LIKE ?
            """,
            (f"%{domain.strip()}%",),
        ).fetchall()

    people: dict[int, dict] = {}
    for r in rows:
        p = people.setdefault(
            r["employee_id"],
            {"employee_id": r["employee_id"], "name": r["name"], "current_role": r["current_role"],
             "email": r["email"], "skills": [], "best_level": 0, "total_level": 0},
        )
        p["skills"].append(_skill_dict(r))
        p["best_level"] = max(p["best_level"], r["level"])
        p["total_level"] += r["level"]

    results = sorted(people.values(), key=lambda p: (-p["best_level"], -p["total_level"], p["name"]))
    for p in results:
        p["skills"].sort(key=lambda s: -s["level"])
    return {"domain": domain, "results": results}


def employee_profile(name: str) -> dict | None:
    """Full profile of one employee, skills grouped by domain."""
    init_db()
    with get_connection() as conn:
        emp = conn.execute("SELECT * FROM employees WHERE name LIKE ?", (f"%{name.strip()}%",)).fetchone()
        if not emp:
            return None
        rows = conn.execute(
            """
            SELECT s.name AS skill, s.domain, es.level, es.years_used, es.evidence
            FROM employee_skills es JOIN skills s ON s.id = es.skill_id
            WHERE es.employee_id = ? ORDER BY s.domain, es.level DESC, s.name
            """,
            (emp["id"],),
        ).fetchall()
    by_domain: dict[str, list] = {}
    for r in rows:
        by_domain.setdefault(r["domain"], []).append(_skill_dict(r))
    return {**dict(emp), "skills_by_domain": by_domain}


def list_employees() -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.id AS employee_id, e.name, e.current_role, e.total_experience_years,
                   COUNT(es.skill_id) AS skill_count
            FROM employees e LEFT JOIN employee_skills es ON es.employee_id = e.id
            GROUP BY e.id ORDER BY e.name
            """
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- terminal output

def _print_corrections(resolved: dict[str, str]) -> None:
    for typed, canonical in resolved.items():
        if typed != canonical:
            print(f"  (interpreted '{typed}' as '{canonical}')")


def _print_search(data: dict) -> None:
    _print_corrections(data["searched"])
    print(f"\nSkills: {', '.join(sorted(set(data['searched'].values())))} | minimum level L{data['min_level']}")
    if not data["results"]:
        print("No matching employees.")
    for i, p in enumerate(data["results"], 1):
        print(f"\n{i}. {p['name']} - {p['current_role'] or ''}")
        for s in p["matched_skills"]:
            print(f"     {s['skill']:<30}{level_label(s['level']):<22}{s['domain']}")


def _print_project(data: dict) -> None:
    _print_corrections(data["searched"])
    print(f"\nProject: {data['project'] or '(unnamed)'}")
    print("Requires: " + ", ".join(f"{s} >= L{l}" for s, l in data["requirements"].items()))
    if not data["results"]:
        print("No employees match any required skill.")
    for i, p in enumerate(data["results"], 1):
        print(f"\n{i}. {p['name']} - {p['current_role'] or ''} | coverage {p['coverage_pct']}% | score {p['score']}")
        for s in p["met"]:
            print(f"     [met]     {s['skill']:<28}{level_label(s['level'])} (needs L{s['required_level']})")
        for s in p["below_required_level"]:
            print(f"     [below]   {s['skill']:<28}{level_label(s['level'])} (needs L{s['required_level']})")
        for s in p["missing"]:
            print(f"     [missing] {s}")


def _print_domain(data: dict) -> None:
    print(f"\nDomain search: '{data['domain']}'")
    if not data["results"]:
        print("No employees found in this domain.")
    for i, p in enumerate(data["results"], 1):
        print(f"\n{i}. {p['name']} - {p['current_role'] or ''}")
        for s in p["skills"]:
            print(f"     {s['skill']:<30}{level_label(s['level']):<22}{s['domain']}")


def _print_domains(data: list[dict]) -> None:
    if not data:
        print("No skills stored yet. Run ingest.py first.")
    for d in data:
        print(f"\n{d['domain']}")
        for s in d["skills"]:
            print(f"   - {s['skill']} ({s['employees']} employee{'s' if s['employees'] != 1 else ''})")


def _print_profile(data: dict | None) -> None:
    if not data:
        print("Employee not found.")
        return
    print(f"\n{data['name']} | {data['current_role'] or ''} | {data['email'] or ''}")
    print(f"Experience: {data['total_experience_years'] or '?'} years")
    print(f"Summary: {data['summary'] or ''}")
    for domain, skills in data["skills_by_domain"].items():
        print(f"\n  {domain}")
        for s in skills:
            print(f"     {s['skill']:<30}{level_label(s['level']):<22}{s['evidence'] or ''}")


def _print_employees(data: list[dict]) -> None:
    if not data:
        print("No employees stored yet. Run ingest.py first.")
    for e in data:
        print(f"  {e['employee_id']:>3}. {e['name']:<28}{(e['current_role'] or ''):<32}{e['skill_count']} skills")


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill matcher (SQLite only, no AI)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="Find employees by skills")
    p.add_argument("--skills", required=True, help='Comma separated, e.g. "Python, Azure"')
    p.add_argument("--min-level", type=int, default=1, choices=range(1, 6))

    p = sub.add_parser("project", help="Rank employees for a project requirement")
    p.add_argument("--file", help="JSON file: {\"project\": \"...\", \"required_skills\": {\"Python\": 3}}")
    p.add_argument("--require", help='Inline, e.g. "Python:3, Azure:2"')

    p = sub.add_parser("domain", help="Employees with skills in a domain")
    p.add_argument("--name", required=True)

    sub.add_parser("domains", help="List all domains and their skills")

    p = sub.add_parser("profile", help="Show one employee's profile")
    p.add_argument("--name", required=True)

    sub.add_parser("employees", help="List all employees")

    # allow --json anywhere on the command line
    argv = sys.argv[1:]
    as_json = "--json" in argv
    args = parser.parse_args([a for a in argv if a != "--json"])

    if args.command == "search":
        data, printer = search_skills(args.skills.split(","), args.min_level), _print_search
    elif args.command == "project":
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                spec = json.load(f)
            reqs, name = spec["required_skills"], spec.get("project", "")
        elif args.require:
            reqs = {}
            for part in args.require.split(","):
                skill, _, lvl = part.rpartition(":")
                reqs[skill.strip()] = int(lvl)
            name = ""
        else:
            parser.error("project needs --file or --require")
        data, printer = match_project(reqs, name), _print_project
    elif args.command == "domain":
        data, printer = employees_by_domain(args.name), _print_domain
    elif args.command == "domains":
        data, printer = list_domains(), _print_domains
    elif args.command == "profile":
        data, printer = employee_profile(args.name), _print_profile
    else:
        data, printer = list_employees(), _print_employees

    if as_json:
        print(json.dumps(data, indent=2))
    else:
        printer(data)


if __name__ == "__main__":
    main()
