"""Annotated seed templates shipped as package data strings.

``wc-caseload seed --template`` writes :data:`CASE_SEED_TEMPLATE`; passing
``--kind caseload`` writes :data:`CASELOAD_SPEC_TEMPLATE`. Both are round-tripped
through the loader in the test-suite, so every field shown here is real, valid
and current.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

CASE_SEED_TEMPLATE = '''\
# ============================================================================
# wc-caseload — annotated CaseSeed template (every controllable field)
#
#   wc-caseload seed --template --out seed.yaml
#
# The seed IS the interface: this one file fully determines a synthetic case.
# Unknown fields are rejected, so a typo fails loudly instead of silently.
# ============================================================================

# Case identifier. Doubles as the output directory name, so keep it path-safe:
# letters, digits, dot, dash, underscore; 1-64 chars.
case_id: martinez-001

# Master seed. Same rng_seed + same engine version => identical case, forever.
rng_seed: 12345

# ---------------------------------------------------------------------------
# profile — the cast. Every field is optional; anything omitted is derived
# deterministically from rng_seed (Faker, seeded). Set fields to pin them.
# ---------------------------------------------------------------------------
profile:
  applicant:
    name: Elena Martinez          # synthetic only — never a real person
    age: 44                       # 16-99
    occupation: Warehouse Associate
    tenure_years: 6.5             # 0-60
  employer:
    name: Valley Fresh Distribution, Inc.
    industry: Food distribution
    county: San Bernardino        # CA county — drives the WCAB venue
  carrier:
    name: Pacific Mutual Compensation Insurance Co.
  attorneys:
    applicant_firm: Reyes & Whitfield, APC     # files are applicant-side POV
    defense_firm: Hallman, Cortez & Ng, LLP
  physicians:
    ptp_specialty: Orthopedic Surgery          # primary treating physician
    qme_specialty: Orthopedic Surgery          # QME/AME panel specialty

# ---------------------------------------------------------------------------
# injury — what happened.
#   type: specific | cumulative_trauma | death
#     specific / death  -> date_of_injury is required
#     cumulative_trauma -> ct_start + ct_end are required (ct_end >= ct_start)
# ---------------------------------------------------------------------------
injury:
  type: specific
  date_of_injury: 2023-04-12
  # For a cumulative trauma claim, drop date_of_injury and use instead:
  # type: cumulative_trauma
  # ct_start: 2021-01-04
  # ct_end: 2023-04-12
  body_parts:                     # 1-5 entries, each with an ICD-10 code
    - part: lumbar_spine
      icd10: M54.5
      detail: L4-L5 disc protrusion with radiculopathy
    - part: shoulder
      icd10: M75.100
      detail: right rotator cuff partial-thickness tear
  mechanism: lifting a pallet of stock from a floor-level rack   # or: auto

# ---------------------------------------------------------------------------
# lifecycle — how far the case went and which branches it took.
# ---------------------------------------------------------------------------
lifecycle:
  # intake | active_treatment | discovery | medical_legal | pre_trial |
  # resolved | post_recon   (post_recon requires reconsideration.enabled)
  target_stage: post_recon

  # accepted | delayed | denied
  claim_response: denied

  # qme | ame | none
  eval_type: qme

  # Utilization review dispute and its optional IMR appeal.
  ur_dispute:
    enabled: true
    decision: upheld            # upheld | overturned (upheld = treatment denied)
    imr: true                   # requires enabled: true
    imr_outcome: upheld         # upheld | overturned; requires imr: true

  # How the case-in-chief ended.
  resolution:
    # stipulations | c_and_r | findings_award | take_nothing | pending
    type: findings_award
    msa: false                  # Medicare Set-Aside allocation in the file

  # Petition for reconsideration round trip (requires an award to attack).
  reconsideration:
    enabled: true
    outcome: granted_remand     # denied | granted_remand | granted_reversed
    # further_litigation | settled | affirmed_final
    #   denied         => must be affirmed_final
    #   granted_remand => further_litigation or settled
    post_recon: settled

  # Lien claimant tracks. Liens routinely outlive the case-in-chief.
  liens:
    count: 3                    # 0-8
    claimants:                  # <= count entries; the rest are derived
      - medical_provider        # medical_provider | hospital | pharmacy |
      - hospital                # ambulance | edd | attorney_costs |
      - edd                     # self_procured
    # lien_stipulation | lien_resolution_agreement | dismissal |
    # order_on_lien | mixed | pending
    resolution: lien_resolution_agreement
    post_resolution_litigation: true   # lien fight continues after resolution

  # Landmark doctrines that flavour the generated content.
  # ogilvie | almaraz_guzman | benson | escobedo | kite | going_and_coming |
  # sibtf | death_dependency | lc3208_3_psych | gfpa |
  # firefighter_presumption | imr_constitutionality | ab5_dynamex |
  # lc4664_prior_award
  doctrine_hooks:
    - almaraz_guzman
    - kite

# ---------------------------------------------------------------------------
# documents — fine-grained control over what lands in the file.
#
# Precedence, highest first:
#   1. overrides[{subtype, count}]    exact count, wins over everything
#   2. include_only / exclude          whitelist then blacklist
#   3. overrides[{type, min, max}]     per-parent-type bounds
#   4. lifecycle emission defaults     what the case would naturally produce
#   5. global_cap                      trims last: filler before core
#
# A subtype the lifecycle would never emit is still emitted if an override
# demands it — with a WARN in the log. Explicit control wins, loudly.
# ---------------------------------------------------------------------------
documents:
  global_cap: 120               # max documents for this case (omit for none)

  # Relative weights for output format assignment; renormalized over
  # output.formats.
  format_mix:
    pdf: 0.6
    scanned_pdf: 0.25
    eml: 0.1
    docx: 0.05

  # Whitelist. Accepts subtype keys and/or parent type keys. Empty = no filter.
  include_only: []

  # Blacklist. Same key rules.
  exclude:
    - SURVEILLANCE_VIDEO

  overrides:
    - subtype: DEPOSITION_TRANSCRIPT   # exact count for one subtype
      count: 2
    - type: MEDICAL_CLINICAL           # bounds for a whole parent type
      min: 8
      max: 25

# ---------------------------------------------------------------------------
# output — filenames and permitted formats.
# ---------------------------------------------------------------------------
output:
  # neutral -> no subtype leak in filenames (honest classifier measurement)
  # corpus  -> TC-###_###_<SUBTYPE>_<YYYY-MM-DD>.pdf (classifier corpus mode)
  filename_style: neutral
  formats:
    - pdf
    - scanned_pdf
    - eml
    - docx
'''

CASELOAD_SPEC_TEMPLATE = '''\
# ============================================================================
# wc-caseload — annotated CaseloadSpec template
#
#   wc-caseload seed --template --kind caseload --out caseload.yaml
#   wc-caseload generate --spec caseload.yaml --out ./build
#
# A caseload = shared defaults + explicit cases + auto-derived cases.
# ============================================================================

caseload_id: demo-2026q3

# ---------------------------------------------------------------------------
# defaults — a partial CaseSeed deep-merged UNDER each entry in cases[].
# Mappings merge key-by-key; lists are replaced wholesale by the case.
# (defaults do not apply to auto-derived cases — those come from the
# distribution fully materialized.)
# ---------------------------------------------------------------------------
defaults:
  documents:
    global_cap: 90
    format_mix:
      pdf: 0.6
      scanned_pdf: 0.25
      eml: 0.1
      docx: 0.05
  output:
    filename_style: neutral
    formats: [pdf, scanned_pdf, eml, docx]
  lifecycle:
    claim_response: accepted
    eval_type: qme

# ---------------------------------------------------------------------------
# cases — explicit seeds. Each is a full CaseSeed (see `seed --template`).
# ---------------------------------------------------------------------------
cases:
  - case_id: martinez-001
    rng_seed: 12345
    injury:
      type: specific
      date_of_injury: 2023-04-12
      body_parts:
        - part: lumbar_spine
          icd10: M54.5
          detail: L4-L5 disc protrusion
      mechanism: lifting a pallet of stock from a floor-level rack
    lifecycle:
      target_stage: resolved
      claim_response: denied          # overrides the default above
      resolution:
        type: c_and_r
      liens:
        count: 2
        claimants: [medical_provider, edd]
        resolution: lien_resolution_agreement

  - case_id: nguyen-002
    rng_seed: 20260727
    injury:
      type: cumulative_trauma
      ct_start: 2021-02-01
      ct_end: 2023-08-15
      body_parts:
        - part: wrist
          icd10: G56.00
          detail: bilateral carpal tunnel syndrome
    lifecycle:
      target_stage: medical_legal
      eval_type: ame
      ur_dispute:
        enabled: true
        decision: upheld
        imr: true
        imr_outcome: upheld

# ---------------------------------------------------------------------------
# auto — derive N additional fully-materialized cases from a calibrated
# distribution. Derived seeds are always written out as seed.yaml per case.
#
# distribution: balanced | early_stage | settlement_heavy | complex_litigation
#   balanced           KB PRD §3 attorney-caseload mix (all stages)
#   early_stage        intake through discovery, nothing resolved
#   settlement_heavy   settlement and resolved files, liens common
#   complex_litigation trials, liens, reconsideration round trips
# ---------------------------------------------------------------------------
auto:
  count: 20
  distribution: balanced
  rng_seed: 777
'''

__all__ = ["CASELOAD_SPEC_TEMPLATE", "CASE_SEED_TEMPLATE"]
