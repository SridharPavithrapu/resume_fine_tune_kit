import os
import json
import pandas as pd
import undetected_chromedriver as uc
from nltk.stem import PorterStemmer

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
    return uc.Chrome(driver_executable_path=chromedriver_path, options=options)

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
    slug = job_title.replace(" ", "_").lower()[:40]
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