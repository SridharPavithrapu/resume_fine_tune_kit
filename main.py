from job_scraper.scrapers.jobspy_scraper import JobSpyScraper

if __name__ == '__main__':
    scraper = JobSpyScraper(
        sites=["indeed", "linkedin"],
        keywords="data analyst OR business analyst",
        hours_old=24,
        results_wanted=10000,
        location=""
    )
    jobs = scraper.search_jobs()
    scraper.save(jobs, 'output/jobspy_jobs.csv')
    print(f"Saved {len(jobs)} jobs to output/jobspy_jobs.csv")
