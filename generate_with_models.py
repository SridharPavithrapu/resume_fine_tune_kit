import os
from docx import Document
from models import call_summary_model, call_bullet_model
from extract_job_keywords import extract_job_info
from docx.shared import Pt
import re
import json
import time
import requests
from resume_tailoring.guard_clean_resume import fix_broken_headers
from resume_tailoring.guard_clean_resume import remove_hallucinated_titles  # 🔼 Import this once at the top
from resume_tailoring.guard_clean_resume import remove_placeholder_bullets


SOFT_SKILLS = [
    "communication", "teamwork", "problem-solving", "adaptability",
    "critical thinking", "time management", "leadership", "attention to detail"
]

DEFAULT_HEADER = "Yoshitha Mudulodu    Email: yoshitha4589@gmail.com    Mobile: +1(669)-399-4052\nMilpitas, CA 95035"
DEFAULT_CERTIFICATIONS = "- Google Data Analytics (Coursera)\n- Excel for Business (Coursera)"
DEFAULT_EDUCATION = "Master of Science in Computer Science, University of Bridgeport, Connecticut  August 2021 – May 2023\nBachelor of Technology in Computer Science & Engineering, KMIT, India  August 2015 – May 2019"

def remove_jobscan_artifacts(text: str) -> str:
    artifacts = [
        "education match", "updating scan information", "HIGH SCORE IMPACT",
        "maintaining job title match", "updating required education level",
        "ensuring education match", "ensuring HIPAA compliance"
    ]
    for phrase in artifacts:
        text = text.replace(phrase, "")
    return text

def load_docx_text(path):
    doc = Document(path)
    return "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])

def is_job_header(line):
    """
    Stricter logic to detect job headers.
    Ensures:
    - Does NOT start with a bullet character
    - Contains an en-dash or hyphen between title and company
    - Contains a year (e.g. 2021, 2023) as a proxy for job dates
    """
    return bool(
        line and
        not line.startswith(("-", "•", "●")) and
        "–" in line and
        re.search(r"\b\d{4}\b", line)
    )

def parse_work_experience_jobs(section_text):
    jobs = []
    lines = section_text.strip().splitlines()

    current_job = {"header": "", "bullets": []}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_job_header(line):
            # Save previous job if complete
            if current_job["header"] and current_job["bullets"]:
                jobs.append(current_job)
            current_job = {"header": line, "bullets": []}
        elif line.startswith(("-", "•", "●")):
            if current_job["header"]:
                current_job["bullets"].append(line)
        elif current_job["header"]:
            # Treat as bullet continuation
            cleaned = re.sub(r"^[-•➔→📌👉➡️🡆➤➥➧➨⮞🔹➢]+\s*", "", line)
            current_job["bullets"].append(f"- {cleaned}")
        else:
            continue  # orphaned line, no active header

    # Append last job if valid
    if current_job["header"] and current_job["bullets"]:
        jobs.append(current_job)

    return jobs

def patch_with_original_experience_headers(tailored_text, base_text):
    """
    Overwrites job headers in tailored resume with those from base resume.
    Uses job count alignment to preserve company names.
    """
    # Extract original headers from base
    pattern = r"^(.*?–.*?)\s+\d{4}"
    base_headers = [
        line.strip() for line in base_text.splitlines()
        if re.search(pattern, line.strip())
    ]

    # Extract job blocks from tailored
    lines = tailored_text.splitlines()
    new_lines = []
    job_idx = 0

    for i, line in enumerate(lines):
        if re.search(pattern, line.strip()):
            if job_idx < len(base_headers):
                new_lines.append(base_headers[job_idx])
                job_idx += 1
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return "\n".join(new_lines)


def parse_sections(text):
    SECTIONS = ["SUMMARY", "SKILLS", "WORK EXPERIENCE", "CERTIFICATIONS", "EDUCATION"]
    sections = {}
    current_section = None
    for line in text.splitlines():
        header_candidate = line.strip().upper().replace("\t", "")
        if header_candidate in SECTIONS:
            current_section = header_candidate
            sections[current_section] = []
        elif current_section:
            sections[current_section].append(line.strip())
    return {k: "\n".join(v) for k, v in sections.items()}

def clean_summary(text):
    text = re.sub(r"(?i)^here is a rewritten summary.*?:\s*", "", text).strip()
    text = text.replace("HIGH SCORE IMPACT", "").replace("Education Match", "")
    return text

def enforce_default_sections(parsed, injected_keywords):
    if "EDUCATION" not in parsed or not parsed["EDUCATION"].strip():
        parsed["EDUCATION"] = DEFAULT_EDUCATION
    if "CERTIFICATIONS" not in parsed or not parsed["CERTIFICATIONS"].strip():
        parsed["CERTIFICATIONS"] = DEFAULT_CERTIFICATIONS
    if "SUMMARY" in parsed:
        parsed["SUMMARY"] = clean_summary(parsed["SUMMARY"])
    return parsed

def fix_and_format_output(full_text):
    return fix_broken_headers(full_text)

def call_groq(prompt):
    headers = {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}
    payload = {
        "model": os.getenv("GROQ_MODEL", "llama3-70b-8192"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
    return response.json()["choices"][0]["message"]["content"].strip()

def tailor_resume_with_models(job_title, job_description, base_resume_path="YoshithaM_Resume_W2.docx", ats_keywords=[], ats_sections=[]):
    base_text = load_docx_text(base_resume_path)
    sections = parse_sections(base_text)

    print(f"📦 Extracted sections: {list(sections.keys())}")
    job_info = extract_job_info(f"Job Title: {job_title}\n\n{job_description}")
    print("🔎 Parsed Job Info →", job_info)

    # ✅ Construct keyword list without repetition
    seen = set()
    ats_cleaned = [kw.strip() for kw in ats_keywords if kw.strip()]
    all_keywords = []

    for kw in ats_cleaned:
        if kw.lower() not in seen:
            all_keywords.append(kw)
            seen.add(kw.lower())

    for source_kw in job_info["skills"] + job_info["verbs"]:
        kw = source_kw.strip()
        if kw and kw.lower() not in seen:
            all_keywords.append(kw)
            seen.add(kw.lower())

    for skill in SOFT_SKILLS:
        if skill.lower() in job_description.lower() and skill.lower() not in seen:
            all_keywords.append(skill)
            seen.add(skill.lower())

    print(f"🔑 Total keywords injected: {len(all_keywords)}")
    print(f"Top summary keywords: {', '.join(all_keywords[:8])}")

    # ✅ Build keyword groupings for better injection guidance
    keywords_for_summary = {
        "Technical Skills": ", ".join(all_keywords[:5]),
        "Soft Skills": ", ".join(all_keywords[5:10]),
        "Domain Terms": ", ".join(all_keywords[10:15])
    }

    original_summary = sections.get("SUMMARY", "")

    # ✅ Cleaner, context-aware summary prompt
    summary_prompt = (
        f"Rewrite the following resume summary to align with the role of a {job_title}. "
        "Use only relevant terms from the grouped keywords below:\n"
        + "\n".join([f"- {k}: {v}" for k, v in keywords_for_summary.items()]) + "\n\n"
        "Make it a strong, concise 4–5 line paragraph. Avoid writing notes or explanations. Do not include quantification or bullet-style metrics.\n\n"
        f"Original Summary:\n{original_summary}\n\nRewritten Summary:"
    )

    prompt_leak_pattern = re.compile(
        r"^(You are|Rewrite|Original Summary|Rewritten Summary|Here is|Responsibilities|Highlight experience|[-•·])",
        re.IGNORECASE
    )

    print("🧠 Calling summary model...")
    raw_summary = call_groq(summary_prompt).strip()
    print("✅ Summary model returned.")

    # ✅ Remove any prompt leakage
    if "Rewritten Summary:" in raw_summary:
        raw_summary = raw_summary.split("Rewritten Summary:", 1)[-1].strip()

    rewritten_summary = " ".join([
        line.strip() for line in raw_summary.splitlines()
        if line.strip() and not prompt_leak_pattern.match(line.strip())
    ])

    # ✅ Fallback if summary comes back empty
    if not rewritten_summary:
        rewritten_summary = f"Experienced {job_title} skilled in {', '.join(all_keywords[:5])}. Known for delivering measurable results through data analysis and business insights."

    # ✅ Fix EDUCATION before section rebuild
    edu_text = sections.get("EDUCATION", "")
    if not edu_text.strip() or "bachelor of technology" not in edu_text.lower():
        print("⚠️ Suspect or missing EDUCATION — injecting fallback.")
        sections["EDUCATION"] = DEFAULT_EDUCATION

    rebuilt = [DEFAULT_HEADER, "", "SUMMARY", "", rewritten_summary]

    # === Rewrite All Sections ===
    ordered_sections = ["SKILLS", "WORK EXPERIENCE", "CERTIFICATIONS", "EDUCATION"]
    for sec in ordered_sections:
        rebuilt.append("")
        rebuilt.append(sec)
        rebuilt.append("")

        section_present = sec in sections and sections[sec].strip()

        if sec == "WORK EXPERIENCE":
            if section_present:
                print("📋 Original WORK EXPERIENCE preview:\n", sections[sec][:1000])
                parsed_jobs = parse_work_experience_jobs(sections[sec])
                print("🧪 Parsed jobs:\n", json.dumps(parsed_jobs, indent=2))

                if len(parsed_jobs) < 3:
                    print("⚠️ Incomplete job extraction. Retrying with base resume WORK EXPERIENCE...")
                    base_sections = parse_sections(base_text)
                    base_exp_block = base_sections.get("WORK EXPERIENCE", "")
                    parsed_jobs = parse_work_experience_jobs(base_exp_block)
                    print("🧪 Parsed jobs (fallback):\n", json.dumps(parsed_jobs, indent=2))

                    if len(parsed_jobs) == 0:
                        print("❌ Failed to parse any jobs even from base resume. Skipping rewrite for WORK EXPERIENCE.")
                        rebuilt.append(sections[sec])
                        continue

                # Identify visualization tools from keywords
                viz_tools = ["Power BI", "Tableau", "Looker", "Qlik", "Excel", "Spotfire"]
                required_visual_tools = [
                    tool for tool in viz_tools
                    if any(tool.lower() in kw.lower() for kw in all_keywords)
                ]
                print(f"🧠 Required visualization tools found in JD: {required_visual_tools}")

                # Combine job blocks
                combined_jobs_text = "\n\n".join(
                    f"{job['header']}\n" + "\n".join(job["bullets"]) for job in parsed_jobs
                )

                # Build keyword grouping
                keyword_groups = {
                    "ATS Keywords": ", ".join(all_keywords[:6]),
                    "Action Verbs & Skills": ", ".join(all_keywords[6:12]),
                    "Other Job Terms": ", ".join(all_keywords[12:18]),
                }

                # Build prompt
                job_prompt = f"""
        You are a resume optimization expert. Rewrite the following WORK EXPERIENCE section for the role of **{job_title}**, tailored for Applicant Tracking Systems (ATS).

        💡 Guidelines:
        - Do **not** change job headers (titles, companies, dates).
        - For **each job**, write **5–6 bullet points** that:
          • Start with "-"
          • Include at least one **quantified achievement**
          • Use keywords **only if contextually appropriate** from the grouped lists below
          • Naturally incorporate the visualization tools across jobs (if multiple), such as: {', '.join(required_visual_tools) or "None"}
        - Avoid repetition across bullets or jobs.
        - Maintain professional tone, measurable impact, and concise language.

        📌 Keyword Groups (use if relevant):
        """ + "\n".join([f"- {label}: {keywords}" for label, keywords in keyword_groups.items()]) + f"""

        🔧 Original WORK EXPERIENCE:
        {combined_jobs_text}
        """
                print("🔍 Prompt length:", len(job_prompt))
                rewritten_block = call_bullet_model(job_prompt, max_tokens=3200).strip()

                # Retry once if blank
                if not rewritten_block:
                    print("⚠️ Retry: First bullet model response was empty. Trying once more.")
                    rewritten_block = call_bullet_model(job_prompt, max_tokens=3200).strip()

                print(f"📏 Rewritten block length: {len(rewritten_block)}")
                print("📋 Rewritten block preview:\n", rewritten_block[:300])
                rewritten_block = remove_jobscan_artifacts(rewritten_block)

                if not rewritten_block:
                    print("❌ Bullet model returned empty. Reverting to original.")
                    rebuilt.append(sections[sec])
                    continue

                with open("prompt_logs/raw_rewritten_work_experience.txt", "w") as f:
                    f.write(rewritten_block)

                print("🔁 Rewriting entire WORK EXPERIENCE section in one pass.")

                # Step 1: split rewritten output
                job_blocks = re.split(r"(?:\n\s*){2,}", rewritten_block.strip())
                job_headers = [job["header"].strip() for job in parsed_jobs]

                # Step 2: parse bullet blocks from each job
                # Parse bullets from model response
                all_bullet_blocks = []
                for block in job_blocks:
                    bullets = [line.strip() for line in block.strip().splitlines() if line.strip().startswith("-")]
                    all_bullet_blocks.append(bullets)

                # Fix length mismatch (if model skips a job)
                while len(all_bullet_blocks) < len(parsed_jobs):
                    all_bullet_blocks.append(parsed_jobs[len(all_bullet_blocks)]["bullets"])

                # Final WORK EXPERIENCE rebuild
                for i, job in enumerate(parsed_jobs):
                    header = job["header"].strip()
                    bullets = all_bullet_blocks[i] if i < len(all_bullet_blocks) else job["bullets"]

                    if not header or not re.search(r"\b\d{4}\b", header):
                        print(f"⚠️ Skipping invalid header: {header}")
                        continue

                    rebuilt.append(header)
                    rebuilt.extend(bullets[:6])
                    rebuilt.append("")  # spacer

            else:
                rebuilt.append("- [Experience not provided]")

        elif sec == "CERTIFICATIONS":
            rebuilt.append(DEFAULT_CERTIFICATIONS)

        elif sec == "EDUCATION":
            rebuilt.append(DEFAULT_EDUCATION)

        else:
            rebuilt.append(sections.get(sec, "- [Section not available]"))

    with open("prompt_logs/latest_resume.txt", "w") as f:
        f.write("\n".join(rebuilt))

    # After rebuilding all jobs
    rebuilt = remove_hallucinated_titles("\n".join(rebuilt)).splitlines()
    final_text_raw = "\n".join(rebuilt)
    #final_text_raw = patch_with_original_experience_headers(final_text_raw, base_text)
    final_text = fix_broken_headers(final_text_raw)
    final_text = remove_placeholder_bullets(final_text)

    # ⬇️ Inject EDUCATION fallback if needed
    def has_both_degrees(text):
        master_found = re.search(r"(Master|M\.S\.|MSc|M\.Sc)", text, re.IGNORECASE)
        bachelor_found = re.search(r"(Bachelor|B\.Tech|BSc|B\.Sc)", text, re.IGNORECASE)
        return master_found and bachelor_found

    if "EDUCATION" not in final_text or not has_both_degrees(final_text):
        print("\ud83d\udcda Incomplete or missing EDUCATION section — injecting default.")
        final_text = re.sub(r"(?s)EDUCATION\n.*?(?=\n[A-Z ]{3,}|$)", "", final_text)
        final_text += "\n\nEDUCATION\n" + DEFAULT_EDUCATION

    return final_text


def save_to_docx(text, path):
    from docx import Document
    from docx.shared import Pt
    import re

    doc = Document()
    VALID_HEADERS = ["SUMMARY", "SKILLS", "WORK EXPERIENCE", "CERTIFICATIONS", "EDUCATION"]

    for line in text.splitlines():
        clean = line.strip().replace("•", "-").replace("·", "-")
        clean = clean.encode("utf-8", "ignore").decode("utf-8")
        clean = clean.replace("\n", " ").strip()

        upper_clean = re.sub(r"[^A-Z]", "", clean.upper())
        matched = next((h for h in VALID_HEADERS if upper_clean == h.replace(" ", "")), None)

        if matched:
            para = doc.add_paragraph()
            run = para.add_run(matched)
            run.bold = True
            para.paragraph_format.space_after = Pt(8)
            continue # ✅ ensures we do not fall through and re-add the broken version
        elif clean:
            para = doc.add_paragraph(clean)
            para.paragraph_format.space_after = Pt(6)
        else:
            doc.add_paragraph("")

    doc.save(path)
