"""
Cheap, free, local pre-filter. Runs on every new posting BEFORE any Claude API call.
This filter's only job is to reject postings from CLEARLY unrelated departments
(engineering, legal, warehouse ops, HR/recruiting, finance, hardware, etc.) -- it should
NOT try to judge fit precisely. The real nuance (seniority, stretch-ability, whether it's
the right flavor of marketing/sales) is Claude's job downstream, not this filter's.
"""
import re

POSITIVE_SIGNALS = [
    "product marketing", "growth marketing", "performance marketing",
    "lifecycle marketing", "go-to-market", "gtm", "brand marketing",
    "marketing manager", "marketing associate", "marketing specialist",
    "growth associate", "growth analyst", "marketing analyst",
    "consumer marketing", "customer marketing", "retention marketing",
    "growth", "marketing", "campaign", "demand generation", "demand gen",
    "revenue", "sales", "business development", "account executive",
    "account manager", "partnerships", "commercial", "customer success",
    "growth strategist", "revenue operations", "revops", "client partner",
    "campaign operations", "integrated marketing", "lifecycle", "retention marketing"
]

# Reject even if a positive signal above also matches -- explicit exclusions
# and unrelated departments that occasionally trip a coincidental word match
# (e.g. "Sales Tax Accountant" contains "sales" but is a finance role).
HARD_EXCLUDE = [
    "senior director", "vp,", "vice president", "svp", "evp",
    "principal", "head of", "chief marketing officer", "cmo",
    "event marketing", "events marketing", "event manager", "events manager",
    "social media manager", "social media specialist", "social media coordinator",
    "copywriter", "copywriting", "creative director",
    "software engineer", "hardware engineer", "electrical engineer",
    "mechanical engineer", "optical engineer", "machine learning engineer",
    "data engineer", "reliability", "manufacturing", "warehouse",
    "forklift", "maintenance mechanic", "maintenance technician",
    "production operator", "production machine operator",
    "recruiter", "recruiting", "talent acquisition", "immigration",
    "paralegal", "counsel", "attorney", "legal",
    "accountant", "accounting", "bookkeeper",
    "executive assistant", "environmental health", "safety specialist",
    "human factors", "supply chain", "logistics coordinator", "chief"
]

# Word-boundary, not substring -- a plain "intern" in HARD_EXCLUDE above would
# also reject "International Marketing Manager" (contains "intern" as a
# substring of "international"), which is a real title, not an internship.
INTERN_PATTERN = re.compile(r"\bintern(ship)?\b", re.IGNORECASE)

# Standalone "VP" anywhere in the title -- word-boundary, not the old
# comma-specific "vp," entry in HARD_EXCLUDE (still there, harmless overlap),
# which missed a real posting titled "VP Product Marketing - Global" (no
# comma right after "VP") and let it through to the judge.
VP_PATTERN = re.compile(r"\bvp\b", re.IGNORECASE)

# "Senior" and "Manager" BOTH present, regardless of order/distance between
# them -- deliberately blocks this combination even for a compound
# functional title (e.g. "Senior Product Marketing Manager", "Senior
# Customer Success Manager"), which the downstream Claude judge otherwise
# treats as a legitimate IC title. This is a stricter, explicit override of
# that nuance, not an oversight -- if a genuinely good compound-title role
# ever gets missed because of this, that's the deliberate tradeoff being
# made here.
SENIOR_PATTERN = re.compile(r"\bsenior\b", re.IGNORECASE)
MANAGER_PATTERN = re.compile(r"\bmanager\b", re.IGNORECASE)


def passes_keyword_filter(title: str, company_key: str) -> bool:
    t = title.lower()

    if INTERN_PATTERN.search(t):
        return False

    if VP_PATTERN.search(t):
        return False

    if SENIOR_PATTERN.search(t) and MANAGER_PATTERN.search(t):
        return False

    if any(bad in t for bad in HARD_EXCLUDE):
        return False

    if company_key == "cocacola":
        return "marketing" in t or "sales" in t or "brand" in t

    return any(kw in t for kw in POSITIVE_SIGNALS)
