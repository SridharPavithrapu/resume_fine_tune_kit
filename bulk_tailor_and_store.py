import os
import sys
import json
import pandas as pd
from docx import Document
from generate_with_models import tailor_resume_with_models, save_to_docx, parse_sections, remove_hallucinated_titles
from resume_tailoring.guard_clean_resume import clean_full_resume, fix_broken_headers
from resume_tailoring.utils import extract_job_title
from jobscan.jobscan_driver_debug import get_jobscan_score_and_feedback
from resume_tailoring.inference import format_prompt, validate_sections
from resume_tailoring.guard_clean_resume import patch_job_titles_with_original
from resume_tailoring.inference import patch_final_resume
import time

DEBUG = True

os.environ["MallocStackLogging"] = "0"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
sys.stderr = open(os.devnull, 'w')

jd_file_path = "data/jobspy_jobs.csv"
jd_df = pd.read_csv(jd_file_path) if os.path.exists(jd_file_path) else pd.DataFrame()

def load_docx_text(path):
    doc = Document(path)
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())

base_resume = load_docx_text("data/YoshithaM_Resume_W2.docx")

with open("prompts/style_resume.txt", "r") as f:
    style_guide = f.read()

os.makedirs("outputs/final_tailored_resumes", exist_ok=True)
os.makedirs("prompt_logs", exist_ok=True)
summary_data = []

print(f"✅ Loaded {len(jd_df)} job listings from {jd_file_path}")

for i, row in jd_df.iterrows():
    print(f"\n📄 [{i+1}/{len(jd_df)}] Processing job: {row.get('title', '')}")
    try:
        title = row["title"]
        jd_text = row["description"]
        job_title = extract_job_title(jd_text, csv_title=title)
        safe_title = title.replace(" ", "_").replace("/", "_")[:50]

        print(f"\n📄 Processing: {title}")
        print(f"📋 Extracted job title: {job_title}")

        best_score = 0
        best_resume = ""
        best_keywords, best_sections = [], []

        for attempt in range(3):
            print(f"\n⏳ Attempt {attempt + 1}")
            try:
                tailored = tailor_resume_with_models(
                    job_title,
                    jd_text,
                    base_resume_path="data/YoshithaM_Resume_W2.docx",
                    ats_keywords=best_keywords,
                    ats_sections=best_sections
                )
            except Exception as e:
                print(f"❌ Tailoring failed: {e}")
                continue

            print(f"✅ Tailor complete. Resume length: {len(tailored)} chars")
            if DEBUG:
                print(f"🧪 Tailored resume preview (first 500 chars):\n{tailored[:500]}")

            cleaned = patch_final_resume(tailored, base_resume)

            if DEBUG:
                print(f"🧪 Cleaned resume preview (first 500 chars):\n{cleaned[:500]}")

            if "SUMMARY" not in cleaned:
                print("🔧 Injecting fallback SUMMARY...")
                fallback_summary = "SUMMARY\n- Business Analyst with 5+ years of experience in SQL, ETL, Agile, and BI tools, delivering insights and driving project success.\n\n"
                cleaned = fallback_summary + cleaned

            if len(cleaned) > 20000:
                print(f"⚠️ Resume too long ({len(cleaned)} chars), trimming to 20000 chars.")
                cleaned = cleaned[:20000]

            section_check = validate_sections(cleaned)
            if not section_check["valid"]:
                print(f"❗ Missing Sections: {section_check['missing_sections']}")
                if "CERTIFICATIONS" in section_check['missing_sections']:
                    cleaned += "\nCERTIFICATIONS\n- [Insert Certification Name]"
                if "EDUCATION" in section_check['missing_sections']:
                    cleaned += "\nEDUCATION\n- [Insert Degree, University Name]"

            parsed = parse_sections(cleaned)
            print(f"📦 Sections found in tailored resume: {list(parsed.keys())}")

            if "SUMMARY" in parsed and parsed["SUMMARY"].lower().startswith("here is"):
                parsed["SUMMARY"] = parsed["SUMMARY"].split(":", 1)[-1].strip()
                cleaned = cleaned.replace(parsed["SUMMARY"], parsed["SUMMARY"].strip())

            print("📸 Attempting OCR scan via Jobscan...")
            score, best_keywords, best_sections = get_jobscan_score_and_feedback(cleaned, jd_text)
            print(f"📊 OCR Score Extracted: {score}")
            print(f"🔍 Missing Keywords: {best_keywords}")
            print(f"🔧 Missing Sections: {best_sections}")

            try:
                score_str = str(score).strip().replace('%', '')
                score_val = int(score_str)
            except Exception as e:
                print(f"⚠️ Could not parse score: {e}")
                score_val = 0

            print(f"▶️ ATS score after attempt {attempt + 1}: {score_val}")
            if score_val > best_score:
                best_score = score_val
                best_resume = cleaned

            try:
                with open(f"prompt_logs/{safe_title}_attempt{attempt + 1}.txt", "w", encoding="utf-8") as logf:
                    logf.write(cleaned.encode("utf-8", "ignore").decode("utf-8"))

                with open(f"prompt_logs/{safe_title}_attempt{attempt + 1}.log", "w", encoding="utf-8") as meta:
                    meta.write(f"Job Title: {job_title}\n")
                    meta.write(f"Attempt: {attempt + 1}\n")
                    meta.write(f"ATS Score: {score}\n")
                    meta.write(f"Missing Keywords: {best_keywords}\n")
                    meta.write(f"Missing Sections: {best_sections}\n\n")
            except Exception as e:
                print(f"⚠️ Failed to write log files: {e}")

            if score_val >= 80:
                print("🎯 Target met. Stopping early.")
                break
            elif score_val < 40 and attempt < 2:
                print("🔁 Score too low — likely OCR error. Retrying...")
                continue
            elif not best_keywords and attempt < 2:
                print("🔁 Missing keyword list empty — retrying to regenerate summary + bullets.")
                continue
            elif attempt < 2:
                print(f"➡️ Retrying for better ATS score... ({attempt + 2}/3)")

            time.sleep(2)

        if not best_resume.strip():
            print("❌ No valid resume generated. Skipping save.")
            continue

        docx_path = f"outputs/final_tailored_resumes/{safe_title}_ATS{best_score}.docx"
        save_to_docx(best_resume, docx_path)
        print(f"📁 Resume saved → {docx_path}")

        try:
            with open(f"outputs/final_tailored_resumes/{safe_title}_ATS{best_score}.txt", "w", encoding="utf-8") as outf:
                outf.write(best_resume.encode("utf-8", "ignore").decode("utf-8"))

            final_prompt = format_prompt(base_resume, jd_text, style_guide, best_keywords, best_sections, job_title)
            with open(f"outputs/final_tailored_resumes/{safe_title}_prompt.txt", "w", encoding="utf-8") as pf:
                pf.write(final_prompt.encode("utf-8", "ignore").decode("utf-8"))
        except Exception as e:
            print(f"⚠️ Failed to write final output files: {e}")

        summary_data.append({
            "title": title,
            "score": best_score,
            "file": docx_path
        })

        print(f"✅ Best resume saved: {docx_path}")
        if best_score < 80:
            print(f"⚠️ Did not reach 80% ATS for: {title}")

        time.sleep(5)

    except Exception as e:
        print(f"❌ Failed processing job #{i+1} due to error:\n{e}")
        continue

summary_df = pd.DataFrame(summary_data)
summary_df.to_csv("outputs/ats_score_summary.csv", index=False)
print("\n📊 Summary written to: outputs/ats_score_summary.csv")
