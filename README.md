DFW Hospital Pricing Transparency Analysis

Author: Kedhar Swaminathan

Federal rules require hospitals to publish machine-readable files of what they charge. This project tests whether those files actually let anyone compare prices — using one common procedure across five Dallas–Fort Worth hospitals.

The short answer is no, and the reason is more interesting than the price spread.

The question

CPT 73721 — MRI of a lower-extremity joint without contrast — is a routine outpatient scan. It is on CMS's shoppable-services list, high-volume, and covered by essentially every payer. If price transparency works anywhere, it should work here.

So: what does the same scan cost across five DFW hospitals, and can a patient or employer meaningfully compare those numbers?

Data

Machine-readable price transparency files from five hospitals, parsed into DuckDB databases (~710 MB total):

Hospital	Type
Baylor University Medical Center	Nonprofit academic
Methodist Dallas Medical Center	Nonprofit
Texas Health Presbyterian Plano	Nonprofit
Medical City Alliance	For-profit (HCA)
Parkland Health	Public safety-net

The raw files are not committed — they are large and publicly available. data/raw/ is gitignored; see Reproducing below.

The hard part: payer classification

The transparency files identify payers as free text. Real examples from these files:

MHS HB MULTIPLAN ADVANTAGE MDMC
AETNA BETTER HEALTH STAR [131700]
WELLPOINT STAR KIDS [100706]
MUTUAL OF OMAHA MEDICARE MANAGED CARE

Before any rate can be compared, each row has to be assigned a line of business — commercial, Medicare Advantage, traditional Medicare, Medicaid and its Texas sub-types, ACA exchange. Getting this wrong silently corrupts every downstream number.

src/queries.py implements this as an ordered rule cascade, refined across four versions as failure cases surfaced:

Plan-name regex, specific patterns before generic ones — Medicare Advantage must match before bare Medicare, or every MA row lands in traditional Medicare
Payer-group defaults where the plan name carries no signal
Payer-name patterns as the final fallback

Fixes that came out of reading misclassified rows:

Medicare PPO and Medicare PFFS are Medicare Advantage plan types, not traditional Medicare
STARKids and STARPerinate are concatenated tokens that a \bSTAR\b word boundary misses
Centene's Ambetter/Superior co-brand is a Medicaid product despite the commercial-sounding name
MCD and MGMCD are Medicaid abbreviations that a literal Medicaid match never catches

The unclassified rows at each stage are in outputs/unknown_payers_v1.txt through v3.txt — the working record of what each version still got wrong.

What the rates look like

Outpatient commercial rates for CPT 73721, one median per hospital:

Hospital	Commercial rate	× Medicare FFS
Baylor University Medical Center	$1,944.56	8.0×
Methodist Dallas	$1,518.00	6.2×
Texas Health Presbyterian Plano	$1,262.69	5.2×
Medical City Alliance	$906.53	3.7×

The same scan costs 2.1× more at the most expensive of these hospitals than the least, and the ordering holds under median, mean, and trimmed mean.

Rates are expressed as a multiple of Medicare's fee schedule because Medicare's rate is set by formula and already adjusted for local wages and hospital characteristics. That strips out most of what would otherwise be blamed on "different hospitals, different costs." Baylor at 8.0× versus Medical City at 3.7× is a difference in negotiating position, not in cost structure.

Notably, the for-profit hospital has the lowest multiple and the large nonprofit academic center the highest — the opposite of what most people assume.

Parkland is excluded, and that is the finding

Parkland initially computed to $3,937.50 — 16.2× Medicare, more than double Baylor. That number is real in the file and meaningless as a price.

Every one of Parkland's commercial contracts for this code is written as a percentage of its chargemaster, not as a dollar amount:

Payer	Percent of charges	Implied dollars
TriWest	75.0%	$9,098.25
Blue Cross Blue Shield	72.0%	$8,734.30
UnitedHealthcare	64.9%	$7,873.00
Cigna / Aetna / Great West	60.0%	$7,278.60

All against a $6,067 list price. Parkland's published commercial rate is therefore a function of what Parkland chooses to list, not of what any payer negotiated.

This is the strongest evidence in the project that the files do not support comparison. Four hospitals publish negotiated dollars; one publishes a percentage of a number it sets itself. Both satisfy the regulation. Neither is comparable to the other, and nothing in the file format flags the difference.

Limitations

The Medicare anchor is unconfirmed. The $243.77 OPPS national rate for APC 5523 comes from a secondary fee-lookup, not directly from CMS Addendum B. Every multiple in this analysis divides by that figure. Verification is pending; the ordering of hospitals does not depend on it, but the multiples do.

One procedure. CPT 73721 is one shoppable service. Whether these patterns hold for surgery, obstetrics, or emergency care is untested.

Point-in-time. Files were pulled in mid-2026 and contracts change.

Wage-index sensitivity was tested and holds. Across wage indices from 0.90 to 1.10, the reference multiple stays within [3.51×, 3.96×] — see notebooks/12_wage_index_sensitivity.ipynb.

Methodist shows a median–mean gap ($1,518 vs $1,274) suggesting a left-skewed distribution worth further examination.

Repository structure
├── src/
│   ├── queries.py          — payer classification cascade, rate queries
│   └── __init__.py
├── notebooks/
│   ├── 01–05  data acquisition, first cross-hospital comparison
│   ├── 06      payer classifier v2
│   ├── 07–10   pricing analysis, cash prices, MCA reconciliation
│   ├── 11–12   Medicare FFS reference rung, wage-index sensitivity
│   ├── 13      cross-hospital commercial comparison  ← main result
│   ├── 14–18   negotiation spread and pricing power
│   └── 19–24   hospital profit margin and budget decomposition
├── outputs/                — figures and payer diagnostics
└── notes/                  — project scoping and decisions

Start with notebooks/13_xhospital_commercial_73721.ipynb. Notebook 11 contains the Parkland investigation.

Reproducing
bash
git clone https://github.com/kedharswaminathan/dfw-hospital-pricing.git
cd dfw-hospital-pricing
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

The five parsed DuckDB files go in data/raw/. They originate from the Trilliant Health public price-transparency data lake and each hospital's published machine-readable file.

Stack

Python · DuckDB · pandas · matplotlib
