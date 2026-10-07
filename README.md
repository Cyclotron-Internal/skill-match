# Skill Matcher – Backend Prototype

A simple backend that turns resumes into a searchable skills database.

```
Resume (PDF / DOCX / TXT)
        │
        ▼
 resume_parser.py ── reads the text
        │
        ▼
 extractor.py ───── LangChain + Azure OpenAI (Foundry)
        │            → name, role, skills, domain, level L1–L5 + evidence
        ▼
 skill_normalizer.py ─ fixes typos, merges duplicates (Pyhton → Python)
        │
        ▼
 db.py ──────────── SQLite (skills.db)
        │
        ▼
 matcher.py ─────── search / project matching / domains / profiles   (NO AI)
```

**AI is used only while loading a resume.** All searching and matching is plain SQLite, so it is instant, free and works offline.

All examples below use **Vasu Reddy's resume** (`input/NALAMALAPU_VASU_REDDY_RESUME.pdf`) with real output from this code.

---

## 1. Setup

```powershell
cd C:\Users\VasuReddy\Documents\SkillMatchT
venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project folder:

```
AZURE_OPENAI_KEY        = "<your key>"
AZURE_OPENAI_ENDPOINT   = "https://<your-resource>.openai.azure.com/"
AZURE_OPENAI_DEPLOYMENT = "gpt-4o"
AZURE_OPENAI_API_VERSION = "2024-12-01-preview"
```

Optional: set `SKILLS_DB_PATH` to use a different database file (default `skills.db`).

---

## 2. Expertise levels

Levels are proposed **strictly on evidence depth** in the resume:

| Level | Label        | Rule                                                                                                                   |
| ----- | ------------ | ---------------------------------------------------------------------------------------------------------------------- |
| L1    | Awareness    | Mentioned once, in passing, or listed only in a skills block                                                           |
| L2    | Intermediate | Used in one project or role, no depth described                                                                        |
| L3    | Practitioner | Used across multiple roles or projects with concrete responsibilities                                                 |
| L4    | Advanced     | Deep, sustained use with ownership of significant work                                                                 |
| L5    | Expert       | Recognised specialisation – architecture ownership, technical leadership, mentoring, publications or conference talks |

How it is enforced (`extractor.py`):

1. **Prompt:** the model must list `found_in`, meaning the projects or roles whose text **explicitly** names the skill. It must not assume a tool was used just because it's typical for that kind of work. Self-descriptions like "expert in" or "proficient" don't count, and when unsure it picks the lower level.
2. **Code check (`apply_rubric`)**, applied after the AI responds:
   - `found_in` empty → forced to **L1** (skills list only)
   - one project/role rated L3 → lowered to **L2** (L3 needs multiple)
   - L4/L5 from one long role is kept (deep, sustained ownership)

Every rating is saved with a one-line **evidence** sentence explaining *why*.

## 3. Skill domains

Every skill is put into exactly one domain (list in `config.py`):

`Programming Languages` · `Frontend` · `Backend & APIs` · `Cloud & DevOps` · `Data Engineering` · `Data Science & Analytics` · `AI / ML` · `Databases` · `Developer Tools` · `Testing & QA` · `Security` · `Mobile` · `ERP / CRM` · `Project Management` · `Soft Skills` · `Other`

---

## 4. Load a resume (uses Azure OpenAI)

```powershell
python ingest.py input\NALAMALAPU_VASU_REDDY_RESUME.pdf
```

Output:

```
Analyzing NALAMALAPU_VASU_REDDY_RESUME.pdf ...

Saved: Vasu Reddy Nalamalapu (employee id 7)
  corrected skill: Scikit-learn -> scikit-learn
  Skill                       Domain                     Level
  ---------------------------------------------------------------------------
  LLMs                        AI / ML                    L4 - Advanced
  Python                      Programming Languages      L4 - Advanced
  LangChain                   AI / ML                    L3 - Practitioner
  RAG                         AI / ML                    L3 - Practitioner
  SQL                         Programming Languages      L3 - Practitioner
  Azure                       Cloud & DevOps             L2 - Intermediate
  Embeddings                  AI / ML                    L2 - Intermediate
  Folium                      Data Science & Analytics   L2 - Intermediate
  LangGraph                   AI / ML                    L2 - Intermediate
  MySQL                       Databases                  L2 - Intermediate
  PostgreSQL                  Databases                  L2 - Intermediate
  ReAct agents                AI / ML                    L2 - Intermediate
  SciPy                       Data Science & Analytics   L2 - Intermediate
  Tableau                     Data Science & Analytics   L2 - Intermediate
  ...
  GitHub                      Developer Tools            L1 - Awareness
  MongoDB                     Databases                  L1 - Awareness
  NumPy                       Data Science & Analytics   L1 - Awareness
  Pandas                      Data Science & Analytics   L1 - Awareness
  scikit-learn                AI / ML                    L1 - Awareness
  ...
```

How to read this against the resume:

| Skill | Where it appears in the resume | Level |
|---|---|---|
| Python | Brillio internship + Agentic SQL Query Executor + Multi-Document RAG Agent + NYC Taxi | L4 |
| LangChain, RAG, SQL | two projects / roles each | L3 |
| Tableau, Folium, SciPy | only the NYC Taxi project | L2 |
| Pandas, NumPy, Matplotlib, MongoDB, GitHub | only the *Skills* section | L1 |

Other ways to run it:

```powershell
python ingest.py input              # every resume in a folder
python ingest.py input --json       # JSON output (for a UI / API)
```

- Supported files: `.pdf`, `.docx`, `.txt`, `.md`
- Re-running on the same person **updates** them – no duplicate employees or skills.
- Every item in the *Skills* section is still stored, even at L1, so it remains searchable.

---

## 5. Search and match (no AI)

### 5.1 List employees

```powershell
python matcher.py employees
```

```
    1. Arjun Mehta                 Full Stack Developer            10 skills
    2. Priya Sharma                Senior Data Engineer            13 skills
    8. Shaik Irfan Shareef         Trainee                         26 skills
    7. Vasu Reddy Nalamalapu       Data Science Intern             36 skills
```

### 5.2 Employee profile (skills grouped by domain)

```powershell
python matcher.py profile --name vasu
```

```
Vasu Reddy Nalamalapu | Data Science Intern | <email>
Experience: 0.5 years
Summary: Data Science Intern with hands-on experience in AI-driven automation, RAG agents,
and data analytics. ...

  AI / ML
     LLMs                          L4 - Advanced         Used in designing RAG agents and SQL query executor.
     LangChain                     L3 - Practitioner     Used in building SQL query executor and multi-document RAG agent.
     RAG                           L3 - Practitioner     Used in designing policy validation systems and multi-document agents.
     Embeddings                    L2 - Intermediate     Applied in multi-document RAG agent for vector indexing.
     ReAct agents                  L2 - Intermediate     Implemented in SQL query executor project.
     Machine Learning              L1 - Awareness        skills list only
     scikit-learn                  L1 - Awareness        skills list only
     ...
```

Partial, case-insensitive names work (`vasu`, `Reddy`).

### 5.3 Search by skills — typos are fixed automatically

```powershell
python matcher.py search --skills "Pyhton, Langchian, rag" --min-level 3
```

```
  (interpreted 'Pyhton' as 'Python')
  (interpreted 'Langchian' as 'LangChain')
  (interpreted 'rag' as 'RAG')

Skills: LangChain, Python, RAG | minimum level L3

1. Vasu Reddy Nalamalapu - Data Science Intern
     Python                        L4 - Advanced         Programming Languages
     RAG                           L3 - Practitioner     AI / ML
     LangChain                     L3 - Practitioner     AI / ML

2. Shaik Irfan Shareef - Trainee
     Python                        L4 - Advanced         Programming Languages
     LangChain                     L3 - Practitioner     AI / ML

3. Priya Sharma - Senior Data Engineer
     Python                        L4 - Advanced         Programming Languages
```

Ranking: most matched skills → highest total level → name.

### 5.4 Match a project requirement

Project file `sample_project_genai.json` (`skill: minimum level`):

```json
{
  "project": "GenAI Policy Assistant (RAG)",
  "required_skills": { "Python": 3, "LangChain": 3, "RAG": 3, "LLMs": 3, "SQL": 2, "Azure": 2 }
}
```

```powershell
python matcher.py project --file sample_project_genai.json
```

```
Project: GenAI Policy Assistant (RAG)
Requires: Python >= L3, LangChain >= L3, RAG >= L3, LLMs >= L3, SQL >= L2, Azure >= L2

1. Vasu Reddy Nalamalapu - Data Science Intern | coverage 100% | score 19
     [met]     Python                      L4 - Advanced (needs L3)
     [met]     SQL                         L3 - Practitioner (needs L2)
     [met]     LLMs                        L4 - Advanced (needs L3)
     [met]     RAG                         L3 - Practitioner (needs L3)
     [met]     LangChain                   L3 - Practitioner (needs L3)
     [met]     Azure                       L2 - Intermediate (needs L2)

2. Shaik Irfan Shareef - Trainee | coverage 67% | score 12
     ...
     [below]   RAG                         L2 - Intermediate (needs L3)
     [missing] Azure

3. Priya Sharma - Senior Data Engineer | coverage 33% | score 6
     ...
4. Arjun Mehta - Full Stack Developer | coverage 0% | score 0
     [below]   Python                      L2 - Intermediate (needs L3)
     ...
```

- **coverage** = % of required skills met at the minimum level
- **score** = sum of levels on the requirements that are met
- `[met]` meets the level · `[below]` has the skill but a lower level · `[missing]` doesn't have it
- Ranking: coverage → score → name

Quick inline version (no file needed):

```powershell
python matcher.py project --require "SQL:3, Tableau:2, SciPy:2"
```

```
1. Vasu Reddy Nalamalapu - Data Science Intern | coverage 100% | score 7
     [met]     SQL                         L3 - Practitioner (needs L3)
     [met]     SciPy                       L2 - Intermediate (needs L2)
     [met]     Tableau                     L2 - Intermediate (needs L2)

2. Priya Sharma - Senior Data Engineer | coverage 0% | score 0
     [below]   SQL                         L2 - Intermediate (needs L3)
     [missing] Tableau
     [missing] SciPy
```

### 5.5 Search by domain

```powershell
python matcher.py domain --name "data science"
```

```
1. Vasu Reddy Nalamalapu - Data Science Intern
     Statistical Analysis          L2 - Intermediate     Data Science & Analytics
     SciPy                         L2 - Intermediate     Data Science & Analytics
     Folium                        L2 - Intermediate     Data Science & Analytics
     Tableau                       L2 - Intermediate     Data Science & Analytics
     NumPy                         L1 - Awareness        Data Science & Analytics
     Pandas                        L1 - Awareness        Data Science & Analytics
     ...

2. Shaik Irfan Shareef - Trainee
     Pandas                        L1 - Awareness        Data Science & Analytics
     ...
```

Partial names work: `cloud`, `ai`, `data science`.

### 5.6 All domains and their skills

```powershell
python matcher.py domains
```

```
AI / ML
   - LangChain (2 employees)
   - LangGraph (2 employees)
   - LLMs (2 employees)
   - RAG (2 employees)
   - scikit-learn (3 employees)
   ...
Cloud & DevOps
   - AWS (2 employees)
   - Azure (1 employee)
   ...
```

### 5.7 JSON output (for a UI or API)

Add `--json` to any command:

```powershell
python matcher.py search --skills "langchain" --json
```

```json
{
  "searched": { "langchain": "LangChain" },
  "min_level": 1,
  "results": [
    { "employee_id": 8, "name": "Shaik Irfan Shareef", "...": "..." },
    {
      "employee_id": 7,
      "name": "Vasu Reddy Nalamalapu",
      "current_role": "Data Science Intern",
      "matched_skills": [
        {
          "skill": "LangChain",
          "domain": "AI / ML",
          "level": 3,
          "level_label": "Practitioner",
          "years_used": 1.0,
          "evidence": "Used in building SQL query executor and multi-document RAG agent."
        }
      ],
      "total_level": 3
    }
  ]
}
```

---

## 6. Spelling correction & unique skills

Every skill is stored **exactly once** with one name. Two layers make sure of this:

1. **AI layer (during ingest)** – the prompt tells the model to fix spelling, expand abbreviations and reuse skill names already in the database.
2. **Code layer (`skill_normalizer.py`, no AI)** – checked before every save and on every search:

| Typed / in resume                      | Stored / searched as                | Rule                               |
| -------------------------------------- | ----------------------------------- | ---------------------------------- |
| `Pyhton`, `Langchian`              | Python, LangChain                   | swapped letters                    |
| `pyton`, `Kubernets`, `Azzure`   | Python, Kubernetes, Azure           | close spelling (≥ 85% similar)    |
| `K8s`, `JS`, `Mongo`, `Golang` | Kubernetes, JavaScript, MongoDB, Go | alias list                         |
| `ReactJS`, `React.js`, `react`   | React                               | ignore case / dots / spaces / "JS" |
| `NodeJS`, `node js`                | Node.js                             | same                               |
| `Scikit-learn`                       | scikit-learn                        | reuses the existing name           |

Safety rules: short names (`C`, `C#`, `Go`, `R`) are never fuzzy-merged, and `Java` ≠ `JavaScript`.
If the same skill appears twice in one resume, it is saved once with the **higher** level.
To teach it a new alias, add it to `ALIASES` in `skill_normalizer.py`.

---

## 7. Use it from an existing UI

Every function returns plain dicts/lists (JSON-ready). No web framework is required.

```python
from ingest import ingest_resume
from matcher import (search_skills, match_project, employees_by_domain,
                     employee_profile, list_domains, list_employees)

# Upload button → load resume
result = ingest_resume(r"input\NALAMALAPU_VASU_REDDY_RESUME.pdf")
# {'employee_id': 7, 'name': 'Vasu Reddy Nalamalapu', 'skills': [...], 'corrections': [...]}

# Search box
search_skills(["Python", "LangChain"], min_level=3)

# Project staffing screen
match_project({"Python": 3, "RAG": 3, "Azure": 2}, "GenAI Policy Assistant")

# Domain filter / profile page
employees_by_domain("AI / ML")
employee_profile("Vasu")
list_domains()
list_employees()
```

Example with FastAPI (optional):

```python
from fastapi import FastAPI
from matcher import match_project

app = FastAPI()

@app.post("/match")
def match(requirements: dict[str, int]):
    return match_project(requirements)
```

A UI in another language (e.g. .NET, Node) can run the CLI with `--json` and read the output.

---

## 8. Database (`skills.db`)

```
employees                         skills                       employee_skills
─────────                         ──────                       ───────────────
id                                id                           employee_id → employees.id
name (unique)                     name (unique)                skill_id    → skills.id
email                             normalized_key (unique)      level        1–5
current_role                      domain                       level_label  Awareness … Expert
total_experience_years                                         years_used
summary                                                        evidence
resume_path
updated_at
```

Open it with any SQLite viewer (e.g. *DB Browser for SQLite* or the VS Code SQLite extension).

---

## 9. Project files

| File                                                   | What it does                                                |
| ------------------------------------------------------ | ----------------------------------------------------------- |
| `config.py`                                          | Reads`.env`; levels, domain list, DB path                 |
| `resume_parser.py`                                   | Reads text from PDF / DOCX / TXT                            |
| `extractor.py`                                       | LangChain + Azure OpenAI prompt and output schema           |
| `skill_normalizer.py`                                | Spelling fixes, aliases, duplicate prevention               |
| `db.py`                                              | SQLite tables and save logic                                |
| `ingest.py`                                          | Resume → AI → DB (CLI +`ingest_resume()`)               |
| `matcher.py`                                         | Search / project match / domain / profile (CLI + functions) |
| `sample_project.json`, `sample_project_genai.json` | Example project requirements                                |
| `samples/`                                           | Two fictional resumes for testing                           |
| `input/`                                             | Real resumes to load                                        |

---

## 10. Good to know

- **Ratings can still vary slightly between runs**, mostly on borderline items like soft skills or whether a service (e.g. *Azure AI Search*) is listed separately from its platform. The `found_in` rule keeps core ratings stable: skills that appear only in a list are always L1. To change the rules, edit `SYSTEM_PROMPT` and `apply_rubric()` in `extractor.py`.
- After changing the rubric, re-ingest all resumes (`python ingest.py input`) so everyone is rated by the same rules.
- **Scanned (image) PDFs** have no text and are rejected with a clear error.
- **Missing `.env` values** are reported by name before any AI call.
- One resume failing does not stop a folder ingest; errors are printed and the rest continue.
