"""
Stage 1, standalone: calls the Fantastic Jobs aggregator only and prints
every raw Greenhouse/Ashby posting it finds -- before ANY filtering.
Confirms the API call itself works and shows real field names/values
before anything downstream touches them.

    python 01_discover.py
"""
import os

from broad_source import discover_greenhouse_ashby_postings


def main():
    key = os.environ.get("FANTASTIC_JOBS_API_KEY")
    if not key:
        raise SystemExit("Set FANTASTIC_JOBS_API_KEY to run this.")

    postings = discover_greenhouse_ashby_postings(key)
    print(f"\n{len(postings)} total postings found (before keyword filter, before judging):\n")
    for p in postings:
        print(f"  [{p['ats']}] {p['company_name']} -- {p['title']} (token={p['board_token']})")


if __name__ == "__main__":
    main()
