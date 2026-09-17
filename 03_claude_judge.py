"""
Stage 3, standalone: chains stages 1-2, then fetches each unique company
board's real postings (full description, not the aggregator's truncated
copy) and runs the Claude fit judge on each one that passes the keyword
and location filters. Prints match/reject + reason per posting -- does
NOT write to batch_state.json, so re-running this doesn't affect what a
real batch run considers "already seen."

Optional --limit N caps how many company boards get fetched, useful for a
quick check without burning through the whole list (and the API calls
that come with it) every time you're just testing this stage.

    python 03_claude_judge.py [--limit 5]
"""
import argparse
import os

from target_list_exclusion import load_target_company_names
from discovery_pipeline import discover_and_judge

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "state", "candidate_profile.md")


def load_profile():
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Cap how many company boards to fetch/judge")
    args = parser.parse_args()

    fantastic_key = os.environ.get("FANTASTIC_JOBS_API_KEY")
    if not fantastic_key:
        raise SystemExit("Set FANTASTIC_JOBS_API_KEY to run this.")
    if not os.environ.get("MASSAPPLY_ANTHROPIC_API_KEY"):
        raise SystemExit("Set MASSAPPLY_ANTHROPIC_API_KEY to run this.")

    profile = load_profile()
    target_names = load_target_company_names()

    matches, rejects = discover_and_judge(fantastic_key, profile, target_names, limit=args.limit)

    print(f"\n=== {len(matches)} match(es), {len(rejects)} reject(s) ===")


if __name__ == "__main__":
    main()
