"""
The actual discover -> keyword-filter -> location-filter -> Claude-judge
chain, factored out so both 03_claude_judge.py (standalone stage test) and
make_batch.py (real run) call the exact same logic instead of two
independently-drifting copies.
"""
from broad_source import discover_greenhouse_ashby_postings
from keyword_filter import passes_keyword_filter
from ats_fetchers import fetch_greenhouse, fetch_ashby, fetch_lever
from location_filter import is_us_location
from nyc_location_filter import passes_nyc_location_filter
from target_list_exclusion import is_target_list_company
from claude_judge_broad import judge_fit_broad
from tech_company_cache import get_known_verdict, record_verdict


FETCHERS = {"greenhouse": fetch_greenhouse, "ashby": fetch_ashby, "lever": fetch_lever}


def _judge_one(title, description, company_name, url, ats, token, profile,
                already_judged_urls, target_names, verbose):
    """Shared per-posting judge logic used by both the board-crawl path
    (greenhouse/ashby/lever) and the direct workday path. Returns a
    (record, is_match) tuple, or None if this posting should be skipped
    entirely (already judged, filtered out, target-list company, or the
    judge call itself failed). Does NOT check location -- the board-crawl
    caller filters that separately per-job since a full board fetch pulls
    in non-US postings too; the workday caller skips it entirely since
    those postings already came through Fantastic Jobs' own
    location='"United States"' filter and were never expanded to
    siblings."""
    if url in already_judged_urls:
        return None
    if is_target_list_company(company_name, target_names):
        if verbose:
            print(f"[skip-target-list] {company_name}")
        return None
    if not passes_keyword_filter(title, token):
        return None

    try:
        verdict = judge_fit_broad(title, description, company_name, profile)
    except Exception as e:
        if verbose:
            print(f"[{token}] judge failed for '{title}': {e}")
        return None

    # is_tech_company is really a property of the COMPANY, not this one
    # posting -- override the judge's fresh (per-posting) guess with a
    # known verdict if this company already has one (manual override, or
    # auto-learned from an earlier True elsewhere), so the same company
    # doesn't flip-flop across different postings depending on how much
    # product detail each one's own text happens to include.
    # role_and_years_ok (captured before the tech gate in
    # claude_judge_broad.py) lets match get recombined correctly here,
    # rather than guessing it from the reason text.
    known = get_known_verdict(company_name)
    if known is not None and known != verdict["is_tech_company"]:
        if verbose:
            print(f"    [tech-gate override] known verdict for {company_name} is "
                  f"is_tech_company={known}, overriding this posting's fresh guess of "
                  f"{verdict['is_tech_company']}")
        verdict["is_tech_company"] = known
        verdict["match"] = known and verdict["role_and_years_ok"]
        verdict["reason"] = verdict["reason"] + f" [tech-gate corrected to {known} for {company_name}]"
    record_verdict(company_name, verdict["is_tech_company"])

    if verbose:
        print(f"  [{ats}] {company_name} -- {title}\n    match={verdict['match']} "
              f"tech={verdict['is_tech_company']} -- {verdict['reason']}")

    record = {"company_name": company_name, "ats": ats, "board_token": token, "title": title,
               "url": url, "description": description, **verdict}
    return record, verdict["match"]


def discover_and_judge(fantastic_key: str, profile: str, target_names: list,
                        already_judged_urls: set = None, limit: int = None, max_matches: int = None,
                        verbose: bool = True) -> tuple:
    """Returns (matches, rejects), each a list of dicts with company_name,
    ats, board_token, title, url, description, match, is_tech_company,
    reason. already_judged_urls (from batch_state.json) is checked so a
    posting already judged in a past run never gets re-judged (and
    re-billed) here.

    max_matches stops judging entirely as soon as that many MATCHES have
    been found -- not the same as limit, which caps how many boards get
    fetched regardless of match count. Without max_matches, every board
    from discovery gets judged (and billed) every run even if you only
    want a small batch out the other end; this is what make_batch.py uses
    to stop as soon as it has enough for the batch size, instead of
    judging all ~200 boards to build 1 folder.

    Greenhouse/Ashby/Lever all have a clean "list every posting on this
    company's board" public API, so those three get the full sibling-
    discovery treatment: every board found gets fully crawled, catching
    other qualifying roles at the same company beyond whichever one
    posting the aggregator's keyword search happened to surface. Workday
    doesn't have an equivalent cheap board-listing call for an arbitrary
    tenant, so Workday postings are judged one at a time directly from
    the aggregator's own copy (title/description), with no sibling-role
    discovery at that company. That's a real gap versus the other three,
    accepted here to avoid a live HTTP call per Workday posting just to
    find out if it's worth judging."""
    already_judged_urls = already_judged_urls or set()

    postings = discover_greenhouse_ashby_postings(fantastic_key)

    board_postings = [p for p in postings if p["ats"] != "workday"]
    workday_postings = [p for p in postings if p["ats"] == "workday"]

    seen_boards = {}
    for p in board_postings:
        key = (p["ats"], p["board_token"])
        if key not in seen_boards:
            seen_boards[key] = p["company_name"]

    boards = list(seen_boards.items())
    if limit:
        boards = boards[:limit]

    matches, rejects = [], []

    for (ats, token), company_name in boards:
        if max_matches and len(matches) >= max_matches:
            if verbose:
                print(f"[stop-early] {max_matches} match(es) found, stopping before checking more boards")
            break

        if is_target_list_company(company_name, target_names):
            if verbose:
                print(f"[skip-target-list] {company_name}")
            continue

        try:
            jobs = FETCHERS[ats](token)
        except Exception as e:
            if verbose:
                print(f"[{token}] FETCH FAILED: {e}")
            continue

        for job in jobs:
            if max_matches and len(matches) >= max_matches:
                break

            title = job["title"]
            url = job.get("url", "")
            loc_string = job.get("location_blob", job.get("location", ""))
            if not is_us_location(loc_string) or not passes_nyc_location_filter(loc_string):
                continue

            result = _judge_one(title, job.get("description", ""), company_name, url, ats, token,
                                 profile, already_judged_urls, target_names, verbose)
            if result is None:
                continue
            record, is_match = result
            (matches if is_match else rejects).append(record)

    # Workday: no board crawl, judge each aggregator-surfaced posting
    # directly (see docstring above for why).
    for p in workday_postings:
        if max_matches and len(matches) >= max_matches:
            if verbose:
                print(f"[stop-early] {max_matches} match(es) found, stopping before checking more workday postings")
            break

        result = _judge_one(p["title"], p.get("description", ""), p["company_name"], p["apply_url"],
                             "workday", p["board_token"], profile, already_judged_urls, target_names, verbose)
        if result is None:
            continue
        record, is_match = result
        (matches if is_match else rejects).append(record)

    return matches, rejects
