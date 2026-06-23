"""
data_cleaner.py — Flatten, clean & enrich candidate data.

============================================================================
WHAT THIS MODULE DOES (written for non-technical teammates)
============================================================================
`data_loader.py` gives us raw candidate dicts that look like this:

    {
      "candidate_id": "CAND_0000001",
      "profile": { "headline": "...", "summary": "...", ... },         # nested dict
      "career_history": [ { "company": "...", ... }, ... ],            # list of dicts
      "skills":         [ { "name": "Python", "proficiency": "...", ... } ],
      "redrob_signals": { "profile_completeness_score": 86.9, ... }    # nested dict
    }

That nesting is hard for the AI model (Person 2) and for the scoring
code (Person 3) to work with. So this module:

  1. FLATTENS the nesting into simple columns:
        - profile.headline          ->  headline           (string column)
        - skills[].name             ->  skills_text        (comma-joined)
        - redrob_signals.*          ->  one column per signal
        - redrob_signals.expected_salary_range_inr_lpa.min -> expected_salary_min_lpa

  2. CLEANS the data:
        - missing text  -> ""           (empty string)
        - missing numbers-> 0
        - HTML tags stripped, whitespace trimmed

  3. BUILDS profile_text  — ONE big text string per candidate that merges
     headline + summary + skills + experience + education. THIS is what
     Person 2's sentence-transformers model will embed & compare to the JD.

  4. EXTRACTS behavioral data  — a clean {candidate_id: {signal: value}}
     dictionary that Person 3 will turn into a behavioral score.

  5. EXPORTS a 5-candidate sample (data/sample_5_candidates.json) that
     the whole team can use for quick tests without loading 487 MB.

============================================================================
THE CONTRACT — functions Persons 2, 3, 4 import from here
============================================================================
    from data_cleaner import get_clean_candidates      # -> DataFrame
    from data_cleaner import get_candidate_profiles    # -> {id: profile_text}
    from data_cleaner import get_behavioral_data       # -> {id: {signal: value}}
    from data_cleaner import get_candidate_ids         # -> [id, id, ...]

============================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Make `src/` importable so we can find sibling modules
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from config import (  # noqa: E402
    CONFIG,
    PATHS,
    BEHAVIORAL_SCALAR_SIGNALS,
    BEHAVIORAL_NESTED_SIGNALS,
    ALL_BEHAVIORAL_SIGNALS,
)
from data_loader import load_candidates  # noqa: E402


# ============================================================================
# CONSTANTS
# ============================================================================
# A small regex to strip HTML tags like <b>foo</b> -> foo
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Skill proficiency ranking — used to weight a candidate's claimed skills.
# Person 3 may want to down-weight "expert" claims that aren't backed by
# duration_months or endorsements (a known keyword-stuffer trap).
_PROFICIENCY_RANK = {
    "beginner":     1,
    "intermediate": 2,
    "advanced":     3,
    "expert":       4,
}

# Scalar signal names only (drop the type hint tuples from config)
_SCALAR_SIGNAL_NAMES = [name for name, _ in BEHAVIORAL_SCALAR_SIGNALS]

# Text columns we KNOW are scalar strings in the profile dict.
# Anything here goes into profile_text. We use a wide net so even if a
# field is empty for some candidate, we just join "".
_PROFILE_TEXT_FIELDS = [
    "headline", "summary", "location", "country",
    "current_title", "current_company", "current_company_size",
    "current_industry",
]


# ============================================================================
# 1. SMALL HELPERS
# ============================================================================
def _clean_text(value: Any) -> str:
    """
    Normalize a value into a clean string:
      - None / NaN -> ""
      - strip leading/trailing whitespace
      - collapse runs of whitespace to single spaces
      - strip HTML tags
    """
    if value is None:
        return ""
    # Detect pandas NaN without importing the sentinel explicitly
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass  # pd.isna blows up on lists/dicts — that's fine, fall through

    text = str(value)
    text = _HTML_TAG_RE.sub("", text)          # drop HTML tags
    text = re.sub(r"\s+", " ", text).strip()    # collapse whitespace
    return text


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert value to float, returning `default` if it can't be parsed."""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Convert value to int (via float first to handle 5.0-style JSON numbers)."""
    return int(_safe_float(value, default))


# ============================================================================
# 2. FLATTEN A SINGLE CANDIDATE RECORD
# ============================================================================
def flatten_candidate(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn ONE nested candidate dict into a flat dict with simple columns.

    The output is one row of the cleaned DataFrame. Example output keys:
        candidate_id, anonymized_name, headline, summary, location, country,
        years_of_experience, current_title, current_company, ...,
        skills_text, skills_count, skills_top_names, ...,
        experience_text, education_text, certifications_text, languages_text,
        profile_text,
        <23 behavioral signal columns>,
        is_honeypot_suspect  (bool — see detect_honeypot)
    """
    row: Dict[str, Any] = {}
    row["candidate_id"] = record.get("candidate_id", "")

    # ---- profile.* (flatten one level) ----
    profile = record.get("profile") or {}
    for key in _PROFILE_TEXT_FIELDS:
        row[key] = _clean_text(profile.get(key, ""))
    # Numeric profile fields
    row["years_of_experience"] = _safe_float(profile.get("years_of_experience"))
    row["anonymized_name"] = _clean_text(profile.get("anonymized_name"))

    # ---- career_history -> one text blob + a few stats ----
    career = record.get("career_history") or []
    career_lines: List[str] = []
    total_exp_months = 0
    for job in career:
        company = _clean_text(job.get("company"))
        title = _clean_text(job.get("title"))
        desc = _clean_text(job.get("description"))
        industry = _clean_text(job.get("industry"))
        dur = _safe_int(job.get("duration_months"))
        total_exp_months += dur
        if title or company:
            career_lines.append(
                f"{title} @ {company} ({industry}, {dur} months): {desc}"
            )
    row["experience_text"] = "\n".join(career_lines)
    row["career_job_count"] = len(career)
    row["career_total_months"] = total_exp_months

    # ---- skills -> comma-joined text + count + "top" names ----
    skills = record.get("skills") or []
    skill_names: List[str] = []
    skill_details: List[str] = []
    for sk in skills:
        name = _clean_text(sk.get("name"))
        if not name:
            continue
        skill_names.append(name)
        prof = _clean_text(sk.get("proficiency"))
        endo = _safe_int(sk.get("endorsements"))
        dur = _safe_int(sk.get("duration_months"))
        skill_details.append(f"{name} ({prof}, {endo} endorsements, {dur}mo)")

    row["skills_text"] = ", ".join(skill_names)
    row["skills_count"] = len(skill_names)
    # Top 10 — helps Person 4 write the "reasoning" column
    row["skills_top_names"] = ", ".join(skill_names[:10])
    row["skills_details_text"] = "; ".join(skill_details)

    # ---- education -> text blob ----
    education = record.get("education") or []
    edu_lines: List[str] = []
    edu_top_tier = "unknown"
    for ed in education:
        inst = _clean_text(ed.get("institution"))
        degree = _clean_text(ed.get("degree"))
        field = _clean_text(ed.get("field_of_study"))
        tier = _clean_text(ed.get("tier"))
        line_parts = [p for p in [degree, field, inst] if p]
        edu_lines.append(" ".join(line_parts) + (f" [{tier}]" if tier else ""))
    row["education_text"] = "\n".join(edu_lines)
    row["education_count"] = len(education)

    # ---- certifications & languages (often empty — that's fine) ----
    certs = record.get("certifications") or []
    row["certifications_text"] = "; ".join(
        _clean_text(c.get("name")) for c in certs if _clean_text(c.get("name"))
    )
    row["certifications_count"] = len(certs)

    langs = record.get("languages") or []
    row["languages_text"] = ", ".join(
        _clean_text(l.get("language")) for l in langs if _clean_text(l.get("language"))
    )
    row["languages_count"] = len(langs)

    # ---- behavioral signals (23 of them) ----
    signals = record.get("redrob_signals") or {}
    # Scalar signals
    for name in _SCALAR_SIGNAL_NAMES:
        row[name] = signals.get(name, None)
    # Nested signals -> flattened column names from config
    for source_path, flat_name in BEHAVIORAL_NESTED_SIGNALS.items():
        # source_path uses dots, e.g. "expected_salary_range_inr_lpa.min"
        node: Any = signals
        for part in source_path.split("."):
            if isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
                break
        row[flat_name] = node

    # skill_assessment_scores stays a dict (variable keys per candidate)
    row["skill_assessment_scores"] = signals.get("skill_assessment_scores", {}) or {}

    # ---- honeypot detection flag (early warning for Person 3) ----
    row["is_honeypot_suspect"] = detect_honeypot(record)

    # ---- COMBINED profile_text — the single most important field ----
    row["profile_text"] = build_profile_text(row, record)
    return row


# ============================================================================
# 3. BUILD profile_text
# ============================================================================
def build_profile_text(row: Dict[str, Any], record: Dict[str, Any]) -> str:
    """
    Merge the important free-text fields into ONE string per candidate.

    This is the text Person 2 embeds with sentence-transformers and compares
    to the job description. We deliberately DON'T include behavioral numbers
    here — those are a separate signal (Person 3's job).

    Design choice: include structured fields as labeled lines so the model
    sees "Title: Senior ML Engineer" not just "Senior ML Engineer". Labels
    give the embedding model helpful context.
    """
    parts: List[str] = []

    # Headline + summary first — they're the densest signal about who the
    # candidate is.
    if row["headline"]:
        parts.append(f"Headline: {row['headline']}")
    if row["summary"]:
        parts.append(f"Summary: {row['summary']}")

    # Current role
    if row["current_title"] or row["current_company"]:
        parts.append(
            f"Current role: {row['current_title']} at {row['current_company']} "
            f"({row['current_industry']}, {row['current_company_size']})"
        )

    # Experience — full career history descriptions
    if row["experience_text"]:
        parts.append("Experience:\n" + row["experience_text"])

    # Skills — include the detailed list with proficiency + duration
    if row["skills_details_text"]:
        parts.append("Skills: " + row["skills_details_text"])

    # Education
    if row["education_text"]:
        parts.append("Education: " + row["education_text"].replace("\n", " | "))

    # Certifications & languages (lighter weight — often empty)
    if row["certifications_text"]:
        parts.append("Certifications: " + row["certifications_text"])
    if row["languages_text"]:
        parts.append("Languages: " + row["languages_text"])

    # Years of experience as a number line (the model benefits from this)
    yoe = row.get("years_of_experience")
    if yoe:
        parts.append(f"Total years of experience: {yoe}")

    return "\n".join(parts).strip()


# ============================================================================
# 4. HONEYPOT DETECTION
# ============================================================================
def detect_honeypot(record: Dict[str, Any]) -> bool:
    """
    Heuristic flag for "subtly impossible" candidate profiles.

    Per redrob_signals_doc.docx Section 7, honeypots have profiles like:
      - "expert" in many skills with 0 months duration (lazy keyword stuffing)
      - years_of_experience inconsistent with career_history total
      - worked at a company for longer than possible

    We DON'T try to catch every honeypot — the spec says "a good ranking
    system should naturally avoid them". This flag is just an early-warning
    helper for Person 3 to optionally down-weight. False positives are OK.

    Returns:
        True if any obvious red flag is found.
    """
    skills = record.get("skills") or []
    # Red flag 1: many "expert" skills with little/no duration
    expert_zero_duration = 0
    for sk in skills:
        if _clean_text(sk.get("proficiency")) == "expert" \
                and _safe_int(sk.get("duration_months")) == 0:
            expert_zero_duration += 1
    if expert_zero_duration >= 5:  # 5+ "expert" skills never actually used
        return True

    # Red flag 2: claimed experience wildly exceeds career history sum
    profile = record.get("profile") or {}
    claimed_yoe = _safe_float(profile.get("years_of_experience"))
    career = record.get("career_history") or []
    career_total_months = sum(_safe_int(j.get("duration_months")) for j in career)
    # 1 year = 12 months. Allow generous slack (some history may be omitted).
    if claimed_yoe > 0 and career_total_months > 0:
        career_years = career_total_months / 12.0
        if claimed_yoe > career_years + 10:  # >10yr gap is suspicious
            return True

    return False


# ============================================================================
# 5. CLEAN NUMERIC / BOOL COLUMNS
# ============================================================================
def _coerce_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast the 23 behavioral columns to their proper types and fill nulls.

    This is important because Person 3 will do math on these — a None would
    crash their code. We default:
      - numbers -> 0.0  (or the signal's natural "missing" sentinel, e.g.
                          github_activity_score = -1 means "no GitHub")
      - bools   -> False
      - strings -> ""
    """
    for name, kind in BEHAVIORAL_SCALAR_SIGNALS:
        if name not in df.columns:
            continue
        col = df[name]
        if kind == "bool":
            df[name] = col.astype("boolean").fillna(False)
        elif kind == "int":
            df[name] = col.apply(lambda v: _safe_int(v, 0))
        elif kind == "float":
            df[name] = col.apply(lambda v: _safe_float(v, 0.0))
        elif kind == "str":
            df[name] = col.fillna("").astype(str)

    # Nested-derived columns
    for flat_name in BEHAVIORAL_NESTED_SIGNALS.values():
        if flat_name not in df.columns:
            continue
        if flat_name.endswith("_lpa"):
            df[flat_name] = df[flat_name].apply(lambda v: _safe_float(v, 0.0))
        # signup_date / last_active_date stay as strings (ISO dates)

    return df


# ============================================================================
# 6. PUBLIC API  (the functions Persons 2, 3, 4 import)
# ============================================================================
# Cache so repeated calls don't reload the whole file
_CLEAN_DF_CACHE: Optional[pd.DataFrame] = None


def get_clean_candidates(limit: Optional[int] = None,
                         use_cache: bool = True) -> pd.DataFrame:
    """
    Load + clean candidates. Returns a flat DataFrame with one row per
    candidate, including the all-important `profile_text` column.

    Columns include:
        - candidate_id
        - headline, summary, current_title, current_company, ...
        - skills_text, skills_count, skills_top_names
        - experience_text, career_total_months
        - education_text, certifications_text, languages_text
        - profile_text            <- Person 2 embeds this
        - <23 behavioral signals> <- Person 3 scores these
        - is_honeypot_suspect     <- early-warning flag

    Args:
        limit: optional cap on number of candidates (fast dev mode).
        use_cache: True = reuse the already-cleaned DataFrame on repeat calls.
    """
    global _CLEAN_DF_CACHE
    if use_cache and _CLEAN_DF_CACHE is not None and limit is None:
        return _CLEAN_DF_CACHE

    raw_df = load_candidates(limit=limit, validate=True)
    flat_rows = [flatten_candidate(rec) for rec in raw_df.to_dict(orient="records")]
    df = pd.DataFrame(flat_rows)
    df = _coerce_signal_columns(df)

    if limit is None:
        _CLEAN_DF_CACHE = df
    return df


def get_candidate_profiles(limit: Optional[int] = None) -> Dict[str, str]:
    """
    Return {candidate_id: profile_text} for Person 2 to embed.

    Only candidates with non-empty profile_text are included.
    """
    df = get_clean_candidates(limit=limit)
    out: Dict[str, str] = {}
    for cid, text in zip(df["candidate_id"], df["profile_text"]):
        if text and text.strip():
            out[cid] = text
    return out


def get_behavioral_data(limit: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """
    Return {candidate_id: {signal_name: value}} for Person 3 to score.

    Includes all 23 behavioral signals plus the honeypot flag.
    `skill_assessment_scores` is included as a nested dict (keys vary).
    """
    df = get_clean_candidates(limit=limit)
    out: Dict[str, Dict[str, Any]] = {}
    extra = ALL_BEHAVIORAL_SIGNALS + ["skill_assessment_scores", "is_honeypot_suspect"]
    for rec in df.to_dict(orient="records"):
        cid = rec["candidate_id"]
        out[cid] = {k: rec.get(k) for k in extra if k in rec}
    return out


def get_candidate_ids(limit: Optional[int] = None) -> List[str]:
    """Return the list of candidate_id values (in file order)."""
    df = get_clean_candidates(limit=limit)
    return df["candidate_id"].tolist()


# ============================================================================
# 7. SAMPLE EXPORT  (for the rest of the team)
# ============================================================================
def export_sample(n: int = 5, out_path: Optional[Path | str] = None) -> Path:
    """
    Save the first N cleaned candidates (all fields) as pretty JSON.

    Persons 2, 3, 4 use this to test their modules on real data without
    having to load the 487 MB file every time.
    """
    out_path = Path(out_path) if out_path else PATHS["sample_5"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = get_clean_candidates(limit=n)
    # to_json with orient='records' + indent gives clean, readable output
    records = json.loads(df.to_json(orient="records", force_ascii=False))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    return out_path


# ============================================================================
# 8. STANDALONE SUMMARY  (python src/data_cleaner.py)
# ============================================================================
def _main() -> int:
    parser = argparse.ArgumentParser(description="Clean & enrich candidate data.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N candidates (dev mode).")
    parser.add_argument("--sample", type=int, default=5,
                        help="How many candidates to dump to sample_5_candidates.json")
    args = parser.parse_args()

    print("=" * 72)
    print(" CANDIDATE DISCOVERY ENGINE — data_cleaner.py summary")
    print("=" * 72)

    print("\n[1/4] Cleaning candidates...")
    df = get_clean_candidates(limit=args.limit)
    print(f"   Cleaned rows: {len(df):,}")

    print(f"\n[2/4] profile_text stats:")
    text_lens = df["profile_text"].str.split().apply(len)
    print(f"   Min words:    {int(text_lens.min())}")
    print(f"   Avg words:    {text_lens.mean():.0f}")
    print(f"   Max words:    {int(text_lens.max())}")
    print(f"   Empty:        {int((text_lens == 0).sum())}")

    print(f"\n[3/4] Behavioral signals found: {len(ALL_BEHAVIORAL_SIGNALS)}")
    print("   " + ", ".join(ALL_BEHAVIORAL_SIGNALS))

    print(f"\n[4/4] Honeypot suspects flagged: "
          f"{int(df['is_honeypot_suspect'].sum())} / {len(df)}")

    # Export sample
    if args.sample > 0:
        out = export_sample(n=min(args.sample, len(df)))
        print(f"\nSample exported: {out}")
        print(f"   ({out.stat().st_size:,} bytes)")

    print("\n" + "=" * 72)
    print(" Done. Import these from other modules:")
    print("   from data_cleaner import (get_clean_candidates, get_candidate_profiles,")
    print("                             get_behavioral_data, get_candidate_ids)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
