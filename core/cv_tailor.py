"""
cv_tailor.py — Tailors a CV for a specific job WITHOUT inventing anything.

Only runs on jobs that already scored >= match_threshold_percent (see
matcher.py). Its job is narrow and honest:
  1. Pick the best-fitting summary variant from skill_bank.json
  2. Reorder skills so JD-relevant ones appear first
  3. Reorder projects/experience so the most relevant ones appear first
  4. Lightly rephrase bullets to mirror the JD's own wording — WITHOUT
     changing what was actually done (this is what closes the gap from an
     80-90% match to a much stronger keyword/phrasing alignment — it is not
     a guarantee of literally 100%, and it will never claim skills you don't have)
  5. Render the result as a clean .docx

This keeps a hard rule: nothing in the output CV can name a skill, tool, or
achievement that isn't already present somewhere in skill_bank.json.
"""

import os
import json
import re
from google import genai
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


def _all_allowed_terms(skill_bank):
    """Every real term the candidate is allowed to be described with."""
    terms = {s["name"].lower() for s in skill_bank.get("skills", [])}
    return terms


def rewrite_bullets_with_ai(bullets, job_description, allowed_terms, api_key=None):
    """
    Ask the AI to rephrase bullets to mirror the JD's language, with an
    explicit instruction not to add any new tools/skills/claims.
    Falls back to the original bullets untouched if the API call fails.
    """
    prompt = f"""Rewrite these resume bullet points so their PHRASING mirrors
the language and keywords used in the job description below. Do NOT add any
new skill, tool, technology, number, or achievement that isn't already in the
original bullets. Only rephrase — same facts, wording closer to the JD.

JOB DESCRIPTION:
{job_description[:2000]}

ORIGINAL BULLETS:
{chr(10).join('- ' + b for b in bullets)}

Return ONLY the rewritten bullets, one per line, no numbering, no extra text."""

    try:
        client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        new_bullets = [line.strip("- ").strip() for line in response.text.strip().split("\n") if line.strip()]

        # Safety check: reject the rewrite if it introduces a term not in the
        # allowed skill list AND not present in any original bullet (crude but effective).
        original_text = " ".join(bullets).lower()
        for nb in new_bullets:
            words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+.#]{2,}", nb.lower()))
            new_terms = words - allowed_terms
            # allow common English words through; only flag if a *tech-looking* new term appears
            suspicious = [w for w in new_terms if w not in original_text and len(w) > 3]
            if len(suspicious) > 2:  # a couple of stray words is normal English, not fabrication
                print(f"[cv_tailor] Rewrite looked suspicious, keeping original bullet: {nb[:50]}...")
                return bullets  # bail out to the safe original set

        return new_bullets if len(new_bullets) == len(bullets) else bullets

    except Exception as e:
        print(f"[cv_tailor] Bullet rewrite failed ({e}), keeping original wording")
        return bullets


def pick_summary_variant(skill_bank, matching_skills):
    """Pick whichever summary variant best matches the job's matched skills."""
    variants = skill_bank.get("summary_variants", {})
    matched_lower = " ".join(matching_skills).lower()

    if any(term in matched_lower for term in ["testing", "qa", "quality assurance", "postman", "unit test", "sqa"]):
        return variants.get("qa", variants.get("general", ""))
    if any(term in matched_lower for term in ["react", "css", "html", "frontend", "ui", "next.js"]):
        return variants.get("frontend", variants.get("general", ""))
    if any(term in matched_lower for term in ["node", "sql", "api", "backend", "server", "c#", ".net"]):
        return variants.get("backend", variants.get("general", ""))
    return variants.get("general", "")


def build_tailored_cv_data(job_title, job_description, skill_bank, match_result, api_key=None):
    """
    Returns a plain dict describing the tailored CV content — reordered and
    reworded, but every fact traceable back to skill_bank.json.
    """
    allowed_terms = _all_allowed_terms(skill_bank)
    matching_skills = match_result.get("matching_skills", [])

    # Reorder skills: matched-relevant ones first, rest after
    all_skills = [s["name"] for s in skill_bank.get("skills", [])]
    matched_set = {m.lower() for m in matching_skills}
    ordered_skills = (
        [s for s in all_skills if s.lower() in matched_set] +
        [s for s in all_skills if s.lower() not in matched_set]
    )

    # Reorder + rewrite projects: relevance = word-level overlap between matched
    # skills and the project's tags/bullets — exact-phrase matching was too
    # strict (e.g. "Unit Testing (NUnit / xUnit basics)" as a skill name rarely
    # appears verbatim in a bullet even when the underlying content matches).
    import re as _re

    def _significant_words(text):
        words = _re.findall(r"[a-zA-Z][a-zA-Z0-9#+.]{2,}", text.lower())
        stopwords = {"the", "and", "for", "with", "using", "via", "basics"}
        return {w for w in words if w not in stopwords}

    matching_words = set()
    for skill in matching_skills:
        matching_words |= _significant_words(skill)

    def relevance(item):
        text = " ".join(item.get("tags", [])) + " " + " ".join(item.get("bullets", []))
        item_words = _significant_words(text)
        return len(matching_words & item_words)

    projects = sorted(skill_bank.get("projects", []), key=relevance, reverse=True)
    experience = sorted(skill_bank.get("experience", []), key=relevance, reverse=True)

    for p in projects:
        p = dict(p)
        p["bullets"] = rewrite_bullets_with_ai(p["bullets"], job_description, allowed_terms, api_key)
    for e in experience:
        e = dict(e)
        e["bullets"] = rewrite_bullets_with_ai(e["bullets"], job_description, allowed_terms, api_key)

    return {
        "summary": pick_summary_variant(skill_bank, matching_skills),
        "skills": ordered_skills,
        "projects": projects,
        "experience": experience,
        "education": skill_bank.get("education", {}),
        "certifications": skill_bank.get("certifications", []),
        "job_title": job_title,
    }


def render_cv_docx(candidate, tailored_data, output_path):
    """Render the tailored CV data into a clean, simple .docx file."""
    doc = Document()

    name_p = doc.add_paragraph()
    name_run = name_p.add_run(candidate.get("name", "Your Name"))
    name_run.font.size = Pt(20)
    name_run.font.bold = True
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    contact_bits = [candidate.get("email", ""), candidate.get("phone", ""), candidate.get("location", "")]
    links = candidate.get("links", {})
    contact_bits += [v for v in links.values() if v]
    contact_p = doc.add_paragraph(" | ".join(b for b in contact_bits if b))
    contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    doc.add_heading("Summary", level=2)
    doc.add_paragraph(tailored_data["summary"])

    doc.add_heading("Skills", level=2)
    doc.add_paragraph(", ".join(tailored_data["skills"]))

    if tailored_data["projects"]:
        doc.add_heading("Projects", level=2)
        for p in tailored_data["projects"]:
            title_p = doc.add_paragraph()
            title_p.add_run(p["title"]).bold = True
            for bullet in p["bullets"]:
                doc.add_paragraph(bullet, style="List Bullet")

    if tailored_data["experience"]:
        doc.add_heading("Experience", level=2)
        for e in tailored_data["experience"]:
            title_p = doc.add_paragraph()
            title_p.add_run(e["title"]).bold = True
            for bullet in e["bullets"]:
                doc.add_paragraph(bullet, style="List Bullet")

    edu = tailored_data.get("education", {})
    if edu:
        doc.add_heading("Education", level=2)
        doc.add_paragraph(f"{edu.get('degree','')} — {edu.get('institute','')}")
        doc.add_paragraph(f"Graduating {edu.get('graduation_year','')} | CGPA {edu.get('cgpa','')}")

    certifications = tailored_data.get("certifications", [])
    if certifications:
        doc.add_heading("Certifications", level=2)
        for cert in certifications:
            doc.add_paragraph(cert, style="List Bullet")

    doc.save(output_path)
    print(f"[cv_tailor] Tailored CV saved -> {output_path}")
    return output_path


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    with open("data/skill_bank.json") as f:
        bank = json.load(f)

    candidate = {"name": "Test Candidate", "email": "test@example.com", "location": "Remote"}
    fake_match = {"matching_skills": ["React", "HTML / CSS", "Git / GitHub"], "score": 85}

    jd = "Looking for a Junior Frontend Developer intern who knows React and CSS. Remote, 6-person team."
    tailored = build_tailored_cv_data("Junior Frontend Developer Intern", jd, bank, fake_match)
    render_cv_docx(candidate, tailored, "test_tailored_cv.docx")
