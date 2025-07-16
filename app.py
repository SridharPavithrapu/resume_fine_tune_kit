import os
import re
import time
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from resume_tailoring.inference import tailor_resume
from guardrail_clean_work_experience import clean_tailored_work_experience

# Load environment variables
load_dotenv()
EMAIL = os.getenv("JOBSCAN_EMAIL")
PASSWORD = os.getenv("JOBSCAN_PASSWORD")
CHROMEDRIVER_PATH = "/opt/homebrew/bin/chromedriver"

TARGET_SCORE = 80
MAX_ATTEMPTS = 3
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----------------- Driver Launch ----------------- #
def launch_driver():
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    driver = uc.Chrome(driver_executable_path=CHROMEDRIVER_PATH, options=options)
    return driver

# ----------------- Jobscan Login ----------------- #
def login_to_jobscan(driver):
    driver.get("https://www.jobscan.co/")
    WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.LINK_TEXT, "Log in"))).click()
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "user_email"))).send_keys(EMAIL)
    driver.find_element(By.ID, "user_password").send_keys(PASSWORD)
    driver.find_element(By.NAME, "commit").click()
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "dashboard")))
    return driver

# ----------------- ATS Score ----------------- #
def get_ats_score(driver, resume_text, job_text):
    driver.get("https://www.jobscan.co/scan/new")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "resumeText"))).clear()
    driver.find_element(By.ID, "resumeText").send_keys(resume_text)
    driver.find_element(By.ID, "jobText").clear()
    driver.find_element(By.ID, "jobText").send_keys(job_text)
    driver.find_element(By.XPATH, "//button[text()='Scan']").click()
    score_el = WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".score-value")))
    score_text = score_el.text
    score = int(re.findall(r"\d+", score_text)[0])
    return score

# ----------------- Jobscan Feedback ----------------- #
def get_jobscan_feedback(driver):
    try:
        keywords = []
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".missing-keyword")))
        keyword_elements = driver.find_elements(By.CSS_SELECTOR, ".missing-keyword")
        for el in keyword_elements:
            keywords.append(el.text.strip())
        return {"missing_keywords": keywords}
    except Exception:
        return {"missing_keywords": []}

# ----------------- Tailor + Score Loop ----------------- #
def tailor_and_score(job_row, base_resume, style_guide, driver):
    all_versions = []
    best_resume = ""
    best_score = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tailored = tailor_resume(job_row, style_guide, base_resume)
        cleaned = clean_tailored_work_experience(tailored)
        score = get_ats_score(driver, cleaned, job_row['Job Description'])
        all_versions.append((score, cleaned))
        if score > best_score:
            best_score = score
            best_resume = cleaned
        if score >= TARGET_SCORE:
            break
    return best_resume, best_score, all_versions

# ----------------- Streamlit UI ----------------- #
def main():
    st.title("Resume Tailoring with Jobscan Integration")

    style_guide = st.text_area("Style Guide (optional)", value="")
    resume_file = st.file_uploader("Upload base resume", type=["txt"])
    job_file = st.file_uploader("Upload job descriptions (CSV)", type=["csv"])

    if resume_file and job_file:
        base_resume = resume_file.read().decode("utf-8")
        job_df = pd.read_csv(job_file)

        if 'jobscan_driver' not in st.session_state:
            driver = launch_driver()
            login_to_jobscan(driver)
            st.session_state['jobscan_driver'] = driver

        driver = st.session_state['jobscan_driver']

        progress_bar = st.progress(0)

        for idx, row in job_df.iterrows():
            st.markdown(f"### Job {idx + 1}: {row['Job Title']}")
            with st.spinner("Tailoring and scoring resume..."):
                tailored, score, attempts = tailor_and_score(row, base_resume, style_guide, driver)
                job_slug = re.sub(r"\W+", "_", row['Job Title'])[:40]
                save_path = os.path.join(OUTPUT_DIR, f"{job_slug}_{score}.txt")

                with open(save_path, "w") as f:
                    f.write(tailored)

                st.success(f"Best ATS Score: {score}")
                st.text_area("Best Tailored Resume", tailored, height=300)

                feedback = get_jobscan_feedback(driver)
                if feedback['missing_keywords']:
                    st.markdown("**Missing Keywords:** " + ", ".join(feedback['missing_keywords']))

                    if st.button(f"Re-Tailor Job {idx+1} with Feedback"):
                        retry_resume = tailor_resume(row, style_guide, base_resume, missing_keywords=feedback['missing_keywords'])
                        cleaned_retry = clean_tailored_work_experience(retry_resume)
                        retry_score = get_ats_score(driver, cleaned_retry, row['Job Description'])
                        st.text_area("Re-Tailored Resume", cleaned_retry, height=300)
                        st.success(f"Re-Tailored ATS Score: {retry_score}")

                st.markdown("---")
                st.markdown("### All Attempts")
                for i, (s, r) in enumerate(attempts):
                    st.markdown(f"**Attempt {i+1}: Score {s}**")
                    st.text_area(f"Resume Attempt {i+1}", r, height=200)

            progress_bar.progress((idx + 1) / len(job_df))

        st.success("All resumes tailored and saved in /outputs")

if __name__ == '__main__':
    main()