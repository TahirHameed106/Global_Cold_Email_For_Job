"""
matcher.py — Field-agnostic CV-to-job match scoring.

Works for ANY field because it never hardcodes skill names — it just hands
your skill_bank.json and the job description to Gemini and asks for an
honest percentage + which skills genuinely overlap.
"""

import os
import json
import re
from google import genai


def _flatten_skill_bank(skill_bank):
    """Turn skill_bank.json into a compact text block for the prompt."""
    lines = []
    lines.append("Skills: " + ", ".join(s["name"] for s in skill_bank.get("skills", [])))
    for p in skill_bank.get("projects", []):
        lines.append(f"Project — {p['title']}: " + " | ".join(p["bullets"]))
    for e in skill_bank.get("experience", []):
        lines.append(f"Experience — {e['title']}: " + " | ".join(e["bullets"]))
    edu = skill_bank.get("education", {})
    if edu:
        lines.append(f"Education: {edu.get('degree','')} at {edu.get('institute','')}, "
                      f"CGPA {edu.get('cgpa','')}")
    return "\n".join(lines)


# Google has been retiring gemini-2.5-flash inconsistently ahead of its
# official shutdown date. "gemini-flash-latest" is an auto-updating alias
# Google maintains to always point at their current fast model, so this
# stays working without needing another manual fix later. A couple of
# explicit fallbacks are tried too in case the alias itself has an outage.
GEMINI_MODEL_CANDIDATES = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3.1-flash-lite"]


def _generate_with_fallback(client, prompt):
    """Try each candidate model in order; return the first one that works."""
    last_error = None
    for model_name in GEMINI_MODEL_CANDIDATES:
        try:
            return client.models.generate_content(model=model_name, contents=prompt)
        except Exception as e:
            last_error = e
            continue
    raise last_error


def score_match(job_title, job_description, skill_bank, api_key=None):
    """
    Returns:
        {
          "score": int (0-100),
          "matching_skills": [str, ...],
          "missing_skills": [str, ...],
          "reasoning": str
        }
    Falls back to a simple keyword-overlap score if the API call fails.
    """
    profile_text = _flatten_skill_bank(skill_bank)

    prompt = f"""You are scoring how well a candidate's real background matches a job posting.
Be honest and strict — do not inflate the score. Only count genuine overlap.

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description[:3000]}

CANDIDATE'S REAL BACKGROUND (skills, projects, experience — nothing outside this list is true):
{profile_text}

Return ONLY valid JSON in exactly this shape, nothing else:
{{
  "score": <integer 0-100>,
  "matching_skills": [<skills/experience from the candidate's background that genuinely match the job>],
  "missing_skills": [<skills the job wants that the candidate's background does NOT show>],
  "reasoning": "<one sentence explaining the score>"
}}"""

    try:
        client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
        response = _generate_with_fallback(client, prompt)
        text = response.text.strip()
        text = re.sub(r"^```json|```$", "", text.strip(), flags=re.MULTILINE).strip()
        result = json.loads(text)
        result["score"] = int(result.get("score", 0))
        return result

    except Exception as e:
        print(f"[matcher] AI scoring failed ({e}), using keyword fallback")
        return _keyword_fallback_score(job_description, skill_bank)


def _keyword_fallback_score(job_description, skill_bank):
    """Simple, honest fallback if the AI call fails — no external dependency."""
    jd_lower = job_description.lower()
    all_skills = [s["name"] for s in skill_bank.get("skills", [])]

    matched = [s for s in all_skills if s.lower() in jd_lower]
    missing = [s for s in all_skills if s.lower() not in jd_lower]

    score = int((len(matched) / len(all_skills)) * 100) if all_skills else 0
    return {
        "score": score,
        "matching_skills": matched,
        "missing_skills": missing,
        "reasoning": "Keyword-overlap fallback (AI scoring unavailable)."
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    with open("data/skill_bank.json") as f:
        bank = json.load(f)

    test_jd = """
    We're a 6-person startup looking for a Junior Frontend Developer intern.
    Must know React, HTML/CSS, and Git. Bonus if you've built anything with
    a REST API. Fully remote, flexible hours.
    """
    result = score_match("Junior Frontend Developer Intern", test_jd, bank)
    print(json.dumps(result, indent=2))