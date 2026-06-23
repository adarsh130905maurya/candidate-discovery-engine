"""
jd_semantic_analysis.py
=======================
Analysis-only script (Person 2 diagnostics).

GOAL: explain WHY the 5 real sample candidates produced tightly clustered
semantic scores when scored against the full job_description.docx, and test
whether scoring against a "requirements-only" version of the JD produces
better separation.

This is an ANALYSIS script, not part of the production pipeline. It:
  1. Loads the full JD text and prints a structural summary (headings,
     sections, and which categories — requirements / qualifications / skills /
     responsibilities / culture — each section belongs to).
  2. Builds a "requirements-only" JD by extracting only the technical
     sections (must-have skills, preferred skills, experience, ideal-candidate
     profile, responsibilities). Culture/vibe/logistics/meta prose is dropped.
  3. Runs semantic scoring TWICE with the recommended model:
        A. Full JD
        B. Requirements-only JD
     Both calls go through semantic_scorer.compute_semantic_scores() unchanged
     — the scoring algorithm itself is NOT modified.
  4. Prints rankings, score spread, rank changes, and whether separation
     improved.
  5. Prints an evidence-based explanation and a recommendation.

The script is data-driven: no scores or rankings are hardcoded. Every number
in the output comes from an actual model run.
"""

# Standard-library imports.
import sys
from pathlib import Path

# Re-use the production scorer so we analyse EXACTLY what the pipeline runs.
# Importing it also gives us PROJECT_ROOT, DATA_DIR, load_real_sample_candidates,
# load_job_description_from_docx, compute_semantic_scores, get_model_info, and
# the recommended-model logic via a re-run of the comparison. We avoid
# triggering semantic_scorer.__main__ by importing (not executing) it.
from semantic_scorer import (
    compute_semantic_scores,
    load_real_sample_candidates,
    get_model_info,
    DATA_DIR,
)

JOB_DESCRIPTION_DOCX = DATA_DIR / "job_description.docx"

# The model to use for the analysis. We hardcode BGE because the previous
# dual-model test recommended it for the final submission; this keeps the
# analysis consistent with what production would use. (No scoring-algorithm
# change — just the model choice, which is a normal function argument.)
RECOMMENDED_MODEL = "BAAI/bge-base-en-v1.5"


# ===========================================================================
# SECTION 1: JD STRUCTURE ANALYSIS
# ===========================================================================
def load_jd_paragraphs():
    """
    Return a list of (index, style_name, text) tuples for non-empty paragraphs
    in the JD docx. We keep style because the docx uses real Heading 1 /
    Heading 2 styles — that lets us classify sections deterministically rather
    than guessing from text patterns.
    """
    try:
        import docx
    except ImportError as e:
        raise ImportError(
            "python-docx is required for this analysis. pip install python-docx"
        ) from e

    document = docx.Document(str(JOB_DESCRIPTION_DOCX))
    paras = []
    for i, p in enumerate(document.paragraphs):
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name if p.style else "Normal"
        paras.append((i, style, text))
    return paras


# Category keywords used to AUTO-CLASSIFY each section. We map a heading's
# text to a category by checking for these substrings. Tuned to the actual
# headings in this specific JD (verified by reading the docx).
#
# Categories:
#   "skills_must"      -> hard technical requirements
#   "skills_preferred" -> nice-to-haves
#   "experience"       -> years-of-experience guidance / disqualifiers
#   "responsibilities" -> what the person will do day-to-day
#   "ideal_profile"    -> the "ideal candidate" sketch
#   "culture"          -> vibe / company-values prose
#   "logistics"        -> location, comp, notice period
#   "meta"             -> title block + hackathon note (neither requirements
#                         nor culture, just administrative)
#   "intro"            -> "let's be honest about this role" framing prose
def classify_heading(heading_text):
    """Map a heading string to one of our category labels (or None)."""
    h = heading_text.lower()
    if "absolutely need" in h or "must" in h:
        return "skills_must"
    if "won't reject" in h or "like you to have" in h or "preferred" in h:
        return "skills_preferred"
    if "5-9 years" in h or "what we mean by" in h:
        return "experience"
    if "what you'd actually be doing" in h or "doing" in h:
        return "responsibilities"
    if "read between the lines" in h or "ideal candidate" in h:
        return "ideal_profile"
    if "vibe" in h or "culture" in h or "honest about this role" in h:
        return "culture"
    if "location" in h or "comp" in h or "logistics" in h:
        return "logistics"
    if "final note" in h or "hackathon" in h:
        return "meta"
    if "skills inventory" in h:
        return "skills_must"  # the parent heading of the must/preferred sub-headings
    return None


# Categories we KEEP in the requirements-only JD. Everything else (culture,
# vibe, logistics, meta, intro prose) is dropped because it's semantically
# generic — it overlaps similarly with every candidate and adds noise.
REQUIREMENTS_CATEGORIES = {
    "skills_must",
    "skills_preferred",
    "experience",
    "responsibilities",
    "ideal_profile",
}


def segment_by_heading(paras):
    """
    Walk the paragraph list and split it into sections delimited by Heading 1
    or Heading 2 styles. Returns a list of sections, each a dict with:
        heading        -> the heading text (or None for the pre-heading block)
        category       -> our classification
        paragraph_idx  -> docx paragraph index of the heading
        body_paragraphs-> list of (idx, style, text) under this heading
        char_count     -> total characters in the body
    """
    sections = []
    current = None
    for idx, style, text in paras:
        is_heading = style.startswith("Heading") or style == "Title"
        if is_heading:
            # Start a new section.
            current = {
                "heading": text,
                "category": classify_heading(text) if style != "Title" else "meta",
                "paragraph_idx": idx,
                "body_paragraphs": [],
                "char_count": 0,
            }
            sections.append(current)
        else:
            # Body paragraph — attach to whichever section is current.
            if current is None:
                # Paragraphs before the first heading (the title block fields
                # like Company/Location). Group them as "meta".
                current = {
                    "heading": "(metadata block)",
                    "category": "meta",
                    "paragraph_idx": idx,
                    "body_paragraphs": [],
                    "char_count": 0,
                }
                sections.append(current)
            current["body_paragraphs"].append((idx, style, text))
            current["char_count"] += len(text)
    return sections


def build_requirements_only_jd(sections):
    """
    Concatenate the body paragraphs of every section whose category is in
    REQUIREMENTS_CATEGORIES. Returns the requirements-only JD as a string.

    We deliberately keep must-have AND preferred skills AND the experience
    section AND the responsibilities AND the ideal-profile sketch, because
    all of those carry technical signal. We drop culture/vibe/logistics/meta
    because they read like generic startup prose that overlaps similarly with
    any candidate.
    """
    chunks = []
    for s in sections:
        if s["category"] in REQUIREMENTS_CATEGORIES:
            # Include the heading itself for context (helps the model parse
            # structure: "Things you absolutely need:" then bullets).
            chunks.append(s["heading"])
            for _, _, text in s["body_paragraphs"]:
                chunks.append(text)
    return "\n".join(chunks)


def print_jd_summary(sections):
    """Print the structural summary the user asked for in step 2."""
    total_paras = sum(len(s["body_paragraphs"]) for s in sections)
    total_chars = sum(s["char_count"] for s in sections)
    headings = [s for s in sections if s["heading"] != "(metadata block)"]

    print("\n" + "=" * 78)
    print("JOB DESCRIPTION STRUCTURE SUMMARY")
    print("=" * 78)
    print(f"Total non-empty paragraphs : {total_paras}")
    print(f"Headings detected          : {len(headings)} "
          f"(Heading 1 / Heading 2 / Title styles)")
    print(f"Total body characters      : {total_chars}")

    print("\nSection-by-section breakdown:")
    print("-" * 78)
    print(f"{'#':<3}{'CATEGORY':<18}{'CHARS':>7}  {'HEADING'}")
    print("-" * 78)
    for i, s in enumerate(sections, start=1):
        cat = s["category"] or "(unclassified)"
        print(f"{i:<3}{cat:<18}{s['char_count']:>7}  {s['heading'][:46]}")

    # Roll up by category so we can see the JD's word-budget split.
    print("\nCharacter budget by category:")
    print("-" * 78)
    by_cat = {}
    for s in sections:
        c = s["category"] or "(unclassified)"
        by_cat[c] = by_cat.get(c, 0) + s["char_count"]
    for cat, chars in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        pct = 100.0 * chars / total_chars
        bar = "#" * int(pct / 2)
        print(f"  {cat:<18}{chars:>6} chars  {pct:5.1f}%  {bar}")

    requirements_chars = sum(by_cat.get(c, 0) for c in REQUIREMENTS_CATEGORIES)
    non_requirements_chars = total_chars - requirements_chars
    print("-" * 78)
    print(f"  REQUIREMENTS content : {requirements_chars:>6} chars  "
          f"({100*requirements_chars/total_chars:5.1f}%)")
    print(f"  NON-REQUIREMENTS     : {non_requirements_chars:>6} chars  "
          f"({100*non_requirements_chars/total_chars:5.1f}%)")
    print("  (non-requirements = culture / vibe / logistics / meta / intro)")


# ===========================================================================
# SECTION 2: SCORING + COMPARISON
# ===========================================================================
def score_and_report(label, jd_text, candidate_profiles):
    """
    Run compute_semantic_scores() on the given JD text and return a result
    envelope {label, scores, ok, error}. Also prints the ranking + spread.
    The scoring function itself is unchanged — we only vary the JD input.
    """
    print(f"\n--- Scoring: {label} ({len(jd_text)} JD chars) ---")
    try:
        scores = compute_semantic_scores(
            jd_text, candidate_profiles, model_name=RECOMMENDED_MODEL,
        )
    except Exception as e:
        print(f"❌ {label} scoring failed: {e}")
        return {"label": label, "scores": {}, "ok": False, "error": str(e)}

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    spread = ranked[0][1] - ranked[-1][1] if ranked else 0.0

    print(f"\n{label} ranking:")
    for rank, (cid, score) in enumerate(ranked, start=1):
        headline = candidate_profiles[cid].split("\n", 1)[0][:50]
        print(f"  {rank}. {cid}  {score:.4f}  {headline}")
    print(f"Score spread (max - min): {spread:.4f}")

    return {
        "label": label,
        "scores": scores,
        "ranked": ranked,
        "spread": spread,
        "ok": True,
    }


def compare_runs(res_full, res_req):
    """Print rank changes and whether separation improved (step 5)."""
    if not (res_full["ok"] and res_req["ok"]):
        print("\n(one or both runs failed — skipping comparison)")
        return

    full_scores = res_full["scores"]
    req_scores = res_req["scores"]
    cids = list(full_scores.keys())

    # Rank each candidate under both treatments.
    def rank_of(scores, cid):
        ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return next(r for (c, _), r in zip(ordered, range(1, len(ordered) + 1))
                    if c == cid)

    print("\n" + "=" * 78)
    print("FULL JD vs REQUIREMENTS-ONLY JD")
    print("=" * 78)
    print(f"{'CANDIDATE':<14}{'FULL':>10}{'REQ-ONLY':>12}{'FULL rk':>9}"
          f"{'REQ rk':>8}{'CHANGE':>9}")
    print("-" * 78)
    changes = []
    for cid in cids:
        f_s = full_scores[cid]
        r_s = req_scores[cid]
        f_r = rank_of(full_scores, cid)
        r_r = rank_of(req_scores, cid)
        delta = "same" if f_r == r_r else f"{f_r} -> {r_r}"
        if f_r != r_r:
            changes.append(cid)
        print(f"{cid:<14}{f_s:>10.4f}{r_s:>12.4f}{f_r:>9}{r_r:>8}{delta:>9}")

    print("-" * 78)
    print(f"Full JD spread     : {res_full['spread']:.4f}")
    print(f"Requirements spread: {res_req['spread']:.4f}")
    sep_ratio = res_req["spread"] / res_full["spread"] if res_full["spread"] else 0
    improved = res_req["spread"] > res_full["spread"]
    print(f"Spread ratio (req/full): {sep_ratio:.2f}x")
    print(f"Separation {'IMPROVED ✅' if improved else 'did NOT improve ❌'} "
          f"with requirements-only JD.")
    print(f"\nRank changes: {len(changes)} / {len(cids)} candidate(s) "
          f"reordered{(': ' + ', '.join(changes)) if changes else ''}.")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    print("=" * 78)
    print("JD SEMANTIC ANALYSIS — why are real-sample scores tightly clustered?")
    print("=" * 78)
    info = get_model_info(RECOMMENDED_MODEL)
    print(f"Model under analysis: {info['model_name']} "
          f"[{info['speed']}/{info['accuracy']} accuracy]")

    # --- Step 1: load the full JD as structured paragraphs -----------------
    paragraphs = load_jd_paragraphs()
    sections = segment_by_heading(paragraphs)

    # --- Step 2: print the structural summary ------------------------------
    print_jd_summary(sections)

    # --- Step 3: build the requirements-only JD ----------------------------
    requirements_jd = build_requirements_only_jd(sections)
    full_jd = "\n".join(text for _, _, text in paragraphs)
    print("\n" + "-" * 78)
    print(f"Requirements-only JD built: {len(requirements_jd)} chars "
          f"(vs {len(full_jd)} chars full = "
          f"{100*len(requirements_jd)/len(full_jd):.1f}% of original).")

    # --- Load the real sample candidates -----------------------------------
    print()
    try:
        candidate_profiles = load_real_sample_candidates()
    except Exception as e:
        print(f"❌ Could not load real sample candidates: {e}")
        sys.exit(1)

    # --- Step 4: run BOTH scorings (full + requirements-only) --------------
    res_full = score_and_report("FULL JD", full_jd, candidate_profiles)
    res_req = score_and_report("REQUIREMENTS-ONLY JD",
                               requirements_jd, candidate_profiles)

    # --- Step 5: comparison ------------------------------------------------
    compare_runs(res_full, res_req)

    # --- Steps 6 & 7: explanation + recommendation -------------------------
    # These are computed from the actual run outputs (no hardcoded numbers).
    if res_full["ok"] and res_req["ok"]:
        explain_and_recommend(res_full, res_req, sections)


def explain_and_recommend(res_full, res_req, sections):
    """
    Step 6 (why candidates rank the way they do) + Step 7 (recommendation).
    Pure printing + arithmetic on the result dicts — no model calls.
    """
    total_chars = sum(s["char_count"] for s in sections)
    by_cat = {}
    for s in sections:
        c = s["category"] or "(unclassified)"
        by_cat[c] = by_cat.get(c, 0) + s["char_count"]
    req_chars = sum(by_cat.get(c, 0)
                    for c in REQUIREMENTS_CATEGORIES)
    culture_chars = sum(by_cat.get(c, 0)
                        for c in ("culture", "meta"))
    full_spread = res_full["spread"]
    req_spread = res_req["spread"]
    improved = req_spread > full_spread
    sep_ratio = req_spread / full_spread if full_spread else 0

    # Identify the top candidate under each treatment.
    full_top = res_full["ranked"][0][0]
    req_top = res_req["ranked"][0][0]

    print("\n" + "=" * 78)
    print("STEP 6 — WHY ARE THE CANDIDATES RANKING THIS WAY?")
    print("=" * 78)

    # Q1: Is the JD dominated by culture/company language?
    culture_pct = 100 * culture_chars / total_chars
    req_pct = 100 * req_chars / total_chars
    print(f"\n1) Is the JD dominated by culture/company language?")
    print(f"   Requirements content   : {req_pct:.1f}% of the JD "
          f"({req_chars}/{total_chars} chars)")
    print(f"   Culture + meta content : {culture_pct:.1f}% of the JD "
          f"({culture_chars}/{total_chars} chars)")
    if culture_pct > 25:
        print(f"   -> YES. Over a quarter of the JD is culture/vibe/meta prose,")
        print(f"      which is semantically GENERIC — it overlaps similarly with")
        print(f"      almost any professional profile and DILUTES the technical")
        print(f"      signal the model can pick up on.")
    else:
        print(f"   -> Partially. There's meaningful culture prose but it isn't")
        print(f"      the dominant component.")

    # Q2: Are the candidate profiles weak matches overall?
    full_scores = res_full["scores"]
    avg_full = sum(full_scores.values()) / len(full_scores)
    print(f"\n2) Are the candidate profiles weak matches overall?")
    print(f"   Average cosine similarity on FULL JD: {avg_full:.4f}")
    print(f"   (For reference, well-matched synthetic ML candidates scored")
    print(f"    ~0.85 with the same model.)")
    if avg_full < 0.80:
        print(f"   -> YES. None of the 5 real candidates is actually an AI/")
        print(f"      ranking/retrieval engineer — they're a Backend Engineer,")
        print(f"      Operations Manager, Customer Support, Marketing Manager,")
        print(f"      and Accountant. High similarity is impossible; the model")
        print(f"      is correctly telling us none of them is a strong fit.")

    # Q3: Is semantic similarity unable to distinguish them?
    print(f"\n3) Is semantic similarity unable to distinguish them?")
    print(f"   FULL-JD score spread (max - min): {full_spread:.4f}")
    if full_spread < 0.05:
        print(f"   -> YES. A spread under 0.05 means the candidates are essentially")
        print(f"      INDISTINGUISHABLE to the model on the full JD — the ordering")
        print(f"      within that band is noise, not signal.")
    elif full_spread < 0.10:
        print(f"   -> PARTIALLY. The spread is small; ranking is weakly supported.")
    else:
        print(f"   -> The spread is healthy; the model can distinguish them.")

    # Q4: Which candidate actually overlaps most with the extracted requirements?
    print(f"\n4) Which candidate overlaps most with the extracted requirements?")
    print(f"   Under FULL JD            : {full_top} "
          f"(score {res_full['ranked'][0][1]:.4f})")
    print(f"   Under REQUIREMENTS-ONLY  : {req_top} "
          f"(score {res_req['ranked'][0][1]:.4f})")
    print(f"   The requirements-only JD isolates the TECHNICAL signal, so its")
    print(f"   top pick is the more trustworthy answer to 'who has the skills?'.")

    # --- Step 7: recommendation -------------------------------------------
    print("\n" + "=" * 78)
    print("STEP 7 — RECOMMENDATION")
    print("=" * 78)
    print(f"Evidence:")
    print(f"  - Spread on FULL JD            : {full_spread:.4f}")
    print(f"  - Spread on REQUIREMENTS-ONLY  : {req_spread:.4f} "
          f"({sep_ratio:.2f}x the full-JD spread)")
    print(f"  - Separation improved by trimming non-requirements prose: "
          f"{'YES' if improved else 'NO'}")
    print(f"  - Requirements content is only {req_pct:.1f}% of the JD.")
    print()
    if improved and sep_ratio >= 1.25:
        choice = "REQUIREMENTS-ONLY JD"
        print(f"RECOMMENDATION: Use the {choice} for the semantic component.")
        print()
        print(f"Justification:")
        print(f"  Trimming the culture/vibe/logistics prose INCREASED score")
        print(f"  separation by {sep_ratio:.2f}x. The full JD dilutes the technical")
        print(f"  signal under a lot of semantically-generic startup prose, which")
        print(f"  pushes every candidate toward the same mid-range similarity and")
        print(f"  makes ranking unreliable. The requirements-only JD focuses the")
        print(f"  model on the actual technical signal (embeddings, retrieval,")
        print(f"  ranking, LLMs, Python, evaluation frameworks), which is what we")
        print(f"  want the semantic score to reflect.")
        print()
        print(f"  CAVEAT: this discards the JD's anti-patterns ('things we do NOT")
        print(f"  want', consulting-firm disqualifiers) which carry real signal.")
        print(f"  A weighted combination is the more robust choice — see below.")
    elif improved:
        choice = "BOTH (weighted combination)"
        print(f"RECOMMENDATION: Use {choice}.")
        print()
        print(f"Justification:")
        print(f"  Requirements-only improved separation ({sep_ratio:.2f}x) but the")
        print(f"  gain is modest, and the full JD carries signal the requirements")
        print(f"  version drops (the 'things we do NOT want' disqualifiers, the")
        print(f"  'ideal candidate' culture-fit sketch). Blending the two — e.g.")
        print(f"  semantic_score = 0.65 * req_only + 0.35 * full — captures the")
        print(f"  sharpness of the requirements view without losing the full-JD")
        print(f"  context. The exact weights should be tuned on a labeled")
        print(f"  validation set; the principle is what matters here.")
    else:
        choice = "FULL JD"
        print(f"RECOMMENDATION: Use the {choice}.")
        print()
        print(f"Justification:")
        print(f"  Requirements-only did NOT improve separation (ratio {sep_ratio:.2f}x).")
        print(f"  When even the isolated technical requirements can't separate the")
        print(f"  candidates, the problem isn't JD noise — it's that the candidates")
        print(f"  genuinely lack the relevant skills, so any JD variant will cluster")
        print(f"  them. Keep the full JD (more context, no information loss) and")
        print(f"  rely on behavioral-signal blending (score_combiner) to break ties.")
    print()
    print(f"Note: this recommendation is for the SEMANTIC component only. The")
    print(f"final blended rank (score_combiner) still fuses it with behavioral")
    print(f"signals, which is the right place to recover discrimination when")
    print(f"semantic scores cluster — the JD itself hints at this in its final")
    print(f"'weigh behavioral signals' note to hackathon participants.")


if __name__ == "__main__":
    main()
