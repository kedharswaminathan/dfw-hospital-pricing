# DFW Hospital Pricing Transparency Analysis

**Author:** Kedhar Swaminathan

Federal rules require hospitals to publish machine-readable files of what they charge. This project tests whether those files actually let anyone compare prices — using one common procedure across five Dallas–Fort Worth hospitals.

The short answer is no, and the reason is more interesting than the price spread.

---

## The question

CPT 73721 — MRI of a lower-extremity joint without contrast — is a routine outpatient scan. It is on CMS's shoppable-services list, high-volume, and covered by essentially every payer. If price transparency works anywhere, it should work here.

So: what does the same scan cost across five DFW hospitals, and can a patient or employer meaningfully compare those numbers?

---

## Data

Machine-readable price transparency files from five hospitals, parsed into DuckDB databases (~710 MB total):

| Hospital | Type |
|---|---|
| Baylor University Medical Center | Nonprofit academic |
| Methodist Dallas Medical Center | Nonprofit |
| Texas Health Presbyterian Plano | Nonprofit |
| Medical City Alliance | For-profit (HCA) |
| Parkland Health | Public safety-net |

Querying CPT 73721 in the outpatient setting across all five returns **278 rows**, each a distinct combination of payer, plan, methodology, and billing class.

The raw files are not committed — they are large and publicly available. `data/raw/` is gitignored; see [Reproducing](#reproducing).

---

## The hard part: payer classification

The transparency files identify payers as free text. Real examples from these files:

```
MHS HB MULTIPLAN ADVANTAGE MDMC
AETNA BETTER HEALTH STAR [131700]
WELLPOINT STAR KIDS [100706]
MUTUAL OF OMAHA MEDICARE MANAGED CARE
```

Before any rate can be compared, each row has to be assigned a line of business — commercial, Medicare Advantage, traditional Medicare, Medicaid and its Texas sub-types, ACA exchange, and several others. Getting this wrong silently corrupts every downstream number: a single Medicare Advantage row misfiled as traditional Medicare contaminates the benchmark that every multiple in this analysis divides by.

`src/queries.py` implements this as an **ordered rule cascade**. The order is the specification, not an implementation detail:

1. **Specialty** (dental, vision) — runs first and overrides everything
2. **Government payer group** (Medicare, Medicaid) — the payer group decides the family; the plan name may only refine the sub-type
3. **Commercial payer group** (BCBS, Aetna, UnitedHealthcare, Cigna, Humana) — plan name wins if it matched, otherwise fall back to the group default
4. **Plan-name regex**, specific patterns before generic ones — `Medicare Advantage` must be tested before bare `Medicare`, or every MA row lands in traditional Medicare
5. **Payer-name regex** — last resort, for rows whose plan name carries no signal
6. **Catch-all** → `unknown`

Every rule returns *which rule fired* alongside the answer, so a misclassification is traceable to a specific line rather than to "the regex."

### The rule worth reading the code for

Version 4 replaced a hardcoded carrier list with a rule grounded in how the program actually works:

> Traditional Medicare fee-for-service is administered by CMS, never by a named carrier.

So a row tagged Medicare with a payer of "Humana" is Medicare Advantage; a row with a payer of "Medicare" or "CMS" stays traditional. That generalizes to procedure codes this dataset does not contain, which a carrier list would not.

### What each version fixed

Unclassified combinations, out of 278:

| Version | Added | Unknown | Share |
|---|---|---|---|
| v1 | Plan-name regex only | 127 | 46% |
| v2 | + payer-group defaults | 59 | 21% |
| v3 | + payer-name fallback | 7 | 2.5% |
| v4 | + Medicare/Medicaid recovery | 5 | 1.8% |

The surviving unknowns at each stage are committed in `outputs/unknown_payers_v1.txt` through `v3.txt` — the working record of what each version still got wrong.

Specific failures found by reading those files:

- `Medicare PPO` and `Medicare PFFS` are Medicare Advantage plan types, not traditional Medicare
- `STARKids` and `STARPerinate` are concatenated tokens that a `\bSTAR\b` word boundary silently misses
- Centene's Ambetter/Superior co-brand is a Medicaid product despite the commercial-sounding name
- `MCD` and `MGMCD` are Medicaid abbreviations that a literal `Medicaid` match never catches
- A dental carrier appears with rows for a knee MRI — a payer-file artifact, and the reason the specialty bucket runs before everything else

The resulting distribution across all 278 rows:

| Line of business | Rows |
|---|---|
| Commercial | 95 |
| Medicare Advantage | 73 |
| Medicaid (CHIP / STAR / STAR+PLUS / other) | 59 |
| TPA / self-funded | 16 |
| ACA exchange | 12 |
| Employer captive | 7 |
| Workers' compensation | 6 |
| Unknown | 5 |
| Federal other (TriWest, HRSA, VA) | 3 |
| Commercial specialty (dental / vision) | 2 |

---

## What the rates look like

Of the 95 commercial rows, 79 carry a dollar rate. The remaining 16 publish only a percentage — 9 at Medical City Alliance, 5 at Texas Health Presbyterian, 2 at Parkland. The loader reports these before dropping them, because the count is itself a finding: percent-of-charges contracts are not unique to one hospital.

Median commercial rate for CPT 73721:

| Hospital | Commercial rate | × Medicare FFS |
|---|---|---|
| Baylor University Medical Center | $1,944.56 | 8.0× |
| Methodist Dallas | $1,518.00 | 6.2× |
| Texas Health Presbyterian Plano | $1,262.69 | 5.2× |
| Medical City Alliance | $906.53 | 3.7× |

**The same scan costs 2.1× more at the most expensive of these hospitals than the least.**

Rates are expressed as a multiple of Medicare's fee schedule because Medicare's rate is set by formula and already adjusted for local wages and hospital characteristics. That strips out most of what would otherwise be blamed on "different hospitals, different costs." Baylor at 8.0× versus Medical City at 3.7× is a difference in negotiating position, not in cost structure.

### How robust is that ordering?

Reporting a median is a choice, and a choice you have not tested is an assumption. Running all three statistics shows which conclusions survive:

| Hospital | Median | Mean | Trimmed mean |
|---|---|---|---|
| Baylor | $1,944.56 | $1,903.34 | $1,932.36 |
| Methodist | $1,518.00 | $1,274.44 | $1,222.15 |
| Texas Health Presbyterian | $1,262.69 | $1,289.77 | $1,267.60 |
| Medical City Alliance | $906.53 | $769.16 | $763.83 |

**The endpoints hold and the middle does not.** Baylor is highest and Medical City lowest under all three, but Methodist and Texas Health Presbyterian swap places under mean and trimmed mean — Methodist's distribution is left-skewed, with a $1,518 median against a $1,274 mean. The top-to-bottom spread also widens, from 2.1× on medians to roughly 2.5× on means.

The headline is robust. The rank ordering between the middle two hospitals is not, and should not be quoted.

Notably, the for-profit hospital has the *lowest* multiple and the large nonprofit academic center the highest — the opposite of what most people assume. With five hospitals, ownership type is collinear with size, teaching status, and case mix, so this is an observation to test on a larger sample rather than a finding.

---

## Parkland is excluded, and that is the finding

Parkland computes to a $3,937.50 median — 16.2× Medicare, more than double Baylor. That number is real in the file and meaningless as a price.

Every one of Parkland's commercial contracts for this code is written as a **percentage of its own chargemaster**, not as a negotiated dollar amount:

| Payer | Plans | Percent of charges | Rate |
|---|---|---|---|
| Blue Cross Blue Shield | 5 | 72.0% | $4,368.24 |
| UnitedHealthcare | 2 | 64.9% | $3,937.50 |
| Cigna / Aetna / Great West | 3 | 60.0% | $3,640.20 |
| Cigna (Parkland employees) | 1 | 47.0% | $2,851.50 |

All against a **$6,067** list price.

This was verified rather than assumed. Dividing each dollar rate by the gross charge gives an implied percentage; if a rate were genuinely negotiated in dollars, that quotient would be arbitrary. Every Parkland row matched its published percentage column to four decimal places.

**Four hospitals publish negotiated dollars. One publishes a percentage of a number it sets itself.** Both satisfy the regulation. Nothing in the file format flags the difference, and a consumer comparing the published figures would conclude Parkland is the most expensive hospital in the metroplex when the number reflects list-price policy rather than negotiation.

That is stronger evidence that these files do not support comparison than any price spread could be. The exclusion *is* the finding.

**Note on notebook 13:** it computes the five-hospital view including Parkland, which produces a 4.34× spread. The exclusion is applied in interpretation, not in code — the raw figure is left visible deliberately, so a reader sees the anomaly being investigated rather than filtered away.

---

## Limitations

**The Medicare anchor is unconfirmed.** The $243.77 OPPS national rate for APC 5523 (CY2026, unadjusted) comes from a secondary fee lookup, not directly from CMS Addendum B. Every multiple in this analysis divides by it, so if it is wrong they all scale together. The hospital-to-hospital ratios — including the 2.1× headline — do not depend on it. Verifying against Addendum B is the top open item.

**The wage index has not been pulled.** Notebook 12 builds the sensitivity machinery but the actual values are placeholders. Across assumed indices from 0.90 to 1.10 the reference multiple stays within [3.51×, 3.96×], so the conclusion is not fragile to that choice — but the real figure has not been checked. Note also that "the DFW wage index" is not one number: Medicare splits the metro into Dallas–Plano–Irving (CBSA 19124) and Fort Worth–Arlington–Grapevine (CBSA 23104), and applies the index per hospital.

**One procedure.** CPT 73721 is a single shoppable service. Whether these patterns hold for surgery, obstetrics, or emergency care is untested.

**Five hospitals.** Not a sample to generalize from. This is an existence proof about the file format, not a market study.

**Point-in-time.** Files were pulled in mid-2026. Contracts change.

**Within-hospital spread often exceeds between-hospital spread.** At Baylor, UnitedHealthcare pays $2,358 and BCBS Blue Advantage $722 for the same scan. Which insurance card you carry may matter more than which hospital you walk into — a result this analysis surfaces but does not pursue.

---

## Repository structure

```
├── src/
│   ├── __init__.py
│   └── queries.py          — payer classification cascade (v1–v4), rate queries
├── notebooks/
│   ├── 01–05   data acquisition, first cross-hospital comparison
│   ├── 06      payer classifier v2
│   ├── 07–10   pricing analysis, cash prices, MCA reconciliation
│   ├── 11–12   Medicare FFS reference rung, wage-index sensitivity
│   ├── 13      cross-hospital commercial comparison  ← main result
│   ├── 14–18   negotiation spread and pricing power
│   └── 19–24   hospital profit margin and budget decomposition
├── outputs/                — figures and unclassified-payer diagnostics
├── notes/                  — project scoping and session decisions
└── requirements.txt
```

**Start with `notebooks/13_xhospital_commercial_73721.ipynb`** — it produces the cross-hospital comparison and ends with an integrity block that reproduces a known anchor value. Notebook 11 contains the Medicare FFS reference work and the Parkland investigation.

`src/queries.py` has a smoke test at the bottom. Run it from the project root:

```bash
python src/queries.py
```

The v4 cases are taken verbatim from real misclassified rows, so it functions as a regression test against actual data rather than invented inputs.

---

## Reproducing

```bash
git clone https://github.com/kedharswaminathan/dfw-hospital-pricing.git
cd dfw-hospital-pricing
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

The five parsed DuckDB files go in `data/raw/`. They originate from the Trilliant Health public price-transparency data lake and each hospital's published machine-readable file. The notebook resolves `data/raw/` from several candidate paths and prints the hospital mapping for every file it finds, including any it cannot map — a file whose name matches no keyword is skipped loudly rather than silently.

---

## Stack

Python · DuckDB · pandas · matplotlib
