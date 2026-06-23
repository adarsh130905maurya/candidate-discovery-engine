"""
config.py — Shared configuration for the Candidate Discovery Engine.

WHAT THIS FILE DOES
-------------------
Every module in the project imports settings from here instead of hard-coding
values. That way, when we want to change the model name, the weights between
semantic vs behavioral scoring, or the number of candidates to output, we only
edit this ONE file.

HOW OTHER MODULES USE IT
------------------------
    from config import CONFIG, PATHS

    model_name = CONFIG["semantic_model"]
    data_path  = PATHS["candidates"]
"""

from pathlib import Path  # pathlib is the modern, cross-platform way to handle paths


# ----------------------------------------------------------------------------
# 1. PROJECT PATHS
# ----------------------------------------------------------------------------
# All paths are computed RELATIVE to the project root, so the project is
# portable — you can move the whole folder and everything still works.
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # .../candidate-discovery-engine/

PATHS = {
    # Input data (provided by the hackathon — do not modify these files)
    "candidates":        PROJECT_ROOT / "data" / "candidates.jsonl",
    "candidate_schema":  PROJECT_ROOT / "data" / "candidate_schema.json",
    "sample_candidates": PROJECT_ROOT / "data" / "sample_candidates.json",
    "job_description":   PROJECT_ROOT / "data" / "job_description.docx",
    "signals_doc":       PROJECT_ROOT / "data" / "redrob_signals_doc.docx",
    "submission_spec":   PROJECT_ROOT / "data" / "submission_spec.docx",
    "readme":            PROJECT_ROOT / "data" / "README.docx",

    # Output data (created by our code)
    "output_dir":        PROJECT_ROOT / "output",
    "docs_dir":          PROJECT_ROOT / "docs",
    "sample_5":          PROJECT_ROOT / "data" / "sample_5_candidates.json",
    "clean_cache":       PROJECT_ROOT / "output" / "clean_candidates.parquet",
}


# ----------------------------------------------------------------------------
# 2. SCORING MODEL CONFIG
# ----------------------------------------------------------------------------
# This is the brain of the system. The final score for each candidate is:
#
#     final_score = semantic_weight   * semantic_match_score
#                 + behavioral_weight * behavioral_score
#
# The weights below are our starting point. Person 3 (Signal Mixer) may tune
# these after experiments. They must always sum to 1.0.
CONFIG = {
    # --- Semantic model (Person 2) ---
    # all-MiniLM-L6-v2 is small (~80MB), fast on CPU, and good for short
    # document matching. It's the standard choice for CPU-only projects.
    "semantic_model": "sentence-transformers/all-MiniLM-L6-v2",

    # --- Score combination weights (Person 3) ---
    "semantic_weight":     0.7,   # How much we trust the resume/JD text match
    "behavioral_weight":   0.3,   # How much we trust engagement/activity signals

    # --- Output (Person 4) ---
    # The hackathon requires EXACTLY the top 100 candidates in the CSV.
    "top_k": 100,

    # --- Compute constraints (from submission_spec.docx Section 3) ---
    # These are hard limits enforced by the hackathon at Stage 3. Keep them
    # here so every module can self-check.
    "max_runtime_minutes": 5,
    "max_ram_gb":          16,
    "cpu_only":            True,
    "network_allowed":     False,

    # --- Data loading ---
    # candidates.jsonl is 487 MB / ~100,000 lines. We stream it line-by-line
    # to avoid loading everything into RAM at once.
    "candidates_encoding": "utf-8",
    "max_candidates_debug": None,  # Set to e.g. 1000 during development to go fast

    # --- The candidate_id format (from candidate_schema.json) ---
    "candidate_id_pattern": r"^CAND_[0-9]{7}$",
}


# ----------------------------------------------------------------------------
# 3. BEHAVIORAL SIGNALS (from redrob_signals_doc.docx)
# ----------------------------------------------------------------------------
# These are the 23 platform-activity signals under each candidate's
# `redrob_signals` object. Person 3 (Signal Mixer) scores these. We list them
# here so data_cleaner.py knows exactly which fields to extract as behavioral
# data (vs. profile text that Person 2 embeds).
#
# IMPORTANT: skill_assessment_scores and expected_salary_range_inr_lpa are
# nested objects, not scalars. The data_cleaner flattens them into separate
# columns (see BEHAVIORAL_NESTED below).
BEHAVIORAL_SCALAR_SIGNALS = [
    # (signal_name, type_hint) — type_hint helps the cleaner cast values
    ("profile_completeness_score", "float"),   # 0-100
    ("open_to_work_flag",          "bool"),    # True/False
    ("profile_views_received_30d", "int"),     # >= 0
    ("applications_submitted_30d", "int"),     # >= 0
    ("recruiter_response_rate",    "float"),   # 0.0-1.0
    ("avg_response_time_hours",    "float"),   # >= 0
    ("connection_count",           "int"),     # >= 0
    ("endorsements_received",      "int"),     # >= 0
    ("notice_period_days",         "int"),     # 0-180
    ("preferred_work_mode",        "str"),     # onsite/hybrid/remote/flexible
    ("willing_to_relocate",        "bool"),    # True/False
    ("github_activity_score",      "float"),   # -1 to 100 (-1 = no GitHub)
    ("search_appearance_30d",      "int"),     # >= 0
    ("saved_by_recruiters_30d",    "int"),     # >= 0
    ("interview_completion_rate",  "float"),   # 0.0-1.0
    ("offer_acceptance_rate",      "float"),   # -1 to 1.0 (-1 = no history)
    ("verified_email",             "bool"),    # True/False
    ("verified_phone",             "bool"),    # True/False
    ("linkedin_connected",         "bool"),    # True/False
]

# Nested signals that we flatten into their own columns for Person 3.
BEHAVIORAL_NESTED_SIGNALS = {
    # source path inside redrob_signals -> flattened column name
    "signup_date":                       "signup_date",        # ISO date string
    "last_active_date":                  "last_active_date",   # ISO date string
    "expected_salary_range_inr_lpa.min": "expected_salary_min_lpa",
    "expected_salary_range_inr_lpa.max": "expected_salary_max_lpa",
}

# skill_assessment_scores is a dict[str, float]; we keep it as-is (a dict)
# because the keys vary per candidate. Person 3 can average or pick relevant ones.


# ----------------------------------------------------------------------------
# 4. CONVENIENCE: list every behavioral signal name (scalar + nested)
# ----------------------------------------------------------------------------
ALL_BEHAVIORAL_SIGNALS = (
    [name for name, _ in BEHAVIORAL_SCALAR_SIGNALS]
    + list(BEHAVIORAL_NESTED_SIGNALS.values())
)


# ----------------------------------------------------------------------------
# 5. SELF-TEST — runs only when you execute this file directly
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("CONFIG SELF-TEST")
    print("=" * 60)
    print(f"Project root: {PROJECT_ROOT}")

    # Check that the data files actually exist where we think they do
    print("\nData files present:")
    for label, p in PATHS.items():
        if label in ("output_dir", "docs_dir", "sample_5", "clean_cache"):
            continue  # these are outputs, not required inputs yet
        status = "OK " if p.exists() else "MISSING"
        print(f"  [{status}] {label}: {p.name}")

    # Check weights sum to 1.0
    w_sum = CONFIG["semantic_weight"] + CONFIG["behavioral_weight"]
    print(f"\nWeights: semantic={CONFIG['semantic_weight']}, "
          f"behavioral={CONFIG['behavioral_weight']}, sum={w_sum}")
    assert abs(w_sum - 1.0) < 1e-6, "Weights must sum to 1.0!"

    print(f"\nBehavioral signals tracked: {len(ALL_BEHAVIORAL_SIGNALS)}")
    print("  " + ", ".join(ALL_BEHAVIORAL_SIGNALS))
    print("\nConfig looks good.")
