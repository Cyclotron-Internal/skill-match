"""Keep every skill uniquely named: fix spelling variants and map aliases to one canonical name.

No AI here - plain Python, so it also works for search input in matcher.py.
"""
import difflib
import re

# Common short forms / alternate spellings -> canonical name.
# Keys are already in normalize_key() form.
ALIASES = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "py": "Python",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "reactjs": "React",
    "react": "React",
    "nodejs": "Node.js",
    "node": "Node.js",
    "vuejs": "Vue.js",
    "angularjs": "Angular",
    "nextjs": "Next.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mssql": "SQL Server",
    "sqlserver": "SQL Server",
    "mongo": "MongoDB",
    "aws": "AWS",
    "amazonwebservices": "AWS",
    "gcp": "Google Cloud",
    "googlecloudplatform": "Google Cloud",
    "azure": "Azure",
    "microsoftazure": "Azure",
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "nlp": "NLP",
    "genai": "Generative AI",
    "llm": "LLMs",
    "llms": "LLMs",
    "cicd": "CI/CD",
    "dotnet": ".NET",
    "net": ".NET",
    "aspnet": "ASP.NET",
    "csharp": "C#",
    "cpp": "C++",
    "golang": "Go",
    "powerbi": "Power BI",
    "tf": "Terraform",
}

FUZZY_CUTOFF = 0.85  # how similar two names must be to count as the same skill
MIN_FUZZY_LENGTH = 4  # never fuzzy-match short names like C, R, Go, C#


def normalize_key(name: str) -> str:
    """'Node.js' / 'NodeJS' / 'node js' -> 'nodejs'. Keeps + and # so C, C++ and C# stay different."""
    key = name.strip().lower()
    key = key.replace("c++", "cpp").replace("c#", "csharp").replace(".net", "dotnet")
    return re.sub(r"[^a-z0-9]", "", key)


def _is_letter_swap(a: str, b: str) -> bool:
    """True if `a` is `b` with two neighbouring letters swapped ('pyhton' vs 'python')."""
    if len(a) != len(b) or a == b:
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]


def resolve_skill(name: str, known_skills: list[str]) -> str:
    """Return the canonical name for `name`.

    Order: exact match with a known skill -> alias -> fuzzy match (typos) -> cleaned input.
    `known_skills` is the list of skill names already stored in the DB.
    """
    cleaned = " ".join(name.split())
    key = normalize_key(cleaned)
    if not key:
        return cleaned

    known_by_key = {normalize_key(s): s for s in known_skills}

    if key in known_by_key:
        return known_by_key[key]

    if key in ALIASES:
        return known_by_key.get(normalize_key(ALIASES[key]), ALIASES[key])

    if len(key) >= MIN_FUZZY_LENGTH:
        candidates = [k for k in known_by_key if len(k) >= MIN_FUZZY_LENGTH]
        candidates += [k for k in ALIASES if len(k) >= MIN_FUZZY_LENGTH]
        swaps = [c for c in candidates if _is_letter_swap(key, c)]
        match = swaps or difflib.get_close_matches(key, candidates, n=1, cutoff=FUZZY_CUTOFF)
        if match:
            hit = match[0]
            if hit in known_by_key:
                return known_by_key[hit]
            return known_by_key.get(normalize_key(ALIASES[hit]), ALIASES[hit])

    return cleaned
