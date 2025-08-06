import os
import re
from datetime import datetime
from .guard_clean_resume import fix_broken_headers
from .guard_clean_resume import remove_hallucinated_titles, patch_job_titles_with_original

MAX_MODEL_TOKENS = 8192
SAVE_LOGS = True
LOG_DIR = "prompt_logs"
DEBUG = os.getenv("DEBUG_RESUME") == "1"
os.makedirs(LOG_DIR, exist_ok=True)

REQUIRED_SECTIONS = ["SUMMARY", "SKILLS", "WORK EXPERIENCE", "CERTIFICATIONS", "EDUCATION"]

def validate_sections(text):
    present = {sec for sec in REQUIRED_SECTIONS if sec in text}
    missing = list(set(REQUIRED_SECTIONS) - present)
    if DEBUG:
        print(f"✅ Present sections: {present}")
        print(f"❌ Missing sections: {missing}")
    return {"valid": len(missing) == 0, "missing_sections": missing}

def check_personal_info_fields(text):
    fields = {
        "name": bool(re.search(r"^[A-Z][a-z]+ [A-Z][a-z]+", text)),
        "email": bool(re.search(r"\b[\w\.-]+@[\w\.-]+\.\w{2,}\b", text)),
        "phone": bool(re.search(r"(\+?\d{1,3}[-.\s])?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)),
        "linkedin": bool(re.search(r"(linkedin\.com|portfolio|github\.io)", text, re.IGNORECASE))
    }
    missing = [k for k in ["name", "email", "phone"] if not fields[k]]
    return {"valid": len(missing) == 0, "missing_fields": missing}

def remove_placeholder_bullets(text):
    return re.sub(r"- Additional relevant responsibility \d+\n?", "", text)

def enforce_min_bullets_per_job(resume_text, min_bullets=6):
    if "WORK EXPERIENCE" not in resume_text:
        return resume_text

    lines = resume_text.splitlines()
    new_lines = []
    in_experience = False
    current_job = []
    bullet_count = 0

    for i, line in enumerate(lines):
        if line.strip() == "WORK EXPERIENCE":
            in_experience = True
            new_lines.append(line)
            continue

        if in_experience:
            if re.match(r"^[A-Z][a-zA-Z]+.*–.*\d{4}", line) and not line.strip().startswith("-"):
                # New job header
                if current_job:
                    if bullet_count < min_bullets:
                        current_job += [f"- Additional relevant responsibility {j+1}" for j in range(min_bullets - bullet_count)]
                    new_lines.extend(current_job)
                    current_job = []
                current_job = [line]
                bullet_count = 0
            elif line.strip().startswith("-"):
                current_job.append(line)
                bullet_count += 1
            elif line.strip() == "" or line.strip().isupper():
                if current_job:
                    if bullet_count < min_bullets:
                        current_job += [f"- Additional relevant responsibility {j+1}" for j in range(min_bullets - bullet_count)]
                    new_lines.extend(current_job)
                    current_job = []
                in_experience = False
                new_lines.append(line)
            else:
                current_job.append(line)
        else:
            new_lines.append(line)

    # Final job block
    if current_job:
        if bullet_count < min_bullets:
            current_job += [f"- Additional relevant responsibility {j+1}" for j in range(min_bullets - bullet_count)]
        new_lines.extend(current_job)

    return "\n".join(new_lines)

def trim_text_to_fit_token_budget(base_resume, jd, style_guide, max_prompt_tokens=3500):
    return jd  # Groq handles long input; trimming no longer needed

def format_prompt(base_resume, jd, style_guide, ats_keywords=None, ats_sections=None, job_title=None):
    prompt = style_guide.strip() + "\n\n###\n\n"
    prompt += "BASE RESUME (for reference only):\n" + base_resume.strip() + "\n\n"
    prompt += "JOB DESCRIPTION (for reference only):\n" + jd.strip() + "\n\n"

    if ats_keywords or ats_sections:
        prompt += "ATS FEEDBACK:\n"
        if ats_keywords:
            prompt += "Missing keywords: " + ", ".join(ats_keywords) + "\n"
        if ats_sections:
            prompt += "Missing sections: " + ", ".join(ats_sections) + "\n"

    prompt += (
        "\n\n###\n\n"
        "Now generate the tailored resume ONLY.\n"
        "Tailor each bullet point using skills and tools from the job description.\n"
        "If the job title matches an experience, mention it once in that job.\n"
        "If not, include it naturally in the SUMMARY.\n"
        "Begin your output below. Do NOT repeat any instructions.\n\n"
        "SUMMARY\n"
    )
    return prompt

def save_prompt_and_output(prompt, output):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(LOG_DIR, f"prompt_{timestamp}.txt"), "w") as f:
        f.write("----- PROMPT -----\n" + prompt + "\n\n----- OUTPUT -----\n" + output)

def tailor_resume(*args, **kwargs):
    raise NotImplementedError("tailor_resume logic is handled externally. This file no longer runs local models.")

def patch_final_resume(tailored_text, base_resume_text):
    """
    Final patch step before saving:
    - Remove hallucinated titles (e.g., ❗Business Analyst)
    - Restore original headers (titles + companies)
    - Ensure at least 6 bullets per job
    - Fix broken headers
    - Remove placeholder bullets
    """
    cleaned = remove_hallucinated_titles(tailored_text)
    patched = patch_job_titles_with_original(cleaned, base_resume_text)
    patched = enforce_min_bullets_per_job(patched, min_bullets=6)
    patched = remove_placeholder_bullets(patched)
    final = fix_broken_headers(patched)
    return final

