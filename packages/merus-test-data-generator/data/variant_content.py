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


# ---------------------------------------------------------------------------
# Diagnostics: lab, electrodiagnostic, sleep
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultRow:
    """One reported measurement: label, value, unit, reference interval."""

    label: str
    value: str
    unit: str
    reference: str


@dataclass(frozen=True)
class DiagnosticScenario:
    """One internally coherent diagnostic report.

    Technique, measurements and impression are bound together in a single
    object and drawn with a single choice, rather than sampled independently.
    Independent sampling is what produced the incoherence this replaces: a
    blood chemistry panel could draw the urine chain-of-custody technique, sleep
    stage percentages need not total 100, an AHI in the severe range could sit
    above an impression reading "mild", and needle-EMG findings could contradict
    the diagnosis printed underneath them.

    A reader — or a classifier trained on these files — can only be misled by
    that, so the coupling is structural: to change one of these fields you have
    to look at the other two.
    """

    key: str
    exam_label: str
    technique: str
    result_heading: str
    rows: tuple[ResultRow, ...]
    impression: str
    secondary_heading: str = ""
    secondary_rows: tuple[ResultRow, ...] = ()
    #: ``"upper"``, ``"lower"`` or ``"any"`` — which body region the scenario
    #: examines, so a study is not reported on anatomy the case never injured.
    region: str = "any"


@dataclass(frozen=True)
class DiagnosticRegister:
    """A diagnostic document that is not a radiology report."""

    key: str
    facilities: tuple[str, ...]
    facility_kind: str
    scenarios: tuple[DiagnosticScenario, ...]
    signer_title: str = "Board Certified Physician"
    signer_credential: str = "CA License"

    def scenarios_for_region(self, region: str | None) -> tuple[DiagnosticScenario, ...]:
        """Scenarios examining *region*, or all of them when none applies.

        Never returns empty: a body part this module cannot place still gets a
        report, drawn from the full set, rather than no document at all.
        """
        if not region:
            return self.scenarios
        matching = tuple(s for s in self.scenarios if s.region in (region, "any"))
        return matching or self.scenarios


#: Body-part token -> limb region, for choosing an anatomically sensible study.
_REGION_TOKENS: tuple[tuple[str, str], ...] = (
    ("cervical", "upper"),
    ("neck", "upper"),
    ("shoulder", "upper"),
    ("elbow", "upper"),
    ("wrist", "upper"),
    ("hand", "upper"),
    ("finger", "upper"),
    ("arm", "upper"),
    ("lumbar", "lower"),
    ("low back", "lower"),
    ("hip", "lower"),
    ("knee", "lower"),
    ("ankle", "lower"),
    ("foot", "lower"),
    ("toe", "lower"),
    ("leg", "lower"),
)


def region_for_body_part(body_part: str | None) -> str | None:
    """Which limb region a body-part description names, or ``None`` if unclear.

    Deliberately conservative. "Spine" and "back" alone are unplaced — a
    cervical study and a lumbosacral study are different examinations, and
    guessing between them on an ambiguous word is how a report ends up
    describing anatomy the case never involved.
    """
    if not body_part:
        return None
    text = body_part.lower()
    for token, region in _REGION_TOKENS:
        if token in text:
            return region
    return None


# ---------------------------------------------------------------------------
# Diagnostics: clinical laboratory
# ---------------------------------------------------------------------------

_LAB_FACILITIES = (
    "Meridian Clinical Laboratory",
    "Crosswind Diagnostics Laboratory",
    "Harbor Point Reference Lab",
    "Fielding Clinical Labs",
)

_VENIPUNCTURE_TECHNIQUE = (
    "Specimen collected by venipuncture and processed on an automated clinical "
    "chemistry analyzer. Results are reported against the performing laboratory's "
    "own reference intervals. Specimen integrity acceptable; no hemolysis noted."
)
_URINE_TECHNIQUE = (
    "Urine specimen collected under standard chain-of-custody procedure. Screening "
    "performed by immunoassay, with presumptive positives confirmed by mass "
    "spectrometry. Specimen validity assessed by creatinine and temperature."
)

LAB_REGISTER = DiagnosticRegister(
    key="lab",
    facilities=_LAB_FACILITIES,
    facility_kind="Clinical Laboratory",
    signer_title="Clinical Laboratory Director",
    signer_credential="CA Clinical Laboratory License",
    scenarios=(
        DiagnosticScenario(
            key="cmp_normal",
            exam_label="CLINICAL LABORATORY REPORT — COMPREHENSIVE METABOLIC PANEL",
            technique=_VENIPUNCTURE_TECHNIQUE,
            result_heading="LABORATORY RESULTS",
            rows=(
                ResultRow("Glucose, fasting", "94", "mg/dL", "70-99"),
                ResultRow("BUN", "14", "mg/dL", "7-20"),
                ResultRow("Creatinine", "0.91", "mg/dL", "0.60-1.30"),
                ResultRow("Sodium", "139", "mmol/L", "135-145"),
                ResultRow("Potassium", "4.0", "mmol/L", "3.5-5.1"),
                ResultRow("Calcium", "9.5", "mg/dL", "8.6-10.2"),
                ResultRow("Total protein", "6.9", "g/dL", "6.0-8.3"),
                ResultRow("Albumin", "4.4", "g/dL", "3.5-5.0"),
                ResultRow("AST", "23", "U/L", "10-40"),
                ResultRow("ALT", "22", "U/L", "7-56"),
                ResultRow("Alkaline phosphatase", "68", "U/L", "44-147"),
                ResultRow("Total bilirubin", "0.6", "mg/dL", "0.1-1.2"),
            ),
            impression=(
                "All analytes within the stated reference intervals. No critical values "
                "identified."
            ),
        ),
        DiagnosticScenario(
            key="cmp_hyperglycemia",
            exam_label="CLINICAL LABORATORY REPORT — COMPREHENSIVE METABOLIC PANEL",
            technique=_VENIPUNCTURE_TECHNIQUE,
            result_heading="LABORATORY RESULTS",
            rows=(
                ResultRow("Glucose, fasting", "132", "mg/dL", "70-99"),
                ResultRow("BUN", "17", "mg/dL", "7-20"),
                ResultRow("Creatinine", "1.02", "mg/dL", "0.60-1.30"),
                ResultRow("Sodium", "141", "mmol/L", "135-145"),
                ResultRow("Potassium", "4.3", "mmol/L", "3.5-5.1"),
                ResultRow("Calcium", "9.2", "mg/dL", "8.6-10.2"),
                ResultRow("Total protein", "7.2", "g/dL", "6.0-8.3"),
                ResultRow("Albumin", "4.1", "g/dL", "3.5-5.0"),
                ResultRow("AST", "29", "U/L", "10-40"),
                ResultRow("ALT", "31", "U/L", "7-56"),
                ResultRow("Alkaline phosphatase", "81", "U/L", "44-147"),
                ResultRow("Total bilirubin", "0.8", "mg/dL", "0.1-1.2"),
            ),
            impression=(
                "Fasting glucose above the reference interval at 132 mg/dL. Remaining "
                "analytes within reference limits. Correlation with glycemic control and "
                "consideration of a hemoglobin A1c is recommended."
            ),
        ),
        DiagnosticScenario(
            key="cbc_normal",
            exam_label="CLINICAL LABORATORY REPORT — COMPLETE BLOOD COUNT WITH DIFFERENTIAL",
            technique=_VENIPUNCTURE_TECHNIQUE,
            result_heading="LABORATORY RESULTS",
            rows=(
                ResultRow("WBC", "6.4", "K/uL", "4.0-10.5"),
                ResultRow("RBC", "4.61", "M/uL", "4.10-5.60"),
                ResultRow("Hemoglobin", "13.6", "g/dL", "12.0-16.0"),
                ResultRow("Hematocrit", "40.7", "%", "36.0-48.0"),
                ResultRow("Platelets", "224", "K/uL", "150-400"),
                ResultRow("Neutrophils", "55", "%", "40-70"),
                ResultRow("Lymphocytes", "33", "%", "20-45"),
            ),
            impression=(
                "Complete blood count within reference limits. No evidence of anemia, "
                "leukocytosis, or thrombocytopenia."
            ),
        ),
        DiagnosticScenario(
            key="inflammatory_elevated",
            exam_label="CLINICAL LABORATORY REPORT — INFLAMMATORY MARKERS",
            technique=_VENIPUNCTURE_TECHNIQUE,
            result_heading="LABORATORY RESULTS",
            rows=(
                ResultRow("Sedimentation rate (ESR)", "31", "mm/hr", "0-20"),
                ResultRow("C-reactive protein", "3.2", "mg/dL", "0.0-1.0"),
                ResultRow("Rheumatoid factor", "<14", "IU/mL", "<14"),
            ),
            impression=(
                "Sedimentation rate and C-reactive protein are both elevated, indicating a "
                "nonspecific inflammatory process. Rheumatoid factor is not elevated. "
                "Clinical correlation is recommended; these markers are not specific to any "
                "single etiology."
            ),
        ),
        DiagnosticScenario(
            key="a1c_elevated",
            exam_label="CLINICAL LABORATORY REPORT — HEMOGLOBIN A1C",
            technique=_VENIPUNCTURE_TECHNIQUE,
            result_heading="LABORATORY RESULTS",
            rows=(
                ResultRow("Hemoglobin A1c", "7.1", "%", "4.0-5.6"),
                ResultRow("Estimated average glucose", "157", "mg/dL", "derived from A1c"),
            ),
            impression=(
                "Hemoglobin A1c of 7.1 percent is above the reference interval and within "
                "the range used to describe established diabetes mellitus. Estimated average "
                "glucose 157 mg/dL. Correlation with the treating provider's records is "
                "recommended."
            ),
        ),
        DiagnosticScenario(
            key="uds_consistent",
            exam_label=(
                "CLINICAL LABORATORY REPORT — URINE DRUG SCREEN, CHRONIC OPIOID THERAPY "
                "MONITORING"
            ),
            technique=_URINE_TECHNIQUE,
            result_heading="LABORATORY RESULTS",
            rows=(
                ResultRow("Opiates", "Detected", "", "Consistent with prescribed therapy"),
                ResultRow("Oxycodone", "Detected", "", "Consistent with prescribed therapy"),
                ResultRow("Benzodiazepines", "Not detected", "", "Not detected"),
                ResultRow("Amphetamines", "Not detected", "", "Not detected"),
                ResultRow("Cocaine metabolite", "Not detected", "", "Not detected"),
                ResultRow("Creatinine, urine", "94", "mg/dL", ">20 (valid specimen)"),
            ),
            impression=(
                "Specimen valid by creatinine. Findings are consistent with the prescribed "
                "opioid regimen. No non-prescribed substances detected."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Diagnostics: electrodiagnostic medicine
# ---------------------------------------------------------------------------

_ELECTRO_FACILITIES = (
    "Crestline Neurodiagnostic Center",
    "Waypoint Electrodiagnostic Associates",
    "Northgate Neuromuscular Diagnostics",
    "Silvermont Nerve Study Center",
)

_UPPER_LIMB_TECHNIQUE = (
    "Motor and sensory nerve conduction studies of the upper limb were performed "
    "using surface stimulation and recording electrodes, with limb temperature "
    "maintained above 32 degrees Celsius. Needle electromyography was performed "
    "with a disposable concentric needle electrode. The patient tolerated the "
    "study well."
)
_LOWER_LIMB_TECHNIQUE = (
    "Motor and sensory nerve conduction studies of the lower limb were performed "
    "using surface stimulation and recording electrodes, with limb temperature "
    "maintained above 32 degrees Celsius. Needle electromyography sampled distal "
    "muscles and the lumbosacral paraspinals. The patient tolerated the study well."
)

ELECTRODIAGNOSTIC_REGISTER = DiagnosticRegister(
    key="emg_ncv",
    facilities=_ELECTRO_FACILITIES,
    facility_kind="Neurodiagnostic Center",
    signer_title="Board Certified Neurologist",
    signer_credential="CA License",
    scenarios=(
        DiagnosticScenario(
            key="median_mild",
            region="upper",
            exam_label="ELECTRODIAGNOSTIC STUDY OF THE UPPER LIMB",
            technique=_UPPER_LIMB_TECHNIQUE,
            result_heading="NERVE CONDUCTION STUDIES",
            rows=(
                ResultRow("Median, motor (wrist-APB)", "4.6 ms, 6.1 mV, 49 m/s", "", "distal latency <4.2 ms"),
                ResultRow("Median, sensory (digit II)", "3.9 ms, 19 uV, 44 m/s", "", "peak latency <3.5 ms"),
                ResultRow("Ulnar, motor (wrist-ADM)", "3.1 ms, 8.2 mV, 53 m/s", "", "distal latency <3.3 ms"),
                ResultRow("Ulnar, sensory (digit V)", "2.9 ms, 24 uV, 51 m/s", "", "peak latency <3.2 ms"),
            ),
            secondary_heading="NEEDLE EMG",
            secondary_rows=(
                ResultRow("Abductor pollicis brevis", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("First dorsal interosseous", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("Cervical paraspinals (C5-C7)", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
            ),
            impression=(
                "Electrodiagnostic evidence of a mild focal median neuropathy at the wrist, "
                "shown by prolonged median distal motor and sensory latencies with preserved "
                "amplitudes. The needle examination shows no denervation. Ulnar studies are "
                "normal. There is no electrodiagnostic evidence of a cervical radiculopathy "
                "in the muscles sampled."
            ),
        ),
        DiagnosticScenario(
            key="median_moderate",
            region="upper",
            exam_label="ELECTRODIAGNOSTIC STUDY OF THE UPPER LIMB",
            technique=_UPPER_LIMB_TECHNIQUE,
            result_heading="NERVE CONDUCTION STUDIES",
            rows=(
                ResultRow("Median, motor (wrist-APB)", "5.4 ms, 4.8 mV, 45 m/s", "", "distal latency <4.2 ms"),
                ResultRow("Median, sensory (digit II)", "4.9 ms, 11 uV, 39 m/s", "", "peak latency <3.5 ms"),
                ResultRow("Ulnar, motor (wrist-ADM)", "3.1 ms, 8.2 mV, 53 m/s", "", "distal latency <3.3 ms"),
                ResultRow("Ulnar, sensory (digit V)", "3.0 ms, 22 uV, 50 m/s", "", "peak latency <3.2 ms"),
            ),
            secondary_heading="NEEDLE EMG",
            secondary_rows=(
                ResultRow("Abductor pollicis brevis", "increased insertional activity, 1+ fibrillations, mildly polyphasic motor unit potentials, mildly reduced recruitment", "", "normal"),
                ResultRow("First dorsal interosseous", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("Cervical paraspinals (C5-C7)", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
            ),
            impression=(
                "Electrodiagnostic evidence of a moderate focal median neuropathy at the "
                "wrist, with prolonged distal motor and sensory latencies, reduced sensory "
                "amplitude, and denervation changes confined to the abductor pollicis "
                "brevis. Ulnar studies are normal, and the cervical paraspinals show no "
                "evidence of radiculopathy."
            ),
        ),
        DiagnosticScenario(
            key="lumbosacral_radiculopathy",
            region="lower",
            exam_label="ELECTRODIAGNOSTIC STUDY OF THE LOWER LIMB",
            technique=_LOWER_LIMB_TECHNIQUE,
            result_heading="NERVE CONDUCTION STUDIES",
            rows=(
                ResultRow("Peroneal, motor (ankle-EDB)", "5.3 ms, 2.9 mV, 39 m/s", "", "distal latency <6.0 ms"),
                ResultRow("Tibial, motor (ankle-AH)", "5.1 ms, 6.4 mV, 42 m/s", "", "distal latency <5.8 ms"),
                ResultRow("Sural, sensory", "3.4 ms, 16 uV, 48 m/s", "", "peak latency <4.4 ms"),
            ),
            secondary_heading="NEEDLE EMG",
            secondary_rows=(
                ResultRow("Tibialis anterior", "increased insertional activity, 1+ fibrillations, mildly polyphasic motor unit potentials, mildly reduced recruitment", "", "normal"),
                ResultRow("Medial gastrocnemius", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("Lumbar paraspinals (L4-S1)", "increased insertional activity, 2+ positive sharp waves, normal motor unit potentials, reduced recruitment", "", "normal"),
            ),
            impression=(
                "Electrodiagnostic findings consistent with a chronic lumbosacral "
                "radiculopathy, indicated by denervation in the tibialis anterior and the "
                "lumbar paraspinals with preserved sural sensory response. The normal sural "
                "response argues against a generalized polyneuropathy."
            ),
        ),
        DiagnosticScenario(
            key="normal_upper",
            region="upper",
            exam_label="ELECTRODIAGNOSTIC STUDY OF THE UPPER LIMB",
            technique=_UPPER_LIMB_TECHNIQUE,
            result_heading="NERVE CONDUCTION STUDIES",
            rows=(
                ResultRow("Median, motor (wrist-APB)", "3.6 ms, 7.2 mV, 52 m/s", "", "distal latency <4.2 ms"),
                ResultRow("Median, sensory (digit II)", "3.2 ms, 28 uV, 48 m/s", "", "peak latency <3.5 ms"),
                ResultRow("Ulnar, motor (wrist-ADM)", "2.8 ms, 9.4 mV, 56 m/s", "", "distal latency <3.3 ms"),
                ResultRow("Ulnar, sensory (digit V)", "2.9 ms, 24 uV, 51 m/s", "", "peak latency <3.2 ms"),
            ),
            secondary_heading="NEEDLE EMG",
            secondary_rows=(
                ResultRow("Abductor pollicis brevis", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("First dorsal interosseous", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("Cervical paraspinals (C5-C7)", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
            ),
            impression=(
                "Study of the upper limb within normal limits. There is no electrodiagnostic "
                "evidence of a focal entrapment neuropathy at the wrist or elbow, and no "
                "evidence of a cervical radiculopathy in the muscles sampled."
            ),
        ),
        DiagnosticScenario(
            key="normal_lower",
            region="lower",
            exam_label="ELECTRODIAGNOSTIC STUDY OF THE LOWER LIMB",
            technique=_LOWER_LIMB_TECHNIQUE,
            result_heading="NERVE CONDUCTION STUDIES",
            rows=(
                ResultRow("Peroneal, motor (ankle-EDB)", "4.2 ms, 4.6 mV, 47 m/s", "", "distal latency <6.0 ms"),
                ResultRow("Tibial, motor (ankle-AH)", "4.4 ms, 8.1 mV, 46 m/s", "", "distal latency <5.8 ms"),
                ResultRow("Sural, sensory", "3.4 ms, 16 uV, 48 m/s", "", "peak latency <4.4 ms"),
            ),
            secondary_heading="NEEDLE EMG",
            secondary_rows=(
                ResultRow("Tibialis anterior", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("Medial gastrocnemius", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
                ResultRow("Lumbar paraspinals (L4-S1)", "normal insertional activity, no spontaneous activity, normal motor unit potentials, full recruitment", "", "normal"),
            ),
            impression=(
                "Study of the lower limb within normal limits. There is no electrodiagnostic "
                "evidence of a generalized polyneuropathy and no evidence of an active "
                "lumbosacral radiculopathy in the muscles sampled."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Diagnostics: sleep medicine
# ---------------------------------------------------------------------------

_SLEEP_FACILITIES = (
    "Lantern Hill Sleep Disorders Center",
    "Rosewater Sleep Medicine Institute",
    "Brightwater Sleep Diagnostics",
    "Kestrel Sleep Health Center",
)

_PSG_TECHNIQUE = (
    "Attended in-laboratory polysomnography was performed with electroencephalography, "
    "electrooculography, submental and tibial electromyography, electrocardiography, "
    "nasal pressure and thermal airflow, thoracoabdominal effort belts, pulse oximetry, "
    "and body position monitoring. Scoring followed standard adult criteria."
)


def _psg_rows(
    tst: str, efficiency: str, latency: str, n1: str, n2: str, n3: str, rem: str,
    arousal: str, ahi: str, nadir: str,
) -> tuple[ResultRow, ...]:
    """Build a polysomnography result table.

    The four sleep-stage percentages are passed together because they are one
    fact, not four: they must total 100, and a helper that takes them
    individually invites a set that does not.
    """
    assert int(n1) + int(n2) + int(n3) + int(rem) == 100, "sleep stages must total 100%"
    return (
        ResultRow("Total sleep time", tst, "minutes", "-"),
        ResultRow("Sleep efficiency", efficiency, "%", ">85"),
        ResultRow("Sleep latency", latency, "minutes", "<20"),
        ResultRow("Stage N1", n1, "%", "2-5"),
        ResultRow("Stage N2", n2, "%", "45-55"),
        ResultRow("Stage N3", n3, "%", "13-23"),
        ResultRow("Stage REM", rem, "%", "20-25"),
        ResultRow("Arousal index", arousal, "/hour", "<10"),
        ResultRow("Apnea-Hypopnea Index (AHI)", ahi, "/hour", "<5"),
        ResultRow("Oxygen saturation nadir", nadir, "%", ">90"),
    )


SLEEP_REGISTER = DiagnosticRegister(
    key="sleep_study",
    facilities=_SLEEP_FACILITIES,
    facility_kind="Sleep Disorders Center",
    signer_title="Board Certified Sleep Medicine Physician",
    signer_credential="CA License",
    scenarios=(
        DiagnosticScenario(
            key="psg_normal",
            exam_label="POLYSOMNOGRAPHY (ATTENDED, IN-LABORATORY)",
            technique=_PSG_TECHNIQUE,
            result_heading="SLEEP ARCHITECTURE AND RESPIRATORY SUMMARY",
            rows=_psg_rows("368", "89", "8", "5", "52", "20", "23", "8", "2.1", "92"),
            impression=(
                "No significant sleep-disordered breathing. The Apnea-Hypopnea Index of 2.1 "
                "per hour is below the diagnostic threshold of 5. Sleep architecture and "
                "oxygenation are preserved."
            ),
        ),
        DiagnosticScenario(
            key="psg_mild",
            exam_label="POLYSOMNOGRAPHY (ATTENDED, IN-LABORATORY)",
            technique=_PSG_TECHNIQUE,
            result_heading="SLEEP ARCHITECTURE AND RESPIRATORY SUMMARY",
            rows=_psg_rows("341", "84", "14", "8", "55", "17", "20", "18", "9.6", "88"),
            impression=(
                "Mild obstructive sleep apnea, with an Apnea-Hypopnea Index of 9.6 per hour "
                "in the mild range of 5 to 15. A trial of positional therapy and weight "
                "management is reasonable, with reassessment if symptoms persist."
            ),
        ),
        DiagnosticScenario(
            key="psg_moderate",
            exam_label="POLYSOMNOGRAPHY (ATTENDED, IN-LABORATORY)",
            technique=_PSG_TECHNIQUE,
            result_heading="SLEEP ARCHITECTURE AND RESPIRATORY SUMMARY",
            rows=_psg_rows("312", "78", "22", "11", "57", "14", "18", "26", "18.4", "84"),
            impression=(
                "Moderate obstructive sleep apnea, with an Apnea-Hypopnea Index of 18.4 per "
                "hour in the moderate range of 15 to 30, and an elevated arousal index. "
                "Positive airway pressure titration is recommended."
            ),
        ),
        DiagnosticScenario(
            key="psg_severe",
            exam_label="POLYSOMNOGRAPHY (ATTENDED, IN-LABORATORY)",
            technique=_PSG_TECHNIQUE,
            result_heading="SLEEP ARCHITECTURE AND RESPIRATORY SUMMARY",
            rows=_psg_rows("284", "71", "31", "15", "58", "11", "16", "34", "31.2", "79"),
            impression=(
                "Severe obstructive sleep apnea, with an Apnea-Hypopnea Index of 31.2 per "
                "hour above the severe threshold of 30, associated oxygen desaturation to a "
                "nadir of 79 percent, and marked sleep fragmentation. Positive airway "
                "pressure therapy is recommended, with follow-up to confirm adherence."
            ),
        ),
    ),
)

_DIAGNOSTIC_REGISTERS = (LAB_REGISTER, ELECTRODIAGNOSTIC_REGISTER, SLEEP_REGISTER)

#: Exact normalized variants each diagnostic register claims — an allowlist, for
#: the same reason the letter registers use one: a keyword match on a shared word
#: silently claims subtypes written for something else.
_DIAGNOSTIC_CLAIMS: dict[str, DiagnosticRegister] = {
    "lab": LAB_REGISTER,
    "labs": LAB_REGISTER,
    "lab_results": LAB_REGISTER,
    "diagnostics_lab_results": LAB_REGISTER,
    "emg_ncv": ELECTRODIAGNOSTIC_REGISTER,
    "emg": ELECTRODIAGNOSTIC_REGISTER,
    "ncv": ELECTRODIAGNOSTIC_REGISTER,
    "electrodiagnostic": ELECTRODIAGNOSTIC_REGISTER,
    "sleep_study": SLEEP_REGISTER,
    "sleep": SLEEP_REGISTER,
    "polysomnography": SLEEP_REGISTER,
}


def diagnostic_register(variant: str | None) -> DiagnosticRegister | None:
    """Register for a diagnostic variant, or ``None`` to keep the default.

    ``imaging`` deliberately resolves to ``None``: the substrate's own default
    document *is* the radiology report, so the imaging variant was never the
    defect and must not be re-implemented into a second, divergent version.
    """
    return _DIAGNOSTIC_CLAIMS.get(normalize_variant(variant))


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


#: Exact normalized variants each hospital register claims — an allowlist, like
#: every other register family here. The bare operative variant is deliberately
#: absent: an operative record is what the default template already renders.
_HOSPITAL_CLAIMS: dict[str, HospitalRegister] = {
    "er": ER_REGISTER,
    "acute": ACUTE_REGISTER,
    "discharge": DISCHARGE_REGISTER,
    "face_sheet": FACE_SHEET_REGISTER,
}


def hospital_register(variant: str | None) -> HospitalRegister | None:
    """Register for a hospital-record variant, or ``None`` to keep the default."""
    return _HOSPITAL_CLAIMS.get(normalize_variant(variant))


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


#: Exact normalized variants each letter register claims — an allowlist, not a
#: keyword match.
#:
#: Substring matching was wrong here and quietly so. ``DefenseCounselLetter``
#: serves 18 registry variants, and several are objections or oppositions to
#: something entirely different: ``objection_dor`` objects to a Declaration of
#: Readiness, ``opposition`` and ``reply`` belong to a Petition for
#: Reconsideration. Matching the word "objection" would have rendered
#: medical-legal QME-objection prose — apportionment, §4663, deposing the
#: evaluator — into a procedural DOR objection. Wrong document, confidently.
#:
#: So each register names the exact variants it claims. A variant absent here
#: renders the substrate default, which is the correct answer for a subtype no
#: register was written for.
_LETTER_CLAIMS: dict[str, LetterRegister] = {
    "advocacy": ADVOCACY_LETTER,
    "advocacy_ptp": ADVOCACY_LETTER,
    "advocacy_qme": ADVOCACY_LETTER,
    "advocacy_ame": ADVOCACY_LETTER,
    "objection_to_qme_ame_report": OBJECTION_LETTER,
    "request_for_supplemental_qme_ame_report": SUPPLEMENTAL_REQUEST_LETTER,
}


def letter_register(variant: str | None) -> LetterRegister | None:
    """Register for a defense-letter variant, or ``None`` to keep the default."""
    return _LETTER_CLAIMS.get(normalize_variant(variant))


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


@dataclass(frozen=True)
class TranscriptRegister:
    """Who a deposition transcript is actually a deposition *of*.

    The transcript template hardcoded the applicant as deponent — cover page,
    appearances, and a witness/applicant-oriented question pool — so the
    registry's ``DEPOSITION_TRANSCRIPT_QME_AME`` subtype produced an applicant
    deposition with the evaluator nowhere in it.

    ``topic_pools`` is a **complete** question set, not a preamble. An earlier
    revision prepended a dozen evaluator questions to the applicant generator,
    which read far worse than leaving it alone: the physician then answered, in
    the first person, what their own date of birth and social security number
    were, where they lived, and how their industrial injury happened. A
    transcript is the deponent's testimony end to end, so the register supplies
    the whole examination.
    """

    key: str
    subject: str
    role_label: str
    appearance_note: str
    #: ``(topic, ((question, answer), ...), min_drawn, max_drawn)``. Same shape
    #: as ``data/deposition_exchanges.py`` uses, so the two generators stay
    #: recognisably the same machine.
    topic_pools: tuple[tuple[str, tuple[tuple[str, str], ...], int, int], ...]


_EVALUATOR_QUALIFICATIONS = (
    ("Doctor, would you state your full name and business address for the record.",
     "My name and office address are as they appear on the face of my report in this matter."),
    ("What is your medical specialty?",
     "I practice in {specialty}."),
    ("Are you board certified in that specialty?",
     "I am, and my certification is listed in the curriculum vitae attached to my report."),
    ("When did you complete your residency training?",
     "The dates of my training appear in my curriculum vitae, which was served with the report."),
    ("Are you licensed to practice medicine in California?",
     "I am, and my license number appears on my report."),
    ("Have you been appointed as a Qualified Medical Evaluator by the Division of Workers' Compensation?",
     "My appointment in this matter is as stated in the cover letter accompanying the evaluation."),
    ("How long have you performed medical-legal evaluations?",
     "I have performed medical-legal evaluations for a substantial portion of my practice."),
    ("Approximately what percentage of your practice is medical-legal work as opposed to treatment?",
     "A portion of my practice is medical-legal; the remainder is clinical."),
    ("Do you perform evaluations at the request of applicants, defendants, or both?",
     "As a panel evaluator I am selected through the statutory process rather than by either party."),
    ("Have you testified as an expert in workers' compensation proceedings before?",
     "I have been deposed in matters of this kind previously."),
    ("Have your qualifications ever been challenged in a workers' compensation proceeding?",
     "I am not aware of a challenge to my qualifications having been sustained."),
    ("Is your curriculum vitae attached to the report current as of the date of the evaluation?",
     "The curriculum vitae served with the report was current as of that date."),
    ("Do you hold any subspecialty certifications relevant to the body parts at issue here?",
     "Any additional certifications I hold are listed in my curriculum vitae."),
    ("Doctor, are you being compensated for your time today?",
     "My time is billed at the rate set out in my fee schedule, which was provided."),
)

_EVALUATOR_RECORDS = (
    ("What records were you provided before you examined {applicant_name}?",
     "I received a set of records under cover letter. The records reviewed are listed in the records-review section of my report."),
    ("Who provided those records to you?",
     "The records were transmitted under cover letter from counsel, as reflected in my file."),
    ("Were the records served on you simultaneously on both parties?",
     "The cover letters in my file reflect the service made on me."),
    ("Did you review every record you were provided?",
     "The records I reviewed are the records enumerated in the records-review section of my report."),
    ("Were there records you were provided that you did not review?",
     "If a record was provided and not reviewed, it would not appear in my records-review section."),
    ("Did you receive any records or communications outside the formal exchange?",
     "I am not aware of receiving anything outside the cover letters reflected in my file."),
    ("Did you request any additional records?",
     "Any request for additional records would appear in my report or in the correspondence in my file."),
    ("Were you provided any prior medical-legal reports concerning {applicant_name}?",
     "Any prior report provided to me would be listed in my records-review section."),
    ("Were you provided imaging studies, or only the reports of those studies?",
     "What I reviewed is described in the records-review section, including whether I reviewed films or reports."),
    ("Did you review any deposition testimony in preparing your report?",
     "Any transcript provided to me is identified in the records-review section."),
    ("Did you review records concerning treatment predating the industrial injury?",
     "Records predating the injury, if provided, are identified in the records-review section."),
    ("Did you review any employment or personnel records?",
     "Any non-medical records provided to me are identified in the same section."),
    ("Do you know whether records exist that you were never provided?",
     "I can only speak to what I was provided; I have no way to know what was not sent."),
    ("If you were provided additional records now, would you review them?",
     "If I were provided additional records, I would review them and address them in a supplemental report if warranted."),
)

_EVALUATOR_HISTORY = (
    ("Doctor, did you take the history from {applicant_name} yourself?",
     "The history reflected in my report was obtained during my evaluation."),
    ("Was an interpreter used during the history?",
     "If an interpreter was used, that is noted in my report."),
    ("How long did you spend obtaining the history?",
     "The time spent on history, examination, and records review is itemized in my report and billing."),
    ("Did anyone other than you speak with {applicant_name} about the history?",
     "The history in my report is the history I obtained."),
    ("Did the history you obtained differ from the history in the treating records?",
     "Where the history I obtained differs from the records, my report describes the difference."),
    ("What did {applicant_name} tell you about how the injury occurred?",
     "The mechanism of injury as reported to me is set out in the history section of my report."),
    ("Did {applicant_name} report any prior injury to {body_parts}?",
     "Any prior injury reported to me is recorded in the history section."),
    ("Did {applicant_name} report symptoms before the date of injury?",
     "Pre-injury symptoms, if reported, are recorded in the history."),
    ("Did you ask about non-industrial activities that could affect {body_parts}?",
     "The history I take covers activities relevant to the body parts at issue."),
    ("Did you rely on the history in reaching your conclusions?",
     "History is one of the inputs to my opinions, together with the examination and the records."),
    ("If the history you were given were inaccurate, would your opinion change?",
     "If I were shown that a material part of the history was inaccurate, I would reconsider and address it."),
    ("Did you document the history contemporaneously?",
     "My report reflects the evaluation as I conducted it."),
)

_EVALUATOR_EXAMINATION = (
    ("Doctor, describe the physical examination you performed on {applicant_name}.",
     "The examination findings are set out in the physical examination section of my report."),
    ("How long did the examination itself take?",
     "The time is itemized in my report and in my billing for this evaluation."),
    ("What instruments did you use to measure range of motion?",
     "Range of motion was measured using standard instrumentation as described in my report."),
    ("Did you take measurements of {body_parts} yourself?",
     "The measurements recorded in my report are the measurements taken at my examination."),
    ("Were the range of motion measurements repeated?",
     "My report reflects the measurements I recorded at the time of examination."),
    ("Did you perform any provocative or special testing?",
     "Any special testing performed is described in the examination section."),
    ("Did you observe any signs of symptom magnification?",
     "Any observation bearing on consistency of effort would be documented in my report."),
    ("Were the examination findings consistent with the reported symptoms?",
     "My report states whether the objective findings correlate with the subjective complaints."),
    ("Did you examine body parts other than {body_parts}?",
     "The scope of my examination is described in the report."),
    ("Was anyone else present during the examination?",
     "The presence of any observer would be noted in my report."),
    ("Did you review the imaging yourself, or rely on the radiologist's reading?",
     "My report states what I reviewed and what I relied upon."),
    ("Do your objective findings support the diagnosis you reached?",
     "The relationship between my findings and my diagnosis is set out in the report."),
)

_EVALUATOR_IMPAIRMENT = (
    ("Doctor, what diagnosis did you reach for {body_parts}?",
     "The diagnoses are listed in the diagnosis section of my report."),
    ("Is {applicant_name} permanent and stationary?",
     "My opinion on permanent and stationary status is stated in my report as of the date of evaluation."),
    ("What did you rely on to arrive at the impairment rating?",
     "The rating is derived from the measurements recorded at examination, applied under the applicable rating methodology, as set out in my report."),
    ("Which edition and which tables did you apply?",
     "The methodology and the specific tables applied are identified in my report."),
    ("Did you consider whether the rating adequately reflects the impairment?",
     "My report addresses whether the described impairment is adequately captured by the rating."),
    ("Did you rate any body part other than {body_parts}?",
     "Every body part rated is identified in the report."),
    ("Would a different measurement have produced a different rating?",
     "The rating follows from the measurements recorded; different measurements would follow the same method."),
    ("Is your impairment opinion stated to a reasonable degree of medical probability?",
     "My opinions are stated to a reasonable degree of medical probability."),
    ("Did you consider work restrictions separately from the impairment rating?",
     "Work restrictions are addressed separately in my report from the impairment rating."),
    ("What future medical care did you recommend?",
     "Future medical care is addressed in the corresponding section of my report."),
    ("Is the need for future care related to the industrial injury?",
     "My report states the basis on which future care is recommended."),
    ("Would you defer any part of the rating to another specialty?",
     "Any deferral to another specialty is stated in my report."),
)

_EVALUATOR_CAUSATION = (
    ("Doctor, in your opinion, was the injury to {body_parts} caused by employment?",
     "My opinion on industrial causation is set out in the causation section of my report."),
    ("What did you rely on in reaching that causation opinion?",
     "I relied on the history, the examination findings, and the records identified in my report."),
    ("Is your causation opinion stated to a reasonable degree of medical probability?",
     "It is."),
    ("Did you consider any non-industrial cause for the condition?",
     "My report describes the factors I considered, industrial and otherwise."),
    ("Could the condition have arisen without the employment?",
     "My report addresses the relationship between the employment and the condition as I found it."),
    ("Did you consider whether the condition is a compensable consequence of another injury?",
     "Any compensable-consequence analysis I performed is set out in the report."),
    ("Would a different mechanism of injury change your causation opinion?",
     "A materially different mechanism could bear on causation, and I would address it if shown one."),
    ("Did the treating physician reach the same causation conclusion?",
     "My report notes where my conclusions differ from those in the records I reviewed."),
    ("Did you consider the possibility of a cumulative trauma in addition to the specific injury?",
     "The report addresses the injury or injuries I was asked to evaluate."),
    ("Do you hold your causation opinion today?",
     "I hold the opinions in my report unless shown information that would change them."),
)

_EVALUATOR_APPORTIONMENT = (
    ("Doctor, did you reach a conclusion on apportionment?",
     "My conclusion on apportionment is stated in the apportionment section of my report."),
    ("What is the basis for that apportionment conclusion?",
     "The basis is stated in the apportionment section, which describes the factors I considered and the reasoning applied to them."),
    ("Can you identify the specific records that support the non-industrial portion?",
     "The records I relied upon are those identified in the records-review and apportionment sections of my report."),
    ("Did you apportion to any pre-existing pathology?",
     "Whether any portion is attributable to a pre-existing condition is addressed in the apportionment section."),
    ("How did you determine the approximate percentage?",
     "My report describes how and why I reached the allocation stated."),
    ("Is your apportionment opinion stated to a reasonable degree of medical probability?",
     "It is."),
    ("Did you apportion to the natural progression of a non-industrial condition?",
     "The factors I considered are identified in the apportionment section."),
    ("Did you apportion any portion to medical treatment provided for the injury?",
     "My report states what I did and did not apportion to."),
    ("Were you provided evidence of a prior award of permanent disability?",
     "Any prior award provided to me would be identified in my records-review section."),
    ("Did you consider whether the current disability overlaps a prior disability?",
     "Any overlap analysis I performed is set out in the report."),
    ("Would additional records change your apportionment opinion?",
     "If I were provided records that materially bear on apportionment, I would consider them and address them in a supplemental report."),
    ("Are you able to apportion without speculating?",
     "I state an apportionment opinion only where I can support it; where I cannot, my report says so."),
    ("Did anyone suggest an apportionment figure to you?",
     "The opinions in my report are my own."),
    ("If your apportionment reasoning were found inadequate, would you supplement the report?",
     "If asked to address a deficiency, I would do so in a supplemental report."),
)

_EVALUATOR_INDEPENDENCE = (
    ("Doctor, did anyone other than you draft any portion of the report you signed?",
     "The opinions in the report are my own, and I signed it as my report."),
    ("Did you use a template or dictation service in preparing the report?",
     "The report reflects my evaluation and my opinions however it was transcribed."),
    ("Did you have any communication with defense counsel about your conclusions?",
     "I am not aware of any communication outside the formal correspondence in my file."),
    ("Did you have any communication with applicant's counsel about your conclusions?",
     "The same answer applies; my file reflects the correspondence I received."),
    ("Have you performed evaluations for this carrier before?",
     "As a panel evaluator I am selected through the statutory process."),
    ("Do you have any financial interest in the outcome of this claim?",
     "I do not."),
    ("Do you have any relationship with {applicant_name} outside this evaluation?",
     "I do not."),
    ("Did you review your report for accuracy before signing it?",
     "I did."),
    ("Have you made any corrections to the report since serving it?",
     "Any correction would be reflected in a supplemental report or an erratum."),
)

_EVALUATOR_CLOSING = (
    ("Doctor, is there anything in your report you would like to correct today?",
     "Nothing that I am aware of at this time."),
    ("Do all of the opinions in your report remain your opinions today?",
     "They do, subject to any information I have not been provided."),
    ("Have you told us everything that supports your apportionment conclusion?",
     "The basis for my conclusion is set out in my report and I have described it here."),
    ("Thank you, Doctor. I have nothing further at this time.",
     "Thank you."),
)

EVALUATOR_TRANSCRIPT = TranscriptRegister(
    key="qme_ame",
    subject="evaluator",
    role_label="Medical-Legal Evaluator",
    appearance_note="The deponent appeared and was sworn as the medical-legal evaluator.",
    topic_pools=(
        ("QUALIFICATIONS AND APPOINTMENT", _EVALUATOR_QUALIFICATIONS, 9, 13),
        ("RECORDS PROVIDED AND REVIEWED", _EVALUATOR_RECORDS, 9, 13),
        ("HISTORY OBTAINED FROM THE EXAMINEE", _EVALUATOR_HISTORY, 8, 11),
        ("EXAMINATION METHODOLOGY", _EVALUATOR_EXAMINATION, 8, 11),
        ("DIAGNOSIS AND IMPAIRMENT", _EVALUATOR_IMPAIRMENT, 8, 11),
        ("CAUSATION", _EVALUATOR_CAUSATION, 7, 10),
        ("BASIS FOR APPORTIONMENT", _EVALUATOR_APPORTIONMENT, 10, 14),
        ("INDEPENDENCE AND EX PARTE CONTACT", _EVALUATOR_INDEPENDENCE, 6, 9),
        ("CLOSING", _EVALUATOR_CLOSING, 3, 4),
    ),
)

_TRANSCRIPT_REGISTERS = (EVALUATOR_TRANSCRIPT,)

#: Exact normalized variants the transcript registers claim. ``witness`` and the
#: interrogatory/production-response variants are deliberately absent: the
#: substrate default is an applicant deposition, which is the right shape for a
#: witness statement and the wrong shape for interrogatory responses — but the
#: latter needs a document this seam does not author, so it keeps the default
#: rather than being handed a QME register that does not fit it either.
_TRANSCRIPT_CLAIMS: dict[str, TranscriptRegister] = {
    "deposition_transcript_qme_ame": EVALUATOR_TRANSCRIPT,
    "qme_ame": EVALUATOR_TRANSCRIPT,
}


def transcript_register(variant: str | None) -> TranscriptRegister | None:
    """Register for a deposition-transcript variant, or ``None`` for the default."""
    return _TRANSCRIPT_CLAIMS.get(normalize_variant(variant))


def generate_evaluator_exchanges(
    register: TranscriptRegister,
    case_data: dict[str, str],
    max_exchanges: int = 95,
) -> list[tuple[str, str]]:
    """A complete evaluator examination, in the substrate's own exchange format.

    Mirrors ``data.deposition_exchanges.generate_deposition_exchanges``
    deliberately, down to the ``Q. ``/``A. `` prefixes the transcript renderer
    expects — an earlier revision returned bare tuples, and every one of those
    lines rendered without its speaker label.

    Topics are drawn in examination order rather than shuffled, because a
    deposition that asks about apportionment before establishing qualifications
    does not read like a transcript.

    Shorter than the applicant generator's 100-180 on purpose. An evaluator
    deposition covers the report rather than a life, and padding it back up to
    an applicant transcript's length would mean repeating questions to hit a
    page count — which is the kind of detail that makes synthetic data look
    synthetic.
    """
    import random as _random

    def fill(text: str) -> str:
        for key, value in case_data.items():
            text = text.replace("{" + key + "}", str(value))
        return text

    exchanges: list[tuple[str, str]] = []
    for _topic, pool, low, high in register.topic_pools:
        count = min(_random.randint(low, high), len(pool))
        # The first question of every topic is an anchor and always asked. A
        # deposition that never establishes the witness's name, never asks what
        # records were reviewed, or never reaches apportionment at all is not a
        # variable transcript, it is an incomplete one — and the topic would
        # silently vanish on some seeds.
        remainder = _random.sample(range(1, len(pool)), max(count - 1, 0))
        chosen = [0] + sorted(remainder)
        for index in chosen:
            question, answer = pool[index]
            exchanges.append((fill(f"Q. {question}"), fill(f"A. {answer}")))

    target = _random.randint(max_exchanges - 25, max_exchanges)
    if len(exchanges) > target:
        # Trim from the middle so the opening and the closing both survive.
        keep_tail = 4
        head = exchanges[: target - keep_tail]
        exchanges = head + exchanges[-keep_tail:]
    return exchanges


#: Exact normalized variants each deponent register claims — an allowlist, for
#: the reason every family here uses one. ``DEPOSITION_NOTICE`` with no variant
#: keeps the substrate's own coin flip, which is the honest answer when the
#: subtype genuinely does not say who is being deposed.
_DEPONENT_CLAIMS: dict[str, DeponentRegister] = {
    "applicant": APPLICANT_DEPONENT,
    "medical_witness": PHYSICIAN_DEPONENT,
    "defendant": EMPLOYER_DEPONENT,
    "qme_ame": EVALUATOR_DEPONENT,
    "deposition_notice_qme_ame": EVALUATOR_DEPONENT,
}


def deponent_register(variant: str | None) -> DeponentRegister | None:
    """Register for a deposition variant, or ``None`` to keep the default."""
    return _DEPONENT_CLAIMS.get(normalize_variant(variant))


# ---------------------------------------------------------------------------
# Whole-module sweep surface
# ---------------------------------------------------------------------------


def all_content_strings() -> list[str]:
    """Every string this module can put into a document.

    Exists so a test can sweep the whole module for real-entity names in one
    assertion, without that test needing to know the shape of each register.
    Deliberately reflective over the dataclasses rather than a hand-listed set
    of fields: a field added to a register must not be able to smuggle a name
    past the sweep by not being listed here.
    """
    out: list[str] = []
    seen: set[int] = set()

    def push(value) -> None:
        if isinstance(value, str):
            out.append(value)
            return
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, dict):
            for key, item in value.items():
                push(key)
                push(item)
        elif isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                push(item)
        elif hasattr(value, "__dataclass_fields__"):
            for name in value.__dataclass_fields__:
                push(getattr(value, name))

    push(_DIAGNOSTIC_REGISTERS)
    push(_HOSPITAL_REGISTERS)
    push(_LETTER_REGISTERS)
    push(_DEPONENT_REGISTERS)
    push(_TRANSCRIPT_REGISTERS)
    return out
