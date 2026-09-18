"""
Per-company cache for the broad-discovery Claude judge's tech-company
gate (see claude_judge_broad.py). Confirmed necessary: the judge decides
is_tech_company FRESH from each individual posting's own text, with
no memory of that same company's other postings -- since is_tech_company
is really a property of the COMPANY, not any one posting, this caused the
same company to get inconsistent verdicts across different postings
depending on how much product detail that specific posting's text
happened to include (worse for a company whose name the aggregator
mangles, e.g. "SpaceXAI" instead of "xAI").

Two tiers, checked in this order:
- Manual overrides (state/tech_company_overrides.json) -- hand-edit
  this directly for a company you know for a fact is or isn't
  tech-core; always wins, checked before ever asking the judge.
- Auto-learned cache (state/tech_company_learned.json) -- once ANY
  posting from a company gets a True verdict from the judge, that's
  trusted and applied to every OTHER posting from that same company too,
  this run and every future run. A False verdict is NEVER auto-learned
  this way -- the gate's own instructions lean toward false whenever a
  given posting's text is ambiguous, so a lone false is common and not
  very informative, while a genuine true is a stronger signal worth
  trusting company-wide.
"""
import json
import os

OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), "state", "tech_company_overrides.json")
LEARNED_PATH = os.path.join(os.path.dirname(__file__), "state", "tech_company_learned.json")


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def get_known_verdict(company_name: str):
    """Returns True/False if this company's tech-core status is
    already known (manual override wins over the learned cache), or None
    if it's never been resolved -- meaning the judge decides fresh this
    time, same as before this cache existed."""
    overrides = _load(OVERRIDES_PATH)
    if company_name in overrides:
        return bool(overrides[company_name])
    learned = _load(LEARNED_PATH)
    if company_name in learned:
        return bool(learned[company_name])
    return None


def record_verdict(company_name: str, is_tech: bool):
    """Only ever records a TRUE verdict -- see module docstring for why a
    lone False is never locked in this way."""
    if not is_tech:
        return
    learned = _load(LEARNED_PATH)
    if learned.get(company_name) is True:
        return
    learned[company_name] = True
    _save(LEARNED_PATH, learned)
