"""
The real run: discovers + judges new postings, then for up to BATCH_SIZE
jobs (newly matched this run, plus any already judged_fit from a
previous run that never made it into a batch), generates a complete,
ready-to-review application folder -- resume + cover letter (separate
PDFs, or one combined PDF if the posting only has one upload slot), a
notes.txt with every real question paired with its best answer, and logs
a row to the same Google Sheet job-finder uses. Prints every portal link
at the end so you have them all in one place.

Nothing here submits anything or touches a browser beyond the read-only
form scan -- output is entirely local files for you to review and act on
by hand.

    python make_batch.py
"""
import argparse
import os
import re
from datetime import date

from target_list_exclusion import load_target_company_names
from discovery_pipeline import discover_and_judge
from form_scanner import scan_fields_only, has_separate_upload_slots
from job_lookup import fetch_job_by_url
from materials_writer import generate_materials
from pdf_builder import build_resume_and_coverletter, build_combined_resume_coverletter
from answer_bank import load_answer_bank
from notes_builder import load_candidate_info, build_notes_text
from sheets_logger import append_application_row
import batch_state as bs

BATCH_SIZE = 10
PROFILE_PATH = os.path.join(os.path.dirname(__file__), "state", "candidate_profile.md")


def load_profile():
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return f.read()


def safe_folder_name(company: str, title: str) -> str:
    # Strip characters that are illegal (Windows) or just awkward in a
    # folder name, keep it readable.
    raw = f"{company} -- {title}".strip()
    return re.sub(r'[\\/*?:"<>|]', "", raw)[:150]


def process_one_job(job: dict, batch_dir: str, candidate_info: dict, bank_entries: list) -> bool:
    """Returns True on success. Sets the job's batch_state status either
    way (in_batch on success, failed_materials/failed_form_scan on
    failure) so it's never silently retried forever.

    job only needs company_name/title/url -- description isn't persisted
    in batch_state.json (would bloat it over time with full posting text
    for every job ever judged), so this re-fetches the live posting fresh
    here instead. That also naturally catches a posting that's been taken
    down since it was judged, rather than generating materials against
    stale/missing text."""
    company, title, url = job["company_name"], job["title"], job["url"]
    folder_name = safe_folder_name(company, title)
    job_dir = os.path.join(batch_dir, folder_name)
    os.makedirs(job_dir, exist_ok=True)

    print(f"\n=== {company} -- {title} ===\n  {url}")

    try:
        live_job = fetch_job_by_url(url, company_name=company)
    except Exception as e:
        print(f"  Could not re-fetch live posting (may have been taken down): {e}")
        return False
    description = live_job["description"]

    try:
        fields = scan_fields_only(url)
    except Exception as e:
        print(f"  Form scan FAILED: {e}")
        return False

    try:
        print("  Generating materials...")
        resume_data, coverletter_data = generate_materials(description, company, title)
    except Exception as e:
        print(f"  Materials generation FAILED: {e}")
        return False

    try:
        if has_separate_upload_slots(fields):
            print("  Building separate resume + cover letter PDFs...")
            resume_pdf, cl_pdf = build_resume_and_coverletter(resume_data, coverletter_data, job_dir)
            os.rename(resume_pdf, os.path.join(job_dir, f"{folder_name} - Resume.pdf"))
            os.rename(cl_pdf, os.path.join(job_dir, f"{folder_name} - Cover Letter.pdf"))
        else:
            print("  Only one upload slot found -- building ONE combined PDF (cover letter pg 1, resume pg 2)...")
            combined_pdf = build_combined_resume_coverletter(resume_data, coverletter_data, job_dir)
            os.rename(combined_pdf, os.path.join(job_dir, f"{folder_name} - Combined.pdf"))
    except Exception as e:
        print(f"  PDF build FAILED: {e}")
        return False

    notes = build_notes_text(fields, candidate_info, bank_entries, company_name=company)
    notes_header = f"{company} -- {title}\nApplication portal: {url}\n\n" + "=" * 40 + "\n\n"
    with open(os.path.join(job_dir, "notes.txt"), "w", encoding="utf-8") as f:
        f.write(notes_header + notes)

    try:
        append_application_row(date.today().isoformat(), title, company, description, job_url=url)
    except Exception as e:
        # A Sheets hiccup shouldn't lose an otherwise-complete folder --
        # worth knowing loudly, not worth failing the whole job over.
        print(f"  WARNING: could not log to Google Sheets: {e}")

    print(f"  Done -- {job_dir}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    fantastic_key = os.environ.get("FANTASTIC_JOBS_API_KEY")
    if not fantastic_key:
        raise SystemExit("Set FANTASTIC_JOBS_API_KEY to run this.")
    if not os.environ.get("MASSAPPLY_ANTHROPIC_API_KEY"):
        raise SystemExit("Set MASSAPPLY_ANTHROPIC_API_KEY to run this.")

    profile = load_profile()
    target_names = load_target_company_names()
    candidate_info = load_candidate_info()
    bank_entries = load_answer_bank()

    state = bs.load_state()
    already_judged_urls = set(state["jobs"].keys())

    # Only discover/judge enough to fill this batch -- previously this
    # judged (and billed for) every board from stage 1 every run,
    # regardless of --batch-size, since that flag only capped the
    # folder-building step after judging, not judging itself. Any
    # judged_fit jobs already sitting unbatched from a previous run count
    # toward the total first, so this doesn't over-search when there's
    # already a backlog waiting.
    already_unbatched = len(bs.jobs_with_status(state, "judged_fit"))
    still_needed = max(0, args.batch_size - already_unbatched)

    if still_needed == 0:
        print(f"Already have {already_unbatched} judged_fit job(s) waiting -- skipping discovery/judging this run.")
        matches, rejects = [], []
    else:
        print(f"Discovering + judging new postings (stopping once {still_needed} new match(es) are found)...")
        matches, rejects = discover_and_judge(fantastic_key, profile, target_names,
                                               already_judged_urls=already_judged_urls, max_matches=still_needed)
    for m in matches:
        bs.set_job_status(state, m["url"], "judged_fit", company_name=m["company_name"], title=m["title"],
                           url=m["url"], ats=m["ats"], board_token=m["board_token"])
    for r in rejects:
        bs.set_job_status(state, r["url"], "judged_reject", company_name=r["company_name"], title=r["title"],
                           url=r["url"], ats=r["ats"], board_token=r["board_token"])
    bs.save_state(state)
    print(f"{len(matches)} new match(es), {len(rejects)} new reject(s) this run.")

    # Jobs ready to go into a batch: newly matched this run, PLUS anything
    # already judged_fit from a previous run that never made it into a
    # batch (e.g. a prior run crashed partway through).
    pending = bs.jobs_with_status(state, "judged_fit")
    to_process = pending[:args.batch_size]

    if not to_process:
        print("\nNothing to batch -- no judged_fit jobs waiting.")
        return

    batch_dir = os.path.join("batches", date.today().isoformat())
    os.makedirs(batch_dir, exist_ok=True)
    print(f"\nBuilding a batch of {len(to_process)} job(s) in {batch_dir}/\n")

    links = []
    for job_id, job in to_process:
        success = process_one_job(job, batch_dir, candidate_info, bank_entries)
        if success:
            bs.set_job_status(state, job_id, "in_batch", batch_folder=batch_dir)
            links.append(f"{job['company_name']} -- {job['title']}: {job['url']}")
        else:
            bs.set_job_status(state, job_id, "failed_materials")
        bs.save_state(state)  # save after every job, not just at the end

    print(f"\n=== Batch complete: {len(links)} of {len(to_process)} succeeded ===")
    print(f"Folder: {batch_dir}\n")
    print("Application portal links:")
    for link in links:
        print(f"  {link}")


if __name__ == "__main__":
    main()
