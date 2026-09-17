"""
Stage 2, standalone: runs stage 1's raw postings through the free local
keyword pre-filter and prints pass/fail for each, so the filter's own
logic can be checked in isolation -- separate from whether the Claude
judge downstream is behaving correctly.

    python 02_keyword_filter.py
"""
import os

from broad_source import discover_greenhouse_ashby_postings
from keyword_filter import passes_keyword_filter


def main():
    key = os.environ.get("FANTASTIC_JOBS_API_KEY")
    if not key:
        raise SystemExit("Set FANTASTIC_JOBS_API_KEY to run this.")

    postings = discover_greenhouse_ashby_postings(key)
    passed, failed = [], []
    for p in postings:
        if passes_keyword_filter(p["title"], p["board_token"]):
            passed.append(p)
        else:
            failed.append(p)

    print(f"\n{len(passed)} of {len(postings)} passed the keyword filter:\n")
    for p in passed:
        print(f"  PASS  [{p['ats']}] {p['company_name']} -- {p['title']}")

    print(f"\n{len(failed)} rejected by the keyword filter:\n")
    for p in failed:
        print(f"  FAIL  [{p['ats']}] {p['company_name']} -- {p['title']}")


if __name__ == "__main__":
    main()
