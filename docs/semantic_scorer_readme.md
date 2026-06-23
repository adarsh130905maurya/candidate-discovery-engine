# semantic_scorer.py — README

## 1. What it does

`semantic_scorer.py` scores how well each candidate's profile matches a job
description using **sentence embeddings + cosine similarity**. It encodes the
job description and every candidate profile into vectors with a
sentence-transformers model, then measures the cosine similarity between the
job vector and each candidate vector to produce a relevance score. This score
becomes the **semantic component** of the final ranked candidate list (blended
with behavioral signals by `score_combiner.py`).

## 2. What model it uses and why

| Model | Size | Dimensions | Speed | Accuracy | When to use |
|-------|------|-----------|-------|----------|-------------|
| `sentence-transformers/all-MiniLM-L6-v2` *(default)* | ~80 MB | 384 | fast | good | Iteration, quick runs, CPU-only machines |
| `BAAI/bge-base-en-v1.5` *(optional)* | ~420 MB | 768 | slow | high | Final submission where ranking quality matters most |

**Why the MiniLM default:** the hackathon spec requires CPU-only inference
with no network during ranking. MiniLM is small enough to load and run
comfortably on a basic laptop in a few seconds, while still producing
meaningful semantic rankings. It's the right tradeoff for development.

**Why BGE is available:** testing showed BGE produces sharper score separation
on ambiguous candidates (it correctly distinguished technical vs. non-technical
profiles where MiniLM clustered them). For the final one-shot submission, the
extra accuracy is worth the larger download. Switch by passing
`model_name="BAAI/bge-base-en-v1.5"`.

Models are cached after first download, so the cost is paid once.

## 3. How to call it from another script

```python
from semantic_scorer import compute_semantic_scores

# Default (fast) model:
scores = compute_semantic_scores(job_text, {id: text_dict})
# Returns: {candidate_id: float_score}

# Or use the more accurate model:
scores = compute_semantic_scores(
    job_text,
    {id: text_dict},
    model_name="BAAI/bge-base-en-v1.5",
)
```

## 4. Input format expected

```python
compute_semantic_scores(job_description, candidate_profiles, model_name=None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_description` | `str` | The full job-description text. Multi-sentence paragraphs are fine. Must be non-empty. |
| `candidate_profiles` | `dict` | Mapping of `{candidate_id: profile_text}`. Each `profile_text` is a string. Must be non-empty. |
| `model_name` | `str` or `None` | Which model to use. `None` falls back to the default (`all-MiniLM-L6-v2`). Must be one of the supported models. |

Example:
```python
job_text = "Senior ML Engineer with Python, PyTorch, and NLP experience..."
candidates = {
    "CAND_0000001": "Senior ML Engineer with 5 years of Python and PyTorch...",
    "CAND_0000002": "Full-stack developer specializing in React and Node.js...",
}
```

## 5. Output format returned

```python
{candidate_id: similarity_score}
```

- A `dict` with the **same keys** as the input `candidate_profiles`.
- Each value is a `float` between **`0.0`** (no semantic overlap) and
  **`1.0`** (near-identical meaning).
- Scores are rounded to 4 decimal places.
- Values are clipped to `[0.0, 1.0]` to guard against floating-point edge cases.

Example:
```python
{
    "CAND_0000001": 0.6906,
    "CAND_0000002": 0.3910,
}
```

## 6. How long it takes (rough estimates)

Timings were measured on a CPU-only laptop. Two phases have very different
costs:

### First run ever (downloads the model)
| Model | Download | Total time |
|-------|---------|------------|
| `all-MiniLM-L6-v2` | ~80 MB | ~1–2 minutes |
| `bge-base-en-v1.5` | ~420 MB | ~5–10 minutes |

### Subsequent runs (model cached locally)
| Model | Model load | Encoding ~5 candidates | Encoding ~100 candidates |
|-------|-----------|----------------------|--------------------------|
| `all-MiniLM-L6-v2` | ~1–2 s | ~2–3 s | ~10–20 s |
| `bge-base-en-v1.5` | ~3–5 s | ~5–8 s | ~30–60 s |

Notes:
- **Encoding scales roughly linearly** with the number of candidates (profiles
  are encoded in batches of 32).
- The **job description is encoded once** per call, regardless of candidate
  count.
- The model is **cached in memory** after first load within a process, so
  repeated calls in the same script skip the load cost entirely.

---

### Files in this module

| File | Purpose |
|------|---------|
| `src/semantic_scorer.py` | The scorer itself (production code) |
| `src/jd_semantic_analysis.py` | Analysis of why scores cluster (diagnostic) |
| `src/semantic_variants.py` | Experiment: full-JD vs requirements-only vs blend |
| `src/test_semantic_variants.py` | Smoke test for the variants API |
| `data/sample_5_candidates.json` | 5-candidate real sample for testing |
| `data/job_description.docx` | The real job description |
