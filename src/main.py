"""
main.py — End-to-end pipeline orchestrator
==========================================
Person 4 (Packager) integration module.

This wires the four team members' modules into ONE pipeline that:
  1. Loads the job description + candidate data        (Person 1: data_loader, data_cleaner)
  2. Scores semantic fit                              (Person 2: semantic_scorer)
  3. Scores behavioral signals + fuses into final rank (Person 3: signal_scorer, score_combiner)
  4. Generates the submission CSV + metadata, validates (Person 4: output_generator)

Every function signature used here was READ FROM THE ACTUAL MODULES — nothing
is invented. See the interface notes below each import.

USAGE
-----
    # Full run over the entire candidate pool (slow, loads the model once):
    python src/main.py

    # Fast dev mode — only score the first N candidates:
    python src/main.py --limit 200

    # Override the model or the top-k output size:
    python src/main.py --model "BAAI/bge-base-en-v1.5" --top-k 100

DESIGN NOTES
------------
- Each stage is wrapped in its own try/except so a failure in one stage is
  reported clearly without aborting the whole script silently.
- Wall-clock time is printed per stage so we can verify we stay inside the
  hackathon's 5-minute CPU budget (CONFIG["max_runtime_minutes"]).
- The honeypot veto is applied AFTER combine_and_rank but BEFORE output, so
  flagged candidates are pushed out of the top-K. (This is the one cross-
  module detail that's easy to forget: data_cleaner flags honeypots, and
  score_combiner.apply_honeypot_veto consumes the flag.)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# ============================================================================
# SYS.PATH SETUP — make sibling modules importable
# ============================================================================
# This file lives at: <project_root>/src/main.py
# The other modules (data_loader, data_cleaner, semantic_scorer, etc.) are
# siblings in the same src/ folder. We add src/ to sys.path so plain
# `from data_loader import ...` works regardless of the current working
# directory (whether run from project root or from inside src/).
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# ============================================================================
# IMPORTS — real signatures confirmed by reading each module
# ============================================================================
# Person 1 (config + data pipeline) -----------------------------------------
from config import CONFIG, PATHS                                   # noqa: E402
from data_loader import get_job_description                       # noqa: E402
#   get_job_description() -> str  (cached, reads data/job_description.docx)
from data_cleaner import (                                         # noqa: E402
    get_candidate_profiles,
    get_behavioral_data,
)
#   get_candidate_profiles(limit=None) -> {candidate_id: profile_text}
#   get_behavioral_data(limit=None)    -> {candidate_id: {signal_name: value}}
#     NOTE: the behavioral dict includes "is_honeypot_suspect" (bool), which
#     we extract separately for the honeypot veto (see STEP 5 below).

# Person 2 (semantic AI engine) ---------------------------------------------
from semantic_scorer import compute_semantic_scores               # noqa: E402
#   compute_semantic_scores(job_description: str,
#                           candidate_profiles: dict,
#                           model_name: str = None) -> {candidate_id: float}
#   ⚠ The param is `model_name`, NOT `model`. Default is MODEL_NAME (MiniLM).

# Person 3 (signal mixer) ---------------------------------------------------
from signal_scorer import compute_behavioral_scores               # noqa: E402
#   compute_behavioral_scores(candidates_behavioral_data,
#                             signal_weights=None,
#                             signal_direction=None) -> {candidate_id: float}
#     Auto-detects real vs legacy data by field name.

from score_combiner import (                                      # noqa: E402
    combine_and_rank,
    apply_honeypot_veto,
    scoring_summary,
)
#   combine_and_rank(semantic_scores, behavioral_scores,
#                    weights=None) -> list[dict] sorted by final_score desc.
#     Each dict: rank, candidate_id, final_score, semantic_score,
#     behavioral_score, semantic_weighted, behavioral_weighted.
#     `weights` expects {"semantic": float, "behavioral": float}
#     (normalized internally if they don't sum to 1.0).
#   apply_honeypot_veto(ranked_list, candidate_attributes=None,
#                       veto_top_k=100) -> list[dict]
#     candidate_attributes must map {candidate_id: {"is_honeypot_suspect": bool}}.

# Person 4 (output) ---------------------------------------------------------
from output_generator import (                                    # noqa: E402
    generate_submission,
    generate_metadata,
    validate_output,
)
#   generate_submission(ranked_candidates: list,
#                       output_dir="output/",
#                       top_k=None,
#                       team_name="team_ai_rankers") -> str (filepath)
#   generate_metadata(team_name, methodology, model_used, output_dir) -> str
#   validate_output(output_filepath) -> bool


# ============================================================================
# HELPERS
# ============================================================================
def _fmt_time(seconds: float) -> str:
    """Human-friendly duration: 1.23s or 2m 03s."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}m {secs:02d}s"


def _stage_timer(stage_name: str):
    """
    A tiny context manager that prints "[stage] ..." on enter and the elapsed
    time on exit. Keeps the main() body readable.

    Usage:
        with _stage_timer("Scoring semantic fit"):
            scores = compute_semantic_scores(...)
    """
    class _Timer:
        def __enter__(self_inner):
            print(f"\n▶ {stage_name}...")
            self_inner.start = time.perf_counter()
            return self_inner

        def __exit__(self_inner, exc_type, exc_val, exc_tb):
            elapsed = time.perf_counter() - self_inner.start
            status = "FAILED" if exc_type else "done"
            print(f"  [{status} in {_fmt_time(elapsed)}]")
            # Don't suppress exceptions — let them propagate to the stage's
            # own try/except so we get a clear per-stage report.
            return False
    return _Timer()


# ============================================================================
# MAIN PIPELINE
# ============================================================================
def run_pipeline(limit: int = None,
                 model_name: str = None,
                 top_k: int = None,
                 team_name: str = "team_ai_rankers",
                 skip_validation: bool = False) -> int:
    """
    Run the full candidate-discovery pipeline end-to-end.

    Parameters
    ----------
    limit : int or None
        Cap on number of candidates processed (dev mode). None = full pool.
        Falls back to CONFIG["max_candidates_debug"] if not given.
    model_name : str or None
        Sentence-transformers model. None -> CONFIG["semantic_model"] default.
    top_k : int or None
        How many to write to the CSV. None -> CONFIG["top_k"] (100).
    team_name : str
        Used for the output filename (should be the registered participant ID).
    skip_validation : bool
        If True, don't run validate_submission.py at the end (faster dev runs).

    Returns
    -------
    int
        0 on success, 1 if a fatal error occurred.
    """
    pipeline_start = time.perf_counter()

    # ---- Resolve defaults from config --------------------------------------
    if limit is None:
        limit = CONFIG["max_candidates_debug"]  # None in production
    if model_name is None:
        model_name = CONFIG["semantic_model"]   # all-MiniLM-L6-v2 by default
    if top_k is None:
        top_k = CONFIG["top_k"]                 # 100 per the submission spec

    weights = {
        "semantic": CONFIG["semantic_weight"],      # 0.7
        "behavioral": CONFIG["behavioral_weight"],  # 0.3
    }

    # ====================================================================
    # BANNER
    # ====================================================================
    print("=" * 72)
    print(" INTELLIGENT CANDIDATE DISCOVERY ENGINE — pipeline")
    print("=" * 72)
    print(f"  Model     : {model_name}")
    print(f"  Weights   : semantic={weights['semantic']}, "
          f"behavioral={weights['behavioral']}")
    print(f"  Limit     : {'all candidates' if limit is None else f'{limit} (dev mode)'}")
    print(f"  Top-K out : {top_k}")
    print(f"  Budget    : {CONFIG['max_runtime_minutes']} min / "
          f"{CONFIG['max_ram_gb']} GB RAM / CPU-only")

    # Stage accumulators — keep references so the summary at the end can
    # report on them even if a later stage fails.
    profiles = {}
    behavioral_data = {}
    semantic_scores = {}
    behavioral_scores = {}
    ranked = []
    submission_path = None
    metadata_path = None
    validation_ok = None

    # ====================================================================
    # STEP 1 — Load data (Person 1: data_loader + data_cleaner)
    # ====================================================================
    try:
        with _stage_timer("STEP 1 — Loading job description & candidate data"):
            jd_text = get_job_description()
            if not jd_text or not jd_text.strip():
                raise RuntimeError(
                    "Job description came back empty — check data/job_description.docx."
                )
            print(f"  Job description: {len(jd_text):,} chars")

            profiles = get_candidate_profiles(limit=limit)
            behavioral_data = get_behavioral_data(limit=limit)

            if not profiles:
                raise RuntimeError(
                    "No candidate profiles returned — is data/candidates.jsonl present?"
                )
            print(f"  Candidate profiles loaded: {len(profiles):,}")
            print(f"  Behavioral records loaded: {len(behavioral_data):,}")

            # The behavioral dict and profiles dict should cover the same IDs.
            id_mismatch = set(profiles) ^ set(behavioral_data)
            if id_mismatch:
                print(f"  ⚠ {len(id_mismatch)} IDs differ between profiles and "
                      f"behavioral data (will be treated as 0.0 where missing).")
    except Exception as exc:
        print(f"\n❌ STEP 1 FAILED: {exc}")
        _print_failure_hint("data loading",
                            "data_loader.py / data_cleaner.py / candidates.jsonl")
        return 1

    # ====================================================================
    # STEP 2 — Semantic scoring (Person 2: semantic_scorer)
    # ====================================================================
    try:
        with _stage_timer("STEP 2 — Semantic scoring (AI matching)"):
            # NOTE: the real signature is compute_semantic_scores(
            #       job_description, candidate_profiles, model_name=...)
            semantic_scores = compute_semantic_scores(
                job_description=jd_text,
                candidate_profiles=profiles,
                model_name=model_name,
            )
            if not semantic_scores:
                raise RuntimeError("Semantic scorer returned no scores.")
            print(f"  Candidates scored: {len(semantic_scores):,}")
            # Quick top-3 preview so you can see the semantic ordering.
            preview = sorted(semantic_scores.items(),
                             key=lambda kv: kv[1], reverse=True)[:3]
            for cid, sc in preview:
                print(f"    top semantic: {cid}  {sc:.4f}")
    except Exception as exc:
        print(f"\n❌ STEP 2 FAILED: {exc}")
        _print_failure_hint("semantic scoring",
                            "sentence-transformers / network for model download")
        return 1

    # ====================================================================
    # STEP 3 — Behavioral scoring (Person 3: signal_scorer)
    # ====================================================================
    try:
        with _stage_timer("STEP 3 — Behavioral signal scoring"):
            # signal_scorer auto-detects real vs legacy data from field names,
            # so we pass the raw behavioral dict straight through.
            behavioral_scores = compute_behavioral_scores(behavioral_data)
            if not behavioral_scores:
                raise RuntimeError("Signal scorer returned no scores.")
            print(f"  Candidates scored: {len(behavioral_scores):,}")
            preview = sorted(behavioral_scores.items(),
                             key=lambda kv: kv[1], reverse=True)[:3]
            for cid, sc in preview:
                print(f"    top behavioral: {cid}  {sc:.4f}")
    except Exception as exc:
        print(f"\n❌ STEP 3 FAILED: {exc}")
        _print_failure_hint("behavioral scoring", "signal_scorer.py")
        return 1

    # ====================================================================
    # STEP 4 — Fuse scores into final ranking (Person 3: score_combiner)
    # ====================================================================
    try:
        with _stage_timer("STEP 4 — Score fusion & ranking"):
            ranked = combine_and_rank(
                semantic_scores=semantic_scores,
                behavioral_scores=behavioral_scores,
                weights=weights,
            )
            if not ranked:
                raise RuntimeError("Score combiner returned an empty list.")
            print(f"  Candidates ranked: {len(ranked):,}")
            print(f"  #1: {ranked[0]['candidate_id']}  "
                  f"final={ranked[0]['final_score']:.4f}")
    except Exception as exc:
        print(f"\n❌ STEP 4 FAILED: {exc}")
        _print_failure_hint("score fusion", "score_combiner.py")
        return 1

    # ====================================================================
    # STEP 5 — Honeypot veto (Person 3: apply_honeypot_veto)
    # ====================================================================
    # INTERFACE MISMATCH HANDLED HERE:
    #   data_cleaner.get_behavioral_data() bundles is_honeypot_suspect into
    #   each candidate's signal dict. apply_honeypot_veto() wants it as a
    #   separate {candidate_id: {"is_honeypot_suspect": bool}} map. We build
    #   that adapter here so the two modules connect cleanly.
    try:
        with _stage_timer("STEP 5 — Honeypot hard-veto"):
            honeypot_attrs = {}
            vetoed_count = 0
            for cid, signals in behavioral_data.items():
                is_hp = False
                if isinstance(signals, dict):
                    is_hp = bool(signals.get("is_honeypot_suspect", False))
                honeypot_attrs[cid] = {"is_honeypot_suspect": is_hp}
                if is_hp:
                    vetoed_count += 1

            ranked = apply_honeypot_veto(
                ranked_list=ranked,
                candidate_attributes=honeypot_attrs,
                veto_top_k=top_k,
            )
            print(f"  Honeypot suspects flagged: {vetoed_count:,}")
            print(f"  (pushed below rank {top_k} — protects submission)")
    except Exception as exc:
        # Honeypot veto failure is non-fatal — log and continue, because the
        # ranking is still valid; we'd just rather not submit honeypots.
        print(f"\n⚠ STEP 5 skipped (honeypot veto error): {exc}")

    # ====================================================================
    # STEP 6 — Generate submission CSV + metadata (Person 4: output_generator)
    # ====================================================================
    try:
        with _stage_timer("STEP 6 — Generating submission CSV + metadata"):
            submission_path = generate_submission(
                ranked_candidates=ranked,
                output_dir=str(PATHS["output_dir"]),
                top_k=top_k,
                team_name=team_name,
            )
            print(f"  CSV written: {submission_path}")

            metadata_path = generate_metadata(
                team_name=team_name,
                methodology=None,   # uses output_generator's default
                model_used=model_name,
                output_dir=str(PATHS["output_dir"]),
            )
            print(f"  Metadata:    {metadata_path}")
    except Exception as exc:
        print(f"\n❌ STEP 6 FAILED: {exc}")
        _print_failure_hint("output generation", "output_generator.py")
        return 1

    # ====================================================================
    # STEP 7 — Validate the output (Person 4: validate_output)
    # ====================================================================
    if not skip_validation:
        try:
            with _stage_timer("STEP 7 — Validating submission"):
                validation_ok = validate_output(submission_path)
        except Exception as exc:
            print(f"\n⚠ STEP 7 skipped (validation error): {exc}")
            validation_ok = None
    else:
        print("\n▶ STEP 7 — Validation (skipped via --skip-validation)")

    # ====================================================================
    # SUMMARY
    # ====================================================================
    total_elapsed = time.perf_counter() - pipeline_start
    print("\n" + "=" * 72)
    print(" PIPELINE SUMMARY")
    print("=" * 72)
    print(f"  Candidates processed : {len(profiles):,}")
    print(f"  Semantic scores      : {len(semantic_scores):,}")
    print(f"  Behavioral scores    : {len(behavioral_scores):,}")
    print(f"  Final ranked         : {len(ranked):,}")

    # Score-combiner's own summary (top/bottom 3, mean, std).
    try:
        stats = scoring_summary(ranked)
        print(f"  Final score range    : {stats['min_score']:.4f} – "
              f"{stats['max_score']:.4f}  (mean {stats['mean_score']:.4f})")
    except Exception:
        pass  # summary is cosmetic; never fail the pipeline on it

    if submission_path:
        print(f"  Output CSV           : {Path(submission_path).name}")
    if metadata_path:
        print(f"  Metadata             : {Path(metadata_path).name}")

    # Budget check — warn (don't fail) if we're over the hackathon limit.
    budget_min = CONFIG["max_runtime_minutes"]
    print(f"  Total runtime        : {_fmt_time(total_elapsed)} "
          f"(budget {budget_min} min)")
    if total_elapsed > budget_min * 60:
        print(f"  ⚠ OVER BUDGET — exceeds {budget_min} min CPU limit. "
              f"Reduce --limit or switch to the MiniLM model.")

    # Validation verdict.
    if validation_ok is True:
        print("  Validation           : ✅ PASSED")
    elif validation_ok is False:
        print("  Validation           : ❌ FAILED (see errors above)")
    else:
        print("  Validation           : (not run)")

    print("=" * 72)
    # Exit code: 0 = clean, but if validation ran and failed, surface that.
    if validation_ok is False:
        return 1
    return 0


def _print_failure_hint(stage: str, likely_culprit: str) -> None:
    """Print a short hint pointing at where to look after a stage fails."""
    print(f"  Pipeline stopped at {stage}.")
    print(f"  Likely culprit: {likely_culprit}.")
    print("  Fix the issue above and re-run.")


# ============================================================================
# COMMAND-LINE ENTRY POINT
# ============================================================================
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Intelligent Candidate Discovery Engine — full pipeline.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only score the first N candidates (dev mode). "
             "Default: CONFIG['max_candidates_debug'] (None = full pool).",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Sentence-transformers model name. "
             "Default: CONFIG['semantic_model'] (all-MiniLM-L6-v2).",
    )
    parser.add_argument(
        "--top-k", type=int, default=None,
        help="How many candidates to write to the submission CSV. "
             "Default: CONFIG['top_k'] (100).",
    )
    parser.add_argument(
        "--team", type=str, default="team_ai_rankers",
        help="Team / participant ID used for the output filename.",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Don't run validate_submission.py at the end (faster dev runs).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exit_code = run_pipeline(
        limit=args.limit,
        model_name=args.model,
        top_k=args.top_k,
        team_name=args.team,
        skip_validation=args.skip_validation,
    )
    sys.exit(exit_code)
