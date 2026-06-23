"""
test_semantic_variants.py   [SMOKE TEST]
=========================================
Minimal end-to-end check that the PUBLIC API of semantic_variants.py works.

It calls score_weighted_blend(...) directly and verifies the contract:
  1. Returns a dict
  2. Same candidate IDs as the input
  3. All values are floats
  4. All values are in [0.0, 1.0]

This is NOT a performance test or an analysis rerun. It uses:
  - the FAST model (all-MiniLM-L6-v2, already cached) to stay cheap,
  - a TINY 2-candidate input so encoding takes ~1 second.

Run it with:
    python src/test_semantic_variants.py
"""

import sys
from pathlib import Path

# Make sure we can import from the src/ folder regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from semantic_variants import score_weighted_blend  # noqa: E402
from semantic_scorer import DATA_DIR                  # noqa: E402

# Use the fast model for the smoke test — the point is to validate the API
# mechanics, not to measure accuracy. BGE would just make it slower.
FAST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Tiny input: 2 candidates with short profiles. Just enough to exercise the
# encode + blend + return path. Content is irrelevant for a smoke test.
SMOKE_CANDIDATES = {
    "SMOKE_001": "Python backend engineer with 3 years of experience "
                 "building data pipelines and REST APIs.",
    "SMOKE_002": "Marketing specialist focused on SEO and content strategy.",
}

JD_DOCX = DATA_DIR / "job_description.docx"


def run_smoke_test():
    """Run the four API-contract checks. Returns True if all pass."""
    print("=" * 60)
    print("SMOKE TEST: score_weighted_blend()")
    print("=" * 60)

    if not JD_DOCX.exists():
        print(f"❌ Cannot run smoke test — JD docx missing: {JD_DOCX}")
        return False

    print(f"Input: {len(SMOKE_CANDIDATES)} candidates, "
          f"model = {FAST_MODEL} (cached, fast)\n")

    # --- Call the public API directly --------------------------------------
    try:
        result = score_weighted_blend(
            JD_DOCX,
            SMOKE_CANDIDATES,
            model_name=FAST_MODEL,
        )
    except Exception as e:
        print(f"❌ score_weighted_blend() raised an exception: {e}")
        return False

    # --- Check 1: returns a dict -------------------------------------------
    check1 = isinstance(result, dict)
    print(f"[{'PASS' if check1 else 'FAIL'}] 1. Returns a dict: "
          f"{type(result).__name__}")

    # --- Check 2: same candidate IDs as input ------------------------------
    check2 = set(result.keys()) == set(SMOKE_CANDIDATES.keys())
    print(f"[{'PASS' if check2 else 'FAIL'}] 2. Same candidate IDs as input: "
          f"{sorted(result.keys())}")

    # --- Check 3: all values are floats ------------------------------------
    check3 = all(isinstance(v, float) for v in result.values())
    types = {type(v).__name__ for v in result.values()}
    print(f"[{'PASS' if check3 else 'FAIL'}] 3. All values are floats: "
          f"types seen = {types}")

    # --- Check 4: all values in [0.0, 1.0] ---------------------------------
    check4 = all(0.0 <= v <= 1.0 for v in result.values())
    print(f"[{'PASS' if check4 else 'FAIL'}] 4. All values in [0, 1]: "
          f"range = [{min(result.values()):.4f}, "
          f"{max(result.values()):.4f}]")

    # --- Summary -----------------------------------------------------------
    all_pass = check1 and check2 and check3 and check4
    print("\n" + ("✅ SMOKE TEST PASSED — public API works end-to-end."
                  if all_pass else
                  "❌ SMOKE TEST FAILED — see failures above."))
    return all_pass


if __name__ == "__main__":
    ok = run_smoke_test()
    sys.exit(0 if ok else 1)
