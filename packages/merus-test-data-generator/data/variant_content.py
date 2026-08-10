"""Per-variant content registers for the variant-content seam (AJC-66).

Several templates serve many registry subtypes. ``DiagnosticReport`` is reached
by imaging, lab, EMG/NCV and sleep-study subtypes; ``OperativeRecord`` by
operative, acute-care, ER, discharge and face-sheet subtypes. Historically the
``variant`` string that distinguishes them was registered and then discarded, so
a lab-results subtype rendered an X-ray report and an emergency-room record
rendered a full surgical narrative.

This module holds the content those variants need. It is *data plus resolution*
only — no reportlab, no rendering. Templates ask :func:`diagnostic_register` (or
a sibling) for a register and render it; a ``None`` answer means "no register
claims this variant", and the template renders exactly what it always did.

Two rules govern everything here:

**Opt-in only.** Nothing in this module is consulted unless the caller sets
``variant_content`` in the document context. The default path must stay
byte-identical; wc-synthetic-caseload-engine pins four golden corpora against it.

**Synthetic only.** Facilities, panels and prose are coined and generic. No real
carrier, firm, employer, facility or physician is named — a synthetic claim file
stops being safely synthetic the moment it can be attributed to a real body.
``all_content_strings`` exists so a test can sweep this whole module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def normalize_variant(variant: str | None) -> str:
    """Fold a registry variant into a matchable token.

    The registry does not use one convention. Most variants are lowercase slugs
    (``"emg_ncv"``, ``"advocacy_qme"``), but a number are human-readable display
    strings (``"Objection to QME/AME Report"``, ``"Deposition Transcript
    (QME/AME)"``). Both must resolve, so matching is done on a lowercased token
    string with every non-alphanumeric run collapsed to a single underscore.

        "Objection to QME/AME Report" -> "objection_to_qme_ame_report"
    """
    if not variant:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(variant).lower()).strip("_")


def _claims(token: str, *needles: str) -> bool:
    """True when the normalized token contains any needle as a whole word run."""
    padded = f"_{token}_"
    return any(f"_{n}_" in padded for n in needles)


# ---------------------------------------------------------------------------
# Diagnostics: lab, electrodiagnostic, sleep
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Analyte:
    """One reported result line: name, candidate values, unit, reference range."""

    name: str
    values: tuple[str, ...]
    unit: str
    reference: str


@dataclass(frozen=True)
class DiagnosticRegister:
    """A diagnostic document that is not a radiology report.

    ``sections`` is an ordered list of ``(heading, body_lines)``, where a body
    line is either free prose or a pre-formatted result row. The template owns
    layout; this owns what the document says.
    """

    key: str
    exam_label: str
    facilities: tuple[str, ...]
    facility_kind: str
    technique: tuple[str, ...]
    result_heading: str
    analytes: tuple[Analyte, ...] = ()
    narrative_findings: tuple[str, ...] = ()
    impressions: tuple[str, ...] = ()
    signer_title: str = "Board Certified Physician"
    signer_credential: str = "CA License"


_LAB_FACILITIES = (
    "Meridian Clinical Laboratory",
    "Crosswind Diagnostics Laboratory",
    "Harbor Point Reference Lab",
    "Fielding Clinical Labs",
)

#: Panels a WC file actually accumulates. The A1c and the opioid-monitoring
#: screen are here deliberately: both are the documentary trace of a
#: comorbidity/treatment story the medical-story layer needs to be able to tell.
_LAB_PANELS: dict[str, tuple[Analyte, ...]] = {
    "COMPREHENSIVE METABOLIC PANEL": (
        Analyte("Glucose, fasting", ("88", "94", "101", "118", "132"), "mg/dL", "70–99"),
        Analyte("BUN", ("11", "14", "17", "20"), "mg/dL", "7–20"),
        Analyte("Creatinine", ("0.78", "0.91", "1.02", "1.14"), "mg/dL", "0.60–1.30"),
        Analyte("Sodium", ("137", "139", "141", "143"), "mmol/L", "135–145"),
        Analyte("Potassium", ("3.7", "4.0", "4.3", "4.6"), "mmol/L", "3.5–5.1"),
        Analyte("Calcium", ("8.9", "9.2", "9.5", "9.8"), "mg/dL", "8.6–10.2"),
        Analyte("Total protein", ("6.4", "6.9", "7.2", "7.7"), "g/dL", "6.0–8.3"),
        Analyte("Albumin", ("3.9", "4.1", "4.4", "4.6"), "g/dL", "3.5–5.0"),
        Analyte("AST", ("18", "23", "29", "36"), "U/L", "10–40"),
        Analyte("ALT", ("16", "22", "31", "44"), "U/L", "7–56"),
        Analyte("Alkaline phosphatase", ("54", "68", "81", "97"), "U/L", "44–147"),
        Analyte("Total bilirubin", ("0.4", "0.6", "0.8", "1.0"), "mg/dL", "0.1–1.2"),
    ),
    "COMPLETE BLOOD COUNT WITH DIFFERENTIAL": (
        Analyte("WBC", ("5.2", "6.4", "7.8", "9.1"), "K/uL", "4.0–10.5"),
        Analyte("RBC", ("4.32", "4.61", "4.88", "5.10"), "M/uL", "4.10–5.60"),
        Analyte("Hemoglobin", ("12.8", "13.6", "14.4", "15.1"), "g/dL", "12.0–16.0"),
        Analyte("Hematocrit", ("38.4", "40.7", "43.2", "45.6"), "%", "36.0–48.0"),
        Analyte("Platelets", ("188", "224", "261", "302"), "K/uL", "150–400"),
        Analyte("Neutrophils", ("48", "55", "61", "67"), "%", "40–70"),
        Analyte("Lymphocytes", ("22", "27", "33", "38"), "%", "20–45"),
    ),
    "INFLAMMATORY MARKERS": (
        Analyte("Sedimentation rate (ESR)", ("8", "14", "22", "31"), "mm/hr", "0–20"),
        Analyte("C-reactive protein", ("0.3", "0.8", "1.6", "3.2"), "mg/dL", "0.0–1.0"),
        Analyte("Rheumatoid factor", ("<14", "<14", "18"), "IU/mL", "<14"),
    ),
    "HEMOGLOBIN A1C": (
        Analyte("Hemoglobin A1c", ("5.4", "5.9", "6.4", "7.1", "8.2"), "%", "4.0–5.6"),
        Analyte("Estimated average glucose", ("108", "123", "137", "157", "189"), "mg/dL", "—"),
    ),
    "URINE DRUG SCREEN — CHRONIC OPIOID THERAPY MONITORING": (
        Analyte("Opiates", ("Detected", "Detected", "Not detected"), "", "Consistent with prescribed therapy"),
        Analyte("Oxycodone", ("Detected", "Not detected"), "", "Consistent with prescribed therapy"),
        Analyte("Benzodiazepines", ("Not detected", "Not detected", "Detected"), "", "Not detected"),
        Analyte("Amphetamines", ("Not detected",), "", "Not detected"),
        Analyte("Cocaine metabolite", ("Not detected",), "", "Not detected"),
        Analyte("Creatinine, urine", ("42", "68", "94", "121"), "mg/dL", ">20 (valid specimen)"),
    ),
}

LAB_REGISTER = DiagnosticRegister(
    key="lab",
    exam_label="CLINICAL LABORATORY REPORT",
    facilities=_LAB_FACILITIES,
    facility_kind="Clinical Laboratory",
    technique=(
        "Specimen collected by venipuncture and processed on an automated clinical "
        "chemistry analyzer. Results reported against the performing laboratory's "
        "own reference intervals. Specimen integrity acceptable; no hemolysis noted.",
        "Specimen collected and processed under standard chain-of-custody procedure. "
        "Screening performed by immunoassay with confirmation of presumptive positives "
        "by mass spectrometry. Reference intervals are those of the performing laboratory.",
    ),
    result_heading="LABORATORY RESULTS",
    impressions=(
        "Results reviewed. Values outside the stated reference interval are flagged above.",
        "No critical values identified. Clinical correlation recommended.",
        "Repeat testing suggested if clinically indicated.",
    ),
    signer_title="Clinical Laboratory Director",
    signer_credential="CA Clinical Laboratory License",
)

_ELECTRO_FACILITIES = (
    "Crestline Neurodiagnostic Center",
    "Waypoint Electrodiagnostic Associates",
    "Northgate Neuromuscular Diagnostics",
    "Silvermont Nerve Study Center",
)

#: Nerve conduction rows: (nerve/site, latency ms, amplitude, velocity m/s, reference)
_NCV_ROWS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str], ...] = (
    ("Median, motor (wrist–APB)", ("3.6", "4.1", "4.8", "5.4"), ("7.2", "6.1", "4.8"), ("52", "49", "45"), "distal latency <4.2 ms"),
    ("Median, sensory (digit II)", ("3.2", "3.7", "4.3", "4.9"), ("28", "19", "11"), ("48", "44", "39"), "peak latency <3.5 ms"),
    ("Ulnar, motor (wrist–ADM)", ("2.8", "3.1", "3.4"), ("9.4", "8.2", "7.1"), ("56", "53", "50"), "distal latency <3.3 ms"),
    ("Ulnar, sensory (digit V)", ("2.9", "3.2", "3.6"), ("24", "18", "13"), ("51", "47", "43"), "peak latency <3.2 ms"),
    ("Peroneal, motor (ankle–EDB)", ("4.2", "4.8", "5.3"), ("4.6", "3.8", "2.9"), ("47", "43", "39"), "distal latency <6.0 ms"),
    ("Sural, sensory", ("3.4", "3.8", "4.2"), ("16", "11", "7"), ("48", "44", "40"), "peak latency <4.4 ms"),
)

#: Needle EMG rows: (muscle, insertional, spontaneous, MUAP, recruitment)
_EMG_ROWS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    ("Abductor pollicis brevis", ("Normal", "Increased"), ("None", "1+ fibrillations"), ("Normal", "Mildly polyphasic"), ("Full", "Mildly reduced")),
    ("First dorsal interosseous", ("Normal",), ("None",), ("Normal",), ("Full",)),
    ("Cervical paraspinals (C5–C7)", ("Normal", "Increased"), ("None", "1+ positive sharp waves"), ("Normal",), ("Full", "Mildly reduced")),
    ("Deltoid", ("Normal",), ("None",), ("Normal",), ("Full",)),
    ("Tibialis anterior", ("Normal", "Increased"), ("None", "1+ fibrillations"), ("Normal", "Mildly polyphasic"), ("Full", "Mildly reduced")),
    ("Lumbar paraspinals (L4–S1)", ("Normal", "Increased"), ("None", "2+ positive sharp waves"), ("Normal",), ("Full", "Reduced")),
)

ELECTRODIAGNOSTIC_REGISTER = DiagnosticRegister(
    key="emg_ncv",
    exam_label="ELECTRODIAGNOSTIC STUDY (NERVE CONDUCTION AND NEEDLE EMG)",
    facilities=_ELECTRO_FACILITIES,
    facility_kind="Neurodiagnostic Center",
    technique=(
        "Nerve conduction studies were performed using surface stimulation and recording "
        "electrodes with limb temperature maintained above 32 degrees Celsius. Needle "
        "electromyography was performed with a disposable concentric needle electrode. "
        "The patient tolerated the study well.",
        "Motor and sensory nerve conduction studies were performed bilaterally where "
        "indicated for comparison, with skin temperature monitored throughout. Needle "
        "examination sampled proximal and distal muscles in the symptomatic distribution.",
    ),
    result_heading="NERVE CONDUCTION STUDIES",
    impressions=(
        "Electrodiagnostic evidence of a mild focal median neuropathy at the wrist. "
        "No electrodiagnostic evidence of a cervical radiculopathy in the muscles sampled.",
        "Electrodiagnostic evidence of a moderate focal median neuropathy at the wrist, "
        "with prolonged distal sensory and motor latencies and mild denervation changes.",
        "Study within normal limits. No electrodiagnostic evidence of focal entrapment "
        "neuropathy, generalized polyneuropathy, or active radiculopathy in the muscles sampled.",
        "Electrodiagnostic findings consistent with a chronic lumbosacral radiculopathy. "
        "No evidence of an acute denervating process.",
        "Findings suggest a mild generalized sensorimotor polyneuropathy. Correlation with "
        "metabolic workup, including glycemic status, is recommended.",
    ),
    signer_title="Board Certified Neurologist",
    signer_credential="CA License",
)

_SLEEP_FACILITIES = (
    "Lantern Hill Sleep Disorders Center",
    "Rosewater Sleep Medicine Institute",
    "Brightwater Sleep Diagnostics",
    "Kestrel Sleep Health Center",
)

SLEEP_REGISTER = DiagnosticRegister(
    key="sleep_study",
    exam_label="POLYSOMNOGRAPHY (ATTENDED, IN-LABORATORY)",
    facilities=_SLEEP_FACILITIES,
    facility_kind="Sleep Disorders Center",
    technique=(
        "Attended in-laboratory polysomnography was performed with electroencephalography, "
        "electrooculography, submental and tibial electromyography, electrocardiography, "
        "nasal pressure and thermal airflow, thoracoabdominal effort belts, pulse oximetry, "
        "and body position monitoring. Scoring followed standard adult criteria.",
    ),
    result_heading="SLEEP ARCHITECTURE AND RESPIRATORY SUMMARY",
    analytes=(
        Analyte("Total sleep time", ("284", "312", "341", "368"), "minutes", "—"),
        Analyte("Sleep efficiency", ("71", "78", "84", "89"), "%", ">85"),
        Analyte("Sleep latency", ("8", "14", "22", "31"), "minutes", "<20"),
        Analyte("Stage N1", ("6", "9", "13", "18"), "%", "2–5"),
        Analyte("Stage N2", ("48", "53", "58", "62"), "%", "45–55"),
        Analyte("Stage N3", ("9", "13", "17", "21"), "%", "13–23"),
        Analyte("Stage REM", ("12", "16", "19", "23"), "%", "20–25"),
        Analyte("Arousal index", ("11", "18", "26", "34"), "/hour", "<10"),
        Analyte("Apnea-Hypopnea Index (AHI)", ("4.1", "9.6", "18.4", "31.2"), "/hour", "<5"),
        Analyte("Oxygen saturation nadir", ("92", "88", "84", "79"), "%", ">90"),
    ),
    impressions=(
        "Mild obstructive sleep apnea. A trial of positional therapy and weight management "
        "is reasonable, with reassessment if symptoms persist.",
        "Moderate obstructive sleep apnea. Positive airway pressure titration is recommended.",
        "Severe obstructive sleep apnea with associated oxygen desaturation. Positive airway "
        "pressure therapy is recommended, with follow-up to confirm adherence and response.",
        "No significant sleep-disordered breathing. Sleep architecture shows reduced slow-wave "
        "and REM sleep with an elevated arousal index, consistent with sleep fragmentation.",
    ),
    signer_title="Board Certified Sleep Medicine Physician",
    signer_credential="CA License",
)

_DIAGNOSTIC_REGISTERS = (LAB_REGISTER, ELECTRODIAGNOSTIC_REGISTER, SLEEP_REGISTER)


def diagnostic_register(variant: str | None) -> DiagnosticRegister | None:
    """Register for a diagnostic variant, or ``None`` to keep the default.

    ``imaging`` deliberately resolves to ``None``: the substrate's own default
    document *is* the radiology report, so the imaging variant was never the
    defect and must not be re-implemented into a second, divergent version.
    """
    token = normalize_variant(variant)
    if not token:
        return None
    if _claims(token, "lab", "labs", "laboratory", "pathology"):
        return LAB_REGISTER
    if _claims(token, "emg", "ncv", "emg_ncv", "electrodiagnostic", "nerve"):
        return ELECTRODIAGNOSTIC_REGISTER
    if _claims(token, "sleep", "sleep_study", "polysomnography"):
        return SLEEP_REGISTER
    return None


# ---------------------------------------------------------------------------
# Hospital records: ER, acute care, discharge, face sheet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HospitalRegister:
    """A hospital document that is not an operative report.

    All four of these subtypes routed to the operative-report template and
    rendered a full surgical narrative — an emergency-room visit for a strain
    came out claiming an operation that never happened. These registers describe
    an encounter without asserting surgery.
    """

    key: str
    title: str
    facilities: tuple[str, ...]
    header_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()
    sections: tuple[tuple[str, tuple[str, ...]], ...] = ()
    dispositions: tuple[str, ...] = ()
    signer_title: str = "Attending Physician"


_HOSPITAL_FACILITIES = (
    "Alder Grove Regional Hospital",
    "Marchmont Community Medical Center",
    "Westbourne General Hospital",
    "Kingsley Park Medical Center",
)

ER_REGISTER = HospitalRegister(
    key="er",
    title="EMERGENCY DEPARTMENT RECORD",
    facilities=_HOSPITAL_FACILITIES,
    header_fields=(
        ("Mode of Arrival", ("Ambulatory", "Private vehicle", "Employer transport", "Ambulance")),
        ("Triage Acuity", ("ESI Level 3 — Urgent", "ESI Level 4 — Less urgent", "ESI Level 2 — Emergent")),
        ("Attending Physician", ("Emergency Medicine", "Emergency Medicine")),
    ),
    sections=(
        (
            "TRIAGE ASSESSMENT",
            (
                "Patient presented to the emergency department reporting a work-related injury "
                "sustained during the course of employment earlier the same day. Patient is alert, "
                "oriented, and in no acute distress at triage. Vital signs stable and within normal limits.",
                "Patient reports the onset of pain immediately following the described mechanism, "
                "with no loss of consciousness and no numbness or weakness distally. Pain is rated as "
                "moderate and is aggravated by movement of the affected region.",
            ),
        ),
        (
            "EMERGENCY DEPARTMENT COURSE",
            (
                "Focused examination performed. The affected region was examined for deformity, "
                "swelling, and range of motion. Neurovascular status intact distally. Plain radiographs "
                "were obtained and reviewed; no acute fracture or dislocation was identified.",
                "Patient was treated with oral analgesia and ice, and was observed in the department. "
                "Symptoms improved during the observation period. The patient was able to ambulate "
                "without assistance prior to discharge.",
            ),
        ),
        (
            "EMERGENCY DEPARTMENT DIAGNOSIS",
            (
                "Acute work-related musculoskeletal injury. No acute surgical pathology identified "
                "during this encounter.",
            ),
        ),
    ),
    dispositions=(
        "Discharged to home in stable condition. Work status: modified duty pending follow-up. "
        "Instructed to follow up with the designated occupational medicine provider within 72 hours. "
        "Return precautions reviewed and understood.",
        "Discharged to home in stable condition. Work status: off work pending re-evaluation. "
        "Referred to the primary treating physician for continued care. Return precautions given.",
        "Discharged in stable condition with a referral for outpatient orthopedic evaluation. "
        "Work restrictions provided in writing. Return precautions reviewed.",
    ),
    signer_title="Emergency Medicine",
)

ACUTE_REGISTER = HospitalRegister(
    key="acute",
    title="ACUTE CARE HOSPITAL RECORD",
    facilities=_HOSPITAL_FACILITIES,
    header_fields=(
        ("Admission Type", ("Direct admission", "Admitted from emergency department", "Observation")),
        ("Attending Physician", ("Internal Medicine", "Hospitalist Service")),
        ("Level of Care", ("Medical/surgical floor", "Telemetry", "Observation unit")),
    ),
    sections=(
        (
            "REASON FOR ADMISSION",
            (
                "Patient was admitted for evaluation and management of symptoms attributed to a "
                "work-related injury, with pain inadequately controlled in the outpatient setting.",
            ),
        ),
        (
            "HOSPITAL COURSE",
            (
                "The patient was admitted and placed on a scheduled analgesic regimen with adjunctive "
                "measures. Serial examinations were performed. The patient remained hemodynamically "
                "stable throughout the admission with no fever and no neurologic change.",
                "Physical therapy was consulted and the patient was mobilized with assistance, "
                "progressing to independent ambulation. Diagnostic studies obtained during the "
                "admission were reviewed and did not demonstrate an acute surgical lesion.",
                "Pain was controlled on an oral regimen prior to discharge. The patient tolerated a "
                "regular diet and required no supplemental oxygen at any point during the stay.",
            ),
        ),
        (
            "CONSULTATIONS",
            (
                "Physical therapy — evaluation and mobilization. Occupational medicine — work status "
                "and restrictions on discharge.",
            ),
        ),
    ),
    dispositions=(
        "DISCHARGE DISPOSITION: Discharged to home in stable condition with outpatient follow-up "
        "arranged. Work status: temporarily totally disabled pending re-evaluation by the primary "
        "treating physician.",
        "DISCHARGE DISPOSITION: Discharged to home with home health services. Work status: modified "
        "duty with restrictions as documented. Follow-up scheduled with the primary treating physician.",
    ),
    signer_title="Attending Physician",
)

DISCHARGE_REGISTER = HospitalRegister(
    key="discharge",
    title="DISCHARGE SUMMARY",
    facilities=_HOSPITAL_FACILITIES,
    header_fields=(
        ("Service", ("Orthopedic Surgery", "Internal Medicine", "Hospitalist Service")),
        ("Attending Physician", ("Attending of record",)),
    ),
    sections=(
        (
            "HOSPITAL COURSE",
            (
                "The patient was admitted, treated, and progressed as expected through the admission. "
                "Serial examinations documented steady improvement. There were no complications during "
                "the hospital stay.",
                "Pain was transitioned from parenteral to oral analgesia and was well controlled at the "
                "time of discharge. The patient was mobilized with therapy and met the functional "
                "milestones required for a safe discharge to home.",
            ),
        ),
        (
            "DISCHARGE MEDICATIONS",
            (
                "Oral analgesic as prescribed, taken as needed. Non-steroidal anti-inflammatory as "
                "tolerated. Bowel regimen while taking opioid analgesia. The patient was counselled on "
                "the sedating effects of the prescribed analgesia and advised not to drive while taking it.",
            ),
        ),
        (
            "FOLLOW-UP INSTRUCTIONS",
            (
                "Follow up with the primary treating physician within one week of discharge. Continue "
                "the prescribed therapy program. Return precautions were reviewed with the patient and "
                "the patient voiced understanding.",
            ),
        ),
    ),
    dispositions=(
        "DISCHARGE DISPOSITION: Home, independent, with outpatient follow-up. Work status: "
        "temporarily totally disabled pending re-evaluation.",
        "DISCHARGE DISPOSITION: Home with outpatient therapy. Work status: modified duty with "
        "restrictions as documented in the discharge instructions.",
    ),
    signer_title="Attending Physician",
)

FACE_SHEET_REGISTER = HospitalRegister(
    key="face_sheet",
    title="FACE SHEET — PATIENT REGISTRATION",
    facilities=_HOSPITAL_FACILITIES,
    header_fields=(
        ("Registration Type", ("Outpatient registration", "Inpatient admission", "Observation registration")),
        ("Financial Class", ("Workers' Compensation",)),
        ("Guarantor", ("Employer of record — workers' compensation carrier",)),
    ),
    sections=(
        (
            "REGISTRATION SUMMARY",
            (
                "This face sheet records the demographic, employment, and payer information captured at "
                "registration. It is a registration record only and contains no clinical narrative, "
                "assessment, or plan.",
            ),
        ),
        (
            "PAYER AND AUTHORIZATION",
            (
                "Claim identified as workers' compensation. Billing directed to the claims "
                "administrator of record rather than to the patient. Authorization status recorded at "
                "registration and subject to utilization review.",
            ),
        ),
    ),
    dispositions=(
        "Registration complete. Clinical documentation for this encounter is filed separately.",
    ),
    signer_title="Patient Registration",
)

_HOSPITAL_REGISTERS = (ER_REGISTER, ACUTE_REGISTER, DISCHARGE_REGISTER, FACE_SHEET_REGISTER)


def hospital_register(variant: str | None) -> HospitalRegister | None:
    """Register for a hospital-record variant, or ``None`` to keep the default.

    The bare operative variant resolves to ``None`` — an operative record is
    what the default template already renders correctly.
    """
    token = normalize_variant(variant)
    if not token:
        return None
    if _claims(token, "er", "emergency", "ed"):
        return ER_REGISTER
    if _claims(token, "acute", "acute_care", "hospital"):
        return ACUTE_REGISTER
    if _claims(token, "discharge"):
        return DISCHARGE_REGISTER
    if _claims(token, "face", "face_sheet", "registration"):
        return FACE_SHEET_REGISTER
    return None


# ---------------------------------------------------------------------------
# Defense-counsel correspondence: the contention loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LetterRegister:
    """A letter body keyed to what its registry subtype actually is.

    The substrate ships five letter bodies and picks one at random for all ~15
    subtypes routed here, so an objection to a medical-legal report and a
    subrogation demand drew from the same five. These are the three registers
    the medical-story contention loop turns on: advocacy out, supplemental
    requested, report objected to.

    Author-role caveat carried from the research note: this template mounts on a
    defense-firm letterhead, so every register here is written in the defense
    voice. An applicant-side advocacy letter is a real and different document
    and needs its own mount; that scoping decision is deliberately left to M3
    rather than guessed at here.
    """

    key: str
    paragraphs: tuple[str, ...]


ADVOCACY_LETTER = LetterRegister(
    key="advocacy",
    paragraphs=(
        "This office represents the defendants in the above-referenced matter. This letter is "
        "served as an advocacy letter pursuant to 8 C.C.R. section 35, and a copy is being served "
        "simultaneously on opposing counsel in accordance with the simultaneous-exchange requirement "
        "of that section.",
        "The medical-legal evaluator is respectfully directed to the following issues, which the "
        "defendants contend are material to the evaluation: the mechanism and industrial causation of "
        "the claimed injury; the existence and extent of any non-industrial contribution to the "
        "current level of impairment; whether the applicant has reached maximum medical improvement; "
        "and the apportionment of permanent disability between industrial and non-industrial factors "
        "pursuant to Labor Code sections 4663 and 4664.",
        "The evaluator is asked to review the enclosed records in their entirety and to state, with "
        "reasoning, the basis for each conclusion reached. Should the evaluator require additional "
        "records or information in order to reach a determination on any issue, please advise this "
        "office and opposing counsel in writing so the records may be obtained and exchanged.",
    ),
)

OBJECTION_LETTER = LetterRegister(
    key="objection",
    paragraphs=(
        "This office represents the defendants in the above-referenced matter. The defendants "
        "hereby object to the medical-legal report referenced above, and to its admission into "
        "evidence, on the grounds set forth below.",
        "The report does not adequately set forth the basis for the conclusions reached. In "
        "particular, the report states a conclusion on apportionment without describing the "
        "approximate percentage of permanent disability attributable to non-industrial factors, and "
        "without explaining how and why that determination was reached, as required. The defendants "
        "further object to the extent the report relies on a history that is incomplete or "
        "inconsistent with the records served on the evaluator.",
        "The defendants reserve all rights with respect to this report, including the right to "
        "depose the evaluator pursuant to Labor Code section 4620 et seq., the right to request a "
        "supplemental report addressing the deficiencies identified above, and the right to seek "
        "a replacement panel where appropriate. Please preserve all correspondence and records "
        "relating to this evaluation.",
    ),
)

SUPPLEMENTAL_REQUEST_LETTER = LetterRegister(
    key="supplemental_request",
    paragraphs=(
        "This office represents the defendants in the above-referenced matter. The defendants "
        "respectfully request a supplemental report from the medical-legal evaluator addressing the "
        "issues identified below. A copy of this request is served simultaneously on opposing counsel.",
        "The report served in this matter did not address, or did not fully address, the following: "
        "the approximate percentage of permanent disability directly caused by the industrial injury "
        "as against that caused by other factors, together with the reasoning supporting that "
        "allocation; whether any portion of the current impairment is attributable to a condition "
        "that predated the industrial injury; and whether the applicant's condition is permanent and "
        "stationary as of the date of the evaluation.",
        "The evaluator is asked to confine the supplemental report to the questions raised above and "
        "to identify any additional records reviewed in preparing it. Enclosed for the evaluator's "
        "review are the records that postdate the original evaluation. If the evaluator is unable to "
        "address any question on the record as it stands, please state what is required to do so.",
    ),
)

_LETTER_REGISTERS = (ADVOCACY_LETTER, OBJECTION_LETTER, SUPPLEMENTAL_REQUEST_LETTER)


def letter_register(variant: str | None) -> LetterRegister | None:
    """Register for a defense-letter variant, or ``None`` to keep the default."""
    token = normalize_variant(variant)
    if not token:
        return None
    if _claims(token, "advocacy"):
        return ADVOCACY_LETTER
    if _claims(token, "objection", "object", "opposition"):
        return OBJECTION_LETTER
    if _claims(token, "supplemental", "supplement"):
        return SUPPLEMENTAL_REQUEST_LETTER
    return None


# ---------------------------------------------------------------------------
# Discovery: who is actually being deposed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeponentRegister:
    """Which witness a deposition document concerns.

    The substrate picked the deponent with a coin flip, so a notice for a
    medical witness could name the applicant and vice versa, and no QME/AME
    deponent existed at all despite a registered subtype for one.
    """

    key: str
    role_label: str
    #: ``applicant``/``physician``/``evaluator``/``employer`` — which person on
    #: the case object the template should name. Kept as a token rather than a
    #: resolved name because only the template holds the case.
    subject: str
    documents: tuple[str, ...] = field(default=())
    examination_topics: tuple[str, ...] = field(default=())


APPLICANT_DEPONENT = DeponentRegister(
    key="applicant",
    role_label="Applicant",
    subject="applicant",
    documents=(
        "All tax returns for the three years prior to the date of injury",
        "All pay stubs from defendant employer",
        "Any and all medical records in your possession",
        "Any correspondence with the insurance carrier or adjuster",
        "Any photographs of the injury or accident scene",
    ),
)

PHYSICIAN_DEPONENT = DeponentRegister(
    key="medical_witness",
    role_label="Treating Physician",
    subject="physician",
    documents=(
        "Complete medical chart for the patient",
        "All diagnostic test results and imaging reports",
        "Treatment notes and progress reports",
        "Billing records and CPT codes",
        "Any correspondence regarding the patient's treatment",
    ),
)

EVALUATOR_DEPONENT = DeponentRegister(
    key="qme_ame",
    role_label="Medical-Legal Evaluator",
    subject="evaluator",
    documents=(
        "The complete evaluation file for this examinee, including all drafts",
        "All records reviewed in preparing the report, and the cover letters transmitting them",
        "All correspondence with either party regarding this evaluation",
        "The curriculum vitae in effect on the date of the evaluation",
        "The fee schedule and all billing submitted for this evaluation",
        "All notes, worksheets, and measurements taken at the time of examination",
    ),
    examination_topics=(
        "the evaluator's qualifications and appointment in this matter",
        "the records reviewed and the records not reviewed",
        "the history obtained from the examinee and its sources",
        "the examination findings and the measurements recorded",
        "the basis for the impairment rating assigned",
        "the basis for the apportionment determination, and the reasoning supporting it",
    ),
)

EMPLOYER_DEPONENT = DeponentRegister(
    key="defendant",
    role_label="Employer Representative",
    subject="employer",
    documents=(
        "The complete personnel file for the applicant",
        "All incident and injury reports concerning the claimed injury",
        "Job descriptions and physical requirements for the applicant's position",
        "All payroll and timekeeping records for the period at issue",
        "Any surveillance or investigative materials concerning the applicant",
    ),
)

_DEPONENT_REGISTERS = (
    APPLICANT_DEPONENT,
    PHYSICIAN_DEPONENT,
    EVALUATOR_DEPONENT,
    EMPLOYER_DEPONENT,
)


def deponent_register(variant: str | None) -> DeponentRegister | None:
    """Register for a deposition variant, or ``None`` to keep the default."""
    token = normalize_variant(variant)
    if not token:
        return None
    if _claims(token, "qme", "ame", "qme_ame", "evaluator"):
        return EVALUATOR_DEPONENT
    if _claims(token, "medical", "medical_witness", "physician", "witness"):
        return PHYSICIAN_DEPONENT
    if _claims(token, "applicant"):
        return APPLICANT_DEPONENT
    if _claims(token, "defendant", "employer"):
        return EMPLOYER_DEPONENT
    return None


# ---------------------------------------------------------------------------
# Whole-module sweep surface
# ---------------------------------------------------------------------------


def all_content_strings() -> list[str]:
    """Every string this module can put into a document.

    Exists so a test can sweep the whole module for real-entity names in one
    assertion, without that test needing to know the shape of each register.
    """
    out: list[str] = []

    def push(value) -> None:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                push(item)
        elif isinstance(value, Analyte):
            push((value.name, value.values, value.unit, value.reference))

    for register in _DIAGNOSTIC_REGISTERS:
        push(
            (
                register.exam_label,
                register.facilities,
                register.facility_kind,
                register.technique,
                register.result_heading,
                register.analytes,
                register.narrative_findings,
                register.impressions,
                register.signer_title,
                register.signer_credential,
            )
        )
    for panel, analytes in _LAB_PANELS.items():
        push(panel)
        push(analytes)
    push(_NCV_ROWS)
    push(_EMG_ROWS)
    for hospital in _HOSPITAL_REGISTERS:
        push(
            (
                hospital.title,
                hospital.facilities,
                hospital.header_fields,
                hospital.sections,
                hospital.dispositions,
                hospital.signer_title,
            )
        )
    for letter in _LETTER_REGISTERS:
        push(letter.paragraphs)
    for deponent in _DEPONENT_REGISTERS:
        push((deponent.role_label, deponent.documents, deponent.examination_topics))
    return out


#: Public panel/row tables the templates read.
LAB_PANELS = _LAB_PANELS
NCV_ROWS = _NCV_ROWS
EMG_ROWS = _EMG_ROWS
