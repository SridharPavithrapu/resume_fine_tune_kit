import os
import json
import pandas as pd
import undetected_chromedriver as uc
from nltk.stem import PorterStemmer
import re

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------- Driver -------------------- #
def launch_driver(chromedriver_path="/opt/homebrew/bin/chromedriver"):
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")

    return uc.Chrome(options=options, driver_executable_path=chromedriver_path)

# -------------------- Load JD File -------------------- #
def load_job_descriptions(file_path):
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        print(f"Error loading job file: {e}")
        return pd.DataFrame()

# -------------------- Normalize Keywords -------------------- #
def normalize_keywords(keywords):
    ps = PorterStemmer()
    return list(set([ps.stem(k.lower().strip()) for k in keywords if k.strip()]))

# -------------------- Save Tailored Resume & JD -------------------- #
def save_tailored_attempts(job_title, jd_text, resumes_with_scores):
    slug = re.sub(r"[^\w]+", "_", job_title.strip().lower())[:40]
    folder = os.path.join(OUTPUT_DIR, slug)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "job_description.txt"), "w") as f:
        f.write(jd_text)
    for i, (score, resume) in enumerate(resumes_with_scores):
        with open(os.path.join(folder, f"attempt_{i+1}_score_{score}.txt"), "w") as f:
            f.write(resume)

# -------------------- Save Prompt + Output JSON -------------------- #
def save_json_log(prompt, output, job_title):
    slug = job_title.replace(" ", "_").lower()[:40]
    folder = os.path.join(OUTPUT_DIR, slug)
    os.makedirs(folder, exist_ok=True)
    log = {"prompt": prompt, "output": output}
    with open(os.path.join(folder, "log.json"), "w") as f:
        json.dump(log, f, indent=2)

def extract_job_title(jd_text, csv_title=None):
    """
    Extracts job title using CSV title (preferred) or job description text.
    """

    # 0. Prefer CSV title if it’s clean
    if csv_title:
        clean_title = csv_title.strip()
        if 5 < len(clean_title) < 120 and not clean_title.lower().startswith("requisition"):
            return clean_title

    # 1. Try labeled lines
    match = re.search(r"(?:Position Title|Job Title|Title)\s*[:\-–]\s*(.+)", jd_text, re.IGNORECASE)
    if match:
        return match.group(1).strip().split("\n")[0]

    # 2. Try bolded lines
    bolded_lines = re.findall(r"\*\*(.+?)\*\*", jd_text)
    for line in bolded_lines:
        if not line.endswith(":") and any(kw in line.lower() for kw in ["analyst", "consultant", "engineer", "manager", "scientist"]):
            return line.strip()

    # 3. Try top lines of JD
    for line in jd_text.strip().splitlines()[:10]:
        line_clean = line.strip()
        if line_clean.endswith(":"):
            continue
        if len(line_clean) < 100 and any(kw in line_clean.lower() for kw in ["analyst", "consultant", "engineer", "manager", "scientist"]):
            return line_clean

    return "Unknown Job Title".title()
