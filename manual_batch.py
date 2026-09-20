"""
Manual batch builder -- for when the discovery API (Fantastic Jobs) is
out of quota, rate-limited, or you'd just rather paste postings you
found yourself. Skips discovery/judging entirely: reads up to 10
hand-pasted job postings from a plain text file and, for each one, runs
the exact same build step make_batch.py uses -- separate resume + cover
letter PDFs, a notes.txt with just the company/title/portal link, and a
row logged to the same Google Sheet job-finder uses -- via the shared
job_builder module, so a manually-sourced job ends up looking identical
to an automatically-discovered one.

No fit-judging happens here either -- these are jobs YOU already decided
are worth applying to, so there's nothing to judge.

INPUT FILE FORMAT -- plain text, one block per job, separated by a line
that's just "===", up to 10 blocks. Inside each block, a "---" line
separates the header (Company/Title/URL) from the pasted description:

===
Company: Acme Corp
Title: Growth Marketing Manager
URL: https://boards.greenhouse.io/acme/jobs/123
---
Paste the full job description here. Can be as many lines/paragraphs as
you want -- everything after the --- line and before the next === line
counts as the description.

===
Company: Another Co
Title: Some Other Role
URL: https://jobs.lever.co/another-co/abc123
---
Another pasted description here.

Usage:
    python manual_batch.py jobs.txt
"""
import argparse
import os
import re
from datetime import date

from job_builder import build_job_folder, safe_folder_name

MAX_JOBS = 10


def parse_jobs_file(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        content = f.read()

    raw_blocks = re.split(r"^===\s*$", content, flags=re.MULTILINE)
    jobs = []
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
        if "---" not in block:
            print(f"  Skipping a block with no '---' separator between header and description "
                  f"(starts: {block[:60]!r})")
            continue

        header, description = block.split("---", 1)
        company = title = url = ""
        for line in header.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "company":
                company = value
            elif key == "title":
                title = value
            elif key == "url":
                url = value

        description = description.strip()
        if not (company and title and url and description):
            print(f"  Skipping a block missing something required "
                  f"(company={company!r}, title={title!r}, url={url!r}, "
                  f"description length={len(description)})")
            continue

        jobs.append({"company_name": company, "title": title, "url": url, "description": description})

    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_file", help="Text file with up to 10 pasted job postings -- "
                                            "see this script's module docstring for the exact format.")
    args = parser.parse_args()

    if not os.environ.get("MASSAPPLY_ANTHROPIC_API_KEY"):
        raise SystemExit("Set MASSAPPLY_ANTHROPIC_API_KEY to run this.")

    jobs = parse_jobs_file(args.input_file)
    if not jobs:
        raise SystemExit("No valid job blocks found in that file -- check the format against "
                          "this script's module docstring (python manual_batch.py --help).")
    if len(jobs) > MAX_JOBS:
        print(f"  Found {len(jobs)} jobs, only building the first {MAX_JOBS}.")
        jobs = jobs[:MAX_JOBS]

    batch_dir = os.path.join("batches", date.today().isoformat())
    os.makedirs(batch_dir, exist_ok=True)
    print(f"Building {len(jobs)} job(s) from {args.input_file} into {batch_dir}/\n")

    links = []
    for job in jobs:
        company, title, url, description = job["company_name"], job["title"], job["url"], job["description"]
        folder_name = safe_folder_name(company, title, url)
        job_dir = os.path.join(batch_dir, folder_name)
        print(f"\n=== {company} -- {title} ===\n  {url}")
        success = build_job_folder(company, title, url, description, job_dir)
        if success:
            links.append(f"{company} -- {title}: {url}")

    print(f"\n=== Batch complete: {len(links)} of {len(jobs)} succeeded ===")
    print(f"Folder: {batch_dir}\n")
    print("Application portal links:")
    for link in links:
        print(f"  {link}")


if __name__ == "__main__":
    main()
