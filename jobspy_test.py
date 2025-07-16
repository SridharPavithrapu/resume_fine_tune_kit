from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term="business analyst OR data analyst OR business intelligence analyst",
    job_type="contract",
    hours_old=24,
    results_wanted=10000,
    location=""
)

role_keywords = ["business analyst", "data analyst", "business intelligence analyst"]
jobs = jobs[
    jobs['title'].str.lower().str.contains('|'.join(role_keywords), na=False)
]
jobs.to_csv("output/jobspy_jobs.csv", index=False)
