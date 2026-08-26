"""
Shared query and classification functions for DFW Hospital Pricing analysis.

Functions:
    classify_plan(plan_name)         -> (lob_bucket, rule_name)
    add_lob(df)                      -> df with 'lob' and 'lob_rule' columns added
    query_procedure_rates_agg(con, code, setting='outpatient') -> aggregated rates DataFrame

Constants:
    LOB_PATTERNS                     -> ordered list of (regex, bucket, rule_name)

Notebook usage:
    from src.queries import classify_plan, add_lob, query_procedure_rates_agg, LOB_PATTERNS

Run smoke test from project root:
    python src/queries.py
"""

import re
import pandas as pd


LOB_PATTERNS = [
    (r'\bCHIP\b',                'medicaid_chip',         'plan_contains_chip'),
    (r'STAR\s*PLUS',             'medicaid_star_plus',    'plan_contains_star_plus'),
    (r'\bSTAR\b',                'medicaid_star',         'plan_contains_star'),
    (r'Medicaid',                'medicaid_other',        'plan_contains_medicaid'),
    (r'Medicare\s*Advantage',    'medicare_advantage',    'plan_contains_medicare_advantage'),
    (r'Exchange|Marketplace|ACA','aca_exchange',          'plan_contains_aca_exchange'),
    (r'Medicare',                'medicare_traditional',  'plan_contains_medicare'),
    (r'Commercial',              'commercial',            'plan_contains_commercial'),
    (r'\bPPO\b|\bHMO\b|\bEPO\b', 'commercial',            'plan_contains_network_type'),
]

LOB_PATTERNS_V2 = [
    # Specialty (highest priority — these aren't general medical LOBs)
    (r'\bDENTAL\b|\bVISION\b',                     'commercial_specialty',  'plan_specialty'),

    # Medicaid sub-types (specific before generic)
    (r'\bCHIP\b',                                  'medicaid_chip',         'plan_chip'),
    (r'STAR\s*\+?\s*PLUS',                         'medicaid_star_plus',    'plan_star_plus'),
    # v4 (Decision 20): boundary-tolerant STAR variants. \bSTAR\b misses the
    # concatenated tokens "STARKids"/"STARPerinate"; match those explicitly
    # BEFORE the bare \bSTAR\b so the sub-bucket is right.
    (r'STAR\s*KIDS|STAR\s*PERINATE',               'medicaid_star',         'plan_star_concat'),
    (r'\bSTAR\b',                                  'medicaid_star',         'plan_star'),
    # v4 (Decision 20): Medicaid abbreviations that \bMedicaid\b misses.
    (r'\bMCD\b|\bMGMCD\b',                          'medicaid_other',        'plan_medicaid_abbrev'),

    # Medicare sub-types (specific before generic)
    (r'Medicare\s*Advantage',                      'medicare_advantage',    'plan_medicare_advantage'),
    # v4 (Decision 19a): added PPO|PFFS — Medicare PPO and Medicare PFFS are MA
    # plan types. THP's "Medicare PPO"/"Medicare PFFS" previously fell through to
    # the generic \bMedicare\b rule below and landed in traditional.
    (r'\bMedicare\s+(HMO|PPO|PFFS|MMP|Managed\s*Care)\b', 'medicare_advantage', 'plan_medicare_qualified'),

    # ACA exchange
    (r'Exchange|Marketplace|\bACA\b',              'aca_exchange',          'plan_aca'),

    # Generic Medicaid/Medicare (catch-alls — AFTER sub-types so they don't shadow them)
    (r'\bMedicaid\b',                              'medicaid_other',        'plan_medicaid'),
    (r'\bMedicare\b',                              'medicare_traditional',  'plan_medicare'),

    # Commercial
    (r'\bCommercial\b',                            'commercial',            'plan_commercial'),
    (r'\bPPO\b|\bHMO\b|\bEPO\b',                   'commercial',            'plan_network_type'),
]

PAYER_GROUP_DEFAULTS = {
    'Medicare':         ('medicare_traditional', 'payer_group_medicare'),
    'Medicaid':         ('medicaid_other',       'payer_group_medicaid'),
    'BCBS':             ('commercial',           'payer_group_commercial_bcbs'),
    'Aetna':            ('commercial',           'payer_group_commercial_aetna'),
    'UnitedHealthcare': ('commercial',           'payer_group_commercial_uhc'),
    'Cigna':            ('commercial',           'payer_group_commercial_cigna'),
    'Humana':           ('commercial',           'payer_group_commercial_humana'),
}

# src/queries.py — add below LOB_PATTERNS_V2 and PAYER_GROUP_DEFAULTS

# Payer-name-level patterns for v3. Read when plan_name regex and payer_group
# default both come up empty. Tuples are (rule_name, compiled_regex, target_lob).
#
# Ordering matters: earlier patterns win. Specificity decreases down the list.
# Government-payer recovery comes first (highest analytical stakes if missed),
# then new-bucket assignment, then named-commercial fallback (lowest specificity).

PAYER_NAME_PATTERNS_V3 = [
    # --- Government payer recovery (was misclassified as Other) ---
    # Centene's Texas Ambetter+Superior co-brand. Decision 15: defaults to Medicaid.
    ("payer_name_ambetter_superior",
     re.compile(r"\bAMBETTER\b.*\bSUPERIOR\b|\bSUPERIOR\b.*\bAMBETTER\b", re.I),
     "medicaid_chip"),

    # Named Medicare Advantage carriers stuck in payer_group='Other'.
    ("payer_name_medicare_advantage_carrier",
     re.compile(
         r"\bCARE\s*IMPROVEMENT\s*PLUS\b"
         r"|\bWELLCARE\b"
         r"|\bGLOBALHEALTH\b"
         r"|\bIMPERIAL\s*INSURANCE\b"
         r"|\bPROVIDER\s*PARTNERS\b"
         r"|\bPROCARE\s*ADVANTAGE\b",
         re.I),
     "medicare_advantage"),

    # v4 (Decision 19b): general managed-Medicare cue on payer_name, in either
    # word order. Catches 'Other'-grouped Methodist rows whose plan_name carries
    # no Medicare token (e.g. payer "MUTUAL OF OMAHA MEDICARE MANAGED CARE",
    # plan "MHS HB MUTUAL OF OMAHA MDMC"). Rows that DO carry a bare Medicare token
    # in plan_name short-circuit to medicare_traditional at step 4 and are instead
    # recovered by the carrier rule in classify_plan_v4 (Decision 23).
    ("payer_name_managed_medicare_general",
     re.compile(r"\bMANAGED\s+MEDICARE\b|\bMEDICARE\s+MANAGED\s*CARE\b", re.I),
     "medicare_advantage"),

    # Texas Medicaid managed care carriers stuck in 'Other' (MCA's Amerigroup row).
    ("payer_name_medicaid_carrier",
     re.compile(r"\bAMERIGROUP\b", re.I),
     "medicaid_chip"),

    # ACA exchange carriers — named exchange products + defunct ACA carriers
    # (Decision 12: Bright/Evry/Friday → aca_exchange on historical category).
    ("payer_name_aca_exchange",
     re.compile(
         r"\bWELLPOINT\s*MARKETPLACE\b"
         r"|\bBRIGHT\s*HEALTHCARE\b"
         r"|\bEVRY\s*HEALTH\b"
         r"|\bFRIDAY\s*HEALTH\s*PLAN\b",
         re.I),
     "aca_exchange"),

    # --- New LOB buckets (Decision 11) ---

    # Workers' compensation: state programs, federal FECA, comp-network carriers.
    ("payer_name_workers_comp",
     re.compile(
         r"\bWORKERS?\s*COMP\b"
         r"|\bCORVEL\b"
         r"|\bWORKFORCE\s*COMMISSION\b"
         r"|\bDEPARTMENT\s*OF\s*LABOR\b"
         r"|\bPRIME\s*HEALTH\s*SERVICES\b"
         r"|\bPOINT\s*COMFORT\s*UNDERWRITERS\b",
         re.I),
     "workers_comp"),

    # Federal programs outside Medicare/Medicaid: VA Community Care, HRSA.
    ("payer_name_federal_other",
     re.compile(
         r"\bTRIWEST\b"
         r"|\bHRSA\b"
         r"|\bVA\s+COMMUNITY\b",
         re.I),
     "federal_other"),

    # Employer / hospital-owned captive plans (Decision 13: kept separate from TPA).
    ("payer_name_employer_captive",
     re.compile(
         r"\b(BAYLOR\s*SCOTT\s*&?\s*WHITE|SCOTT\s*&?\s*WHITE).*HEALTH\s*PLAN\b"
         r"|\bPARKLAND\s*COMMUNITY\s*HEALTH\s*PLAN\b"
         r"|\bDART\s*MEMBER\s*CARE\b",
         re.I),
     "employer_captive"),

    # Third-party administrators / self-funded administrators.
    ("payer_name_tpa",
     re.compile(
         r"\bTPA\b"
         r"|\bWEB\s*TPA\b"
         r"|\bHEALTHSMART\b"
         r"|\bPHCS\b"
         r"|\bHEALTHSCOPE\b"
         r"|\b90\s*DEGREE\b"
         r"|\bKEMPTON\b"
         r"|\bVELOCITY\b"
         r"|\bMEDICAL\s*COST\s*CONTAINMENT\b"
         r"|\bHEALTHCARE\s*HIGHWAYS\b"
         r"|\bALTERNATIVE\s*SERVICE\s*CONCEPTS\b"
         r"|\bENTRUST\b"
         r"|\bINDEPENDENT\s*MEDICAL\s*SYSTEMS\b"
         r"|\bNATIONAL\s*HEALTHCARE\s*SOLUTIONS\b",
         re.I),
     "tpa_self_funded"),

    # --- Named-commercial-carrier recovery (lowest specificity, runs last) ---
    # These are payers that ARE commercial insurers but got stuck in 'Other':
    # MCA's bare "United" rows, Cigna legacy Great-West, Humana's ChoiceCare brand.
    # Anchored ^...$ where possible to avoid matching "UnitedHealthcare Medicaid".
    ("payer_name_commercial_carrier",
     re.compile(
         r"^United$"
         r"|^UnitedHealthcare$"
         r"|\bGREAT\s*WEST\b"
         r"|\bCHOICECARE\b",
         re.I),
     "commercial"),
]

def _match_plan_name(plan_name) -> tuple[str | None, str | None]:
    """Run LOB_PATTERNS_V2 against plan_name. Returns (lob, lob_rule) or (None, None) if no match."""
    if plan_name is None or pd.isna(plan_name) or not str(plan_name).strip():
        return (None, None)
    name = str(plan_name)
    for pattern, lob, rule in LOB_PATTERNS_V2:
        if re.search(pattern, name, flags=re.IGNORECASE):
            return (lob, rule)
    return (None, None)

def classify_plan_v2(row: pd.Series) -> tuple[str, str]:
    """
    Classify a row's line of business using plan_name + payer_group.

    Reads:  row['plan_name'], row['payer_group']
    Returns: (lob, lob_rule)

    Order of operations:
      1. Specialty (dental/vision) — runs first, regardless of payer_group.
      2. Government payer_group (Medicare, Medicaid) — payer_group hard-overrides
         plan_name's LOB family, but plan_name can refine the sub-LOB.
      3. Commercial payer_group (BCBS, Aetna, UHC, Cigna, Humana) — plan_name
         wins if matched, else fall back to commercial default.
      4. Molina, 'Other', or missing payer_group — plan_name regex only.
         (payer_name fallback deferred to Phase 2.2)
    """
    plan_name   = row.get('plan_name')
    payer_group = row.get('payer_group')

    plan_lob, plan_rule = _match_plan_name(plan_name)

    # 1. Specialty pre-check — overrides everything.
    if plan_lob == 'commercial_specialty':
        return (plan_lob, plan_rule)

    # 2. Government payer_groups: payer_group wins on LOB family,
    #    plan_name can refine the sub-LOB.
    if payer_group == 'Medicare':
        if plan_lob in ('medicare_advantage', 'medicare_traditional'):
            return (plan_lob, plan_rule)
        return PAYER_GROUP_DEFAULTS['Medicare']

    if payer_group == 'Medicaid':
        if plan_lob in ('medicaid_chip', 'medicaid_star_plus', 'medicaid_star', 'medicaid_other'):
            return (plan_lob, plan_rule)
        return PAYER_GROUP_DEFAULTS['Medicaid']

    # 3. Commercial payer_groups: plan_name wins if matched, else commercial fallback.
    if payer_group in PAYER_GROUP_DEFAULTS:  # BCBS, Aetna, UHC, Cigna, Humana
        if plan_lob is not None:
            return (plan_lob, plan_rule)
        return PAYER_GROUP_DEFAULTS[payer_group]

    # 4. Molina, 'Other', NaN, or anything else: plan_name only.
    if plan_lob is not None:
        return (plan_lob, plan_rule)
    return ('unknown', 'no_match')

def add_lob_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'lob' and 'lob_rule' columns using v2 classifier (plan_name + payer_group).

    Requires columns: 'plan_name', 'payer_group'.
    """
    result = df.copy()
    classifications = result.apply(classify_plan_v2, axis=1)
    result['lob'] = classifications.apply(lambda x: x[0])
    result['lob_rule'] = classifications.apply(lambda x: x[1])
    return result
# src/queries.py — add below classify_plan_v2 / add_lob_v2

def classify_plan_v3(row: pd.Series) -> tuple[str, str]:
    """
    Classify a row's line of business using plan_name + payer_group + payer_name.

    Reads:  row['plan_name'], row['payer_group'], row['payer_name']
    Returns: (lob, lob_rule)

    Order of operations (extends v2 with a payer_name pass):
      1. Specialty (dental/vision) — runs first, regardless of payer_group.
      2. Government payer_group (Medicare, Medicaid) — payer_group hard-overrides
         plan_name's LOB family; plan_name can refine the sub-LOB.
      3. Commercial payer_group (BCBS, Aetna, UHC, Cigna, Humana) — plan_name
         wins if matched, else fall back to commercial default.
      4. Plan_name regex (LOB_PATTERNS_V2) — trust it if it matched. Plan_name is
         the more specific signal when present (Decision 17). Methodist's
         duplicative plan_name field is a degenerate case where running plan_name
         first costs nothing, so this ordering is strictly better.
      5. NEW: payer_name regex pass (PAYER_NAME_PATTERNS_V3) — last-resort signal
         when plan_name was silent. Catches:
           - Government carriers stuck in payer_group='Other' (Wellcare MA, etc.)
           - New LOB buckets: workers_comp, tpa_self_funded, employer_captive, federal_other
           - Named commercial carriers stuck in 'Other' (bare 'United', ChoiceCare)
         Payer_name is stripped of surrounding quote characters before matching
         (some hospitals emit payer_name strings wrapped in literal quotes,
         e.g. MCA's '"United"').
      6. Catch-all → unknown.
    """
    plan_name   = row.get('plan_name')
    payer_group = row.get('payer_group')
    payer_name  = row.get('payer_name')

    plan_lob, plan_rule = _match_plan_name(plan_name)

    # 1. Specialty pre-check — overrides everything.
    if plan_lob == 'commercial_specialty':
        return (plan_lob, plan_rule)

    # 2. Government payer_groups: payer_group wins on LOB family,
    #    plan_name can refine the sub-LOB.
    if payer_group == 'Medicare':
        if plan_lob in ('medicare_advantage', 'medicare_traditional'):
            return (plan_lob, plan_rule)
        return PAYER_GROUP_DEFAULTS['Medicare']

    if payer_group == 'Medicaid':
        if plan_lob in ('medicaid_chip', 'medicaid_star_plus', 'medicaid_star', 'medicaid_other'):
            return (plan_lob, plan_rule)
        return PAYER_GROUP_DEFAULTS['Medicaid']

    # 3. Commercial payer_groups: plan_name wins if matched, else commercial fallback.
    if payer_group in PAYER_GROUP_DEFAULTS:  # BCBS, Aetna, UHC, Cigna, Humana
        if plan_lob is not None:
            return (plan_lob, plan_rule)
        return PAYER_GROUP_DEFAULTS[payer_group]

    # 4. Plan_name regex — trust it if it matched (Decision 17).
    if plan_lob is not None:
        return (plan_lob, plan_rule)

    # 5. Payer_name regex pass — last-resort signal when plan_name was silent.
    if payer_name is not None and not pd.isna(payer_name) and str(payer_name).strip():
        pname = str(payer_name).strip().strip('"').strip("'")
        for rule, pattern, lob in PAYER_NAME_PATTERNS_V3:
            if pattern.search(pname):
                return (lob, rule)

    # 6. Catch-all.
    return ('unknown', 'no_match')

def add_lob_v3(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'lob' and 'lob_rule' columns using v3 classifier
    (plan_name + payer_group + payer_name).

    Requires columns: 'plan_name', 'payer_group', 'payer_name'.
    """
    result = df.copy()
    classifications = result.apply(classify_plan_v3, axis=1)
    result['lob'] = classifications.apply(lambda x: x[0])
    result['lob_rule'] = classifications.apply(lambda x: x[1])
    return result

# ============================================================================
# v4 — promotes the Day 10 notebook-local relabel into the classifier.
#   Decision 19/23: Medicare -> Medicare Advantage recovery (carrier-vs-program).
#   Decision 20:    Medicaid leak recovery (commercial that is really Medicaid).
#
# v4 is layered ON TOP of v3: it runs classify_plan_v3 unchanged, then applies
# two targeted recovery passes gated on the *output* bucket. Layering (rather
# than rewriting the v3 control flow) keeps the diff small and makes the
# validation-vs-Day10-blanket cell a clean equality check.
#
# Why a carrier-vs-program rule rather than the notes' "PPO/PFFS + payer_name
# managed-medicare rule" (Day 11 audit finding):
#   * Most medicare_traditional rows carry a bare "MEDICARE" token in plan_name
#     (Methodist "MHS HB ... MEDICARE ... MDMC", Baylor "Medicare") that matches
#     generic \bMedicare\b at step 4 and short-circuits BEFORE the payer_name
#     pass — so a payer_name rule alone never fires for them.
#   * Baylor's three rows (Humana / WellPoint(Amerigroup) / Superior, plan
#     "Medicare") carry no managed/Advantage/PPO/PFFS text at all.
#   The principle the data supports: traditional Medicare FFS is administered by
#   CMS, never by a named carrier. So Medicare + named-carrier payer => MA;
#   Medicare + the program itself => traditional. All 37 current rows have carrier
#   payers and none is the program, so v4 reproduces the Day 10 blanket relabel
#   exactly here, while staying correct when the basket extension reaches a code
#   that DOES publish a CMS FFS line (payer "Medicare" => stays traditional).
# ============================================================================

def _strip_quotes(s) -> str:
    """Normalize a possibly-null, possibly-quote-wrapped string to a bare str."""
    if s is None or pd.isna(s) or not str(s).strip():
        return ""
    return str(s).strip().strip('"').strip("'")

# Recognizes the Medicare program itself (traditional FFS) in payer_name, as
# opposed to a named carrier. Currently never matches in this dataset (Decision
# 22: no FFS line is published), but keeps v4 correct for the basket extension.
_MEDICARE_PROGRAM_RE = re.compile(
    r"^\s*(?:traditional\s+|original\s+)?medicare"
    r"(?:\s+(?:ffs|fee[-\s]*for[-\s]*service|part\s*a(?:\s*&?\s*b)?|part\s*b|a\s*&?\s*b))?\s*$"
    r"|^\s*cms\s*$",
    re.I,
)

# Order-agnostic text cues that independently mark a Medicare row as MA. The
# carrier test is the primary signal; this is a safety net for rows whose
# payer_name looks program-like but whose plan_name names an MA product.
_MA_TEXT_CUE_RE = re.compile(
    r"medicare\s+advantage"
    r"|managed\s+medicare|medicare\s+managed\s*care"
    r"|medicare\s+(?:hmo|ppo|pffs|mmp)"
    r"|secure\s*horizons"
    r"|medicare\s+(?:complete|direct)",
    re.I,
)

def _is_medicare_program(payer_name) -> bool:
    """True iff payer_name denotes the Medicare program itself (traditional FFS),
    not a named carrier. Empty/unknown payer => treated as program (conservative;
    leaves the row traditional). Does not occur in the current 73721 data."""
    name = _strip_quotes(payer_name)
    if not name:
        return True
    return bool(_MEDICARE_PROGRAM_RE.search(name))

def _recover_medicare_advantage(lob, plan_name, payer_name):
    """Decision 19/23. If v3 produced medicare_traditional, upgrade to
    medicare_advantage when (a) the payer is a named carrier, or (b) a text MA
    cue is present. Returns (lob, rule) or None if no change."""
    if lob != 'medicare_traditional':
        return None
    if not _is_medicare_program(payer_name):
        return ('medicare_advantage', 'v4_ma_carrier')
    if _MA_TEXT_CUE_RE.search(_strip_quotes(plan_name)) or \
       _MA_TEXT_CUE_RE.search(_strip_quotes(payer_name)):
        return ('medicare_advantage', 'v4_ma_text_cue')
    return None

# Decision 20 — Medicaid leak recovery. Two classes of fix:
#   (1) Plan-name token concatenation (implemented, low-risk, pure tokenization):
#       "STARKids"/"STARPerinate" miss \bSTAR\b; "MCD"/"MGMCD" miss \bMedicaid\b.
#       Also handled at source in LOB_PATTERNS_V2; this post-pass catches rows that
#       still surfaced as 'commercial' (e.g. routed there by a commercial payer_group).
#   (2) Medicaid-BRAND payer routing (Aetna Better Health, community "United",
#       Humana managed Medicaid, Cigna HealthSpring): DEFERRED pending the actual
#       5 MCA rows. HealthSpring in particular is MA-vs-Medicaid ambiguous, so it
#       is intentionally NOT routed blind. See the TODO below.
_MEDICAID_STAR_CUE_RE    = re.compile(r"STAR\s*KIDS|STAR\s*PERINATE|\bMCDSTAR\b", re.I)
_MEDICAID_ABBREV_CUE_RE  = re.compile(r"\bMCD\b|\bMGMCD\b", re.I)

def _recover_medicaid(lob, plan_name, payer_name):
    """Decision 20 (partial). Recover Medicaid rows mislabeled commercial via
    plan-name tokenization only. Returns (lob, rule) or None."""
    if lob not in ('commercial', 'unknown'):
        return None
    pn = _strip_quotes(plan_name)
    if _MEDICAID_STAR_CUE_RE.search(pn):
        return ('medicaid_star', 'v4_medicaid_star_concat')
    if _MEDICAID_ABBREV_CUE_RE.search(pn):
        return ('medicaid_other', 'v4_medicaid_abbrev')
    # TODO(needs the 5 MCA rows): Medicaid-brand payer routing, e.g.
    #   AETNA BETTER HEALTH -> medicaid_*, HUMANA managed Medicaid -> medicaid_*.
    #   Confirm each row's payer_name/payer_group/plan_name and target sub-bucket
    #   before adding, and decide HealthSpring (MA vs Medicaid) explicitly.
    return None

def classify_plan_v4(row: pd.Series) -> tuple[str, str]:
    """v4 = v3 + Decision 19/23 (Medicare->MA recovery) + Decision 20 (Medicaid
    recovery, partial). Reads plan_name, payer_group, payer_name."""
    lob, rule = classify_plan_v3(row)
    plan_name  = row.get('plan_name')
    payer_name = row.get('payer_name')

    ma = _recover_medicare_advantage(lob, plan_name, payer_name)
    if ma is not None:
        return ma

    md = _recover_medicaid(lob, plan_name, payer_name)
    if md is not None:
        return md

    return (lob, rule)

def add_lob_v4(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'lob' and 'lob_rule' columns using v4 classifier.
    Requires columns: 'plan_name', 'payer_group', 'payer_name'.
    """
    result = df.copy()
    classifications = result.apply(classify_plan_v4, axis=1)
    result['lob'] = classifications.apply(lambda x: x[0])
    result['lob_rule'] = classifications.apply(lambda x: x[1])
    return result

def classify_plan(plan_name) -> tuple[str, str]:
    """
    Given a plan_name string, return (lob_bucket, rule_name).
    Returns ('unknown', 'no_match') if no pattern matches.
    """
    if plan_name is None or pd.isna(plan_name) or not str(plan_name).strip():
        return ('unknown', 'null_or_empty_plan_name')

    name = str(plan_name)
    for pattern, bucket, rule_name in LOB_PATTERNS:
        if re.search(pattern, name, flags=re.IGNORECASE):
            return (bucket, rule_name)
    return ('unknown', 'no_match')


def add_lob(df: pd.DataFrame) -> pd.DataFrame:
    """Add 'lob' and 'lob_rule' columns based on plan_name."""
    result = df.copy()
    classifications = result['plan_name'].apply(classify_plan)
    result['lob'] = classifications.apply(lambda x: x[0])
    result['lob_rule'] = classifications.apply(lambda x: x[1])
    return result


def query_procedure_rates_agg(con, code: str, setting: str = 'outpatient') -> pd.DataFrame:
    """
    Aggregated version of query_procedure_rates.
    Returns one row per (payer_name, plan_name, methodology_normalized, billing_class_normalized).

    Aggregation:
      - dollar_rate         = median of standard_charge_dollar across charge_ids
      - dollar_min/dollar_max = visibility into combo-level variation (Parkland 34%, THP 9% of combos vary)
      - pct_rate            = max of standard_charge_percentage (stable within combo, max ignores nulls)
      - n_charge_ids        = how many charge_ids contributed to this row
      - gross_min/gross_max = chargemaster gross_charge range across charge_ids
    """
    q = """
    SELECT
        payer_name,
        plan_name,
        payer_group,
        payer_type,
        methodology_normalized,
        billing_class_normalized,
        COUNT(*) AS n_charge_ids,
        MEDIAN(standard_charge_dollar) AS dollar_rate,
        MIN(standard_charge_dollar) AS dollar_min,
        MAX(standard_charge_dollar) AS dollar_max,
        MAX(standard_charge_percentage) AS pct_rate,
        MIN(gross_charge) AS gross_min,
        MAX(gross_charge) AS gross_max,
        STRING_AGG(DISTINCT description, ' | ') AS descriptions
    FROM standard_charge_details
    WHERE (cpt = ? OR hcpcs = ?)
      AND setting_normalized = ?
    GROUP BY payer_name, plan_name, payer_group, payer_type, methodology_normalized, billing_class_normalized
    """
    return con.execute(q, [code, code, setting]).fetchdf()


if __name__ == "__main__":
    # Run from project root: python src/queries.py
    # ---- Legacy classify_plan smoke test (v1 LOB_PATTERNS) --------------------
    # NOTE: the 'BSW Plus' case is an intentional KNOWN FAIL flag (it is really
    # commercial); the v1 legacy test is expected to report a failure.
    legacy_cases = [
        ('ABOVE FPIL AETNA CHIP PERINATE',                      'medicaid_chip'),
        ('AETNA BETTER HEALTH STAR PLUS',                       'medicaid_star_plus'),
        ('AETNA BETTER HEALTH STAR',                            'medicaid_star'),
        ('Texas Medicaid Managed Care',                         'medicaid_other'),
        ('Aetna Medicare Advantage',                            'medicare_advantage'),
        ('Aetna Marketplace HMO',                               'aca_exchange'),
        ('Medicare Part B',                                     'medicare_traditional'),
        ('Aetna Commercial PPO',                                'commercial'),
        ('BCBS PPO',                                            'commercial'),
        ('BSW Plus - Large Group',                              'unknown'),   # known flag
        (None,                                                   'unknown'),
        ('',                                                     'unknown'),
        ('Some New Plan We Have Not Seen',                      'unknown'),
    ]
    print("=== Legacy classify_plan smoke test (v1) ===")
    for plan_name, expected in legacy_cases:
        actual, rule = classify_plan(plan_name)
        status = 'PASS' if actual == expected else 'FAIL'
        plan_display = f"'{plan_name}'" if plan_name else repr(plan_name)
        print(f"  [{status}] {plan_display:55s} -> {actual:25s} (rule: {rule})")

    # ---- v4 row-based smoke test (Decisions 19/23 + 20) -----------------------
    # Each case is (payer_group, payer_name, plan_name, expected_lob).
    # Strings are taken verbatim from the Day 10 medicare_traditional audit so
    # this harness is a regression test against real data, not invented inputs.
    v4_cases = [
        # --- Decision 19/23: Medicare -> MA (carrier rule), both payer_group paths ---
        ('Other',    'Humana',                                  'Medicare',                              'medicare_advantage'),
        ('Medicare', 'Humana',                                  'Medicare',                              'medicare_advantage'),
        ('Other',    'WellPoint (fka Amerigroup)',              'Medicare',                              'medicare_advantage'),
        ('Medicare', 'Superior Health Plan',                    'Medicare',                              'medicare_advantage'),
        ('Medicare', 'HUMANA MEDICARE MANAGED CARE [7005]',     'MHS HB HUMANA MEDICARE MDMC',           'medicare_advantage'),
        ('Medicare', 'MULTIPLAN MEDICARE MANAGED CARE [7022]',  'MHS HB MULTIPLAN ADVANTAGE MDMC',       'medicare_advantage'),
        ('Other',    'GENERIC MEDICARE MANAGED CARE [7004]',    'MHS HB MANAGED MEDICARE PART A & B MDMC','medicare_advantage'),
        ('Other',    'MUTUAL OF OMAHA MEDICARE MANAGED CARE',   'MHS HB MUTUAL OF OMAHA MDMC',           'medicare_advantage'),  # caught by payer_name general rule at step 5
        ('Medicare', 'UST HEALTH PROOF [1005]',                 'MHS HB UHC MEDICARE COMPLETE MDMC',      'medicare_advantage'),
        # --- Decision 19a: explicit PPO/PFFS plan tokens ---
        ('Medicare', 'THP Medicare Plan',                       'Medicare PPO',                          'medicare_advantage'),
        ('Other',    'Some Carrier',                            'Medicare PFFS',                         'medicare_advantage'),
        # --- Negatives: the program itself must stay traditional (generalization) ---
        ('Medicare', 'Medicare',                                'Medicare Part B',                       'medicare_traditional'),
        ('Other',    'CMS',                                     'Traditional Medicare',                  'medicare_traditional'),
    ]
    print("\n=== v4 classifier smoke test (Decisions 19/23) ===")
    v4_pass = True
    for pg, pyr, pln, expected in v4_cases:
        row = pd.Series({'payer_group': pg, 'payer_name': pyr, 'plan_name': pln})
        actual, rule = classify_plan_v4(row)
        status = 'PASS' if actual == expected else 'FAIL'
        if actual != expected:
            v4_pass = False
        print(f"  [{status}] {pyr[:34]:34s} | {pln[:34]:34s} -> {actual:20s} ({rule})")

    # --- Decision 20: Medicaid tokenization (helper-level; pipeline path depends
    #     on payer_group, which is pending the 5 MCA rows) ---
    print("\n=== v4 Medicaid tokenization smoke test (Decision 20, helper-level) ===")
    medicaid_cases = [
        ('commercial', 'STARKids',        'Aetna Better Health', 'medicaid_star'),
        ('commercial', 'STAR Perinate',   'Aetna Better Health', 'medicaid_star'),
        ('commercial', 'Some MCD Plan',   'United',              'medicaid_other'),
        ('commercial', 'MGMCD Managed',   'United',              'medicaid_other'),
        ('unknown',    'MCDSTAR',         'Molina',              'medicaid_star'), 
        ('commercial', 'Regular PPO',     'Aetna',               None),  
    ]
    for lob_in, pln, pyr, expected in medicaid_cases:
        res = _recover_medicaid(lob_in, pln, pyr)
        actual = res[0] if res is not None else None
        status = 'PASS' if actual == expected else 'FAIL'
        if actual != expected:
            v4_pass = False
        print(f"  [{status}] {pln[:20]:20s} -> {str(actual):20s}")

    print(f"\n{'v4 ALL PASS' if v4_pass else 'v4 FAILURES PRESENT'}")
