# Submission Spec Analysis — Redrob Hackathon v4

Plain-English breakdown of exactly what we need to produce. Source: `data/submission_spec.docx`, `data/submission_metadata_template.yaml`, `data/validate_submission.py`, `data/sample_submission.csv`.

> **TL;DR:** One CSV named `<team_id>.csv`, UTF-8, with a header + **exactly 100 rows** ranking our top-100 candidates. Columns: `candidate_id,rank,score,reasoning`. Scores must go from high (rank 1) to low (rank 100), never the other way.

---

## 1. Output File Format

| Item | Value |
|------|-------|
| **File format** | **CSV** (plain text, comma-separated). NOT `.xlsx`, NOT `.json`. |
| **Filename** | Your team's **registered participant ID** + `.csv`. Example: `team_xxx.csv`. (We'll get this exact ID at registration.) |
| **Encoding** | **UTF-8** (mandatory — the validator rejects non-UTF-8). |
| **Header row (row 1)** | Must be **exactly**: `candidate_id,rank,score,reasoning` — in this order, no extra columns, no missing columns, exact spelling. |
| **Data rows (rows 2–101)** | **Exactly 100 rows.** Not 99, not 101. |

### Required columns (in this exact order)

| # | Column | Type | Required? | Rules |
|---|--------|------|-----------|-------|
| 1 | `candidate_id` | string | ✅ Yes | Format **`CAND_XXXXXXX`** — the literal text `CAND_` followed by **exactly 7 digits**. Must exist in `candidates.jsonl`. No duplicates. |
| 2 | `rank` | integer | ✅ Yes | Whole number **1 to 100**. Each integer 1–100 must appear **exactly once**. Rank 1 = best, rank 100 = worst. (Do NOT start at 0.) |
| 3 | `score` | float (decimal) | ✅ Yes | Your model's score. Must be **non-increasing** as rank increases (rank 1 ≥ rank 2 ≥ … ≥ rank 100). Ties allowed, but see tie-break rule below. All-same scores = auto-reject (model isn't differentiating). |
| 4 | `reasoning` | string | ⚠ Optional but strongly recommended | 1–2 sentences justifying the rank. Manually reviewed at Stage 4. Empty/templated/hallucinated reasoning is penalized. |

### Sort order
Sorted by `rank` ascending (1 → 100). This is equivalent to `score` **descending** (high → low).

---

## 2. Candidate Count

- **Exactly the top 100 candidates.** Rank 1 = best fit, rank 100 = 100th best.
- Candidates ranked 101+ are **not** included in the file at all.
- There are **100,000 candidates** in `candidates.jsonl`, so we're picking the top **0.1%**.
- **Minimum = maximum = 100.** Any other number of rows fails validation instantly.

---

## 3. Metadata Template (`submission_metadata.yaml`)

Copy `data/submission_metadata_template.yaml` to the **repo root** and fill it in. It must match what we submit via the portal.

### Required fields (all of these MUST be filled)

| Field | Required | Notes |
|-------|----------|-------|
| `team_name` | ✅ Yes | For leaderboard/announcements. |
| `primary_contact.name` | ✅ Yes | One point of contact. |
| `primary_contact.email` | ✅ Yes | Organizer communication. |
| `primary_contact.phone` | ✅ Yes | For top-50/top-10 outreach. |
| `github_repo` | ✅ Yes | Format `https://github.com/USER/REPO`. Private OK if we grant access at Stage 3. |
| `sandbox_link` | ✅ Yes | A **working hosted demo** (HuggingFace Spaces / Streamlit Cloud / Replit / Colab / Docker / Binder). See §5 gotchas. |
| `reproduce_command` | ✅ Yes | The **single command** that builds the CSV from `candidates.jsonl`. Example: `python rank.py --candidates ./candidates.jsonl --out ./submission.csv`. |
| `compute.platform` / `cpu_cores` / `ram_gb` / `python_version` / `os` | ✅ Yes | Describe our machine. |
| `compute.uses_gpu_for_inference` | ✅ Yes | **Must be `false`.** |
| `compute.has_network_during_ranking` | ✅ Yes | **Must be `false`.** |
| `compute.pre_computation_required` / `pre_computation_time_minutes` | ✅ Yes | True if we pre-compute embeddings offline (allowed; only the *ranking* step is time-boxed). |
| `ai_tools_used` | ✅ Yes | Multi-select: Claude / ChatGPT / Copilot / Cursor / Gemini / Other / None. **Honest** declaration — not penalized. |
| `ai_usage_summary` | ✅ Yes (implied) | One-paragraph description of how AI was used. |
| `team_members` (list with name+email) | ✅ Yes | Name + email per member. `role` is optional. |
| `declarations.read_submission_spec` | ✅ Yes | Set `true`. |
| `declarations.code_is_original_work` | ✅ Yes | Set `true`. |
| `declarations.no_collusion` | ✅ Yes | Set `true`. |
| `declarations.reproduction_tested` | ✅ Yes | Set `true` (and actually test it!). |

### Optional fields

| Field | Required | Notes |
|-------|----------|-------|
| `methodology_summary` | Optional | ≤200 words. **Strongly recommended** — helps at Stage 4 review. |
| `team_members[].role` | Optional | e.g. "Team Lead", "Data Engineer". |
| `declarations.honeypot_check_done` | Optional | Set `true` if we explicitly filtered honeypots. |

---

## 4. Validation — What `validate_submission.py` Checks

The provided script (`data/validate_submission.py`) performs **local format checks only** (it does NOT score us — scoring is against hidden ground truth, done once after submissions close).

### Checks performed (each failure = one error, submission rejected if any error)

1. **File extension** is `.csv` (and the filename stem is non-empty).
2. **UTF-8 encoding** — a `UnicodeDecodeError` fails it.
3. **Header row** equals **exactly** `candidate_id,rank,score,reasoning` (order + spelling).
4. **Row count** = exactly **100 data rows** after the header.
5. **Column count** = 4 per row (no extra/missing columns).
6. **`candidate_id` format** matches regex `^CAND_[0-9]{7}$` (`CAND_` + 7 digits).
7. **`candidate_id` unique** — no duplicates.
8. **`rank`** is an integer 1–100, and `str(int)` matches the raw string (so `"1.0"` or `" 1"` are rejected).
9. **`rank` unique** — each 1–100 appears exactly once (missing ranks are also flagged).
10. **`score`** parses as a float.
11. **Monotonic scores** — score at rank *i* ≥ score at rank *i+1* (non-increasing). Any increase = error.
12. **Tie-break ordering** — when two candidates have **equal scores**, the one with the **smaller rank** must have the **lexicographically smaller `candidate_id`** (i.e. ties broken by `candidate_id` ascending). If the lower-ranked (better) candidate has a larger ID, it's an error.

### Most common reasons submissions fail (the spec calls these out explicitly)
- 99 or 101 rows instead of exactly 100.
- Ranks starting at **0** instead of 1.
- Duplicate `candidate_id`s.
- `candidate_id` typos not present in `candidates.jsonl` *(note: the local script does NOT check existence — but the server-side validator does. We must check this ourselves.)*
- All scores identical (model not differentiating).
- Scores **increasing** with rank (rank 1 has the lowest score — backwards).
- Submitting `.xlsx`/`.json` instead of `.csv`.

> ⚠ **Important:** The local `validate_submission.py` does NOT verify that candidate IDs actually exist in `candidates.jsonl`. The **server-side** auto-validator does. We should add our own existence check (all 100 IDs must be found in the JSONL) before submitting.

---

## 5. Gotchas, Edge Cases & Quirks

### 🔴 Critical (auto-reject)
- **Exactly 100 rows**, header + 100. No more, no less.
- **Ranks 1–100**, each used exactly once, starting at **1 not 0**.
- **Scores non-increasing** down the list. A single violation (rank 5 score < rank 6 score) fails the whole file.
- **Tie-break rule is strict**: equal scores must be ordered by `candidate_id` **ascending**. E.g., if `CAND_0001111` and `CAND_0002222` tie at 0.95, the `0001111` one must come first. The validator enforces this.
- **CSV only**, UTF-8. No BOM issues, no Excel quirks.
- **Header spelling/order exact**: `candidate_id,rank,score,reasoning`.
- **No duplicate candidate_ids**, and (server-side) every ID **must exist** in `candidates.jsonl`.

### 🟠 Strategy-level (disqualification risk)
- **Honeypots:** ~80 fake candidates with impossible profiles (e.g., 8 years at a company founded 3 years ago; "expert" in 10 skills with 0 years used). They're forced to relevance tier 0 in ground truth. **If >10% of our top-100 are honeypots → disqualified at Stage 3.** Ranking honeypots in the top 10 signals keyword-stuffing-only matching. A good profile-reading ranker avoids them naturally — no need to special-case, but worth a sanity check.
- **Compute constraints (enforced at Stage 3 in a sandboxed Docker container):**
  - ≤ **5 minutes wall-clock** for the ranking step.
  - ≤ **16 GB RAM**.
  - **CPU only — no GPU.**
  - **No network during ranking** — no OpenAI/Anthropic/Cohere/Gemini/hosted-LLM calls. (Pre-computation may exceed 5 min, but the final CSV-producing step must fit.)
  - ≤ 5 GB intermediate disk state.
- **3-submission cap.** Only 3 submissions total; the last valid one counts. No live leaderboard, so local validation matters.
- **Code repo must be reproducible.** A single command must produce the CSV. Stage 3 reproduces it in their sandbox. Fake/missing repo = disqualification.

### 🟡 Quality (Stage 4 manual review)
- **Reasoning column** is optional for format but **heavily** matters for scoring top submissions. 10 random rows are reviewed for: specific facts from the profile, JD connection, honest concerns, **no hallucination** (don't invent skills/employers), variation (not templated), and rank-consistency (tone matches rank).
- **Git history authenticity** — real iteration beats a single dump.
- **Defend-your-work interview** (Stage 5) — must be able to explain our own architecture.

### 🟢 Practical / numeric
- No fixed decimal-place rule for `score` (the validator just does `float()`), but the sample uses **4 decimals** (e.g., `0.9920`). We can match that for cleanliness.
- `score` range isn't pinned to 0–1 by the validator, but conceptually it's our model's confidence — keeping it in 0–1 is sensible and matches the sample.
- `reasoning` field — if it contains commas, the CSV writer **must quote it** (use Python's `csv` module, not manual string concatenation, to avoid breaking columns). The sample shows quoted reasoning.
- `reproduce_command` in the YAML must actually work end-to-end on a clean checkout — test it.

### 📦 What we submit (3 parts, all required)
1. The **CSV** (top-100 ranking).
2. **Portal metadata** (filled in at upload; mirrors the YAML).
3. **GitHub repo** containing: README with single reproduce command, full source, any pre-computed artifacts (or a script to build them), `requirements.txt` with versions, and `submission_metadata.yaml` at root.

---

## Quick reference — the perfect submission in one glance

```
File:   team_xxx.csv   (our registered participant ID)
Encode: UTF-8
Row 1:  candidate_id,rank,score,reasoning
Rows 2-101: 100 rows, rank 1→100, score high→low (non-increasing, ties broken by candidate_id asc)
IDs:    every CAND_XXXXXXX must exist in candidates.jsonl; no dupes
Check:  python data/validate_submission.py output/team_xxx.csv  → must print "Submission is valid."
```
