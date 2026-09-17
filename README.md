# mass-apply

Local CLI tool that generates a batch of up to 10 fully-prepared job
applications -- tailored resume, cover letter, and a notes file with every
application question answered -- as local files for you to review and
submit by hand. Built as a spinoff of the job-finder repo's auto-apply
pipeline, after Ashby's anti-bot detection flagged a fully automated
headless submission as spam.

Nothing here submits an application or touches a real browser beyond a
read-only scan of each posting's form. Everything it produces is a file on
your own disk.

## One-time setup

1. **Python deps**: `pip install -r requirements.txt`
2. **Playwright's browser**: `python -m playwright install chromium`
3. **Node deps** (for the resume/cover-letter PDF builder):
   ```
   cd resume-builder
   npm install
   cd ..
   ```
4. **LibreOffice**: needs to be installed for the DOCX-to-PDF conversion step.
   Defaults to `C:\Program Files\LibreOffice\program\soffice.exe` on Windows
   (standard install location -- if you installed it there, nothing else to
   do). Otherwise set `SOFFICE_PATH` to wherever `soffice`/`soffice.exe`
   actually is.
5. **Environment variables** (Windows CMD: `set VAR=value`; PowerShell:
   `$env:VAR="value"`):
   ```
   MASSAPPLY_ANTHROPIC_API_KEY=<your Anthropic API key>
   FANTASTIC_JOBS_API_KEY=<your RapidAPI key for the Fantastic Jobs aggregator>
   ```
6. **`state/candidate_info.json`** (gitignored, local only) -- copy this
   from job-finder's own local copy, or build it fresh using
   `state/candidate_info.example.json` as the shape to fill in.
7. **Google Sheets credentials** (gitignored, local only) -- copy
   `client_secret.json` and `token.json` from job-finder's local copy into
   this repo's root. Same underlying Google Sheet (`SPREADSHEET_ID` in
   `sheets_logger.py` is already set to the same one job-finder uses), so
   the same OAuth token works here too.

## Testing each stage on its own

Each of these can be run and checked independently before trusting the
full pipeline:

```
python 01_discover.py                              # raw postings from the aggregator, no filtering
python 02_keyword_filter.py                         # + free local keyword pre-filter
python 03_claude_judge.py [--limit 5]                # + Claude fit judge, full chain
python 04_resume.py "<job url>" [--company "Name"]   # resume PDF only, for one job
python 05_coverletter.py "<job url>" [--company "Name"]  # cover letter PDF only, for one job
python 06_notes.py "<job url>" [--company "Name"]    # notes.txt only (real scanned questions + best answers)
```

`--company` overrides the display company name for the single-job test
scripts (they don't have access to the aggregator's copy, since they fetch
directly from the ATS by URL) -- defaults to the board's URL slug,
title-cased, which is usually close enough for a quick test.

Test output goes to `test_output/` (gitignored), separate from any real
batch folder.

## Running a real batch

```
python make_batch.py [--batch-size 10]
```

For each job: creates `batches/<date>/<Company> -- <Title>/` containing
either a separate `Resume.pdf` + `Cover Letter.pdf`, or one
`Combined.pdf` (cover letter page 1, resume page 2) if the posting only
has a single upload slot, plus a `notes.txt` with every real application
question and its best available answer (a clear
`[NOT YET ANSWERED -- write your own here]` placeholder for anything with
no answer yet). Logs each job to the same Google Sheet job-finder uses.
Prints every application portal link at the end.

Re-running it later picks up where it left off -- `state/batch_state.json`
tracks every job already judged or already batched, so nothing gets
re-judged, re-billed, or duplicated into a second batch.

## What's NOT here yet

The "second-brain" answer generator (drafting real, in-your-own-voice
answers to open-ended questions, instead of the placeholder) is a planned
future addition, not built yet -- `notes_builder.py`'s `PLACEHOLDER`
constant is exactly where that would plug in.
