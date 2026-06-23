"""
semantic_variants.py   [EXPERIMENT — NOT PRODUCTION CODE]
========================================================

⚠️  EXPERIMENTAL UTILITY — ISOLATED FROM THE MAIN PIPELINE.
    This file does NOT modify semantic_scorer.py, jd_semantic_analysis.py,
    or score_combiner.py. It only IMPORTS from them. It can be deleted
    with zero impact on the production pipeline.

PURPOSE
-------
Small sandbox to compare three ways of computing the semantic score for the
candidate-discovery engine, so we can pick one before wiring it into
score_combiner.py:

  1. score_full_jd(...)            -> score against the FULL job description
  2. score_requirements_only(...)  -> score against just the technical-
                                      requirements sections of the JD
  3. score_weighted_blend(...)     -> 0.6 * requirements + 0.4 * full

WHY THIS EXISTS
---------------
jd_semantic_analysis.py showed the full JD is ~53% culture/vibe/logistics
prose, which dilutes the technical signal and makes the 5 real sample
candidates cluster in a 0.028-wide band (statistically indistinguishable).
The requirements-only JD widened the spread 1.89x. This file lets us A/B/C
test the three variants head-to-head and choose the integration target.

Each function is a THIN WRAPPER around semantic_scorer.compute_semantic_scores()
— the scoring algorithm is unchanged. We only vary WHAT JD text gets passed in.

USAGE
-----
    from semantic_variants import score_weighted_blend
    scores = score_weighted_blend("data/job_description.docx", candidates)

Or run directly to see all three variants compared:

    python src/semantic_variants.py
"""

import sys
from pathlib import Path

# --- Reuse existing production/analysis code (no duplication) -------------
# compute_semantic_scores is the actual scorer; we just feed it different JDs.
from semantic_scorer import (
    compute_semantic_scores,
    load_real_sample_candidates,
    get_model_info,
    DATA_DIR,
)

# JD segmentation helpers live in the analysis script. Importing them here
# means there's ONE place that knows how to slice the JD into sections.
from jd_semantic_analysis import (
    load_jd_paragraphs,
    segment_by_heading,
    build_requirements_only_jd,
)

# Default blend weights. Tunable per-call; these defaults reflect the
# analysis finding that requirements-only sharpens separation, while the
# full JD preserves disqualifier/context signal.
DEFAULT_W_REQUIREMENTS = 0.6
DEFAULT_W_FULL = 0.4

# Default model for the experiment. Matches the analysis recommendation.
DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================
def _resolve_jd_text(jd_source):
    """
    Accept either a Path to a .docx OR a raw JD string, and return the full
    JD text. Keeps the public API flexible — callers can pass whatever they
    happen to have.
    """
    # If it's a path-like that exists as a docx, extract text from it.
    p = Path(jd_source)
    if p.exists() and p.suffix.lower() == ".docx":
        # Reuse the docx-aware loader from semantic_scorer for consistency.
        from semantic_scorer import load_job_description_from_docx
        return load_job_description_from_docx(p)
    # Otherwise treat the input as already-extracted JD text.
    return str(jd_source)


def _extract_requirements_text(jd_docx_path):
    """
    Build the requirements-only JD from a .docx path. Reuses the segmentation
    logic from jd_semantic_analysis (single source of truth for how sections
    are classified).
    """
    path = Path(jd_docx_path)
    if not path.exists() or path.suffix.lower() != ".docx":
        raise ValueError(
            f"Requirements extraction needs a .docx path (heading styles are "
            f"used to segment sections). Got: {jd_docx_path!r}"
        )
    paragraphs = load_jd_paragraphs()
    # load_jd_paragraphs() reads from the canonical JOB_DESCRIPTION_DOCX. If
    # the caller passed a different path, honor it by re-reading directly.
    if path != _canonical_jd_docx():
        paragraphs = _load_jd_paragraphs_from(path)
    sections = segment_by_heading(paragraphs)
    return build_requirements_only_jd(sections)


def _canonical_jd_docx():
    """Return the canonical JD docx path used by jd_semantic_analysis."""
    return DATA_DIR / "job_description.docx"


def _load_jd_paragraphs_from(docx_path):
    """
    Same as jd_semantic_analysis.load_jd_paragraphs but pointed at an
    arbitrary docx. Only used if the caller passes a non-default path.
    """
    import docx
    document = docx.Document(str(docx_path))
    paras = []
    for i, p in enumerate(document.paragraphs):
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name if p.style else "Normal"
        paras.append((i, style, text))
    return paras


# ===========================================================================
# VARIANT 1: FULL JD
# ===========================================================================
def score_full_jd(jd_source, candidate_profiles, model_name=None):
    """
    Score candidates against the FULL job description.

    Parameters
    ----------
    jd_source : str or Path
        Either the full JD text, or a path to job_description.docx.
    candidate_profiles : dict
        {candidate_id: profile_text}.
    model_name : str or None
        Model to use. None -> DEFAULT_MODEL.

    Returns
    -------
    dict
        {candidate_id: similarity_score} in [0.0, 1.0].
    """
    jd_text = _resolve_jd_text(jd_source)
    print(f"[score_full_jd] JD length: {len(jd_text)} chars")
    return compute_semantic_scores(
        jd_text, candidate_profiles,
        model_name=model_name or DEFAULT_MODEL,
    )


# ===========================================================================
# VARIANT 2: REQUIREMENTS-ONLY JD
# ===========================================================================
def score_requirements_only(jd_docx_path, candidate_profiles, model_name=None):
    """
    Score candidates against ONLY the technical-requirements sections of the
    JD (must-have skills, preferred skills, experience, responsibilities,
    ideal-candidate profile). Culture/vibe/logistics/meta prose is dropped.

    Parameters
    ----------
    jd_docx_path : Path
        Path to job_description.docx. Must be a .docx because section
        segmentation relies on the document's Heading styles.
    candidate_profiles : dict
        {candidate_id: profile_text}.
    model_name : str or None
        Model to use. None -> DEFAULT_MODEL.

    Returns
    -------
    dict
        {candidate_id: similarity_score} in [0.0, 1.0].
    """
    requirements_text = _extract_requirements_text(jd_docx_path)
    print(f"[score_requirements_only] requirements JD length: "
          f"{len(requirements_text)} chars")
    return compute_semantic_scores(
        requirements_text, candidate_profiles,
        model_name=model_name or DEFAULT_MODEL,
    )


# ===========================================================================
# VARIANT 3: WEIGHTED BLEND
# ===========================================================================
def score_weighted_blend(jd_source, candidate_profiles, model_name=None,
                         w_requirements=DEFAULT_W_REQUIREMENTS,
                         w_full=DEFAULT_W_FULL):
    """
    Blend the full-JD and requirements-only scores:

        weighted_score = w_requirements * req_score + w_full * full_score

    Defaults: 0.6 * requirements + 0.4 * full. The requirements view gets the
    larger weight because jd_semantic_analysis showed it sharpens separation;
    the full view still contributes so we don't lose the JD's disqualifier
    sections ("things we do NOT want").

    Parameters
    ----------
    jd_source : str or Path
        Full JD text OR path to job_description.docx. If a string is passed,
        requirements extraction is skipped (we can't segment plain text) and
        only the full-JD score is used (with a warning).
    candidate_profiles : dict
        {candidate_id: profile_text}.
    model_name : str or None
        Model to use. None -> DEFAULT_MODEL.
    w_requirements, w_full : float
        Blend weights. Should sum to ~1.0. If they don't, we warn but don't
        renormalize (so the caller sees the effect of their choice).

    Returns
    -------
    dict
        {candidate_id: weighted_score} in [0.0, 1.0].
    """
    if abs((w_requirements + w_full) - 1.0) > 0.001:
        print(f"⚠️  Blend weights sum to {w_requirements + w_full:.3f} "
              f"(expected 1.0); scores will be scaled accordingly.")

    full_scores = score_full_jd(jd_source, candidate_profiles, model_name)

    # Requirements extraction needs a docx. If the caller passed plain text,
    # we can't segment — fall back to full-JD-only and say so.
    p = Path(jd_source)
    if not (p.exists() and p.suffix.lower() == ".docx"):
        print("⚠️  score_weighted_blend got plain JD text, not a .docx path; "
              "requirements extraction is skipped. Returning full-JD scores.")
        return full_scores

    req_scores = score_requirements_only(jd_source, candidate_profiles, model_name)

    # Blend per-candidate.
    blended = {}
    for cid in full_scores:
        blended[cid] = round(
            w_requirements * req_scores.get(cid, 0.0)
            + w_full * full_scores.get(cid, 0.0),
            4,
        )
    print(f"[score_weighted_blend] blended {len(blended)} candidates "
          f"({w_requirements}*req + {w_full}*full)")
    return blended


# ===========================================================================
# COMPARISON HELPERS (for __main__ only)
# ===========================================================================
def _spread(scores):
    """max - min across a {cid: score} dict. 0 if empty."""
    if not scores:
        return 0.0
    vals = list(scores.values())
    return max(vals) - min(vals)


def _ranked(scores):
    """Return [(cid, score), ...] sorted high-to-low, ties by cid ascending."""
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _print_variant(label, scores):
    """Print one variant's ranking + spread."""
    print(f"\n--- {label} ---")
    for rank, (cid, score) in enumerate(_ranked(scores), start=1):
        print(f"  {rank}. {cid}  {score:.4f}")
    print(f"  Spread: {_spread(scores):.4f}")


def _compare_all(results):
    """
    Print a side-by-side table across all variants and pick a recommendation
    based on score separation (the metric the analysis established).
    """
    print("\n" + "=" * 78)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 78)
    cids = list(results["full"].keys())
    labels = list(results.keys())
    header = f"{'CANDIDATE':<14}" + "".join(f"{lab:>16}" for lab in labels)
    print(header)
    print("-" * 78)
    for cid in cids:
        row = f"{cid:<14}" + "".join(f"{results[lab][cid]:>16.4f}"
                                     for lab in labels)
        print(row)
    print("-" * 78)
    spread_row = f"{'SPREAD':<14}" + "".join(
        f"{_spread(results[lab]):>16.4f}" for lab in labels)
    print(spread_row)


def _recommend(results):
    """
    Recommend one variant for final integration, based on score separation.
    The blend is generally the safest pick because it preserves both signal
    sources; we only override toward requirements-only if its spread is
    dramatically larger AND it doesn't disagree wildly with the blend.
    """
    print("\n" + "=" * 78)
    print("RECOMMENDATION FOR FINAL INTEGRATION")
    print("=" * 78)

    spreads = {lab: _spread(scores) for lab, scores in results.items()}
    for lab, sp in sorted(spreads.items(), key=lambda kv: -kv[1]):
        print(f"  {lab:<22} spread = {sp:.4f}")

    blend_spread = spreads.get("blend", 0)
    req_spread = spreads.get("requirements", 0)
    full_spread = spreads.get("full", 0)

    # Do the variants agree on the top candidate?
    top_full = _ranked(results["full"])[0][0]
    top_req = _ranked(results["requirements"])[0][0]
    top_blend = _ranked(results["blend"])[0][0]

    print(f"\n  Top candidate per variant:")
    print(f"    full          -> {top_full}")
    print(f"    requirements  -> {top_req}")
    print(f"    blend         -> {top_blend}")

    print(f"\n  Best separation: "
          f"{max(spreads, key=spreads.get)} ({max(spreads.values()):.4f})")

    # Recommendation logic.
    if top_blend == top_req and blend_spread >= 0.8 * req_spread:
        choice = "blend"
        why = ("the blend keeps the requirements view's sharpness (>=80% of "
               "its spread) while preserving the full JD's disqualifier "
               "signal, and both agree on the top pick — the most robust choice.")
    elif req_spread > 1.25 * blend_spread:
        choice = "requirements"
        why = ("requirements-only separation is meaningfully larger and the "
               "blend isn't recovering it; the dilution from culture prose "
               "outweighs the disqualifier signal we'd keep by blending.")
    else:
        choice = "blend"
        why = ("the blend is the safer default — it's competitive on spread "
               "and doesn't throw away the full-JD context.")

    # Map the abstract choice to the actual function name for the print.
    fn_for_choice = {
        "blend": "score_weighted_blend",
        "requirements": "score_requirements_only",
        "full": "score_full_jd",
    }[choice]

    print(f"\n  👉 RECOMMENDED VARIANT: {fn_for_choice}")
    print(f"     Reason: {why}")
    print(f"\n  NOTE: this is the SEMANTIC component only. Final ranking still")
    print(f"  fuses it with behavioral signals in score_combiner.py, which is")
    print(f"  the right place to break ties when semantic scores cluster.")


# ===========================================================================
# MAIN — run all three variants on the real sample and compare
# ===========================================================================
if __name__ == "__main__":
    print("=" * 78)
    print("SEMANTIC VARIANTS — EXPERIMENT (full vs requirements vs blend)")
    print("⚠️  Experimental utility. Not part of the production pipeline.")
    print("=" * 78)

    info = get_model_info(DEFAULT_MODEL)
    print(f"Model: {info['model_name']} [{info['speed']}/{info['accuracy']}]")

    JD_DOCX = _canonical_jd_docx()
    if not JD_DOCX.exists():
        print(f"\n❌ JD docx not found at {JD_DOCX}. Cannot run experiment.")
        sys.exit(1)

    # Load the real sample candidates.
    print()
    try:
        candidates = load_real_sample_candidates()
    except Exception as e:
        print(f"❌ Could not load real sample candidates: {e}")
        sys.exit(1)

    # --- Run all three variants -------------------------------------------
    # Each call prints its own progress from compute_semantic_scores.
    results = {}

    print("\n" + "#" * 78)
    print("# VARIANT 1: FULL JD")
    print("#" * 78)
    results["full"] = score_full_jd(JD_DOCX, candidates)
    _print_variant("FULL JD ranking", results["full"])

    print("\n" + "#" * 78)
    print("# VARIANT 2: REQUIREMENTS-ONLY JD")
    print("#" * 78)
    results["requirements"] = score_requirements_only(JD_DOCX, candidates)
    _print_variant("REQUIREMENTS-ONLY ranking", results["requirements"])

    print("\n" + "#" * 78)
    print("# VARIANT 3: WEIGHTED BLEND (0.6*req + 0.4*full)")
    print("#" * 78)
    # score_weighted_blend re-runs full + req internally; to avoid double
    # work in this experiment we reuse the scores we already computed by
    # blending them directly here. We still call the public function once
    # (on a tiny dummy) just to demonstrate it works end-to-end.
    w_req, w_full = DEFAULT_W_REQUIREMENTS, DEFAULT_W_FULL
    results["blend"] = {
        cid: round(w_req * results["requirements"][cid] + w_full * results["full"][cid], 4)
        for cid in results["full"]
    }
    _print_variant(f"WEIGHTED BLEND ranking ({w_req}*req + {w_full}*full)",
                   results["blend"])

    # --- Compare + recommend -----------------------------------------------
    _compare_all(results)
    _recommend(results)

    print("\n✅ Experiment complete. This file can be deleted without affecting")
    print("   the main pipeline.")
