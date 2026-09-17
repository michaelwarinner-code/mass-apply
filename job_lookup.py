"""
Shared by the per-stage test scripts (04, 05, 06) and make_batch.py: given
one job's apply URL, figures out which ATS it's on, fetches that
company's board, and returns the matching posting's full data (title,
company, description) -- not the aggregator's possibly-truncated copy.
"""
from broad_source import GREENHOUSE_URL_RE, ASHBY_URL_RE
from ats_fetchers import fetch_greenhouse, fetch_ashby


def fetch_job_by_url(url: str, company_name: str = None) -> dict:
    """Raises ValueError if the URL isn't a recognized Greenhouse/Ashby
    posting, or if that company's board doesn't currently list this URL
    (posting taken down, or the URL's slightly off).

    ats_fetchers' per-job records don't include a company name (that only
    exists on the aggregator's own copy, from stage 1/broad_source.py) --
    company_name lets a caller that already knows it (make_batch.py,
    threading it through from the judge stage) pass the real one through
    instead of falling back to the raw board_token slug."""
    gh = GREENHOUSE_URL_RE.search(url)
    if gh:
        token, ats = gh.group(1), "greenhouse"
    else:
        ashby = ASHBY_URL_RE.search(url)
        if not ashby:
            raise ValueError(f"Not a recognized Greenhouse/Ashby URL: {url}")
        token, ats = ashby.group(1), "ashby"

    jobs = fetch_greenhouse(token) if ats == "greenhouse" else fetch_ashby(token)
    for job in jobs:
        if job.get("url", "").rstrip("/") == url.rstrip("/"):
            resolved_company = company_name or token.replace("-", " ").replace("_", " ").title()
            return {"ats": ats, "board_token": token, "title": job["title"],
                     "company_name": resolved_company,
                     "description": job.get("description", ""), "url": job.get("url", url)}

    raise ValueError(f"URL not found on {token}'s current board -- posting may have been taken down: {url}")
