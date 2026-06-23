# 🧠 Intelligent Candidate Discovery Engine

![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![AI](https://img.shields.io/badge/AI-Transformers-orange.svg)
![Status](https://img.shields.io/badge/Status-Hackathon%20Project-success.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Build](https://img.shields.io/badge/Build-Production--Ready-brightgreen.svg)

> **AI system that ranks job candidates using semantic understanding + behavioral intelligence instead of keyword matching.**

---

# 🚀 Overview

Recruitment systems today fail because they rely on **keyword-based filtering**, which cannot understand real meaning or intent. As a result, strong candidates are missed while poorly matched ones get ranked higher.

**Intelligent Candidate Discovery Engine** solves this by introducing an AI-driven ranking system that evaluates candidates based on:

- 🧠 **Semantic Understanding** → What the candidate *actually means* using transformer embeddings  
- 📊 **Behavioral Intelligence** → How active, responsive, and complete the candidate is  

These signals are combined into a **single unified ranking score**, producing a high-quality shortlist that is both **relevant and actionable**.

---

# ⚔️ Problem vs Solution

| Problem in ATS Systems | Our Solution |
|----------------------|-------------|
| Keyword matching fails to capture intent | Semantic embeddings capture meaning 🧠 |
| Good candidates get filtered out | Hidden talent is surfaced |
| No behavioral context | Engagement + activity included 📊 |
| Static ranking | Dynamic scoring engine ⚡ |
| Poor hiring accuracy | Real-world hiring signals |

---

# ✨ Key Features

- 🧠 Transformer-based semantic resume understanding  
- 📊 Behavioral scoring (activity, engagement, responsiveness)  
- ⚖️ Hybrid ranking system (semantic + behavioral fusion)  
- 🎯 Job-description-aware filtering (hard constraints)  
- 🔀 Plug-and-play AI models (MiniLM / BGE support)  
- 📄 Automated CSV submission generator  
- ✅ Fully validator-compliant output format  
- 🧩 Modular and scalable architecture  

---

# 🧠 How It Works

## 1. Semantic Matching Engine
We convert job descriptions and resumes into embeddings using Sentence Transformers.

Example:
- “built ML models in production”
- “deployed AI systems at scale”

👉 These are treated as highly similar even without shared words.

Similarity is calculated using cosine similarity.

---

## 2. Behavioral Scoring Engine

We evaluate real-world candidate activity using:

- 🕒 Login activity
- 💬 Responsiveness
- 📈 Engagement level
- 🧾 Profile completeness

All signals are normalized to a 0–1 scale.

---

## 3. Score Fusion

Final Score =
  0.7 × Semantic Score
+ 0.3 × Behavioral Score

---

## 4. Hard Filters

- Must-have skill enforcement  
- Penalty-based scoring  
- Disqualification rules  

---

# 🏗️ Architecture

Job Description + Candidates  
→ Semantic AI Engine  
→ Behavioral Scoring  
→ Score Fusion  
→ Hard Filters  
→ Final Ranked Output (Top 100)

---

# 📈 Results & Impact

- Improved semantic matching vs keyword systems  
- Faster candidate shortlisting  
- Better separation of strong vs weak candidates  
- Reduced keyword-stuffing bias  
- Fully compliant structured output  

---

# 🛠️ Tech Stack

Python 3.11  
Sentence Transformers  
Hugging Face Transformers  
scikit-learn  
pandas, numpy  
python-docx  
CSV + YAML output  
JSON Schema validation  

---

## 📁 Project Structure

```text
candidate-discovery-engine/
│
├── data/                                  # Challenge datasets & specifications
│   ├── candidates.jsonl
│   ├── candidate_schema.json
│   ├── job_description.docx
│   ├── README.docx
│   ├── redrob_signals_doc.docx
│   ├── sample_5_candidates.json
│   ├── sample_candidates.json
│   ├── sample_submission.csv
│   ├── submission_metadata_template.yaml
│   ├── submission_spec.docx
│   └── validate_submission.py
│
├── docs/                                  # Documentation & analysis
│   ├── semantic_scorer_readme.md
│   └── submission_analysis.md
│
├── output/                                # Generated submission files
│   ├── submission_metadata.yaml
│   └── team_ai_rankers.csv
│
├── src/
│   ├── config.py                          # Central configuration
│   ├── data_cleaner.py                    # Data preprocessing
│   ├── data_loader.py                     # Dataset loading utilities
│   ├── jd_semantic_analysis.py            # Job description analysis
│   ├── main.py                            # End-to-end pipeline entry point
│   ├── output_generator.py                # CSV output generation
│   ├── score_combiner.py                  # Weighted score fusion
│   ├── semantic_scorer.py                 # Embedding-based ranking
│   ├── semantic_variants.py               # Model comparison experiments
│   ├── signal_scorer.py                   # Behavioral signal scoring
│   └── test_semantic_variants.py          # Evaluation & testing
│
├── requirements.txt                       # Python dependencies
├── README.md                              # Project documentation
└── .gitignore
```



# ⚙️ Usage

git clone https://github.com/[TEAM]/candidate-discovery-engine.git  
cd candidate-discovery-engine  
pip install -r requirements.txt  
python src/main.py  

---

# 👥 Team

Ashish Maurya — Data Pipeline  
Adarsh Maurya — Semantic AI Engine  
Anish Maurya — Behavioral Scoring  
Priya Manna — Output & Integration  

---

# 🔮 Future Scope

Explainable AI ranking  
Multilingual support  
LLM candidate summaries  
Recruiter dashboard UI  

---

# 🏁 Why This Wins

Real-world hiring problem solved  
Modern AI (transformers + embeddings)  
Hybrid intelligence system  
Production-style architecture  
Judge-friendly output  

---

# 📜 License

MIT License
