"""The CaseFacts ledger — one record of what clinically happened in a case.

Before this module, every template that wanted a clinical detail invented one on
the spot. A QME report drew ``random.choice(["MRI", "X-ray", "CT scan"])`` per
body part and asserted imaging that no diagnostic report in the same case had
ever produced; the diagnostic report drew its own modality independently; and
``has_surgery`` gated six document *rules* while reaching no document *content*
at all, so a post-operative progress report described conservative care.

Nothing was wrong with any single draw. What was wrong is that there was no
place for the case to agree with itself. This module is that place: derived once
per case at plan time, read by every fact-aware template, and published in the
manifest so a reader can check the documents against it.

Two design rules hold the guarantee up.

**Namespaced streams.** Every draw here comes from
:func:`~wc_caseload_engine.seeds.derive_seed` under a ``facts:`` prefix, never
from a stream an existing draw already consumes. A case that seeds no
``scenario:`` block and reaches no fact-aware subtype therefore renders byte for
byte as it did at 0.2.0 — the ledger is computed, published, and simply not
consulted.

**The seed wins, the derivation fills in.** Anything ``scenario:`` states is
taken as given. Anything it leaves open is derived, and the derivation
deliberately reproduces the substrate's own prior behaviour where one existed —
the surgery coin is still 35% off the same ``clinical`` stream, so
``has_surgery`` parity holds for every seed written before this block existed.
"""

from __future__ import annotations

import datetime as dt
import random
from datetime import timedelta
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from wc_caseload_engine.seeds import CaseSeed, derive_seed
from wc_caseload_engine.substrate import import_substrate

log = structlog.get_logger(__name__)


type Modality = Literal["mri", "ct", "xray", "emg", "labs"]
"""The diagnostic vocabulary a ``scenario:`` block may name.

Deliberately small. These are the modalities the substrate's medical templates
can actually render prose for; admitting a value no template can speak would
produce a ledger entry that no document could honour, which is the failure this
module exists to prevent.
"""

MODALITIES: tuple[str, ...] = ("mri", "ct", "xray", "emg", "labs")
"""Runtime mirror of :data:`Modality`, for validation messages and iteration."""

MODALITY_DISPLAY: dict[str, str] = {
    "mri": "MRI",
    "ct": "CT",
    "xray": "X-Ray",
    "emg": "EMG",
    "labs": "Laboratory Studies",
}
"""How each modality is written in a rendered document.

One spelling per modality, in one place, because the coherence harness greps
for these strings — two spellings would make "no document names an absent
modality" unenforceable.
"""

#: Modalities a ``DIAGNOSTICS_IMAGING`` document can actually render.
#:
#: The substrate's diagnostic report picks its TECHNIQUE paragraph off the exam
#: type — MRI gets pulse sequences, CT gets slice thickness, and **anything
#: else falls through to radiographic projections**. Handing that template an
#: EMG produces a nerve conduction study described in X-ray language, which is
#: worse than the incoherence the ledger exists to remove.
IMAGING_MODALITIES: tuple[str, ...] = ("mri", "ct", "xray")

#: Modalities the derivation may draw when the seed does not say.
#:
#: ``labs`` and ``emg`` are both excluded on purpose, for the same reason and
#: with the same consequence: they are orderable in the schema so a seed can
#: state them, and the QME governs their presence and absence, but neither can
#: be *assigned to an imaging report*. Drawing them unprompted would either put
#: lab studies in orthopedic files that have no reason to hold them, or route
#: an EMG into the radiographic template above.
_DERIVABLE_MODALITIES: tuple[str, ...] = IMAGING_MODALITIES

SURGERY_CPT_CODES: dict[str, tuple[str, str]] = {
    "lumbar_spine": ("63030", "Lumbar laminotomy with decompression"),
    "cervical_spine": ("63075", "Cervical discectomy, anterior approach"),
    "thoracic_spine": ("63055", "Thoracic laminectomy with decompression"),
    "shoulder": ("29827", "Arthroscopic rotator cuff repair"),
    "knee": ("29881", "Arthroscopic partial medial meniscectomy"),
    "wrist": ("64721", "Carpal tunnel release"),
    "ankle": ("27822", "Open treatment of ankle fracture"),
    "elbow": ("24357", "Lateral epicondylitis release"),
}
"""Body part -> (CPT, description) for a surgery the ledger says happened.

The CPT is the single figure the coherence harness checks across documents: an
operative report, a QME's surgical history and a treating physician's plan must
all name the same procedure or the file is describing two different operations.
"""

_DEFAULT_CPT: tuple[str, str] = ("64999", "Unlisted procedure, nervous system")


class DiagnosticFact(BaseModel):
    """One diagnostic study — performed, or deliberately not.

    The *absent* half is the half that makes the ledger enforceable. Recording
    only what happened lets a template invent anything it likes about what did
    not; recording an explicit absence gives the harness something to grep for.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    modality: str
    body_part: str
    date: dt.date | None = None
    performed: bool = True

    @property
    def display(self) -> str:
        """The modality as a rendered document spells it."""
        return MODALITY_DISPLAY.get(self.modality, self.modality.upper())


class SurgeryFact(BaseModel):
    """Whether an operation happened, and if so which one.

    Four states, and only one of them puts a knife anywhere near the applicant.
    ``recommended`` and ``denied_by_ur`` both describe a *proposed* procedure —
    one pending, one refused — so both name a CPT and neither emits an
    operative document. Keeping them distinct from ``none`` is what lets a
    treating report say "surgical consultation obtained, authorization denied"
    without the file also containing an operation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["none", "performed", "recommended", "denied_by_ur"] = "none"
    body_part: str | None = None
    cpt_code: str | None = None
    cpt_description: str | None = None
    date: dt.date | None = None

    @property
    def performed(self) -> bool:
        return self.status == "performed"

    @property
    def proposed(self) -> bool:
        """A procedure was named but never done."""
        return self.status in ("recommended", "denied_by_ur")

    @property
    def names_a_procedure(self) -> bool:
        """Any state in which a CPT belongs in the ledger."""
        return self.status != "none"


class ProviderFact(BaseModel):
    """One treating or examining provider.

    Exists so subpoenaed-records packets can be attributed to *different*
    providers. The engine never set ``provider_index``, so every packet in every
    case was attributed to the treating physician — a records subpoena to one
    provider, answered four times by the same clinic.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    specialty: str
    facility: str


class VisitFact(BaseModel):
    """One dated clinical contact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: dt.date
    kind: Literal["initial", "follow_up", "post_operative", "final"] = "follow_up"


class LateBenefitEvent(BaseModel):
    """A benefit notice or payment that missed its statutory window.

    Recorded rather than inferred. The LC 5814 penalty petition is gated on
    this list being non-empty, so "was the administrator late" has to be a fact
    the ledger holds, not a coin the planner flips — otherwise the file can
    contain a penalty petition alleging a delay that never happened, which is
    what the substrate's flat 10% rule produced.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    """Which obligation was missed — a key of :data:`BENEFIT_NOTICE_WINDOWS`."""

    due_date: dt.date
    actual_date: dt.date
    days_late: int = Field(ge=1)


class CaseFacts(BaseModel):
    """What clinically happened in one case, decided once.

    Derived at plan time by :func:`derive_case_facts` and carried alongside the
    plan, so the planner, the renderer and the manifest all read the same
    answer instead of three independent guesses.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    diagnostics: tuple[DiagnosticFact, ...] = ()
    surgery: SurgeryFact = Field(default_factory=SurgeryFact)
    providers: tuple[ProviderFact, ...] = ()
    visits: tuple[VisitFact, ...] = ()
    treatment_status: Literal["ongoing", "discharged", "gap", "never_treated"] = "ongoing"
    trajectory: Literal["improving", "plateau", "worsening"] = "plateau"
    adjuster_diligence: Literal["attentive", "ordinary", "negligent"] = "ordinary"
    attorney_cadence: Literal["every_30_days", "event_driven", "sporadic"] = "event_driven"
    late_benefit_events: tuple[LateBenefitEvent, ...] = ()
    adjuster_letter_types_allowed: frozenset[str] = frozenset()
    """Letter contents this case's lifecycle can support — see ``ADJUSTER_LETTER_TYPES``."""
    mmi_date: dt.date | None = None
    wpi: int | None = None
    pd: int | None = None

    @property
    def discharge_date(self) -> dt.date | None:
        """When care ended, for a discharged file. ``None`` otherwise."""
        if self.treatment_status != "discharged":
            return None
        final = [v for v in self.visits if v.kind == "final"]
        return final[-1].date if final else None

    @property
    def treatment_gap(self) -> tuple[dt.date, dt.date] | None:
        """The largest hole in the visit series, when the seed asked for one.

        Computed from the dates rather than stored beside them, so the fact the
        documents describe and the fact the ledger publishes cannot drift.
        """
        if self.treatment_status != "gap" or len(self.visits) < 2:
            return None
        pairs = list(zip(self.visits, self.visits[1:], strict=False))
        start, end = max(pairs, key=lambda pair: (pair[1].date - pair[0].date).days)
        return (start.date, end.date)

    def phrase_for(self, index: int) -> str:
        """The status phrase for the *index*-th treating report in the case.

        Monotone within the arc: consecutive reports move forward through the
        phrase list and hold at the last one rather than wrapping. Wrapping
        would put "approaching maximum medical improvement" before "showing
        steady improvement" in a later report, which is the zig-zag this
        replaces.
        """
        phrases = TRAJECTORY_PHRASES[self.trajectory]
        return phrases[min(index, len(phrases) - 1)]

    @property
    def performed_diagnostics(self) -> tuple[DiagnosticFact, ...]:
        return tuple(fact for fact in self.diagnostics if fact.performed)

    @property
    def absent_diagnostics(self) -> tuple[DiagnosticFact, ...]:
        return tuple(fact for fact in self.diagnostics if not fact.performed)

    def performed_modalities(self) -> frozenset[str]:
        return frozenset(fact.modality for fact in self.performed_diagnostics)

    def absent_modalities(self) -> frozenset[str]:
        """Absent modalities that are not performed for some *other* body part.

        A study can be performed on the lumbar spine and deliberately absent on
        the shoulder; the modality itself is then not absent from the file, and
        a document naming it is not incoherent. Only a modality that appears
        nowhere as performed is greppable as an absence.
        """
        return frozenset(
            fact.modality for fact in self.absent_diagnostics
        ) - self.performed_modalities()

    def diagnostic_for(self, index: int) -> DiagnosticFact | None:
        """The performed study the imaging report at *index* should report.

        Round-robin rather than modulo-with-repeats-first so that a case with
        three performed studies and three imaging reports emits one of each,
        which is what makes "one document per performed diagnostic" checkable.

        Filtered to :data:`IMAGING_MODALITIES`: a seed may state a performed
        EMG or lab panel, and the QME governs whether it is cited or noted
        absent, but neither can be handed to the imaging template — it would
        render a nerve conduction study in radiographic language.
        """
        performed = [f for f in self.performed_diagnostics if f.modality in IMAGING_MODALITIES]
        if not performed:
            return None
        return performed[index % len(performed)]

    def provider_for(self, index: int) -> ProviderFact | None:
        """The provider a records packet at *index* is answered by."""
        if not self.providers:
            return None
        return self.providers[index % len(self.providers)]


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def _rng(seed: CaseSeed, salt: str) -> random.Random:
    """A private stream under the ``facts:`` namespace.

    Never the global :mod:`random` the substrate templates draw from, and never
    a salt an existing draw already uses — that separation is what lets a case
    with no ``scenario:`` block keep its 0.2.0 bytes.
    """
    return random.Random(derive_seed(seed.rng_seed, f"facts:{salt}"))


def _body_parts(seed: CaseSeed) -> list[str]:
    return [part.part for part in seed.injury.body_parts]


def _derive_diagnostics(seed: CaseSeed, timeline: Any) -> tuple[DiagnosticFact, ...]:
    """Ledger entries for every study, performed or deliberately absent.

    The seed's ``scenario.diagnostics`` is authoritative. What it does not
    mention is derived: each body part draws a study with a probability that
    leaves some parts deliberately un-imaged, because a file where every region
    was scanned is exactly the tell this ledger exists to remove.
    """
    scenario = seed.scenario.diagnostics
    parts = _body_parts(seed)
    primary = parts[0] if parts else "spine"
    rng = _rng(seed, "diagnostics")

    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    facts: list[DiagnosticFact] = []
    claimed: set[tuple[str, str]] = set()

    def add(modality: str, body_part: str, *, performed: bool) -> None:
        key = (modality, body_part)
        if key in claimed:
            return
        claimed.add(key)
        study_date = onset + timedelta(days=30 + 25 * len(facts)) if performed else None
        facts.append(
            DiagnosticFact(
                modality=modality,
                body_part=body_part,
                date=study_date,
                performed=performed,
            )
        )

    # Explicit first, so a derived draw can never contradict a seeded statement.
    for entry in scenario.performed:
        add(entry.modality, entry.body_part or primary, performed=True)
    for entry in scenario.absent:
        add(entry.modality, entry.body_part or primary, performed=False)

    if not scenario.performed and not scenario.absent:
        for position, part in enumerate(parts):
            # The first region is always studied — a claim that reached a
            # medical-legal evaluation without imaging its main complaint is
            # rarer than the realism gained by pretending otherwise.
            if position == 0 or rng.random() < 0.6:
                add(rng.choice(_DERIVABLE_MODALITIES), part, performed=True)
            else:
                add(rng.choice(_DERIVABLE_MODALITIES), part, performed=False)

    return tuple(facts)


#: The substrate's own per-document status phrases, drawn inline at
#: ``treating_physician_report.py:127``. Matched exactly so the override can
#: recognise the draw it is replacing; if this list moves upstream, the shim
#: stops firing and says so rather than silently reverting to random.
SUBSTRATE_STATUS_PHRASES: tuple[str, ...] = (
    "unchanged since last visit",
    "slowly improving",
    "fluctuating with activity",
    "worsening despite treatment",
)

#: Trajectory phrases, earliest-to-latest within each arc.
#:
#: Ordered on purpose. The substrate drew one phrase per document from a flat
#: list, so a three-report case could read worsening, improving, worsening — a
#: file that contradicts itself in the only dimension a reader is tracking. The
#: ledger picks an arc and walks it monotonically, which is what a trajectory
#: is.
#:
#: Each phrase completes the substrate's own sentence frame, "Patient reports
#: that symptoms are ___." Written to fit it, because the override replaces the
#: drawn value inside that sentence rather than rewriting the sentence.
TRAJECTORY_PHRASES: dict[str, tuple[str, ...]] = {
    "improving": (
        "improving steadily with conservative care",
        "continuing to improve, with increasing range of motion",
        "much improved and approaching maximum medical improvement",
    ),
    "plateau": (
        "stable, with residual pain at the injury site",
        "unchanged since the prior evaluation",
        "at a functional plateau despite continued treatment",
    ),
    "worsening": (
        "increased since the prior visit",
        "declining despite conservative measures",
        "substantially worse, warranting further diagnostic workup",
    ),
}

TRAJECTORIES: tuple[str, ...] = ("improving", "plateau", "worsening")

#: The treatment arcs a seed may state, and the ledger may publish.
TREATMENT_STATUSES: tuple[str, ...] = ("ongoing", "discharged", "gap", "never_treated")


#: Statutory windows, in days from the anchoring event, for the benefit
#: obligations this engine models.
#:
#: These are the deadlines a delay-and-penalty file is argued over. Days from
#: the date of injury unless noted; the citation is in the comment because a
#: number in a table with no authority behind it is a number somebody will
#: change.
BENEFIT_NOTICE_WINDOWS: dict[str, int] = {
    "claim_form_provided": 1,  # LC 5401(a) — one working day from notice of injury
    "first_td_payment": 14,  # LC 4650(a) — 14 days from knowledge of injury
    "delay_notice": 14,  # CCR 9812(f) — 14 days to notify of a delayed decision
    "claim_decision": 90,  # LC 5402(b) — presumption of compensability at 90 days
    "first_pd_payment": 14,  # LC 4650(b) — 14 days after the last TD payment
}

#: How much of each statutory window a given diligence typically consumes.
#:
#: The bands are the persona. ``attentive`` acts in the first part of the
#: window; ``ordinary`` uses most of it and can graze the edge; ``negligent``
#: routinely overruns, and the overrun is what becomes a
#: :class:`LateBenefitEvent`. Note ``ordinary`` reaches 1.0 but not past it —
#: an ordinary administrator is late only at the boundary, never grossly.
DILIGENCE_WINDOW_FRACTIONS: dict[str, tuple[float, float]] = {
    "attentive": (0.10, 0.55),
    "ordinary": (0.45, 1.00),
    "negligent": (0.70, 2.60),
}

DILIGENCES: tuple[str, ...] = ("attentive", "ordinary", "negligent")

#: Weights for deriving diligence when the seed does not state one.
#:
#: Deliberately not uniform. Most claims files are handled competently, and a
#: corpus where a third of administrators are negligent would train a reader to
#: expect penalties everywhere.
DILIGENCE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("attentive", 3),
    ("ordinary", 5),
    ("negligent", 2),
)

CADENCES: tuple[str, ...] = ("every_30_days", "event_driven", "sporadic")

CADENCE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("every_30_days", 3),
    ("event_driven", 4),
    ("sporadic", 3),
)

#: Every content type the adjuster-letter template can render.
#:
#: Named for the substrate's own private methods
#: (``AdjusterLetter._initial_acceptance`` and friends), because the override
#: recognises the draw by matching that exact list of bound methods. If the
#: substrate's list moves, the shim must stop firing loudly rather than
#: silently reverting to a free draw.
ADJUSTER_LETTER_TYPES: tuple[str, ...] = (
    "initial_acceptance",
    "pd_advance_offer",
    "settlement_discussion",
    "medical_records_request",
    "ur_decision",
)


def _weighted(rng: random.Random, weights: tuple[tuple[str, int], ...]) -> str:
    """Pick one weighted option off *rng*, without importing a helper."""
    total = sum(weight for _name, weight in weights)
    roll = rng.randrange(total)
    for name, weight in weights:
        roll -= weight
        if roll < 0:
            return name
    return weights[-1][0]


def resolve_adjuster_diligence(seed: CaseSeed) -> str:
    """How diligently this file's administrator behaved. **The** answer.

    Resolved once, like surgery and treatment status, because three consumers
    depend on it and must not disagree: the benefit-notice date draws, the
    correspondence density, and the penalty-petition gate. Unspecified derives
    on the ``facts:`` namespace, so it can never perturb a stream an existing
    document reads.
    """
    return seed.scenario.adjuster.diligence or _weighted(
        _rng(seed, "adjuster"), DILIGENCE_WEIGHTS
    )


def resolve_attorney_cadence(seed: CaseSeed) -> str:
    """How often counsel wrote to the client. **The** answer."""
    return seed.scenario.attorney.cadence or _weighted(_rng(seed, "attorney"), CADENCE_WEIGHTS)


def _derive_late_benefit_events(
    seed: CaseSeed, timeline: Any, diligence: str
) -> tuple[LateBenefitEvent, ...]:
    """Which statutory obligations this administrator missed, and by how long.

    Each window is drawn once against the diligence band. A draw past 1.0 of
    the window is late, and the overrun is recorded rather than recomputed —
    the penalty petition, the delay chain and the manifest all read the same
    number, so a file cannot allege 40 days of delay in one document and 12 in
    another.
    """
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    horizon = getattr(timeline, "resolution_date", None) or getattr(
        timeline, "application_filed_date", None
    )
    low, high = DILIGENCE_WINDOW_FRACTIONS[diligence]
    rng = _rng(seed, "benefits")

    events: list[LateBenefitEvent] = []
    for kind, window in BENEFIT_NOTICE_WINDOWS.items():
        due = onset + timedelta(days=window)
        actual_days = round(window * rng.uniform(low, high))
        actual = onset + timedelta(days=actual_days)
        if horizon is not None and actual > horizon:
            # A notice that would land past the file's own horizon is not a
            # late notice, it is a notice this case never reached. Clamping it
            # to the horizon would manufacture lateness out of a short runway.
            continue
        days_late = (actual - due).days
        if days_late > 0:
            events.append(
                LateBenefitEvent(
                    kind=kind, due_date=due, actual_date=actual, days_late=days_late
                )
            )
    return tuple(events)


def _derive_allowed_letter_types(seed: CaseSeed) -> frozenset[str]:
    """Which adjuster-letter contents this case's lifecycle can support.

    The substrate drew a letter type per document from all five, so a case with
    no UR dispute still received a UR-decision letter, and a file could hold
    three separate letters each announcing that the claim had been accepted for
    the first time.
    """
    # Always available: a records request fits any open claim, and an
    # acceptance letter exists on every file that was not denied outright.
    allowed = {"medical_records_request"}
    if seed.lifecycle.claim_response != "denied":
        allowed.add("initial_acceptance")
    if seed.lifecycle.ur_dispute.enabled:
        allowed.add("ur_decision")
    if seed.lifecycle.resolution.type != "none":
        allowed.add("settlement_discussion")
        allowed.add("pd_advance_offer")
    return frozenset(allowed)


def resolve_treatment_status(seed: CaseSeed) -> str:
    """The treatment arc this case tells. **The** answer, for every consumer.

    Resolved once for the same reason surgery is: the planner decides which
    documents exist from it, the ledger decides what they say, and two
    independent answers would let a case suppress its treating reports while
    its QME described ongoing care.

    Unspecified derives ``ongoing`` rather than drawing. There is nothing to
    supersede here — the substrate had no notion of a trajectory at all — so a
    draw would invent variance where v0.3.0 had none and move bytes on every
    existing seed. Derivation that changes nothing is the honest default.
    """
    return seed.scenario.treatment.status or "ongoing"


def resolve_has_surgery(seed: CaseSeed) -> bool:
    """Whether this case was operated on. **The** answer, for every consumer.

    Two things need it and must never disagree: the substrate's
    ``CaseParameters.has_surgery``, which gates whether operative documents are
    planned at all, and :class:`CaseFacts`, which decides what those documents
    say. When they were computed independently, ``scenario.surgery: performed``
    could produce a ledger asserting an operation with no operative record
    behind it, and ``none`` could leave an operation rendered that the ledger
    denied. So it is resolved once, here, and both read the result.

    The 35% coin is drawn **unconditionally**, even when the scenario already
    decides the answer. Skipping the draw would shift every later consumer of
    the ``clinical`` stream the moment a seed stated ``surgery:``, turning a
    content knob into a silent byte change across unrelated documents. Drawing
    and discarding costs nothing and keeps the stream where it was.

    A stated scenario beats the substrate's own exclusions too: a seed that
    explicitly asks for surgery on a psych or death claim gets it. Refusing
    silently would be the same defect this function exists to remove — a knob
    that does not reach.
    """
    return resolve_surgery_status(seed) == "performed"


def resolve_surgery_status(seed: CaseSeed) -> str:
    """The full four-state surgery answer behind :func:`resolve_has_surgery`.

    ``recommended`` and ``denied_by_ur`` are *not* operations, so they resolve
    ``has_surgery`` false and emit no operative document — but they are also not
    ``none``, because a procedure was named and the file has to say so.
    """
    parts = _body_parts(seed)
    coin = seed.rng("clinical").random() < 0.35

    if seed.scenario.surgery is not None:
        return seed.scenario.surgery

    # Unspecified: the substrate's original rule, term for term, including its
    # treatment of ``lc3208_3_psych`` as a psychiatric component.
    psych = any(part == "psyche" for part in parts) or (
        "lc3208_3_psych" in seed.lifecycle.doctrine_hooks
    )
    return "performed" if (seed.injury.type != "death" and not psych and coin) else "none"


def _derive_surgery(seed: CaseSeed, timeline: Any) -> SurgeryFact:
    """Ledger entry for the surgery, off the one shared resolution."""
    parts = _body_parts(seed)
    part = parts[0] if parts else "lumbar_spine"
    status = resolve_surgery_status(seed)

    if status == "none":
        return SurgeryFact(status="none")

    if status != "performed":
        # Proposed, not done: the CPT is what the RFA asked for, and there is no
        # operative date because there was no operation.
        code, description = _pick_cpt(seed, parts, part)
        return SurgeryFact(
            status=status,  # type: ignore[arg-type]
            body_part=part,
            cpt_code=code,
            cpt_description=description,
        )

    code, description = _pick_cpt(seed, parts, part)
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    return SurgeryFact(
        status="performed",
        body_part=part,
        cpt_code=code,
        cpt_description=description,
        date=onset + timedelta(days=210),
    )


def _pick_cpt(seed: CaseSeed, parts: list[str], primary: str) -> tuple[str, str]:
    """The operation this case had, drawn from the substrate's own pool.

    ``operative_record._select_surgical_cpts`` maps body parts to CPT
    categories and the template then picks from that list. Drawing the ledger's
    CPT from the *same* pool is what lets the operative record be pinned to it
    (ISC-93) instead of the two disagreeing — a ledger CPT the template's pool
    does not contain could only be forced by contradicting the template's own
    body-part logic.

    Falls back to the local table if the substrate is unavailable or the pool
    comes back empty, so the ledger always names some procedure.
    """
    try:
        operative = import_substrate("pdf_templates.medical.operative_record")
        pool = list(operative._select_surgical_cpts(parts) or ())
    except Exception:
        pool = []
    if pool:
        return tuple(_rng(seed, "surgery").choice(pool))  # type: ignore[return-value]
    return SURGERY_CPT_CODES.get(primary, _DEFAULT_CPT)


def _derive_providers(
    seed: CaseSeed, cast: Any, status: str = "ongoing"
) -> tuple[ProviderFact, ...]:
    """The providers a records subpoena can be answered by.

    Read off the substrate case's own ``prior_providers`` rather than invented
    here, because that is the list ``SubpoenaedRecords._select_provider``
    indexes into. A ledger naming different people than the template can render
    would make ISC-94's round-robin unverifiable — the attribution in the
    document would not match the attribution in the manifest.

    Falls back to the treating physician when the case has no prior providers,
    which is the same degradation the substrate template already applies.
    """
    if status == "never_treated":
        # Nobody treated, so there is nobody to subpoena. Publishing the
        # substrate's four prior providers here asserted a treating roster for a
        # case whose documents say the applicant never went — and a published
        # fact reads as a verified one.
        #
        # The renderer only sets ``provider_index`` when the roster is
        # non-empty, so subpoena attribution falls back to the substrate's own
        # treating-physician default rather than dividing by zero.
        return ()

    case = getattr(cast, "case", None)
    providers: list[ProviderFact] = []

    for physician in getattr(case, "prior_providers", None) or ():
        providers.append(
            ProviderFact(
                name=str(getattr(physician, "full_name", physician)),
                specialty=str(getattr(physician, "specialty", "") or "Medicine"),
                facility=str(getattr(physician, "facility", "") or ""),
            )
        )

    if not providers:
        treating = getattr(case, "treating_physician", None)
        providers.append(
            ProviderFact(
                name=str(getattr(treating, "full_name", treating) or "Treating Physician"),
                specialty=str(getattr(treating, "specialty", "") or "Medicine"),
                facility=str(getattr(treating, "facility", "") or ""),
            )
        )

    wanted = seed.scenario.treatment.providers
    if wanted is None:
        return tuple(providers)

    # A stated roster size trims or repeats the substrate's own people rather
    # than inventing new ones, because the round-robin indexes into the list the
    # template renders from. Repeating is honest for a small roster: two
    # subpoenas answered by the same custodian is a real filing pattern; a name
    # the template cannot produce is not.
    if wanted <= len(providers):
        return tuple(providers[:wanted])
    return tuple(providers[index % len(providers)] for index in range(wanted))


def _derive_visits(
    seed: CaseSeed, timeline: Any, surgery: SurgeryFact, status: str
) -> tuple[VisitFact, ...]:
    """A dated visit series consistent with the timeline it hangs off.

    The trajectory shapes the series rather than being narrated over the top of
    it: ``never_treated`` produces the initial visit and nothing after it,
    ``gap`` opens a seeded hole in the middle, and ``discharged`` ends the
    series at a final visit. A document that describes a gap the visit dates do
    not contain is the same class of incoherence as a QME citing an MRI nobody
    ordered.
    """
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    horizon = getattr(timeline, "resolution_date", None) or getattr(
        timeline, "application_filed_date", None
    )
    if status == "never_treated":
        # No visits at all. An earlier version kept an "initial" visit here on
        # the reasoning that somebody reported the injury — but a *reported*
        # injury is not a *treatment* visit, and publishing one made the ledger
        # assert a clinical encounter in a file whose whole premise is that
        # none happened. The first-report tier still emits its documents; it
        # just no longer claims a visit behind them.
        return ()

    visits: list[VisitFact] = [VisitFact(date=onset + timedelta(days=3), kind="initial")]

    step = 45
    gap_after = 1
    # A gap case has fewer visits, because that is what a gap is — and the
    # visits it does not have are the runway the gap occupies. Five follow-ups
    # at 45 days already consume more than some cases have between injury and
    # the horizon, so a gap appended to a full schedule falls past the horizon
    # and vanishes. The first version of this did exactly that and produced
    # gap-status cases with no gap in them.
    follow_ups = 2 if status == "gap" else 5

    gap_days = 0
    if status == "gap":
        # Drawn on the facts stream, so it can never perturb a draw an existing
        # document consumes, then clamped to what the timeline can hold. Short
        # cases get a shorter gap rather than none: a file that settles four
        # months after injury cannot contain a seven-month hole, and the
        # trajectory it *can* show is still a gap.
        wanted = _rng(seed, "treatment").choice((120, 150, 180, 210))
        room = (
            (horizon - onset).days - (3 + step * follow_ups) if horizon is not None else wanted
        )
        gap_days = max(0, min(wanted, room))

    offset = 0
    for position in range(1, follow_ups + 1):
        if status == "gap" and position == gap_after + 1:
            offset += gap_days
        moment = onset + timedelta(days=3 + step * position + offset)
        if horizon is not None and moment > horizon:
            break
        kind: Literal["initial", "follow_up", "post_operative", "final"] = "follow_up"
        if surgery.performed and surgery.date is not None and moment > surgery.date:
            kind = "post_operative"
        visits.append(VisitFact(date=moment, kind=kind))

    if status == "discharged" and len(visits) > 1:
        last = visits[-1]
        visits[-1] = VisitFact(date=last.date, kind="final")

    return tuple(visits)


def _derive_trajectory(seed: CaseSeed, status: str) -> str:
    """Which arc the treating reports walk.

    Drawn on the ``facts:`` namespace, never on a stream a document reads, and
    constrained by the trajectory the seed already implies: a discharged file
    improved its way to discharge, and a file built around a treatment gap is
    not a file where the applicant was steadily getting better.
    """
    if status == "discharged":
        return "improving"
    if status == "never_treated":
        return "plateau"
    if status == "gap":
        return _rng(seed, "trajectory").choice(("plateau", "worsening"))
    return _rng(seed, "trajectory").choice(TRAJECTORIES)


def derive_case_facts(seed: CaseSeed, timeline: Any, cast: Any = None) -> CaseFacts:
    """Decide, once, what clinically happened in this case.

    Args:
        seed: the case seed. ``scenario:`` is authoritative wherever it speaks.
        timeline: the built :class:`CaseTimeline`, so dates hang off the same
            spine the documents do.
        cast: the case cast, when one exists — supplies the treating physician
            so the provider list names people the file already knows.

    Returns:
        A frozen :class:`CaseFacts`. Derivation is pure: same seed, same facts.
    """
    status = resolve_treatment_status(seed)
    diligence = resolve_adjuster_diligence(seed)
    cadence = resolve_attorney_cadence(seed)
    late_events = _derive_late_benefit_events(seed, timeline, diligence)
    diagnostics = _derive_diagnostics(seed, timeline)
    surgery = _derive_surgery(seed, timeline)
    providers = _derive_providers(seed, cast, status)
    visits = _derive_visits(seed, timeline, surgery, status)
    trajectory = _derive_trajectory(seed, status)

    rng = _rng(seed, "rating")
    mmi = getattr(timeline, "resolution_date", None)
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    if mmi is None:
        mmi = onset + timedelta(days=300)
    wpi = rng.randint(3, 24) if seed.lifecycle.eval_type != "none" else None
    pd = min(100, int(wpi * 1.4)) if wpi is not None else None

    facts = CaseFacts(
        diagnostics=diagnostics,
        surgery=surgery,
        providers=providers,
        visits=visits,
        treatment_status=status,  # type: ignore[arg-type]
        trajectory=trajectory,  # type: ignore[arg-type]
        adjuster_diligence=diligence,  # type: ignore[arg-type]
        attorney_cadence=cadence,  # type: ignore[arg-type]
        late_benefit_events=late_events,
        adjuster_letter_types_allowed=_derive_allowed_letter_types(seed),
        mmi_date=mmi,
        wpi=wpi,
        pd=pd,
    )
    log.debug(
        "case_facts.derived",
        case_id=seed.case_id,
        performed=len(facts.performed_diagnostics),
        absent=len(facts.absent_diagnostics),
        surgery=facts.surgery.status,
        providers=len(facts.providers),
    )
    return facts


def facts_manifest_block(facts: CaseFacts) -> dict[str, Any]:
    """The ``caseFacts`` object a manifest publishes.

    Published so the ledger is auditable from the output alone: a reader with
    the manifest and the documents can check every coherence claim this package
    makes without rerunning the generator.

    Restricted to :data:`GOVERNED_LEDGER_FIELDS`, which is what keeps that
    sentence true. A field no template renders cannot be checked against the
    documents, so publishing it would let the manifest assert things the case
    file contradicts — the exact failure the ledger was built to remove.
    """
    # One entry per modality, not per study. Body parts are not published (no
    # template renders a per-study body part), and without them two entries for
    # the same modality with opposite ``performed`` flags would read as a
    # contradiction rather than as "scanned one region, not the other". Collapse
    # to the claim the documents actually make: performed *somewhere* means the
    # QME may cite it, absent everywhere means it must be recorded as absent.
    performed_modalities = {f.modality for f in facts.diagnostics if f.performed}
    diagnostics = [
        {
            "modality": modality,
            "display": MODALITY_DISPLAY[modality],
            "performed": modality in performed_modalities,
        }
        for modality in MODALITIES
        if any(f.modality == modality for f in facts.diagnostics)
    ]

    return {
        # Published because a document honours it: the LC 5814 petition exists
        # if and only if ``lateBenefitEvents`` is non-zero, so a reader holding
        # the manifest can check the pleading against the fact behind it. The
        # day counts are recoverable from the notice dates in the file.
        #
        # ``adjuster_diligence`` is deliberately *not* here, and that took a
        # review to see. It is a persona *input*: no rendered document reflects
        # it, so a reader cannot check it against anything.
        #
        # ``letterTypesAllowed`` and ``attorney.cadence`` were withheld under
        # that same rule and have now earned their place, which is the rule
        # working rather than an exception to it. The letter sequence renders
        # from the allowed set (ISC-121), and the client letters are dated by
        # the cadence (ISC-123/124) — both are checkable against the documents
        # in the folder, which is the whole test for publication.
        "adjuster": {
            "lateBenefitEvents": len(facts.late_benefit_events),
            "maxDaysLate": (
                max(event.days_late for event in facts.late_benefit_events)
                if facts.late_benefit_events
                else 0
            ),
            "letterTypesAllowed": sorted(facts.adjuster_letter_types_allowed),
        },
        "attorney": {"cadence": facts.attorney_cadence},
        "treatment": {
            "status": facts.treatment_status,
            "trajectory": facts.trajectory,
            "dischargeDate": (
                facts.discharge_date.isoformat() if facts.discharge_date else None
            ),
            "gapStart": facts.treatment_gap[0].isoformat() if facts.treatment_gap else None,
            "gapEnd": facts.treatment_gap[1].isoformat() if facts.treatment_gap else None,
        },
        "diagnostics": diagnostics,
        "surgery": {
            "status": facts.surgery.status,
            "cptCode": facts.surgery.cpt_code,
            "cptDescription": facts.surgery.cpt_description,
        },
        "providers": [
            {"name": p.name, "specialty": p.specialty, "facility": p.facility}
            for p in facts.providers
        ],
    }


#: The only ledger fields that may be published, and the template that renders each.
#:
#: A published fact is a promise the documents keep. Every field below is read
#: by a registry template and appears in rendered text, so a reader holding the
#: manifest and the documents can check one against the other. Fields the ledger
#: derives but nothing renders — ``wpi``, ``pd``, ``mmi_date``, ``visits``, and
#: the per-fact body parts and dates — stay on the model for later phases and
#: out of the output, because publishing them would let the manifest state
#: things its own documents contradict.
GOVERNED_LEDGER_FIELDS: dict[str, tuple[str, ...]] = {
    "adjuster": ("lateBenefitEvents", "maxDaysLate", "letterTypesAllowed"),
    "attorney": ("cadence",),
    "treatment": ("status", "trajectory", "dischargeDate", "gapStart", "gapEnd"),
    "diagnostics": ("modality", "display", "performed"),
    "surgery": ("status", "cptCode", "cptDescription"),
    "providers": ("name", "specialty", "facility"),
}


__all__ = [
    "ADJUSTER_LETTER_TYPES",
    "BENEFIT_NOTICE_WINDOWS",
    "CADENCES",
    "CADENCE_WEIGHTS",
    "DILIGENCES",
    "DILIGENCE_WEIGHTS",
    "DILIGENCE_WINDOW_FRACTIONS",
    "GOVERNED_LEDGER_FIELDS",
    "IMAGING_MODALITIES",
    "MODALITIES",
    "MODALITY_DISPLAY",
    "SUBSTRATE_STATUS_PHRASES",
    "SURGERY_CPT_CODES",
    "TRAJECTORIES",
    "TRAJECTORY_PHRASES",
    "TREATMENT_STATUSES",
    "CaseFacts",
    "DiagnosticFact",
    "LateBenefitEvent",
    "Modality",
    "ProviderFact",
    "SurgeryFact",
    "VisitFact",
    "derive_case_facts",
    "facts_manifest_block",
    "resolve_adjuster_diligence",
    "resolve_attorney_cadence",
    "resolve_surgery_status",
    "resolve_treatment_status",
]
