"""
Stage 5, standalone: given one job's URL, generates materials and builds
ONLY the cover letter PDF -- resume is generated too (same one API call
as stage 4), but discarded here. Saves to test_output/, doesn't touch
batch_state.json or any batch folder.

    python 05_coverletter.py "<job url>" [--company "Real Company Name"]
"""
import argparse
import os

from job_lookup import fetch_job_by_url
from materials_writer import generate_materials
from pdf_builder import build_resume_and_coverletter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--company", default=None, help="Override the display company name (defaults to the board token, title-cased)")
    args = parser.parse_args()

    job = fetch_job_by_url(args.url, company_name=args.company)
    print(f"Generating cover letter for: {job['company_name']} -- {job['title']}")

    resume_data, coverletter_data = generate_materials(job["description"], job["company_name"], job["title"])

    out_dir = os.path.join("test_output", "05_coverletter")
    _, cl_pdf = build_resume_and_coverletter(resume_data, coverletter_data, out_dir)
    print(f"\nCover letter built: {cl_pdf}")


if __name__ == "__main__":
    main()
