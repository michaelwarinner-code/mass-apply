"""
Stage 6, standalone: scans a job's REAL live application form and writes a
notes.txt pairing every actual question with its best available answer --
identity fields from candidate_info.json, known answers from the reusable
bank, and a clear placeholder for anything with no answer yet (open-ended
questions, until the second-brain generator exists to draft those). Does
NOT touch materials/PDFs/Sheets/batch_state -- purely the form scan +
notes file, so this stage can be checked on its own.

    python 06_notes.py "<job url>"
"""
import argparse
import os

from form_scanner import scan_fields_only
from answer_bank import load_answer_bank
from job_lookup import fetch_job_by_url
from notes_builder import load_candidate_info, build_notes_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--company", default=None, help="Override the display company name (defaults to the board token, title-cased)")
    args = parser.parse_args()

    job = fetch_job_by_url(args.url, company_name=args.company)

    candidate_info = load_candidate_info()
    bank_entries = load_answer_bank()

    fields = scan_fields_only(args.url)
    print(f"Scanned {len(fields)} field(s) for {job['company_name']} -- {job['title']}.")

    notes = build_notes_text(fields, candidate_info, bank_entries, company_name=job["company_name"])

    out_dir = os.path.join("test_output", "06_notes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "notes.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(notes)

    print(f"\nNotes written: {out_path}\n")
    print(notes)


if __name__ == "__main__":
    main()
