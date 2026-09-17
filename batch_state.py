"""
Tracks per-job status across batches, so a job that's already been judged
(match or reject) or already went into a past batch is never re-processed
or re-billed on a later run.

State file: state/batch_state.json
{
  "jobs": {
    "<job_url>": {
      "status": "judged_reject" | "judged_fit" | "in_batch" |
                 "failed_materials" | "failed_form_scan",
      "company_name": str, "title": str, "url": str, "ats": str, "board_token": str,
      "first_seen": iso timestamp, "last_updated": iso timestamp,
      "batch_folder": str (only once status == "in_batch")
    }
  }
}

Deliberately much smaller than job-finder's auto_apply_state.json -- no
daily cap (nothing here submits anything), no pending_answer/Telegram
fields (no live form-filling or escalation happens in this project, only
scanning + generation of files for you to review by hand).
"""
import json
import os
from datetime import datetime, timezone

STATE_PATH = os.path.join(os.path.dirname(__file__), "state", "batch_state.json")

TERMINAL_STATUSES = {"judged_reject", "in_batch", "failed_materials", "failed_form_scan"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"jobs": {}}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_job_status(state: dict, job_id: str):
    job = state["jobs"].get(job_id)
    return job["status"] if job else None


def set_job_status(state: dict, job_id: str, status: str, **fields):
    existing = state["jobs"].get(job_id, {})
    job = {
        "status": status,
        "first_seen": existing.get("first_seen", _now_iso()),
        "last_updated": _now_iso(),
    }
    job.update(fields)
    # Carry over batch_folder once set, same as job-finder carries over
    # job_specific_answers -- a later status update (e.g. re-marking after
    # a manual submit) shouldn't silently lose where the files already are.
    if "batch_folder" in existing and "batch_folder" not in fields:
        job["batch_folder"] = existing["batch_folder"]
    state["jobs"][job_id] = job


def jobs_with_status(state: dict, status: str) -> list:
    return [(jid, j) for jid, j in state["jobs"].items() if j.get("status") == status]
