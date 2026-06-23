"""
================================================================================
signal_scorer.py  —  Behavioral Signal Scorer  (Person 3 — Signal Mixer)
================================================================================

WHAT THIS FILE DOES (plain English):
------------------------------------
Each candidate has "behavioral" data — activity numbers like how often they
log in, how complete their profile is, how fast they reply to messages, etc.

These numbers are on totally different scales:
    - profile_completeness is 0 to 100 (a percentage)
    - avg_response_time_hours might be 0 to 200+
    - notice_period_days is 0 to 180

We can't average those directly (a 100 would drown out everything else).
So this module:

    1. Scales every signal to a clean 0.0 - 1.0 range  (MinMax scaling)
    2. Flips "lower is better" signals  (e.g. fast replies => high score)
    3. Takes a weighted average across all signals
    4. Returns ONE behavioral score per candidate (0.0 to 1.0)

SUPPORTS TWO DATA FORMATS (auto-detected):
------------------------------------------
- LEGACY test data:   login_count, profile_completeness, response_time_hours, ...
- REAL Person 1 data: profile_completeness_score, avg_response_time_hours,
                      notice_period_days, last_active_date, open_to_work_flag, ...

The module auto-detects which format it's looking at based on field names
and switches to the right weight/direction config. Both work.

REAL-DATA SPECIAL HANDLING:
- Sentinels: github_activity_score=-1 and offer_acceptance_rate=-1 mean
  "missing" (no GitHub / no offer history), NOT bad scores. These are
  treated as None (excluded from min/max, given neutral 0.5).
- Booleans: open_to_work_flag=True -> 1.0, False -> 0.0
- Dates: last_active_date="2026-05-20" -> "days since most recent" -> lower better

EXPORTED FUNCTIONS:
    - compute_behavioral_scores(...)   -> main one, returns {id: score}
    - get_signal_breakdown(...)        -> detailed per-signal view (debugging)
    - normalize_signal(...)            -> the 0-1 scaler (legacy, no None)
    - normalize_signal_robust(...)     -> the 0-1 scaler (handles None/sentinels)
    - scoring_summary(...)             -> quick stats on the final scores
================================================================================
"""

import logging
from datetime import datetime

# Logger for this module.
logger = logging.getLogger("signal_scorer")
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("  ⚠️  %(name)s: %(message)s"))
    logger.addHandler(handler)


# ============================================================================
# PART A — LEGACY TEST DATA (built-in, for standalone testing)
# These 5 fake candidates let us test WITHOUT Person 1's real files.
# CAND_004 is super active on every metric (should rank #1).
# CAND_002 is inactive everywhere     (should rank last).
# ============================================================================

TEST_BEHAVIORAL_DATA = {
    "CAND_001": {
        "login_count": 45,
        "profile_completeness": 92,
        "response_time_hours": 2,
        "days_since_last_active": 1,
        "applications_submitted": 12,
        "profile_views": 340,
        "skills_endorsed": 15,
    },
    "CAND_002": {
        "login_count": 3,
        "profile_completeness": 35,
        "response_time_hours": 120,
        "days_since_last_active": 90,
        "applications_submitted": 1,
        "profile_views": 20,
        "skills_endorsed": 2,
    },
    "CAND_003": {
        "login_count": 22,
        "profile_completeness": 78,
        "response_time_hours": 8,
        "days_since_last_active": 5,
        "applications_submitted": 7,
        "profile_views": 150,
        "skills_endorsed": 9,
    },
    "CAND_004": {
        "login_count": 60,
        "profile_completeness": 100,
        "response_time_hours": 1,
        "days_since_last_active": 0,
        "applications_submitted": 20,
        "profile_views": 500,
        "skills_endorsed": 25,
    },
    "CAND_005": {
        "login_count": 10,
        "profile_completeness": 55,
        "response_time_hours": 48,
        "days_since_last_active": 30,
        "applications_submitted": 3,
        "profile_views": 60,
        "skills_endorsed": 5,
    },
}

# Legacy direction + weights (for test data).
SIGNAL_DIRECTION = {
    "login_count": "higher",
    "profile_completeness": "higher",
    "response_time_hours": "lower",
    "days_since_last_active": "lower",
    "applications_submitted": "higher",
    "profile_views": "higher",
    "skills_endorsed": "higher",
}

SIGNAL_WEIGHTS = {
    "login_count": 0.10,
    "profile_completeness": 0.25,
    "response_time_hours": 0.20,
    "days_since_last_active": 0.20,
    "applications_submitted": 0.10,
    "profile_views": 0.05,
    "skills_endorsed": 0.10,
}


# ============================================================================
# PART B — REAL DATA CONFIG (Person 1's actual field names)
# Weights are JD-INFORMED: data_exploration.md says these signals matter most
# for the "Senior AI Engineer" role at Redrob AI.
#
# Key insight from the JD: "Active on Redrob / clearly in the job market" is
# just as important as skill match. So we weight availability signals heavily.
# ============================================================================

# Real field names from Person 1's data_cleaner.get_behavioral_data()
# Direction: "higher" = bigger is better, "lower" = smaller is better
REAL_SIGNAL_DIRECTION = {
    "profile_completeness_score": "higher",   # 0-100, effort invested
    "last_active_date":           "lower",    # ISO date -> days since; stale = unavailable
    "recruiter_response_rate":    "higher",   # 0.0-1.0, will they reply to us?
    "avg_response_time_hours":    "lower",    # >= 0, faster = more reachable
    "notice_period_days":         "lower",    # 0-180, JD wants < 30
    "open_to_work_flag":          "higher",   # bool, actively job-seeking
    "applications_submitted_30d": "higher",   # seeking intensity
    "saved_by_recruiters_30d":    "higher",   # market demand signal
    "endorsements_received":      "higher",   # credibility
    "search_appearance_30d":      "higher",   # visibility to recruiters
}

# JD-informed weights (sum to 1.0).
# Biggest weight goes to last_active_date (stale = disqualified per JD),
# recruiter_response_rate, and avg_response_time_hours.
REAL_SIGNAL_WEIGHTS = {
    "profile_completeness_score": 0.10,
    "last_active_date":           0.20,   # JD critical: >180 days = unavailable
    "recruiter_response_rate":    0.15,   # < 0.1 = won't reply to Redrob
    "avg_response_time_hours":    0.15,   # fast responders are reachable
    "notice_period_days":         0.10,   # JD wants < 30, > 90 is a problem
    "open_to_work_flag":          0.10,   # explicit job-seeking signal
    "applications_submitted_30d": 0.05,
    "saved_by_recruiters_30d":    0.05,
    "endorsements_received":      0.05,
    "search_appearance_30d":      0.05,
}

# Sentinel values: -1 means "missing" for these fields (NOT a bad score).
# github_activity_score = -1 -> no GitHub linked.
# offer_acceptance_rate = -1 -> no prior offer history.
SENTINEL_VALUES = {
    "github_activity_score": -1,
    "offer_acceptance_rate": -1,
}

# Boolean fields: convert True/False -> 1.0/0.0 before scaling.
BOOLEAN_FIELDS = {
    "open_to_work_flag",
    "willing_to_relocate",
    "verified_email",
    "verified_phone",
    "linkedin_connected",
}

# Date fields: convert ISO date string -> "days since most recent date".
DATE_FIELDS = {
    "last_active_date",
    "signup_date",
}

# Any field name that ONLY appears in the real data (not in legacy test data).
# Used for auto-detecting whether we're in real-data mode.
_REAL_ONLY_FIELDS = set(REAL_SIGNAL_DIRECTION.keys())


# ============================================================================
# PART C — VALUE PREPROCESSING (booleans, dates, sentinels -> clean floats)
# ============================================================================

def _preprocess_value(field_name, raw_value, reference_date=None):
    """
    Convert a raw signal value into a clean float (or None if missing).

    Handles the three special cases in real data:
    1. SENTINELS: github_activity_score=-1 -> None (means "no GitHub", not bad)
    2. BOOLEANS:  open_to_work_flag=True -> 1.0, False -> 0.0
    3. DATES:     last_active_date="2026-05-20" -> days since reference_date

    For ordinary numeric fields, just converts to float safely.

    Parameters
    ----------
    field_name : str
        The signal name (e.g. "open_to_work_flag", "last_active_date").
    raw_value : any
        The raw value from the candidate's data.
    reference_date : date or None
        Used for date fields. If None, computed from the data (most recent).

    Returns
    -------
    float or None
        Clean numeric value, or None if the value is a sentinel/missing.
    """
    import math

    # ---- Sentinel check: -1 on github_activity_score or offer_acceptance_rate ----
    if field_name in SENTINEL_VALUES and raw_value is not None:
        try:
            if float(raw_value) == SENTINEL_VALUES[field_name]:
                return None  # treated as missing, NOT as a bad score
        except (ValueError, TypeError):
            pass

    # ---- Boolean fields: True/False/"true"/1 -> 1.0, else 0.0 ----
    if field_name in BOOLEAN_FIELDS:
        if isinstance(raw_value, bool):
            return 1.0 if raw_value else 0.0
        if isinstance(raw_value, (int, float)):
            return 1.0 if raw_value != 0 else 0.0
        if isinstance(raw_value, str):
            return 1.0 if raw_value.strip().lower() in ("true", "1", "yes") else 0.0
        return 0.0

    # ---- Date fields: ISO string -> days since reference ----
    if field_name in DATE_FIELDS:
        if raw_value is None or raw_value == "":
            return None
        try:
            # Take just the date part (handles "2026-05-20" and ISO datetime).
            parsed = datetime.fromisoformat(str(raw_value)[:10]).date()
            if reference_date is None:
                # If no reference given, return the date ordinal (caller will fix).
                return float(parsed.toordinal())
            return float((reference_date - parsed).days)
        except (ValueError, TypeError):
            logger.warning("Could not parse date %r for field '%s'", raw_value, field_name)
            return None

    # ---- Ordinary numeric field ----
    if raw_value is None:
        return None
    try:
        f = float(raw_value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        logger.warning("Non-numeric value %r for field '%s' — treating as None",
                       raw_value, field_name)
        return None


def _compute_reference_date(candidates_data, date_field):
    """
    Find the most recent date in the dataset for a date field.
    Used as the "today" reference so the most active candidate = 0 days.
    Returns None if no valid dates found.
    """
    max_date = None
    for cid, signals in candidates_data.items():
        if not isinstance(signals, dict):
            continue
        raw = signals.get(date_field)
        if raw is None or raw == "":
            continue
        try:
            parsed = datetime.fromisoformat(str(raw)[:10]).date()
            if max_date is None or parsed > max_date:
                max_date = parsed
        except (ValueError, TypeError):
            continue
    return max_date


# ============================================================================
# PART D — SCALING FUNCTIONS
# ============================================================================

def normalize_signal(values, direction="higher"):
    """
    Legacy MinMax scaler. Does NOT handle None (treats them as 0.0).
    Kept for backward compatibility. For real data with sentinels/missing,
    use normalize_signal_robust() instead.
    """
    if not values:
        return []

    import math
    clean = []
    for v in values:
        if v is None:
            clean.append(0.0)
            continue
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                clean.append(0.0)
            else:
                clean.append(f)
        except (ValueError, TypeError):
            clean.append(0.0)

    min_val = min(clean)
    max_val = max(clean)

    if max_val == min_val:
        return [0.5 for _ in clean]

    scaled = [(x - min_val) / (max_val - min_val) for x in clean]
    if direction == "lower":
        scaled = [1.0 - s for s in scaled]
    return scaled


def normalize_signal_robust(values, direction="higher"):
    """
    MinMax scaling that gracefully handles None (missing/sentinel) values.

    None entries are EXCLUDED from the min/max calculation and given a
    neutral 0.5 score. This is the key fix for real data where
    github_activity_score=-1 and offer_acceptance_rate=-1 are sentinels
    meaning "missing", not bad scores.

    Parameters
    ----------
    values : list of (float or None)
        Raw values for ONE signal across all candidates.
        None means "missing" (sentinel, unparseable, etc.).
    direction : str
        "higher" = bigger is better (use as-is after scaling)
        "lower"  = smaller is better (invert: 1.0 - scaled)

    Returns
    -------
    list of floats (0.0 - 1.0), same length as input.

    Edge cases:
    - Empty list -> []
    - All None -> [0.5, 0.5, ...]
    - All same value -> [0.5, 0.5, ...] (avoids division by zero)
    - Mixed None + values -> None entries get 0.5, others get proper MinMax
    """
    if not values:
        return []

    # Separate present values from None (missing/sentinel).
    present = [v for v in values if v is not None]
    if not present:
        return [0.5 for _ in values]

    min_val = min(present)
    max_val = max(present)

    if max_val == min_val:
        return [0.5 for _ in values]

    result = []
    for v in values:
        if v is None:
            # Neutral score for missing data — not punished, not rewarded.
            result.append(0.5)
        else:
            scaled = (v - min_val) / (max_val - min_val)
            if direction == "lower":
                scaled = 1.0 - scaled
            result.append(scaled)
    return result


def _normalize_weights(weights):
    """
    Makes sure the weights sum to exactly 1.0.
    Returns {} if the total is 0 (prevents division by zero).
    """
    total = sum(weights.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in weights.items()}


def _detect_real_data_mode(candidates_data):
    """
    Check whether the input data uses Person 1's real field names.
    Returns True if ANY real-only field name appears in the data.
    """
    if not candidates_data:
        return False
    for signals in candidates_data.values():
        if not isinstance(signals, dict):
            continue
        if any(field in signals for field in _REAL_ONLY_FIELDS):
            return True
        break  # only check the first valid candidate
    return False


# ============================================================================
# PART E — MAIN SCORING FUNCTION
# ============================================================================

def compute_behavioral_scores(candidates_behavioral_data,
                              signal_weights=None,
                              signal_direction=None):
    """
    Turns each candidate's raw behavioral numbers into ONE score (0.0 - 1.0).

    AUTO-DETECTS data format:
    - If the data has real Person 1 field names (e.g. profile_completeness_score,
      avg_response_time_hours, last_active_date) -> uses REAL config + handles
      sentinels, booleans, dates automatically.
    - Otherwise -> uses legacy config (for built-in test data).

    Parameters
    ----------
    candidates_behavioral_data : dict
        {candidate_id: {signal_name: raw_value}}
    signal_weights : dict, optional
        Override the default weights. If None, auto-selected based on data format.
    signal_direction : dict, optional
        Override the default directions. If None, auto-selected.

    Returns
    -------
    dict
        {candidate_id: behavioral_score}  where score is 0.0 - 1.0.
    """

    # ---- Step 0: input validation --------------------------------------
    if not candidates_behavioral_data or not isinstance(candidates_behavioral_data, dict):
        logger.warning("compute_behavioral_scores: received empty or non-dict input.")
        return {}

    # ---- Step 1: detect mode & pick defaults ---------------------------
    real_mode = _detect_real_data_mode(candidates_behavioral_data)

    if signal_direction is None:
        signal_direction = REAL_SIGNAL_DIRECTION if real_mode else SIGNAL_DIRECTION
    if signal_weights is None:
        signal_weights = REAL_SIGNAL_WEIGHTS if real_mode else SIGNAL_WEIGHTS

    if real_mode:
        logger.info("Real-data mode detected: using JD-informed weights + "
                    "sentinel/boolean/date handling.")

    # ---- Step 2: normalize the weights to sum to 1.0 -------------------
    weights = _normalize_weights(signal_weights)
    if not weights:
        logger.warning("All weights are zero — can't score.")
        return {}

    # ---- Step 3: figure out which signals we can actually score --------
    candidate_ids = list(candidates_behavioral_data.keys())
    usable_signals = [s for s in weights.keys() if s in signal_direction]

    if not usable_signals:
        logger.warning("No signals have both a weight AND a direction.")
        return {}

    # Warn about unused signals in the data.
    all_data_signals = set()
    for cid in candidate_ids:
        inner = candidates_behavioral_data.get(cid)
        if isinstance(inner, dict):
            all_data_signals.update(inner.keys())
    unused = all_data_signals - set(usable_signals)
    if unused:
        logger.info("Signals in data but not scored: %s", sorted(unused))

    # ---- Step 4: preprocess + normalize each signal --------------------
    # For date fields, compute the reference date first (most recent in data).
    date_references = {}
    for signal in usable_signals:
        if signal in DATE_FIELDS:
            date_references[signal] = _compute_reference_date(
                candidates_behavioral_data, signal
            )

    # normalized[signal][candidate_id] = 0.0-1.0 score
    normalized = {}
    for signal in usable_signals:
        ref_date = date_references.get(signal)
        raw_values = []
        for cid in candidate_ids:
            inner = candidates_behavioral_data.get(cid)
            if not isinstance(inner, dict):
                logger.warning("Candidate %s data is not a dict — treating as missing.", cid)
                raw_values.append(None)
                continue
            raw = inner.get(signal)
            # Preprocess: handle sentinels, booleans, dates.
            clean = _preprocess_value(signal, raw, ref_date)
            raw_values.append(clean)

        direction = signal_direction.get(signal, "higher")
        # Use robust scaler always (it produces identical results to legacy
        # when there are no None values, so test mode is unaffected).
        scaled_values = normalize_signal_robust(raw_values, direction)
        normalized[signal] = {cid: scaled_values[i] for i, cid in enumerate(candidate_ids)}

    # ---- Step 5: weighted average per candidate ------------------------
    behavioral_scores = {}
    for cid in candidate_ids:
        total = 0.0
        for signal in usable_signals:
            w = weights[signal]
            total += w * normalized[signal][cid]
        behavioral_scores[cid] = min(1.0, max(0.0, total))

    return behavioral_scores


# ============================================================================
# PART F — DEBUG / DETAIL FUNCTION
# ============================================================================

def get_signal_breakdown(candidates_behavioral_data,
                         signal_weights=None,
                         signal_direction=None):
    """
    Returns a DETAILED per-candidate, per-signal breakdown.

    Returns
    -------
    dict
        {candidate_id: {signal_name: normalized_score, ..., "total": score}}
    """

    if not candidates_behavioral_data or not isinstance(candidates_behavioral_data, dict):
        return {}

    real_mode = _detect_real_data_mode(candidates_behavioral_data)
    if signal_direction is None:
        signal_direction = REAL_SIGNAL_DIRECTION if real_mode else SIGNAL_DIRECTION
    if signal_weights is None:
        signal_weights = REAL_SIGNAL_WEIGHTS if real_mode else SIGNAL_WEIGHTS

    weights = _normalize_weights(signal_weights)
    if not weights:
        return {}

    candidate_ids = list(candidates_behavioral_data.keys())
    usable_signals = [s for s in weights.keys() if s in signal_direction]

    date_references = {}
    for signal in usable_signals:
        if signal in DATE_FIELDS:
            date_references[signal] = _compute_reference_date(
                candidates_behavioral_data, signal
            )

    normalized = {}
    for signal in usable_signals:
        ref_date = date_references.get(signal)
        raw_values = []
        for cid in candidate_ids:
            inner = candidates_behavioral_data.get(cid)
            if not isinstance(inner, dict):
                raw_values.append(None)
                continue
            raw = inner.get(signal)
            raw_values.append(_preprocess_value(signal, raw, ref_date))
        scaled = normalize_signal_robust(raw_values, signal_direction.get(signal, "higher"))
        normalized[signal] = {cid: scaled[i] for i, cid in enumerate(candidate_ids)}

    breakdown = {}
    for cid in candidate_ids:
        row = {}
        total = 0.0
        for signal in usable_signals:
            nscore = normalized[signal][cid]
            row[signal] = round(nscore, 4)
            total += weights[signal] * nscore
        row["total"] = round(min(1.0, max(0.0, total)), 4)
        breakdown[cid] = row

    return breakdown


# ============================================================================
# PART G — SUMMARY FUNCTION
# ============================================================================

def scoring_summary(scores_dict):
    """
    Quick statistical summary of any {id: score} dict.
    Returns {count, mean, std, min, max, top_3, bottom_3}.
    """
    if not scores_dict:
        return {"count": 0, "error": "empty input"}

    vals = list(scores_dict.values())
    sorted_items = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)

    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = variance ** 0.5

    return {
        "count": len(vals),
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "top_3": [{"id": k, "score": round(v, 4)} for k, v in sorted_items[:3]],
        "bottom_3": [{"id": k, "score": round(v, 4)} for k, v in sorted_items[-3:]],
    }


# ============================================================================
# PART H — TEST MODE (runs only when executed directly)
#           Tests BOTH legacy data AND real data.
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("BEHAVIORAL SIGNAL SCORER - TEST MODE")
    print("=" * 60)

    # =====================================================================
    # TEST 1: LEGACY DATA (backward compatibility)
    # Expected: CAND_004 = #1, CAND_002 = last
    # =====================================================================
    print("\n" + "-" * 60)
    print("TEST 1: LEGACY TEST DATA (backward compatibility)")
    print("-" * 60)

    scores = compute_behavioral_scores(TEST_BEHAVIORAL_DATA)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    print(f"\n{'Rank':<6}{'Candidate ID':<14}{'Behavioral Score':<18}")
    print("-" * 40)
    for rank, (cid, score) in enumerate(ranked, start=1):
        print(f"#{rank:<5}{cid:<14}{score:<18.4f}")

    top_cid = ranked[0][0]
    bottom_cid = ranked[-1][0]
    all_in_range = all(0.0 <= s <= 1.0 for s in scores.values())
    legacy_ok = (top_cid == "CAND_004" and bottom_cid == "CAND_002" and all_in_range)

    print(f"\n  Highest: {top_cid} (expected CAND_004)")
    print(f"  Lowest:  {bottom_cid} (expected CAND_002)")
    print(f"  All in [0,1]: {'YES' if all_in_range else 'NO'}")
    print(f"  Legacy test: {'PASS ✅' if legacy_ok else 'FAIL ❌'}")

    # =====================================================================
    # TEST 2: REAL DATA (from Person 1's sample_5_candidates.json)
    # Uses real field names, sentinels, booleans, dates.
    # =====================================================================
    print("\n" + "-" * 60)
    print("TEST 2: REAL DATA (Person 1's field names + sentinels/dates)")
    print("-" * 60)

    import json
    import os
    sample_path = os.path.join(os.path.dirname(__file__), "..", "data",
                               "sample_5_candidates.json")
    try:
        with open(sample_path, "r", encoding="utf-8") as f:
            real_candidates = json.load(f)

        # Convert to {candidate_id: {signal: value}} format.
        real_data = {}
        for cand in real_candidates:
            cid = cand["candidate_id"]
            real_data[cid] = {k: v for k, v in cand.items()
                              if k not in ("candidate_id", "profile_text",
                                           "experience_text", "skills_text",
                                           "skills_details_text",
                                           "education_text", "headline",
                                           "summary", "anonymized_name")}

        real_scores = compute_behavioral_scores(real_data)
        real_ranked = sorted(real_scores.items(), key=lambda x: x[1], reverse=True)

        print(f"\n  Real mode detected: {_detect_real_data_mode(real_data)}")
        print(f"  Candidates scored: {len(real_scores)}")
        print(f"\n  {'Rank':<6}{'Candidate ID':<18}{'Score':<10}")
        print("  " + "-" * 34)
        for rank, (cid, score) in enumerate(real_ranked, start=1):
            print(f"  #{rank:<5}{cid:<18}{score:<10.4f}")

        real_in_range = all(0.0 <= s <= 1.0 for s in real_scores.values())
        print(f"\n  All scores in [0,1]: {'YES' if real_in_range else 'NO'}")
        print(f"  Real data test: {'PASS ✅' if real_in_range and len(real_scores) == 5 else 'FAIL ❌'}")

        # Show the breakdown to prove sentinels/dates were handled.
        breakdown = get_signal_breakdown(real_data)
        if breakdown:
            print("\n  Signal breakdown for top candidate:")
            top_real = real_ranked[0][0]
            for sig, val in breakdown[top_real].items():
                print(f"    {sig:<32} {val:.4f}")

    except FileNotFoundError:
        print(f"\n  (sample_5_candidates.json not found at {sample_path})")
        print("  Skipping real data test. Copy it to data/ to enable.")
        real_in_range = True  # don't fail overall

    # =====================================================================
    # TEST 3: SENTINEL HANDLING (github_activity_score = -1)
    # =====================================================================
    print("\n" + "-" * 60)
    print("TEST 3: SENTINEL HANDLING (-1 = missing, not bad)")
    print("-" * 60)

    sentinel_data = {
        "A": {"github_activity_score": 50, "offer_acceptance_rate": 0.8},
        "B": {"github_activity_score": -1, "offer_acceptance_rate": -1},  # missing!
        "C": {"github_activity_score": 10, "offer_acceptance_rate": 0.3},
    }
    custom_dir = {"github_activity_score": "higher", "offer_acceptance_rate": "higher"}
    custom_w = {"github_activity_score": 0.5, "offer_acceptance_rate": 0.5}
    sentinel_scores = compute_behavioral_scores(sentinel_data, custom_w, custom_dir)

    print(f"\n  A (github=50, offer=0.8): {sentinel_scores.get('A', '?')}")
    print(f"  B (github=-1, offer=-1):  {sentinel_scores.get('B', '?')}  <- should be ~0.5 (neutral)")
    print(f"  C (github=10, offer=0.3): {sentinel_scores.get('C', '?')}")

    b_score = sentinel_scores.get("B", 999)
    sentinel_ok = 0.3 <= b_score <= 0.7  # B should be neutral, not 0
    print(f"\n  B got neutral score (not punished for missing GitHub): {'YES ✅' if sentinel_ok else 'NO ❌'}")

    # =====================================================================
    # FINAL VERDICT
    # =====================================================================
    print("\n" + "=" * 60)
    all_ok = legacy_ok and real_in_range and sentinel_ok
    if all_ok:
        print("ALL TESTS PASSED ✅")
    else:
        print("⚠️  SOME TESTS FAILED — review above.")
    print("=" * 60)
