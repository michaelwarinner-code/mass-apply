"""
Shared "given a company/title/url/description, build the folder" logic --
used by make_batch.py (auto discovery) and manual_batch.py (hand-pasted
postings, for when the discovery API is out of quota or unavailable) so
a manually-sourced job ends up producing an identical folder to an
automatically-discovered one: separate resume + cover letter PDFs, a
notes.txt with just the company/title/portal link, and a row logged to
the same Google Sheet job-finder uses.

Folder-naming (safe_folder_name/_job_id_from_url) lives here too since
both callers need the same same-company+same-title collision handling.
"""
import os
import re
from datetime import date

from materials_writer import generate_materials
from pdf_builder import build_resume_and_coverletter
from sheets_logger import append_application_row

_USED_FOLDER_NAMES = set()


def _job_id_from_url(url: str) -> str:
    m = re.search(r'/jobs/([A-Za-z0-9]+)', url)
    return m.group(1) if m else str(abs(hash(url)) % 10000)


def safe_folder_name(company: str, title: str, url: str = "") -> str:
    # Strip characters that are illegal (Windows) or just awkward in a
    # folder name, keep it readable. When two different postings share
    # the same company+title (e.g. the same role open in two cities),
    # tag the job's id from its URL onto the folder name so they don't
    # collide -- a collision here isn't just cosmetic: the second job's
    # PDF build tries to rename into a file the first job already
    # created, which crashes on Windows and silently loses that job's
    # materials for the run.
    raw = f"{company} -- {title}".strip()
    base = re.sub(r'[\\/*?:"<>|]', "", raw)[:150]
    name = base
    if name in _USED_FOLDER_NAMES:
        job_id = _job_id_from_url(url)
        suffix = f" ({job_id})"
        name = base[:150 - len(suffix)] + suffix
    _USED_FOLDER_NAMES.add(name)
    return name


def build_job_folder(company: str, title: str, url: str, description: str, job_dir: str) -> bool:
    """Generates materials, builds PDFs, writes notes.txt, and logs to
    Sheets for one job into job_dir. Returns True on success. A Sheets
    logging failure is loud but non-fatal -- an otherwise-complete folder
    shouldn't be lost over a Sheets hiccup."""
    os.makedirs(job_dir, exist_ok=True)

    try:
        print("  Generating materials...")
        resume_data, coverletter_data = generate_materials(description, company, title)
    except Exception as e:
        print(f"  Materials generation FAILED: {e}")
        return False

    try:
        print("  Building separate resume + cover letter PDFs...")
        resume_pdf, cl_pdf = build_resume_and_coverletter(resume_data, coverletter_data, job_dir)
        os.rename(resume_pdf, os.path.join(job_dir, "michael_warinner_resume.pdf"))
        os.rename(cl_pdf, os.path.join(job_dir, "michael_warinner_cover_letter.pdf"))
    except Exception as e:
        print(f"  PDF build FAILED: {e}")
        return False

    notes_header = f"{company} -- {title}\nApplication portal: {url}\n"
    with open(os.path.join(job_dir, "notes.txt"), "w", encoding="utf-8") as f:
        f.write(notes_header)

    try:
        append_application_row(date.today().isoformat(), title, company, description, job_url=url)
    except Exception as e:
        print(f"  WARNING: could not log to Google Sheets: {e}")

    print(f"  Done -- {job_dir}")
    return True
