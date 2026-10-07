"""Use Azure OpenAI (via LangChain) to extract the employee profile and rate skills L1-L5."""
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

import config


class SkillRating(BaseModel):
    skill: str = Field(description="Canonical, correctly spelled skill name, e.g. 'Python', 'Kubernetes', 'React'")
    domain: str = Field(description="One domain from the allowed list")
    found_in: list[str] = Field(
        description="Names of the projects / roles whose description text explicitly names this skill. "
        "Empty list if it appears only in a skills / tools list."
    )
    level: int = Field(ge=1, le=5, description="Expertise level 1-5, based strictly on evidence depth per the rubric")
    years_used: Optional[float] = Field(default=None, description="Approximate years of hands-on use, if inferable")
    evidence: str = Field(description="One short sentence naming the projects/roles that justify this level, or 'skills list only'")


class ResumeAnalysis(BaseModel):
    name: str = Field(description="Full name of the employee")
    email: Optional[str] = Field(default=None)
    current_role: Optional[str] = Field(default=None, description="Most recent job title")
    total_experience_years: Optional[float] = Field(default=None)
    summary: str = Field(description="2-3 sentence professional summary")
    skills: list[SkillRating]


SYSTEM_PROMPT = """You are an expert technical recruiter. Analyze the resume and return the employee's
profile and every technical and professional skill with an expertise level.

RATE EACH SKILL 1-5 BASED STRICTLY ON EVIDENCE DEPTH in the resume:
- 1 Awareness:    mentioned once, in passing, or listed only in a skills block.
- 2 Intermediate: used in one project or role, no depth described.
- 3 Practitioner: used across multiple roles or projects with concrete responsibilities.
- 4 Advanced:     deep, sustained use with ownership of significant work.
- 5 Expert:       recognised specialisation - architecture ownership, technical leadership,
                  mentoring, publications, or conference talks on it.

RATING RULES:
- Judge only what the resume text shows. Self-descriptions ('expert in', 'proficient', 'strong') are not evidence.
- 'found_in' = the projects / roles whose text EXPLICITLY names the skill (or, for a parent platform / concept,
  explicitly names one of its services or libraries). Never assume a tool was used because it is typical for
  that kind of work (e.g. do not credit Pandas to a data-analysis project that does not mention Pandas).
- The level must match found_in: empty -> 1; one project or role -> 2 (4+ only for deep, sustained ownership
  in a long role); 3 needs at least two. When unsure between two levels, pick the lower.
- Soft skills follow the same rules: rate them only from concrete examples, otherwise level 1.
- 'evidence' names the projects / roles behind the level, or exactly 'skills list only' when found_in is empty.

WHAT TO INCLUDE: EVERY item in the skills section (even if it ends up level 1) AND every skill visible in projects / experience:
- the parent platform as its own skill when its services are used (e.g. 'Azure' for AKS / Azure Data Factory),
- each database, tool, framework, library and practice (e.g. 'PostgreSQL', 'CI/CD'),
- the concept behind a library (e.g. 'Machine Learning' when scikit-learn is used).

SKILL NAMING RULES (very important - every skill must be stored exactly once):
- Fix spelling mistakes (e.g. 'Pyhton' -> 'Python', 'Kubernets' -> 'Kubernetes').
- Expand abbreviations to the common name ('JS' -> 'JavaScript', 'K8s' -> 'Kubernetes').
- Merge variants of the same skill ('ReactJS' and 'React' -> one 'React' entry with the higher level).
- If the skill already exists in this list, use EXACTLY that spelling: {existing_skills}
- Do not list the same skill twice.

DOMAIN: choose exactly one of: {domains}
Examples: Pandas, NumPy, SciPy, Matplotlib, Seaborn, Plotly, Tableau, Power BI, Excel -> Data Science & Analytics;
LangChain, LangGraph, LLMs, RAG, scikit-learn, PyTorch -> AI / ML; Git, GitHub, VS Code, Jupyter, Jira -> Developer Tools;
Airflow, Spark, dbt, Databricks -> Data Engineering. Use 'Other' only if nothing fits.
"""


def _build_llm() -> AzureChatOpenAI:
    missing = [
        name
        for name, value in {
            "AZURE_OPENAI_KEY": config.AZURE_OPENAI_KEY,
            "AZURE_OPENAI_ENDPOINT": config.AZURE_OPENAI_ENDPOINT,
            "AZURE_OPENAI_DEPLOYMENT": config.AZURE_OPENAI_DEPLOYMENT,
            "AZURE_OPENAI_API_VERSION": config.AZURE_OPENAI_API_VERSION,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing values in .env: {', '.join(missing)}")

    return AzureChatOpenAI(
        api_key=config.AZURE_OPENAI_KEY,
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        azure_deployment=config.AZURE_OPENAI_DEPLOYMENT,
        api_version=config.AZURE_OPENAI_API_VERSION,
        temperature=0,  # consistent ratings between runs
    )


def analyze_resume(resume_text: str, existing_skills: list[str] | None = None) -> dict:
    """Send resume text to Azure OpenAI and return a ResumeAnalysis as a plain dict."""
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", "RESUME:\n\n{resume}")]
    )
    chain = prompt | _build_llm().with_structured_output(ResumeAnalysis, method="function_calling")
    result: ResumeAnalysis = chain.invoke(
        {
            "resume": resume_text,
            "existing_skills": ", ".join(sorted(existing_skills or [])) or "(none yet)",
            "domains": ", ".join(config.DOMAINS),
        }
    )
    analysis = result.model_dump()

    for s in analysis["skills"]:
        s["level"] = apply_rubric(s["level"], s["found_in"])
    return analysis


def apply_rubric(level: int, found_in: list[str]) -> int:
    """Enforce the evidence-depth rubric on the AI's rating.

    no project/role evidence -> L1 (skills list only)
    one project/role         -> L3 is not allowed (needs multiple), becomes L2
    L4/L5 from one long role is kept (deep, sustained ownership)
    """
    sources = {f.strip().lower() for f in found_in if f.strip()}
    if not sources:
        return 1
    if len(sources) == 1 and level == 3:
        return 2
    return level
