# 🧠 Intelligent Candidate Discovery Engine

> **A predictive candidate ranking engine that uses semantic AI and behavioral signals to intelligently match candidates to job descriptions.**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![AI](https://img.shields.io/badge/AI-Semantic%20Matching-purple)
![Status](https://img.shields.io/badge/Status-Hackathon%20Ready-brightgreen)

---

## 📖 Overview

Recruiters today are drowning in applications. A single job posting can attract hundreds — sometimes thousands — of candidates, and traditional filtering systems handle this volume the worst possible way: by matching keywords. The result is a double failure. Strong candidates who simply used different words for the same skills get buried, while keyword-stuffers who game the system rise to the top. The recruiter is forced to manually re-read profiles that the algorithm already failed to understand, and the real talent slips away.

**Semantic understanding solves the hidden-match problem.** Instead of asking "do these words match?", a transformer-based engine asks "do these *meanings* match?" A candidate who wrote "built prediction models in production" and a job that asks for "applied machine learning at scale" never share a keyword — but to a semantic model, they are nearly identical. This is the difference between a system that reads resumes and a system that *understands* them.

**But meaning alone isn't enough.** A brilliant resume from a candidate who hasn't logged in for six months, never responds to messages, and left their profile half-finished is a poor hiring bet in practice. Behavioral signals — login recency, engagement, responsiveness, profile completeness — capture whether a candidate is genuinely *reachable and interested*. Ignoring them produces rankings that look good on paper but fail in the real world of recruiting.

Our system **combines both approaches** into a single, transparent ranking pipeline. Semantic matching establishes *fit*; behavioral signals establish *viability*; and a weighted fusion formula produces a final score that reflects the whole picture. The result is a ranked shortlist that a recruiter can trust — candidates who are both qualified and genuinely ready to engage.

---

## ✨ Key Features

- 🧠 **Semantic resume understanding** — Transformer embeddings capture meaning, not just keywords
- 📊 **Behavioral signal scoring** — Login recency, engagement, responsiveness & profile completeness
- 🔀 **Multi-model AI support** — Pluggable models (`all-MiniLM-L6-v2` for speed, `BAAI/bge-base-en-v1.5` for accuracy)
- 🎯 **Requirements-aware ranking** — Must-have skills and hard filters shape the final ordering
- ⚖️ **Weighted score fusion** — Configurable blend of semantic fit and behavioral viability
- 📄 **Automated CSV submission** — One command produces the exact ranked output file
- ✅ **Validator-compliant output** — Built against the official `validate_submission.py` rules
- 🧩 **Modular architecture** — Each stage is independent, testable, and swappable

---

## 🏗️ Architecture

```text
                    ┌───────────────────────┐
                    │  Job Description      │
                    │  (job_description.docx)│
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Candidate Profiles   │
                    │  (candidates.jsonl)   │
                    └───────────┬───────────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
                ▼                               ▼
   ┌───────────────────────┐      ┌───────────────────────┐
   │  Semantic AI Engine   │      │  Behavioral Signals   │
   │  (Transformer embeds  │      │  (activity, response, │
   │   + cosine similarity)│      │   completeness, etc.) │
   └───────────┬───────────┘      └───────────┬───────────┘
               │                              │
               │   0.7 weight                 │  0.3 weight
               └───────────────┬──────────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │  Hard Filters         │
                   │  (must-have reqs,     │
                   │   penalties, dq rules)│
                   └───────────┬───────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │  Weighted Fusion      │
                   │  → Final Ranking Score│
                   └───────────┬───────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │  Ranking + Validation │
                   │  (top-100 CSV output) │
                   └───────────────────────┘
```

---

## 🧪 Methodology

### Semantic Matching

At the core of the engine is **`sentence-transformers`**, a Hugging Face library built on top of transformer architectures. Each candidate's profile text is converted into a dense **embedding** — a numerical vector of a few hundred dimensions that captures the *meaning* of the text. The job description is embedded the same way.

We then compare the job-description vector to each candidate vector using **cosine similarity**, which measures the angle between two vectors regardless of their length. Two texts that *mean* the same thing point in nearly the same direction in vector space and score close to `1.0`.

The critical advantage over keyword matching: "machine learning engineer" and "AI developer building prediction models" share almost no words, yet their embeddings are nearly identical. Semantic matching recovers these hidden matches that keyword filters systematically miss.

### Behavioral Signals

A strong resume is necessary but not sufficient. We extract four families of behavioral signals from each candidate's activity data:

| Signal | What it captures |
|--------|------------------|
| **Activity score** | How recently and frequently the candidate logs in |
| **Engagement score** | Depth of platform interaction (applications, updates) |
| **Responsiveness** | How quickly the candidate replies to outreach |
| **Profile completeness** | Whether the profile is filled out enough to evaluate |

All signals are **MinMax-normalized** to a `0.0–1.0` range so that no single signal dominates simply because of its raw scale. For "lower is better" signals (e.g., response time), the score is inverted so that `1.0` always means "best".

### Score Fusion

The two score families are combined with a configurable weighted blend:

```text
Final Score =
    0.7 × Semantic Score
  + 0.3 × Behavioral Score
```

Weighted fusion improves ranking quality because the two signals are **complementary, not redundant**. Semantic fit is the *primary* driver — it answers "can this person do the job?" Behavioral signals are the *modifier* — they answer "is this person worth contacting *right now*?" Giving semantic match the larger weight ensures we never promote an unqualified-but-active candidate above a qualified-but-quiet one, while still rewarding genuine engagement.

### Hard Filters

Not every candidate should be ranked, no matter how they score. A **hard filter** layer enforces non-negotiable business rules:

- **Must-have requirements** — If the JD demands a skill, candidates missing it are penalized or excluded
- **Penalties** — Partial-miss candidates receive a multiplicative deduction, not full disqualification
- **Disqualification logic** — Candidates with impossible/contradictory profiles (e.g., honeypots) are pushed to relevance tier 0
- **Business rule enforcement** — Ensures the final ranking reflects real hiring constraints, not just model math

---

## 📈 Results & Insights

Findings from the development and testing phase:

| Finding | Detail |
|---------|--------|
| 🔬 **Model comparison** | Benchmarked `all-MiniLM-L6-v2` against `BAAI/bge-base-en-v1.5` across speed and accuracy trade-offs |
| 👥 **Real-world validation** | Candidate testing completed against the released 100K-candidate pool |
| 📊 **Score separation** | In our development experiments, requirements-focused scoring increased candidate score separation by approximately 1.9× on the evaluated sample |
| 🎯 **Discrimination** | Semantic scoring successfully distinguished genuinely relevant candidates from keyword-stuffers and adjacent-skill-only matches |
| ✅ **Output compliance** | Generated submissions validate cleanly against the official `validate_submission.py` with zero errors |

> **Note on the score-separation figure:** This observation was measured during development testing on the evaluated candidate sample. Results may vary depending on the job description and candidate pool. The figure is included as an empirical project insight rather than a universal performance guarantee.

---

## 🛠️ Tech Stack

| Category         | Technology            |
| ---------------- | --------------------- |
| Language         | Python 3.11           |
| AI Models        | Sentence Transformers |
| NLP              | Hugging Face          |
| ML Utilities     | scikit-learn          |
| Data Processing  | pandas, numpy         |
| Document Parsing | python-docx           |
| Validation       | JSON Schema           |
| Output           | CSV + YAML            |

---

## 📁 Project Structure

```text
candidate-discovery-engine/
│
├── data/                        # Raw challenge inputs (candidates, JD, spec, validator)
├── docs/                        # Analysis & design documentation
│   └── submission_analysis.md   # Plain-English breakdown of the submission spec
├── output/                      # Generated CSV submissions + metadata
├── src/
│   ├── semantic_scorer.py       # Core semantic matching engine (embeddings + cosine)
│   ├── semantic_variants.py     # Model-swap variants (MiniLM vs BGE)
│   ├── jd_semantic_analysis.py  # Job-description requirement extraction
│   ├── output_generator.py      # Formats ranked list → validator-compliant CSV
│   ├── validate_submission.py   # Official format validator (run before submit)
│   └── main.py                  # End-to-end pipeline entry point
│
├── requirements.txt             # Python dependencies
├── README.md                    # This file
└── .gitignore                   # Ignores output/, data caches, model weights
```

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/[TEAM]/candidate-discovery-engine.git

# 2. Move into the project folder
cd candidate-discovery-engine

# 3. Install dependencies (Python 3.11 recommended)
pip install -r requirements.txt
```

**Setup notes:**
- Python **3.11** is recommended (matches the declared compute environment).
- The default model (`all-MiniLM-L6-v2`, ~90 MB) downloads automatically on first run.
- Everything runs **CPU-only** — no GPU required.
- No external API keys are needed; no network calls are made during ranking.

---

## ▶️ Usage

```bash
python src/main.py
```

Running the pipeline executes the full flow end-to-end:

1. **Loads** the job description from `data/job_description.docx`
2. **Loads** candidate profiles from `data/candidates.jsonl`
3. **Computes** semantic similarity (transformer embeddings + cosine)
4. **Computes** behavioral scores from activity signals
5. **Fuses** the two with weighted scoring + hard filters
6. **Generates** the submission CSV and metadata YAML in `output/`
7. **Validates** the output against the official validator

To test the output formatter independently (without the full pipeline):

```bash
python src/output_generator.py
```

---

## ⚙️ Configuration

Key parameters live at the top of the relevant modules and are fully tunable:

```python
# — Model selection —
# Speed-first (~90MB, fast on CPU):
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Accuracy-first (larger, higher quality):
MODEL_NAME = "BAAI/bge-base-en-v1.5"

# — Score fusion weights (must sum to 1.0) —
SEMANTIC_WEIGHT = 0.7
BEHAVIORAL_WEIGHT = 0.3

# — Output sizing —
TOP_K = 100
```

**How to tune these:**
- **`MODEL_NAME`** — Swap to a larger model when accuracy matters more than latency, or to MiniLM when the 5-minute CPU budget is tight.
- **`SEMANTIC_WEIGHT` / `BEHAVIORAL_WEIGHT`** — Rebalance fit-vs-engagement. A recruiting funnel optimized for *quality* raises the semantic weight; one optimized for *response rate* raises behavioral.
- **`TOP_K`** — Controls how many candidates appear in the final ranked output (the hackathon requires exactly 100).

---

## 👥 Team Members

| Member | Role |
|--------|------|
| **Ashish Maurya** | Data Pipeline & Ingestion |
| **Adarsh Maurya** | Semantic AI Engine |
| **Anish Maurya** | Behavioral Scoring & Fusion |
| **Priya Manna** | Output, Validation & Integration |

---

## 🔮 Future Improvements

- 💡 **Explainable AI ranking insights** — Per-candidate breakdowns of *why* they ranked where they did
- 🎚️ **Adaptive weighting strategies** — Learn optimal fusion weights from recruiter feedback over time
- 🌍 **Multi-language candidate matching** — Cross-lingual embeddings for global talent pools
- 📝 **LLM-powered candidate summaries** — Concise, honest one-line rationale per candidate (within compute budget)
- 🖥️ **Recruiter dashboard integration** — Live ranking UI with drill-down and re-ranking controls

---

## 📄 License

Released under the **MIT License**. See the project root for the full license text.

---

> *Advancing intelligent talent discovery through AI-driven candidate ranking — matching the right people to the right opportunities, at scale.*
