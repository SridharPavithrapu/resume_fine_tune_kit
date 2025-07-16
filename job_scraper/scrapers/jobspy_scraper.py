from ..base_scraper import BaseScraper
import pandas as pd

class JobSpyScraper(BaseScraper):
    def __init__(self, sites=["indeed", "linkedin"], keywords="data analyst OR business analyst", hours_old=24, results_wanted=10000, location=""):
        self.sites = sites
        self.keywords = keywords
        self.hours_old = hours_old
        self.results_wanted = results_wanted
        self.location = location

    def search_jobs(self, keyword=None, location=None, num_pages=1):
        from jobspy import scrape_jobs
        jobs = scrape_jobs(
            site_name=self.sites,
            search_term=keyword or self.keywords,
            hours_old=self.hours_old,
            results_wanted=self.results_wanted,
            location=location or self.location,
        )
        # Standardize output fields
        cols = ["title", "company", "location", "description", "job_url", "date_posted"]
        for col in cols:
            if col not in jobs.columns:
                jobs[col] = ""
        return jobs[cols].to_dict(orient="records")

    def parse_listing(self, listing_html):
        # Not needed for JobSpy (parsing is internal)
        return None

    def save(self, jobs, filename):
        pd.DataFrame(jobs).to_csv(filename, index=False)
