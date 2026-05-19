## Session 1 — Project kickoff (May 18, 2026)

### Decisions made

**Project:** DFW Hospital Pricing: A Decision Tool for Texas Employers
**Domain:** Healthcare — hospital price transparency
**Geography:** Dallas-Fort Worth metroplex (local LinkedIn angle)
**Protagonist (v1):** Benefits manager at a ~200-person DFW employer
**Potential v2:** Self-pay patient angle, only if v1 ships cleanly
**Narrative voice:** "Economist who builds" — econ lens + working tools
**Econ framing:** Market failure under asymmetric information; ERISA fiduciary duty as the actionable hook
**Timeline:** 10 weeks at 10–15 hrs/week

### Data sources (all free)

- **Primary:** Trilliant Health public DuckDB data lake — 6B negotiated rates from 5,000+ US hospitals — https://oria-data.trillianthealth.com/
- **Supporting:** CMS shoppable services list (~70 procedures), CMS HPT rule docs, public hospital metadata (NPI, bed count, teaching status)
- **Backup:** Raw machine-readable files from individual hospital websites

### Tech stack

- Python 3.11+, virtual environment
- DuckDB + SQL for big data queries
- pandas, scikit-learn for analysis and modeling
- Streamlit for deployed app (Streamlit Cloud free tier)
- GitHub public repo, name `dfw-hospital-pricing`

### Project structure (10 weeks)

| Weeks | Phase | LinkedIn |
|-------|-------|----------|
| 1–2 | Scoping + data acquisition | Post #1 |
| 3–4 | Market analysis (price dispersion, payer comparison) | Posts #2–3 |
| 5–6 | Predictive model + feature importance | Post #4 |
| 7–8 | Streamlit decision tool, deployed | Post #5 |
| 9–10 | Polish, case study writeup, outreach | Posts #6–7 |

### Deliverables

1. Reproducible DFW price variation analysis (case study)
2. Live, deployed Streamlit tool with public URL
3. Clean public GitHub repo with documented methodology
4. Price prediction model with interpretable feature importance
5. 8–10 LinkedIn posts; ≥1 with meaningful industry engagement

### Explicit non-goals

- No patient out-of-pocket cost estimation
- No quality measurement (price-only, called out as a limitation)
- No specific hospital recommendations to specific patients
- Not medical advice, not a clinical tool

### LinkedIn strategy

- Cadence: 1 post/week
- Format: chart/screenshot + short hook + 3–5 sentences + question to drive comments
- Voice: "Look what I found," not "Look at me learning"
- ~30 min/week engaging on others' posts (Trilliant Health, Turquoise Health, KFF, health economists)
- Refresh headline + About before post #1

### README / project brief

- Final version drafted with layered CTAs (employer → data people → press → hiring — hiring last on purpose)
- Tagline: *"Turning public hospital price data into a decision tool for Texas employers."*
- To be committed as `README.md` at repo root when ready

### Key principles agreed on

- Ship working tools, not just notebooks
- Frame everything as decisions with dollars, not metrics alone
- Build in public — weekly LinkedIn cadence keeps the project honest
- Lean into econ background as the differentiator
- Scope ruthlessly; finish > breadth
- Claude is a thinking partner and reviewer, not a code generator — I own the work and the understanding

### Open questions / things to think about

- Which 3–5 procedures to start with? (Candidates: knee MRI, colonoscopy, normal childbirth, knee arthroscopy, cataract surgery — all CMS-shoppable, high-volume, broad payer coverage)
- Which DFW hospitals to start with? Likely the big systems: Baylor Scott & White, Texas Health Resources, Methodist Health System, HCA North Texas, Medical City Healthcare
- How granular on payers? Start with 2–3 majors: Blue Cross Blue Shield of TX, UnitedHealthcare, Aetna

---

## Workflow rules for this project

- One new Claude chat per working session, all inside this Claude project
- Each chat starts with: *"Continuing DFW hospital pricing project — today I want to [X]."*
- This `notes.md` is the source of truth for decisions and to-dos — update it at the end of every session
- All code lives in the GitHub repo, not in chats
- Weekly LinkedIn post is the forcing function — if I haven't shipped enough to post about by end of week, the week wasn't productive enough
## Session 4 — Disk cleanup, Python reinstall, Springboard recovery (May 18, 2026)

### Context

Session 2 (local env setup) and Session 3 (clean rebuild attempt) were not separately logged. Both happened on May 18–19. This entry consolidates what got done across all the setup work, ending with today's recovery from a disk-space crisis.

### What got done — across Sessions 2, 3, and 4

**Project structure**
- Created `C:\Users\kedha\Documents\dfw-hospital-pricing\` with subfolders `notebooks/`, `data/`, `src/`, `notes/`
- Initialized git, renamed default branch to `main`
- Created `.gitignore` with Python, venv, Jupyter, data, IDE, OS, and secrets exclusions
- Added `data/.gitkeep` placeholder

**Environment crisis and recovery**
- First attempt at `pip install` failed midway: disk had only 0.13 GB free
- Diagnosed with WizTree: Anaconda (12 GB) and hibernation file (6 GB) were the easiest wins; aruna's OneDrive (33.8 GB) deferred for a separate conversation
- Uninstalled Anaconda (cleanly removed registry; some leftover files in `C:\Users\kedha\anaconda3\` may remain — non-blocking)
- Disabled hibernation via `powercfg /hibernate off` from admin PowerShell
- Disk space recovered: 0.13 GB → 17+ GB free
- Discovered Anaconda had been providing the system Python; uninstall took Python with it
- Installed Python 3.13.13 fresh from python.org with "Add to PATH" checked

**Project environment (final state)**
- venv created at `dfw-hospital-pricing/venv/` using Python 3.13.13
- Packages installed: duckdb 1.5.2, pandas 3.0.3, jupyter, matplotlib, seaborn, ipykernel, scikit-learn
- `requirements.txt` generated (112 lines, ~4.3 KB)
- All key imports verified working

**Springboard recovery**
- Confirmed Springboard notebooks are stored in OneDrive at `OneDrive/Desktop/Documents/Springboard/`
- After Python reinstall, Springboard notebooks pick up global Python 3.13.13 automatically in VS Code
- Installed data science packages globally (separate from project venv) so Springboard notebooks work without activating any venv: pandas, numpy, scipy, matplotlib, seaborn, scikit-learn, jupyter, ipykernel, statsmodels, plotly
- Tested with "Gradient Boosting Case Study" notebook — Run All works after a kernel restart

### Two-environment model going forward

| Environment | Path | Use |
|---|---|---|
| Global Python 3.13.13 | `C:\Users\kedha\AppData\Local\Programs\Python\Python313\` | Springboard notebooks and other ad-hoc work |
| Project venv | `dfw-hospital-pricing/venv/` | DFW project only — activate before working on it |

### Open / deferred

- Talk to aruna about OneDrive Files On-Demand setting (for ~33 GB recovery if ever needed) — not urgent
- VS Code interpreter still needs to be set to project venv for our project
- First git commit not yet done
- First sanity-check notebook (`notebooks/01_sanity_check.ipynb`) not yet created
- First Trilliant data pull not yet attempted
- Decision: full name (first + last) for public repo and LinkedIn
- Decision: dedicated job-search email vs LinkedIn-only contact
- Recreate `README-draft.md` in notes folder when ready to publish

### Next session starts with

1. Set VS Code interpreter to project venv (`dfw-hospital-pricing/venv/Scripts/python.exe`)
2. Create `notebooks/01_sanity_check.ipynb` with imports + a hello-world chart
3. First git commit and push to GitHub (after creating the public GitHub repo)

### Hard-won lessons logged

- "Add Python to PATH" is the single most important checkbox in the Python installer
- Anaconda owning the system Python is silent and easy to miss
- A near-full disk silently breaks installers and PATH operations in ways that look unrelated
- Springboard's environment is separate from project venvs — both can coexist on the same machine

---