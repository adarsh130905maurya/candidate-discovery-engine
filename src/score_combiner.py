"""
================================================================================
score_combiner.py  —  Final Score Fusion & Ranking  (Person 3 — Signal Mixer)
================================================================================

WHAT THIS FILE DOES (plain English):
------------------------------------
We now have TWO scores per candidate:
    - SEMANTIC score   (from Person 2 — how well the resume matches the job)
    - BEHAVIORAL score (from our signal_scorer.py — how active/engaged they are)

This module fuses those two into ONE final score, then ranks every candidate
from best to worst.

    final = (w_semantic * semantic) + (w_behavioral * behavioral)

Defaults: 70% semantic, 30% behavioral.
Why? A great resume fit matters more than being active — but a super-active
candidate with a totally wrong resume should NOT win. (See the CAND_004 test.)

This module ships with BUILT-IN TEST DATA so you can run it standalone:
    python src/score_combiner.py

EXPORTED FUNCTIONS (used by other team members):
    - combine_and_rank(...)        -> main one, returns ranked list of dicts
    - compare_weight_configs(...)  -> shows how 3 weight setups change the ranking
    - apply_penalties(...)         -> hard-filter hook for Person 1 / Person 4
    - scoring_summary(...)         -> quick stats on the final ranking
================================================================================
"""

import logging

# Logger for this module.
logger = logging.getLogger("score_combiner")
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("  ⚠️  %(name)s: %(message)s"))
    logger.addHandler(handler)

# ----------------------------------------------------------------------------
# 1. BUILT-IN TEST DATA
#    Fake scores that mimic what Person 2 and our signal_scorer would output.
#    Note the trap: CAND_004 is super active (0.95 behavioral) but a TERRIBLE
#    resume match (0.15 semantic). With 70/30 weights, CAND_004 must NOT win.
# ----------------------------------------------------------------------------

# Fake semantic scores (as if from Person 2's AI matching module)
TEST_SEMANTIC_SCORES = {
    "CAND_001": 0.89,   # Great AI/ML match
    "CAND_002": 0.35,   # Poor match (web developer)
    "CAND_003": 0.72,   # Decent match (data science)
    "CAND_004": 0.15,   # Terrible match (marketing)
    "CAND_005": 0.91,   # Excellent match (AI researcher)
}

# Fake behavioral scores (as if from our signal_scorer module)
TEST_BEHAVIORAL_SCORES = {
    "CAND_001": 0.82,
    "CAND_002": 0.12,
    "CAND_003": 0.58,
    "CAND_004": 0.95,   # Very active, but bad semantic match
    "CAND_005": 0.45,
}

# Default fusion weights: how much we trust resume fit vs activity signals.
DEFAULT_WEIGHTS = {
    "semantic": 0.7,    # 70% weight on resume-job match
    "behavioral": 0.3,  # 30% weight on activity signals
}


# ============================================================================
# HELPER: _validate_and_normalize_weights
# ============================================================================
def _validate_and_normalize_weights(weights):
    """
    Checks the weights dict has the two expected keys and normalizes them
    so they sum to 1.0. Returns normalized weights, or None if invalid.

    We accept the two keys in either spelling so callers can't easily break it:
        {"semantic": ..., "behavioural": ...}  (British)
        {"semantic": ..., "behavioral": ...}   (American)
    """
    if not weights or not isinstance(weights, dict):
        return None

    # Pull out the semantic weight (only one spelling).
    if "semantic" not in weights:
        return None

    # Accept either spelling of behavioral.
    behav = weights.get("behavioral", weights.get("behavioural"))
    if behav is None:
        return None

    total = weights["semantic"] + behav
    if total <= 0:
        return None

    return {
        "semantic": weights["semantic"] / total,
        "behavioral": behav / total,
    }


# ============================================================================
# MAIN FUNCTION: combine_and_rank
# ============================================================================
def combine_and_rank(semantic_scores, behavioral_scores, weights=None):
    """
    Fuses semantic + behavioral scores into one final score per candidate,
    then returns them ranked best-first.

    Parameters
    ----------
    semantic_scores : dict
        {candidate_id: float}  (0.0 - 1.0)
    behavioral_scores : dict
        {candidate_id: float}  (0.0 - 1.0)
    weights : dict, optional
        {"semantic": float, "behavioral": float}.
        Defaults to DEFAULT_WEIGHTS (70/30) if not given.
        Don't worry if they don't sum to 1 — we'll normalize them.

    Returns
    -------
    list of dicts, sorted by final_score DESCENDING:
        [
            {
                "rank": 1,
                "candidate_id": "CAND_005",
                "final_score": 0.8720,
                "semantic_score": 0.91,
                "behavioral_score": 0.45,
                "semantic_weighted": 0.6370,
                "behavioral_weighted": 0.1350,
            },
            ...
        ]

    Edge cases handled
    ------------------
    - Candidate missing from one dict -> treated as 0.0 in the missing one.
    - Weights not summing to 1.0 -> auto-normalized.
    - Invalid weights -> falls back to DEFAULT_WEIGHTS.
    - All scores rounded to 4 decimal places.
    - final_score is clamped to [0.0, 1.0].
    """

    # ---- Step 0: friendly handling of bad input -------------------------
    if not isinstance(semantic_scores, dict) or not isinstance(behavioral_scores, dict):
        print("⚠️  combine_and_rank: both inputs must be dicts.")
        return []

    # ---- Step 1: settle on valid weights --------------------------------
    w = _validate_and_normalize_weights(weights)
    if w is None:
        if weights is not None:
            print("⚠️  combine_and_rank: weights dict was invalid — using default 70/30.")
        w = _validate_and_normalize_weights(DEFAULT_WEIGHTS)

    # ---- Step 2: union of all candidate IDs across both dicts -----------
    all_ids = set(semantic_scores.keys()) | set(behavioral_scores.keys())
    if not all_ids:
        return []

    # ---- Step 3: compute final score per candidate ----------------------
    ranked = []
    for cid in all_ids:
        # FIX R2/R3: clamp raw scores to [0, 1] before any math.
        # Upstream modules might send <0 or >1 due to rounding, NaN, or bugs.
        sem = max(0.0, min(1.0, semantic_scores.get(cid, 0.0)))
        beh = max(0.0, min(1.0, behavioral_scores.get(cid, 0.0)))

        sem_w = sem * w["semantic"]
        beh_w = beh * w["behavioral"]
        final = sem_w + beh_w

        # Clamp defensively and round to 4 decimals for clean output.
        final = round(min(1.0, max(0.0, final)), 4)

        ranked.append({
            "candidate_id": cid,
            "final_score": final,
            "semantic_score": round(sem, 4),
            "behavioral_score": round(beh, 4),
            "semantic_weighted": round(sem_w, 4),
            "behavioral_weighted": round(beh_w, 4),
        })

    # ---- Step 4: sort by final_score DESCENDING, then assign ranks -----
    # Tie-break on candidate_id so the order is deterministic.
    ranked.sort(key=lambda x: (-x["final_score"], x["candidate_id"]))
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i

    # Reorder keys so "rank" comes first (nicer when printed).
    ordered = [{
        "rank": item["rank"],
        "candidate_id": item["candidate_id"],
        "final_score": item["final_score"],
        "semantic_score": item["semantic_score"],
        "behavioral_score": item["behavioral_score"],
        "semantic_weighted": item["semantic_weighted"],
        "behavioral_weighted": item["behavioral_weighted"],
    } for item in ranked]

    return ordered


# ============================================================================
# ANALYSIS FUNCTION: compare_weight_configs
# ============================================================================
def compare_weight_configs(semantic_scores, behavioral_scores):
    """
    Runs the ranking under THREE different weight setups and prints them
    side-by-side. Useful for deciding the final weights with the team.

    Config A: 80% semantic, 20% behavioral  (resume fit dominates)
    Config B: 70% semantic, 30% behavioral  (DEFAULT — balanced)
    Config C: 60% semantic, 40% behavioral  (activity matters more)

    Highlights any candidate whose rank CHANGES between configs.
    """

    configs = [
        ("Config A (80/20)", {"semantic": 0.8, "behavioral": 0.2}),
        ("Config B (70/30) — DEFAULT", {"semantic": 0.7, "behavioral": 0.3}),
        ("Config C (60/40)", {"semantic": 0.6, "behavioral": 0.4}),
    ]

    print("Running 3 weight configurations...\n")

    # Store each config's {candidate_id: rank} so we can spot changes.
    rank_maps = []
    labels = []

    for label, cfg in configs:
        ranked = combine_and_rank(semantic_scores, behavioral_scores, cfg)
        rank_map = {item["candidate_id"]: item["rank"] for item in ranked}
        rank_maps.append(rank_map)
        labels.append(label)

        # ---- Print this config's top 5 --------------------------------
        print(f"  {label}")
        print(f"  {'Rank':<6}{'Candidate':<12}{'Final':<10}{'Semantic':<10}{'Behavioral':<10}")
        print("  " + "-" * 48)
        for item in ranked[:5]:
            print(f"  #{item['rank']:<5}{item['candidate_id']:<12}"
                  f"{item['final_score']:<10.4f}{item['semantic_score']:<10.4f}"
                  f"{item['behavioral_score']:<10.4f}")
        print()

    # ---- Highlight candidates whose rank changed across configs ----------
    all_cands = set()
    for rm in rank_maps:
        all_cands.update(rm.keys())

    print("  Candidates whose rank changed between configs:")
    print("  " + "-" * 60)
    changed_any = False
    for cid in sorted(all_cands):
        ranks = [rm.get(cid, "-") for rm in rank_maps]
        if len(set(ranks)) > 1:  # rank differs across at least one config
            changed_any = True
            print(f"    {cid:<12} -> A: rank {ranks[0]} | "
                  f"B: rank {ranks[1]} | C: rank {ranks[2]}")
    if not changed_any:
        print("    (none — ranking is stable across all three weightings)")
    print("  " + "-" * 60)


# ============================================================================
# HARD-FILTER FUNCTION: apply_penalties
# ============================================================================
def apply_penalties(ranked_list, penalty_rules=None,
                    candidate_attributes=None):
    """
    Applies score penalties based on "hard filter" rules.

    Why this exists
    ---------------
    Sometimes a candidate looks great by the numbers but fails a must-have
    requirement (e.g. needs 3+ years experience, must be in NYC/Remote).
    Person 1 or Person 4 can pass in penalty_rules + candidate_attributes.

    Parameters
    ----------
    ranked_list : list of dicts
        Output of combine_and_rank(...).
    penalty_rules : dict, optional
        If None (default), NO penalties are applied — the list is returned
        unchanged (just copied for safety).

        Supported rule types:

        1. **threshold rule** — penalize if a numeric attribute is below a
           minimum:
           {"min_experience_years": {"threshold": 3, "penalty": -0.2}}

           If the candidate's `experience_years` value is < 3, their
           final_score gets the penalty subtracted.

        2. **values rule** — penalize if an attribute is NOT in an allowed set:
           {"required_location": {"values": ["Remote", "NYC"], "penalty": -0.3}}

           If the candidate's `location` is NOT in the list, penalty applied.

        3. **below_threshold rule** — penalize if a numeric attribute is
           below a ceiling (like profile_completeness):
           {"min_profile_score": {"below_threshold": 50, "penalty": -0.1}}

    candidate_attributes : dict, optional
        {candidate_id: {attribute_name: value}}
        Maps candidate IDs to their raw attributes (e.g. years of experience,
        location, etc.). Required for penalty rules to actually work.

        Example:
        {
            "CAND_001": {"experience_years": 5, "location": "Remote"},
            "CAND_002": {"experience_years": 1, "location": "Chicago"},
        }

    Returns
    -------
    list of dicts
        Same shape as the input, with penalties subtracted from final_score,
        re-ranked. final_score is clamped to [0.0, 1.0] so it never goes
        below zero.
    """

    # No rules -> nothing to do. Return a defensive copy.
    if not penalty_rules:
        return [dict(item) for item in ranked_list]

    # If rules given but no attributes, warn and return unchanged.
    if not candidate_attributes:
        logger.warning(
            "Penalty rules provided but no candidate_attributes dict — "
            "penalties cannot be checked. Returning unchanged list."
        )
        return [dict(item) for item in ranked_list]

    # Build a quick lookup: {candidate_id: {attr: value}}
    attrs = candidate_attributes if isinstance(candidate_attributes, dict) else {}

    penalized = []
    for item in ranked_list:
        new_item = dict(item)
        cid = item["candidate_id"]
        total_penalty = 0.0

        cand_attrs = attrs.get(cid, {})

        for rule_name, rule in penalty_rules.items():
            penalty_amount = rule.get("penalty", 0.0)

            # Type 1: "threshold" — penalize if numeric value is below threshold
            if "threshold" in rule:
                attr_key = rule_name  # e.g. "min_experience_years"
                raw_val = _to_float(cand_attrs.get(attr_key), cid, attr_key)
                if raw_val < rule["threshold"]:
                    total_penalty += penalty_amount
                    logger.info(
                        "  Penalty on %s: %s=%s < threshold=%s -> %s",
                        cid, attr_key, raw_val, rule["threshold"], penalty_amount,
                    )

            # Type 2: "values" — penalize if value NOT in allowed list
            elif "values" in rule:
                attr_key = rule_name
                cand_val = cand_attrs.get(attr_key)
                if cand_val not in rule["values"]:
                    total_penalty += penalty_amount
                    logger.info(
                        "  Penalty on %s: %s=%s not in %s -> %s",
                        cid, attr_key, cand_val, rule["values"], penalty_amount,
                    )

            # Type 3: "below_threshold" — penalize if value is below a ceiling
            elif "below_threshold" in rule:
                attr_key = rule_name
                raw_val = _to_float(cand_attrs.get(attr_key), cid, attr_key)
                if raw_val < rule["below_threshold"]:
                    total_penalty += penalty_amount
                    logger.info(
                        "  Penalty on %s: %s=%s < below_threshold=%s -> %s",
                        cid, attr_key, raw_val, rule["below_threshold"], penalty_amount,
                    )

        # Apply total penalty.
        new_item["final_score"] = new_item["final_score"] + total_penalty
        # Clamp so it can't go negative or above 1.0.
        new_item["final_score"] = min(1.0, max(0.0, new_item["final_score"]))
        if total_penalty != 0.0:
            new_item["penalty_applied"] = round(total_penalty, 4)
        penalized.append(new_item)

    # Re-rank in case penalties shuffled the order.
    penalized.sort(key=lambda x: (-x["final_score"], x["candidate_id"]))
    for i, item in enumerate(penalized, start=1):
        item["rank"] = i

    return penalized


def _to_float(value, candidate_id="<unknown>", attr_name="<unknown>"):
    """Safe float conversion. Reuses the same logic as signal_scorer."""
    import math
    if value is None:
        return 0.0
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


# ============================================================================
# HONEYPOT HARD-VETO FUNCTION (JD-critical)
# ============================================================================
def apply_honeypot_veto(ranked_list, candidate_attributes=None,
                        veto_top_k=100):
    """
    Hard-veto candidates flagged as honeypots from the top-K.

    Why this exists (from data_exploration.md §6)
    ----------------------------------------------
    The challenge has ~80 honeypot candidates (subtly impossible profiles).
    The rules state: "Submissions with honeypot rate > 10% in top 100 are
    DISQUALIFIED." Person 1's data_cleaner flags obvious ones via
    `is_honeypot_suspect`. We push flagged candidates OUT of the top-K so
    we never accidentally submit one and get disqualified.

    This is a HARD veto (not a soft penalty). Flagged candidates are moved
    to the very bottom of the list, regardless of their score.

    Parameters
    ----------
    ranked_list : list of dicts
        Output of combine_and_rank(...). Each dict has at least
        "candidate_id", "final_score", "rank".
    candidate_attributes : dict, optional
        {candidate_id: {attribute_name: value}}.
        Must include "is_honeypot_suspect" (bool) for the veto to work.
        If None, no veto applied (defensive — module still returns a copy).
    veto_top_k : int
        Number of top candidates to protect (default 100, matches the
        submission requirement). Honeypots are pushed below rank `veto_top_k`.

    Returns
    -------
    list of dicts
        Same shape as input, re-ranked so honeypots sit below rank `veto_top_k`.
        Honeypot candidates get an extra field: "honeypot_vetoed": True.
    """
    # No attributes -> nothing to veto. Return a defensive copy.
    if not candidate_attributes or not isinstance(candidate_attributes, dict):
        return [dict(item) for item in ranked_list]

    # Split into clean and vetoed, preserving original order.
    clean = []
    vetoed = []
    for item in ranked_list:
        new_item = dict(item)
        cid = item["candidate_id"]
        attrs = candidate_attributes.get(cid, {})
        is_hp = attrs.get("is_honeypot_suspect", False)

        # Be lenient about the type: True, 1, "true" all count as flagged.
        flagged = (
            is_hp is True
            or (isinstance(is_hp, (int, float)) and is_hp != 0)
            or (isinstance(is_hp, str) and is_hp.strip().lower() in ("true", "1", "yes"))
        )
        if flagged:
            new_item["honeypot_vetoed"] = True
            # Drop the score to 0 so they sort to the very bottom.
            new_item["final_score"] = 0.0
            vetoed.append(new_item)
            logger.info("Honeypot veto on %s (pushed below top-%d).",
                        cid, veto_top_k)
        else:
            new_item["honeypot_vetoed"] = False
            clean.append(new_item)

    # Sort clean candidates by score (desc), then sort vetoed to the bottom.
    clean.sort(key=lambda x: (-x["final_score"], x["candidate_id"]))
    vetoed.sort(key=lambda x: x["candidate_id"])

    combined = clean + vetoed

    # Reassign ranks. Clean candidates occupy 1..N, vetoed come after.
    # If we have fewer than veto_top_k clean candidates, the vetoed still
    # just go to the end (which is the safe behavior).
    for i, item in enumerate(combined, start=1):
        item["rank"] = i

    vetoed_count = len(vetoed)
    if vetoed_count > 0:
        logger.info("Honeypot veto: %d candidate(s) pushed below top-%d.",
                    vetoed_count, veto_top_k)

    return combined


# ============================================================================
# SUMMARY FUNCTION: scoring_summary
# ============================================================================
def scoring_summary(ranked_list):
    """
    Quick statistical summary of the final ranked output.

    Useful for Person 4 to include stats in the README or submission output.

    Parameters
    ----------
    ranked_list : list of dicts
        Output of combine_and_rank(...).

    Returns
    -------
    dict with: count, mean_score, std_score, top_3, bottom_3.
    """
    if not ranked_list:
        return {"count": 0, "error": "empty input"}

    scores = [item["final_score"] for item in ranked_list]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std = variance ** 0.5

    return {
        "count": len(scores),
        "mean_score": round(mean, 4),
        "std_score": round(std, 4),
        "min_score": round(min(scores), 4),
        "max_score": round(max(scores), 4),
        "top_3": [
            {"rank": it["rank"], "id": it["candidate_id"], "score": it["final_score"]}
            for it in ranked_list[:3]
        ],
        "bottom_3": [
            {"rank": it["rank"], "id": it["candidate_id"], "score": it["final_score"]}
            for it in ranked_list[-3:]
        ],
    }


# ============================================================================
# TEST MODE — runs only when you execute this file directly.
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SCORE COMBINER - TEST MODE")
    print("=" * 60)

    # ---- Test 1: basic combination with default 70/30 weights -----------
    ranked = combine_and_rank(TEST_SEMANTIC_SCORES, TEST_BEHAVIORAL_SCORES)

    print("\nFINAL RANKING  (weights: semantic=0.7, behavioral=0.3)")
    print("-" * 78)
    print(f"{'Rank':<6}{'Candidate':<12}{'Final':<10}{'Semantic':<10}"
          f"{'Behavioral':<12}{'Sem*w':<10}{'Beh*w':<8}")
    print("-" * 78)
    for item in ranked:
        print(f"#{item['rank']:<5}{item['candidate_id']:<12}"
              f"{item['final_score']:<10.4f}{item['semantic_score']:<10.4f}"
              f"{item['behavioral_score']:<12.4f}{item['semantic_weighted']:<10.4f}"
              f"{item['behavioral_weighted']:<8.4f}")
    print("-" * 78)

    # ---- Sanity checks --------------------------------------------------
    top_cid = ranked[0]["candidate_id"]
    cand004 = next((it for it in ranked if it["candidate_id"] == "CAND_004"), None)
    cand004_rank = cand004["rank"] if cand004 else "-"
    all_in_range = all(0.0 <= it["final_score"] <= 1.0 for it in ranked)

    print("\nSANITY CHECKS")
    print(f"  #1 candidate    : {top_cid}  (expected CAND_001 or CAND_005)")
    print(f"  CAND_004 rank   : #{cand004_rank}  (must NOT be #1)")
    print(f"  All scores in [0.0, 1.0]: {'YES' if all_in_range else 'NO'}")

    # ---- Test 2: weight sensitivity analysis ----------------------------
    print("\n--- Weight Sensitivity Analysis ---")
    compare_weight_configs(TEST_SEMANTIC_SCORES, TEST_BEHAVIORAL_SCORES)

    # ---- Test 3: apply_penalties with no rules (should be a no-op) ------
    penalized = apply_penalties(ranked)
    no_change = all(
        penalized[i]["candidate_id"] == ranked[i]["candidate_id"]
        for i in range(len(ranked))
    )
    print(f"\napply_penalties (no rules) is a clean no-op: {'YES' if no_change else 'NO'}")

    # ---- Test 4: honeypot hard-veto -------------------------------------
    print("\n--- Honeypot Hard-Veto Test ---")
    # Pretend the top candidate (CAND_001) is a honeypot — it must be pushed
    # out of the top-K even though it had the highest score.
    veto_attrs = {
        "CAND_001": {"is_honeypot_suspect": True},   # was rank #1, should drop
        "CAND_002": {"is_honeypot_suspect": False},
        "CAND_003": {"is_honeypot_suspect": False},
        "CAND_004": {"is_honeypot_suspect": False},
        "CAND_005": {"is_honeypot_suspect": False},
    }
    vetoed = apply_honeypot_veto(ranked, veto_attrs, veto_top_k=3)
    vetoed_ids = [it["candidate_id"] for it in vetoed]
    print(f"\n  Before veto: {[it['candidate_id'] for it in ranked]}")
    print(f"  After veto:  {vetoed_ids}")
    vetoed_flags = [it.get("honeypot_vetoed") for it in vetoed]
    cand001_new_rank = next(it["rank"] for it in vetoed if it["candidate_id"] == "CAND_001")

    # Veto is correct if CAND_001 is pushed below rank 3 (the veto_top_k).
    veto_ok = cand001_new_rank > 3 and vetoed_flags[vetoed_ids.index("CAND_001")] is True
    print(f"\n  CAND_001 new rank: #{cand001_new_rank} (must be > 3)")
    print(f"  CAND_001 flagged as honeypot_vetoed: "
          f"{vetoed_flags[vetoed_ids.index('CAND_001')]}")
    print(f"  Honeypot veto test: {'PASS ✅' if veto_ok else 'FAIL ❌'}")

    # ---- Final verdict --------------------------------------------------
    print("\n" + "=" * 60)
    if (top_cid in ("CAND_001", "CAND_005")
            and cand004_rank != 1
            and all_in_range
            and veto_ok):
        print("ALL TESTS PASSED ✅")
        print("(CAND_004 not #1, all scores in [0,1], honeypot veto works)")
    else:
        print("⚠️  SOME TESTS FAILED — review above.")
    print("=" * 60)
