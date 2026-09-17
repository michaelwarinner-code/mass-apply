"""
The actual discover -> keyword-filter -> location-filter -> Claude-judge
chain, factored out so both 03_claude_judge.py (standalone stage test) and
make_batch.py (real run) call the exact same logic instead of two
independently-drifting copies.
"""
from broad_source import discover_greenhouse_ashby_postings
from keyword_filter import passes_keyword_filter
from ats_fetchers import fetch_greenhouse, fetch_ashby
from location_filter import is_us_location
from nyc_location_filter import passes_nyc_location_filter
from target_list_exclusion import is_target_list_company
from claude_judge_broad import judge_fit_broad


def discover_and_judge(fantastic_key: str, profile: str, target_names: list,
                        already_judged_urls: set = None, limit: int = None, verbose: bool = True) -> tuple:
    """Returns (matches, rejects), each a list of dicts with company_name,
    ats, board_token, title, url, description, match, is_software_company,
    reason. already_judged_urls (from batch_state.json) is checked so a
    posting already judged in a past run never gets re-judged (and
    re-billed) here."""
    already_judged_urls = already_judged_urls or set()

    postings = discover_greenhouse_ashby_postings(fantastic_key)
    seen_boards = {}
    for p in postings:
        key = (p["ats"], p["board_token"])
        if key not in seen_boards:
            seen_boards[key] = p["company_name"]

    boards = list(seen_boards.items())
    if limit:
        boards = boards[:limit]

    matches, rejects = [], []
    for (ats, token), company_name in boards:
        if is_target_list_company(company_name, target_names):
            if verbose:
                print(f"[skip-target-list] {company_name}")
            continue

        try:
            jobs = fetch_greenhouse(token) if ats == "greenhouse" else fetch_ashby(token)
        except Exception as e:
            if verbose:
                print(f"[{token}] FETCH FAILED: {e}")
            continue

        for job in jobs:
            title = job["title"]
            url = job.get("url", "")
            if url in already_judged_urls:
                continue
            if not passes_keyword_filter(title, token):
                continue
            loc_string = job.get("location_blob", job.get("location", ""))
            if not is_us_location(loc_string) or not passes_nyc_location_filter(loc_string):
                continue

            try:
                verdict = judge_fit_broad(title, job.get("description", ""), company_name, profile)
            except Exception as e:
                if verbose:
                    print(f"[{token}] judge failed for '{title}': {e}")
                continue

            if verbose:
                print(f"  [{ats}] {company_name} -- {title}\n    match={verdict['match']} "
                      f"software={verdict['is_software_company']} -- {verdict['reason']}")

            record = {"company_name": company_name, "ats": ats, "board_token": token, "title": title,
                       "url": url, "description": job.get("description", ""), **verdict}
            (matches if verdict["match"] else rejects).append(record)

    return matches, rejects
