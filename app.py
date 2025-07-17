
import os
import re
import time
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from inference import tailor_resume
from guardrail_clean_work_experience import clean_tailored_work_experience
from jobscan_driver import get_jobscan_score  # Updated to use Playwright + OCR

load_dotenv()

st.set_page_config(page_title="AI Resume Tailor", layout="wide")

st.title("AI Resume Tailoring Agent 🔍📄")
uploaded_resume = st.file_uploader("Upload your resume", type=["pdf", "docx"])
uploaded_jd = st.file_uploader("Upload the job description", type=["pdf", "txt", "docx"])

if uploaded_resume and uploaded_jd:
    resume_path = f"/tmp/{uploaded_resume.name}"
    jd_path = f"/tmp/{uploaded_jd.name}"

    with open(resume_path, "wb") as f:
        f.write(uploaded_resume.read())
    with open(jd_path, "wb") as f:
        f.write(uploaded_jd.read())

    st.info("Generating tailored resume...")
    tailored_resume = tailor_resume(resume_path, jd_path)
    cleaned_resume = clean_tailored_work_experience(tailored_resume)

    st.success("Tailored resume generated!")

    st.download_button("Download Tailored Resume", cleaned_resume, file_name="tailored_resume.txt")

    st.info("Running Jobscan analysis...")
    score = get_jobscan_score(resume_path, jd_path)
    st.write(f"✅ Jobscan Score: **{score}%**")
