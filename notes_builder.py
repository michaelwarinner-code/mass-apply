"""
The actual question-to-answer resolution logic for the notes file, factored
out so both 06_notes.py (standalone stage test) and make_batch.py (real
run) call the exact same logic instead of two independently-drifting
copies.
"""
import json
import os
import re

from answer_bank import match_question
from company_question_classifier import is_company_specific_question

CANDIDATE_INFO_PATH = os.path.join(os.path.dirname(__file__), "state", "candidate_info.json")

# Same mapping job-finder's form-filling logic uses -- kept in sync by
# hand, no shared source between the two repos.
IDENTITY_KEYWORD_MAP = [
    (re.compile(r"first name", re.I), "first_name"),
    (re.compile(r"last name", re.I), "last_name"),
    (re.compile(r"\bname\b", re.I), "full_name"),
    (re.compile(r"e-?mail", re.I), "email"),
    (re.compile(r"phone", re.I), "phone"),
    (re.compile(r"linkedin", re.I), "linkedin_url"),
    (re.compile(r"website|portfolio(?!\s+compan)", re.I), "website_url"),
    (re.compile(r"location|city", re.I), "location_city"),
    (re.compile(r"country", re.I), "country"),
    (re.compile(r"school|university|college", re.I), "school"),
    (re.compile(r"degree", re.I), "degree"),
    (re.compile(r"pronoun", re.I), "pronouns"),
]

PLACEHOLDER = "[NOT YET ANSWERED -- write your own here]"


def load_candidate_info() -> dict:
    if not os.path.exists(CANDIDATE_INFO_PATH):
        return {}
    with open(CANDIDATE_INFO_PATH, encoding="utf-8") as f:
        return json.load(f)


def resolve_answer(question: str, candidate_info: dict, bank_entries: list, company_name: str) -> str:
    for pattern, key in IDENTITY_KEYWORD_MAP:
        if pattern.search(question):
            if key == "full_name":
                return f'{candidate_info.get("first_name", "")} {candidate_info.get("last_name", "")}'.strip() or PLACEHOLDER
            return candidate_info.get(key, "") or PLACEHOLDER

    if not is_company_specific_question(question, company_name) and bank_entries:
        idx, answer = match_question(question, bank_entries)
        if answer:
            return answer

    return PLACEHOLDER


def build_notes_text(fields: list, candidate_info: dict, bank_entries: list, company_name: str) -> str:
    lines = []
    for f in fields:
        if f["field_type"] == "file":
            continue  # Resume/Cover Letter uploads -- nothing to write in a text notes file
        question = f.get("group_question") or f["question"]
        answer = resolve_answer(question, candidate_info, bank_entries, company_name)
        lines.append(f"Q: {question}")
        if f.get("options"):
            lines.append(f"   (options: {', '.join(f['options'])})")
        lines.append(f"A: {answer}")
        lines.append("")
    return "\n".join(lines)
