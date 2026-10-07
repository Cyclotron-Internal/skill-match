"""SQLite storage: employees, skills (unique) and employee skill levels."""
import sqlite3
from datetime import datetime

from config import DB_PATH, DOMAINS, LEVELS
from skill_normalizer import normalize_key, resolve_skill

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    name                   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email                  TEXT,
    current_role           TEXT,
    total_experience_years REAL,
    summary                TEXT,
    resume_path            TEXT,
    updated_at             TEXT
);

CREATE TABLE IF NOT EXISTS skills (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    normalized_key TEXT NOT NULL UNIQUE,
    domain         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_skills (
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    level       INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    level_label TEXT NOT NULL,
    years_used  REAL,
    evidence    TEXT,
    PRIMARY KEY (employee_id, skill_id)
);
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def get_all_skill_names(conn: sqlite3.Connection) -> list[str]:
    return [row["name"] for row in conn.execute("SELECT name FROM skills")]


def _get_or_create_skill(conn: sqlite3.Connection, name: str, domain: str) -> int:
    """Return the skill id; a skill is created only once (unique by normalized key)."""
    key = normalize_key(name)
    domain = domain if domain in DOMAINS else "Other"
    row = conn.execute("SELECT id, domain FROM skills WHERE normalized_key = ?", (key,)).fetchone()
    if row:
        # Upgrade an old 'Other' (or retired) domain when a better one is known
        if domain != "Other" and (row["domain"] == "Other" or row["domain"] not in DOMAINS):
            conn.execute("UPDATE skills SET domain = ? WHERE id = ?", (domain, row["id"]))
        return row["id"]
    cur = conn.execute(
        "INSERT INTO skills (name, normalized_key, domain) VALUES (?, ?, ?)", (name, key, domain)
    )
    return cur.lastrowid


def save_employee(analysis: dict, resume_path: str = "", db_path: str = DB_PATH) -> dict:
    """Insert or update an employee and replace their skills.

    `analysis` is a dict shaped like extractor.ResumeAnalysis.
    Returns {"employee_id", "name", "skills": [...], "corrections": [(original, canonical), ...]}.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        known = get_all_skill_names(conn)

        # 1) Resolve every skill to its canonical name and merge duplicates (keep highest level)
        merged: dict[str, dict] = {}
        corrections = []
        for s in analysis.get("skills", []):
            original = s["skill"]
            canonical = resolve_skill(original, known)
            if canonical != original.strip():
                corrections.append((original, canonical))
            key = normalize_key(canonical)
            level = max(1, min(5, int(s["level"])))
            if key not in merged or level > merged[key]["level"]:
                merged[key] = {**s, "skill": canonical, "level": level}
            if canonical not in known:
                known.append(canonical)

        # 2) Upsert the employee
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO employees (name, email, current_role, total_experience_years, summary, resume_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                email = excluded.email,
                current_role = excluded.current_role,
                total_experience_years = excluded.total_experience_years,
                summary = excluded.summary,
                resume_path = excluded.resume_path,
                updated_at = excluded.updated_at
            """,
            (
                analysis["name"].strip(),
                analysis.get("email"),
                analysis.get("current_role"),
                analysis.get("total_experience_years"),
                analysis.get("summary"),
                resume_path,
                now,
            ),
        )
        employee_id = conn.execute(
            "SELECT id FROM employees WHERE name = ?", (analysis["name"].strip(),)
        ).fetchone()["id"]

        # 3) Replace this employee's skills (re-running ingest never duplicates rows)
        conn.execute("DELETE FROM employee_skills WHERE employee_id = ?", (employee_id,))
        saved = []
        for s in merged.values():
            skill_id = _get_or_create_skill(conn, s["skill"], s.get("domain", "Other"))
            conn.execute(
                """
                INSERT INTO employee_skills (employee_id, skill_id, level, level_label, years_used, evidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (employee_id, skill_id, s["level"], LEVELS[s["level"]], s.get("years_used"), s.get("evidence")),
            )
            domain = conn.execute("SELECT domain FROM skills WHERE id = ?", (skill_id,)).fetchone()["domain"]
            saved.append({"skill": s["skill"], "domain": domain, "level": s["level"], "level_label": LEVELS[s["level"]]})

        # Remove skills no employee has any more (e.g. after a re-ingest)
        conn.execute("DELETE FROM skills WHERE id NOT IN (SELECT skill_id FROM employee_skills)")

    saved.sort(key=lambda x: (-x["level"], x["skill"]))
    return {"employee_id": employee_id, "name": analysis["name"].strip(), "skills": saved, "corrections": corrections}
