"""Rule pack #1 — a surgical procedure code that contradicts the injured anatomy.

A case whose record asserts an operation on anatomy nobody claims was injured is
incoherent: a wrist-injury file whose operative record bills 29827, an arthroscopic
rotator cuff repair. The contradiction is visible from the supplied record alone,
which is why it belongs here and not in a legal-authority adapter.

Independence of the knowledge table
-----------------------------------
:data:`OPERATIVE_CPT_ANATOMY` and :data:`BODY_PART_ALIASES` are maintained **by hand,
in this package**, and are deliberately not imported from — or generated from — any
case generator's pools. The analyzer is a product component: its medical knowledge has
to stand on its own in front of a real case file, whose procedure codes were chosen by
a surgeon rather than by a seeded draw. Deriving the table from a generator would also
make every check a tautology — the two would agree by construction and agree just as
happily when both were wrong.

Content overlap with a generator's tables is expected and fine: 29827 is a shoulder
operation as a matter of medical fact, and two honest tables must say so. **Shared
provenance is what is forbidden, not shared content.**

Why this reads such a narrow surface
------------------------------------
Only facts whose own field/path vocabulary marks them as an *asserted operation* are
read for procedure codes — ``caseFacts.surgery.cptCode`` and its kin. A CPT appearing
in a billing record, a treating-physician report, or a utilization-review line is
**not** an operation assertion, and is ignored.

That restraint is load-bearing rather than cautious. Those document families sample
procedure codes independently of the injury, so a lumbar case's billing record may
legitimately name a shoulder code. A detector that read every CPT in the ledger as an
asserted operation would fire on a large share of clean cases — and precision on clean
corpora is the measure this detector is scored against. Nor is a five-digit value in
any field named ``*Code`` a procedure code: ``postalCode`` and ``authorizationCode``
sit happily beside an operation, so a bare number needs its field to name CPT outright
or pair "code" with procedure vocabulary.

The rule throughout is that silence is the default and a finding requires an
affirmative contradiction:

* an operation is asserted on a surface that claims to describe an operation, **and**
* the table knows what anatomy that code implies, **and**
* at least one injured body part is affirmatively claimed, **and**
* no claimed injured part is compatible with the code's anatomy.

Anything less — an unknown code, an uncoded operation, a nonlocalizable unlisted code,
an injection, an unrecognized body part, an unsegmented "back" against a cervical code
— yields nothing at all. An unknown code raises no note either: one note per
unclassified code would put noise on every case, and the table's real gap signal is
recall measured over a scored corpus, not a per-case remark.

A prior operation is likewise not this case's operation. ``priorCptCode`` and
``medicalHistory.priorSurgeries[]`` describe anatomy that is *expected* to differ, and a
history ledger makes them routine. That is classified by **namespace**, not by token:
``priorAuthorization`` and ``historyAndPhysical`` read historical word by word yet hold
current care, and a flat token scan discarded exactly the operations this pack checks.
See :data:`HISTORICAL_NAMESPACES` and :data:`CURRENT_CARE_NAMESPACES`.

Restraint cuts the other way too, and that failure mode is quieter. A body part merely
*mentioned* is not one that was injured, so injured anatomy is read only from the
enumerated path shapes in :data:`INJURED_PART_PATH_SHAPES`. A recognized leaf name in
the wrong namespace does not qualify — ``scenario.diagnostics[].body_part``,
``exam.body_parts[].part`` and ``medicalHistory.priorInjury.bodyPart`` all name anatomy
without claiming this case injured it.

Both selectors are closed worlds rather than vocabulary rules, and that is deliberate.
Three review rounds redrew the same boundary by adding and subtracting tokens, each time
leaving another namespace on the wrong side of it. The archive grammar is knowable, so
it is enumerated; an unrecognized shape costs a finding rather than inventing one, which
is the trade this package already makes for unknown procedure codes.

Free-form prose is not read for anatomy at all, in either direction, and that is a
refusal rather than a gap. Deciding whether "No evidence of injury to shoulder" asserts
or denies the shoulder means resolving negation scope across clauses, and no proximity
rule handles both "wrist sprain; no shoulder injury" and its reverse. Structured
body-part fields are always materialized in this corpus, so the parsing problem is
declined outright instead of half-solved.

Maintenance contract
--------------------
* Every entry is a five-digit CPT code in exactly one class — operative (implies one
  anatomical region), non-operative (an injection or diagnostic study, never an
  operation), localizable unlisted (names a body area but not a procedure), or
  nonlocalizable unlisted (names neither).
* Adding a code means adding it to exactly one table; disjointness, table shape, and
  region reachability are asserted by the suite, so a typo cannot sit here silently
  matching nothing.
* Widening a region alias is the cheap fix for a false positive; deleting an operative
  entry is the cheap fix for a wrong one. Prefer both to loosening
  :func:`contradicts`, which is what keeps precision legible.
* This table is not a billing authority and must never be used to price, validate, or
  substantiate a claim. It exists to answer one question: does this code's anatomy
  contradict this case's anatomy.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from types import MappingProxyType

from adjudica_case_analysis_engine.models import Fact, Finding
from adjudica_case_analysis_engine.rules.base import Rule, RuleContext
from adjudica_case_analysis_engine.text import (
    canonical_field,
    split_words,
    tokens,
    unescape_segment,
)

#: The finding code this pack owns.
ANATOMICAL_CONTRADICTION = "anatomical_contradiction"

#: Surgical CPT code -> the anatomical region the operation is performed on.
#:
#: Hand-maintained; see the module docstring for why it is independent of any
#: generator's pools. Grouped by region so a reviewer can check a row against the
#: rest of its group rather than against the whole table.
OPERATIVE_CPT_ANATOMY: Mapping[str, str] = MappingProxyType(
    {
        # Cervical spine.
        "22551": "cervical_spine",  # Anterior cervical discectomy with fusion, below C2
        "22554": "cervical_spine",  # Arthrodesis, anterior interbody, cervical below C2
        "63020": "cervical_spine",  # Laminotomy with decompression, cervical, one interspace
        "63075": "cervical_spine",  # Discectomy, anterior, cervical, single interspace
        "63081": "cervical_spine",  # Vertebral corpectomy, anterior, cervical
        # Thoracic spine.
        "22556": "thoracic_spine",  # Arthrodesis, anterior interbody, thoracic
        "63046": "thoracic_spine",  # Laminectomy/facetectomy/foraminotomy, thoracic
        "63055": "thoracic_spine",  # Transpedicular decompression, thoracic
        # Lumbar spine.
        "22558": "lumbar_spine",  # Arthrodesis, anterior interbody, lumbar
        "22612": "lumbar_spine",  # Arthrodesis, posterolateral, lumbar
        "22630": "lumbar_spine",  # Arthrodesis, posterior interbody, lumbar
        "63030": "lumbar_spine",  # Laminotomy with discectomy, lumbar, one interspace
        "63042": "lumbar_spine",  # Laminotomy, re-exploration, lumbar
        "63047": "lumbar_spine",  # Laminectomy/facetectomy/foraminotomy, lumbar
        # Shoulder.
        "23412": "shoulder",  # Repair of ruptured musculotendinous cuff, open, chronic
        "23430": "shoulder",  # Tenodesis of long tendon of biceps
        "23472": "shoulder",  # Arthroplasty, glenohumeral joint, total shoulder
        "29806": "shoulder",  # Arthroscopy, shoulder, capsulorrhaphy
        "29826": "shoulder",  # Arthroscopy, shoulder, subacromial decompression
        "29827": "shoulder",  # Arthroscopy, shoulder, with rotator cuff repair
        # Elbow.
        "24342": "elbow",  # Reinsertion of ruptured biceps or triceps tendon, distal
        "24357": "elbow",  # Tenotomy, elbow, lateral or medial, percutaneous
        "24358": "elbow",  # Tenotomy, elbow, debridement, open
        "64718": "elbow",  # Neuroplasty/transposition, ulnar nerve at elbow
        # Wrist.
        "25000": "wrist",  # Incision, extensor tendon sheath, wrist
        "25111": "wrist",  # Excision of ganglion, wrist, primary
        "64721": "wrist",  # Neuroplasty/transposition, median nerve at carpal tunnel
        # Hand.
        "26055": "hand",  # Tendon sheath incision, trigger finger release
        "26123": "hand",  # Fasciectomy, partial palmar, with release
        "26160": "hand",  # Excision of lesion of tendon sheath or joint capsule, hand
        # Hip.
        "27125": "hip",  # Hemiarthroplasty, hip, femoral
        "27130": "hip",  # Arthroplasty, acetabular and femoral head replacement
        "27132": "hip",  # Conversion of previous hip surgery to total hip arthroplasty
        "29862": "hip",  # Arthroscopy, hip, with debridement
        # Knee.
        "27446": "knee",  # Arthroplasty, knee, unicompartmental
        "27447": "knee",  # Arthroplasty, knee, condyle and plateau, total knee
        "29880": "knee",  # Arthroscopy, knee, medial AND lateral meniscectomy
        "29881": "knee",  # Arthroscopy, knee, medial OR lateral meniscectomy
        "29888": "knee",  # Arthroscopically aided cruciate ligament repair
        # Ankle.
        "27650": "ankle",  # Repair, primary, open, ruptured Achilles tendon
        "27792": "ankle",  # Open treatment of distal fibular fracture
        "27822": "ankle",  # Open treatment of trimalleolar ankle fracture
        "29891": "ankle",  # Arthroscopy, ankle, excision of osteochondral defect
        # Foot.
        "28060": "foot",  # Fasciectomy, plantar fascia, partial
        "28110": "foot",  # Ostectomy, partial excision, fifth metatarsal head
        "28285": "foot",  # Correction, hammertoe
        "28296": "foot",  # Correction, hallux valgus, with distal metatarsal osteotomy
    }
)

#: Codes that are injections or diagnostic studies rather than operations.
#:
#: Listed so they are affirmatively excluded rather than falling through as merely
#: unknown. A diagnostic block or an epidural injection at a level adjacent to the
#: injury is ordinary care, so treating one as an operation would manufacture
#: contradictions out of correct records.
NON_OPERATIVE_CPT_CODES: frozenset[str] = frozenset(
    {
        "20550",  # Injection, tendon sheath or ligament
        "20551",  # Injection, tendon origin or insertion
        "20605",  # Arthrocentesis, intermediate joint
        "20610",  # Arthrocentesis, major joint
        "62321",  # Epidural injection with imaging, cervical or thoracic
        "62323",  # Epidural injection with imaging, lumbar or sacral
        "64483",  # Transforaminal epidural injection, lumbar or sacral, single level
        "64484",  # Transforaminal epidural injection, each additional level
        "64490",  # Paravertebral facet joint injection, cervical or thoracic
        "64493",  # Paravertebral facet joint injection, lumbar or sacral
        "72148",  # MRI, lumbar spine, without contrast
        "73721",  # MRI, any joint of lower extremity, without contrast
        "95886",  # Needle electromyography, complete
    }
)

#: Unlisted-procedure codes that still name a body area, mapped to every region they
#: are compatible with.
#:
#: An unlisted code says the *operation* was not codeable — it does not say the surgeon
#: forgot where they were. "Unlisted procedure, shoulder" is a claim about the shoulder,
#: so a wrist case reporting one is as incoherent as one reporting 29827. The region
#: sets are deliberately permissive where the code's own body area spans joints (a femur
#: code is compatible with hip and knee), because widening a set only withholds findings.
LOCALIZABLE_UNLISTED_CPT_ANATOMY: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        # Unlisted procedure, spine — segment unnamed, so every segment is compatible.
        "22899": frozenset({"spine", "cervical_spine", "thoracic_spine", "lumbar_spine"}),
        "23929": frozenset({"shoulder"}),  # Unlisted procedure, shoulder
        "24999": frozenset({"elbow", "shoulder"}),  # Unlisted procedure, humerus or elbow
        "26989": frozenset({"hand"}),  # Unlisted procedure, hands or fingers
        "27299": frozenset({"hip"}),  # Unlisted procedure, pelvis or hip joint
        "27599": frozenset({"knee", "hip"}),  # Unlisted procedure, femur or knee
        "27899": frozenset({"ankle", "knee"}),  # Unlisted procedure, leg or ankle
        "28899": frozenset({"foot"}),  # Unlisted procedure, foot or toes
    }
)

#: Unlisted-procedure codes that name no body area at all, and so contradict nothing.
NONLOCALIZABLE_UNLISTED_CPT_CODES: frozenset[str] = frozenset(
    {
        "29999",  # Unlisted procedure, arthroscopy — any joint
        "64999",  # Unlisted procedure, nervous system — any nerve
    }
)

#: Every unlisted-procedure code, both halves.
UNLISTED_CPT_CODES: frozenset[str] = (
    frozenset(LOCALIZABLE_UNLISTED_CPT_ANATOMY) | NONLOCALIZABLE_UNLISTED_CPT_CODES
)

#: Body-part phrase -> anatomical region, matched on whole word tokens.
#:
#: Bare "spine" and "back" are mapped to the unsegmented :data:`_SPINE` region rather
#: than guessed at: a record that names no segment has not named a wrong one.
BODY_PART_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        # Spine, by segment.
        "cervical spine": "cervical_spine",
        "cervical": "cervical_spine",
        "neck": "cervical_spine",
        "thoracic spine": "thoracic_spine",
        "thoracic": "thoracic_spine",
        "mid back": "thoracic_spine",
        "middle back": "thoracic_spine",
        "upper back": "thoracic_spine",
        "lumbar spine": "lumbar_spine",
        "lumbosacral spine": "lumbar_spine",
        "lumbosacral": "lumbar_spine",
        "lumbar": "lumbar_spine",
        "low back": "lumbar_spine",
        "lower back": "lumbar_spine",
        "spine": "spine",
        "back": "spine",
        # Upper extremity.
        "rotator cuff": "shoulder",
        "shoulder": "shoulder",
        "shoulders": "shoulder",
        "elbow": "elbow",
        "elbows": "elbow",
        "carpal tunnel": "wrist",
        "wrist": "wrist",
        "wrists": "wrist",
        "hand": "hand",
        "hands": "hand",
        "finger": "hand",
        "fingers": "hand",
        "thumb": "hand",
        # Lower extremity.
        "hip": "hip",
        "hips": "hip",
        "knee": "knee",
        "knees": "knee",
        "achilles": "ankle",
        "ankle": "ankle",
        "ankles": "ankle",
        "plantar fascia": "foot",
        "heel": "foot",
        "foot": "foot",
        "feet": "foot",
        "toe": "foot",
        "toes": "foot",
    }
)

#: The unsegmented spine, compatible with every named segment.
_SPINE = "spine"
_SPINE_SEGMENTS = frozenset({"cervical_spine", "thoracic_spine", "lumbar_spine"})

#: Vocabulary marking a fact as part of an operation assertion.
#:
#: "procedure" is deliberately absent: `procedureCode` is ordinary billing vocabulary,
#: and admitting it would pull every billed line into the operative surface.
_OPERATION_MARKERS = frozenset({"surgery", "surgeries", "surgical", "operation", "operative"})

#: The closed world of path shapes that assert *this case's* injured anatomy.
#:
#: A shape is a normalized path suffix: list indices collapse to ``[]`` and every segment
#: is canonicalized, so ``$.case.injury.body_parts[0].part`` matches
#: ``injury.body_parts[].part``. Matching a suffix tolerates the wrappers real archives
#: add (``case.``, ``caseFacts.``) while keeping the namespace itself exact.
#:
#: **A leaf name alone never qualifies**, and that is the whole point. The generator seed
#: carries ``scenario.diagnostics[].body_part`` — a diagnostic scoped to a region,
#: including regions deliberately *not* imaged; an examination carries
#: ``exam.body_parts[].part``; a history block carries
#: ``medicalHistory.priorInjury.bodyPart``. Every one names anatomy without claiming this
#: case injured it, and admitting any one silently clears a contradictory operation.
#:
#: Enumerating is affordable because the archive grammar is knowable, and an unrecognized
#: shape costs a finding rather than inventing one — which is this package's standing
#: trade everywhere else.
INJURED_PART_PATH_SHAPES: frozenset[str] = frozenset(
    {
        # The generator seed's injury block (wc_caseload_engine InjurySpec.body_parts).
        "injury.body_parts[].part",
        "injury.body_parts[]",
        "injury.body_parts",
        # Document-intake extraction shapes.
        "injury.body_part",
        "injury.site",
        "injury.sites[]",
        "injuries[].body_part",
        "injuries[].body_parts[]",
        # Self-describing names, which carry the namespace inside the field itself.
        "injured_part",
        "injured_parts",
        "injured_parts[]",
        "injured_body_part",
        "injured_body_parts",
        "injured_body_parts[]",
        "injury_body_part",
        "injury_body_parts",
        "injury_body_parts[]",
        "injury_site",
        "injury_sites",
        "injury_sites[]",
        "injured_site",
        "body_part_injured",
        "body_parts_injured",
    }
)

#: Namespaces whose contents describe the patient's past rather than this case.
HISTORICAL_NAMESPACES: frozenset[str] = frozenset(
    {
        "medical_history",
        "surgical_history",
        "past_medical_history",
        "prior_surgeries",
        "prior_surgery",
        "previous_surgeries",
        "past_surgeries",
        "prior_injury",
        "prior_injuries",
        "prior_treatment",
        "history",
    }
)

#: Namespaces that read as historical word by word but hold current-care records.
#:
#: ``priorAuthorization`` is a request to authorize an operation *now*, and
#: ``historyAndPhysical`` is the admission note for the current episode. A flat token
#: scan discarded both, silently dropping exactly the operations this pack exists to
#: check — so classification is by whole namespace, and current care wins where both
#: appear.
CURRENT_CARE_NAMESPACES: frozenset[str] = frozenset(
    {
        "prior_authorization",
        "prior_authorizations",
        "history_and_physical",
        "current_surgery",
        "current_treatment",
        "current_care",
        "current_episode",
    }
)

#: Field names marking the code itself as a record of a past operation.
HISTORICAL_CODE_FIELDS: frozenset[str] = frozenset(
    {
        "prior_cpt_code",
        "previous_cpt_code",
        "past_cpt_code",
        "prior_procedure_code",
        "previous_procedure_code",
        "prior_surgical_code",
    }
)

#: Field vocabulary that makes a bare five-digit value readable as a procedure code.
#:
#: A bare "code" is not enough. ``postalCode``, ``authorizationCode``, ``diagnosisCode``
#: and ``facilityCode`` all hold five-digit values and all sit happily beside an
#: operation, so the field has to name CPT outright or pair "code" with procedure
#: vocabulary.
_CPT_FIELD_MARKERS = frozenset({"cpt"})
_CODE_NOUNS = frozenset({"code", "codes"})
_PROCEDURE_QUALIFIERS = frozenset(
    {"procedure", "procedures", "surgical", "surgery", "operation", "operative"}
)

_SEPARATORS = re.compile(r"[^a-z0-9]+")
_BARE_CODE = re.compile(r"\d{5}")
#: A code named as a code inside prose — the literal "CPT" is the affirmative marker.
_CODE_IN_TEXT = re.compile(r"\bCPT\s*#?\s*:?\s*(\d{5})\b", re.IGNORECASE)


def _words(value: str) -> tuple[str, ...]:
    """Ordered lowercase word tokens, splitting camelCase the way the ledger does."""
    return tuple(part for part in _SEPARATORS.split(split_words(value).lower()) if part)


#: Alias phrases longest first, so "low back" is consumed before bare "back" can match.
_ALIAS_WORDS: tuple[tuple[tuple[str, ...], str], ...] = tuple(
    sorted(
        ((_words(phrase), region) for phrase, region in BODY_PART_ALIASES.items()),
        key=lambda entry: (-len(entry[0]), entry[0]),
    )
)


def regions_named_by(text: str) -> frozenset[str]:
    """Every anatomical region a string names.

    Purely lexical: it reports what the string mentions, never whether the string
    claims it. Whether a mention is an injury claim is decided by *which field* the
    string came from — see :data:`_INJURED_PART_FIELDS` — because deciding it from the
    sentence would mean resolving negation scope across clauses.

    Matching is on whole word-token sequences, never raw substrings, so "background"
    is not a back and "secondhand" is not a hand. The longest phrase wins and consumes
    its words: "low back" is the lumbar spine, and must not also register as the
    unsegmented spine, or a wrong-segment contradiction would be masked.
    """
    words = _words(text)
    if not words:
        return frozenset()
    claimed = [False] * len(words)
    found: set[str] = set()
    for phrase, region in _ALIAS_WORDS:
        span = len(phrase)
        for start in range(len(words) - span + 1):
            if any(claimed[start : start + span]):
                continue
            if words[start : start + span] == phrase:
                found.add(region)
                claimed[start : start + span] = [True] * span
    return frozenset(found)


def _compatible(procedure_region: str, injured_region: str) -> bool:
    """Whether an operation on one region is consistent with an injury to another."""
    if procedure_region == injured_region:
        return True
    pair = {procedure_region, injured_region}
    return _SPINE in pair and bool(pair & _SPINE_SEGMENTS)


def compatible_regions(code: str) -> frozenset[str]:
    """Every region a code is consistent with, or empty when it names no anatomy.

    An operative code names exactly one region. A localizable unlisted code names a
    body area without naming the operation — still a claim about where the surgeon was.
    Everything else — unknown codes, injections, and unlisted codes that name no area —
    returns empty and can contradict nothing.
    """
    region = OPERATIVE_CPT_ANATOMY.get(code)
    if region is not None:
        return frozenset({region})
    return LOCALIZABLE_UNLISTED_CPT_ANATOMY.get(code, frozenset())


def contradicts(code: str, injured_regions: frozenset[str]) -> bool:
    """Whether this table affirmatively places ``code`` outside every injured region.

    False for everything the table cannot speak to: an unknown code, an injection, a
    nonlocalizable unlisted procedure, or a case with no recognized injured part.
    Unknown is not wrong.
    """
    candidates = compatible_regions(code)
    if not candidates or not injured_regions:
        return False
    return not any(
        _compatible(candidate, injured) for candidate in candidates for injured in injured_regions
    )


def _is_code_field(fact: Fact) -> bool:
    """Whether this field's own name says its value is a procedure code."""
    words = tokens(fact.field)
    if words & _CPT_FIELD_MARKERS:
        return True
    return bool(words & _CODE_NOUNS and words & _PROCEDURE_QUALIFIERS)


def _codes_asserted_by(fact: Fact) -> tuple[str, ...]:
    """Procedure codes this fact states, with no guessing from bare digits.

    A five-digit value counts only in a field that names itself a code; anywhere else
    it needs the literal "CPT" beside it. Claim numbers and postal codes are five
    digits too, and "N/A" is a CPT-shaped string that is not a code.
    """
    value = fact.value
    if isinstance(value, bool):
        return ()
    if isinstance(value, int):
        text = str(value)
        return (text,) if _is_code_field(fact) and _BARE_CODE.fullmatch(text) else ()
    if not isinstance(value, str):
        return ()
    stripped = value.strip()
    if _is_code_field(fact) and _BARE_CODE.fullmatch(stripped):
        return (stripped,)
    return tuple(dict.fromkeys(match.group(1) for match in _CODE_IN_TEXT.finditer(value)))


def _declares_uncoded(context: RuleContext, fact: Fact) -> bool:
    """Whether the record says outright that its operation carries no code.

    Post-AJC-55 corpora record uncoded operations explicitly. Honouring that flag
    means a leftover or historical code beside it is never read as this operation's.
    """
    for sibling in context.record_of(fact):
        if "uncoded" not in tokens(sibling.field):
            continue
        value = sibling.value
        if value is True or (isinstance(value, str) and value.strip().lower() == "true"):
            return True
    return False


def _shape_segments(source_path: str) -> tuple[str, ...]:
    """A path reduced to its shape: indices collapse to ``[]``, segments canonicalize."""
    segments: list[str] = []
    for raw in source_path.split("."):
        if not raw or raw == "$":
            continue
        name, bracket, _ = raw.partition("[")
        canonical = canonical_field(unescape_segment(name))
        segments.append(f"{canonical}[]" if bracket else canonical)
    return tuple(segments)


#: :data:`INJURED_PART_PATH_SHAPES`, pre-split for suffix comparison.
_INJURED_PART_SHAPES: tuple[tuple[str, ...], ...] = tuple(
    tuple(shape.split(".")) for shape in INJURED_PART_PATH_SHAPES
)


def _names_injured_anatomy(fact: Fact) -> bool:
    """Whether this fact sits at a shape that asserts this case's injured anatomy."""
    if fact.scope == "claim":
        # A promoted claim names its own field; its path is the container, not a shape.
        return (canonical_field(fact.field),) in _INJURED_PART_SHAPES
    segments = _shape_segments(fact.source_path)
    return any(
        len(shape) <= len(segments) and segments[len(segments) - len(shape) :] == shape
        for shape in _INJURED_PART_SHAPES
    )


def _is_historical(fact: Fact) -> bool:
    """Whether a fact records a past operation rather than this case's.

    Classified by whole namespace rather than by token, because ``priorAuthorization``
    and ``historyAndPhysical`` are current-care records whose names read historical word
    by word. Current care wins wherever both classifications appear.
    """
    if canonical_field(fact.field) in HISTORICAL_CODE_FIELDS:
        return True
    namespaces = {segment.removesuffix("[]") for segment in _shape_segments(fact.source_path)}
    if namespaces & CURRENT_CARE_NAMESPACES:
        return False
    return bool(namespaces & HISTORICAL_NAMESPACES)


def _injured_regions(context: RuleContext) -> tuple[frozenset[str], tuple[str, ...]]:
    """Recognized injured regions, and the facts that claimed them.

    Facts on the operation surface are excluded even when they name a body part:
    ``surgery.bodyPart`` records the part that was operated on, chosen together with
    the code, so reading it back as an injury would make the check answer itself.
    """
    regions: set[str] = set()
    cited: list[str] = []
    for fact in context.facts:
        if not isinstance(fact.value, str) or not _names_injured_anatomy(fact):
            continue
        if context.words(fact) & _OPERATION_MARKERS:
            continue
        claimed = regions_named_by(fact.value)
        if claimed:
            regions |= claimed
            cited.append(fact.id)
    return frozenset(regions), tuple(cited)


def _asserted_operations(context: RuleContext) -> Iterator[tuple[Fact, str]]:
    """Every procedure code asserted as this case's operation, in ledger order."""
    for fact in context.matching(_OPERATION_MARKERS):
        if _is_historical(fact) or _declares_uncoded(context, fact):
            continue
        for code in _codes_asserted_by(fact):
            yield fact, code


def _label(region: str) -> str:
    return region.replace("_", " ")


def _procedure_label(code: str) -> str:
    """How to name a code's anatomy in a message.

    A code compatible with the whole spine is reported as the spine rather than as a
    list of every segment it could be.
    """
    regions = compatible_regions(code)
    if _SPINE in regions:
        regions = frozenset({_SPINE})
    return ", ".join(sorted(_label(region) for region in regions))


def detect(context: RuleContext) -> Iterator[Finding]:
    """Report operations this record places on anatomy it never claims was injured."""
    injured, cited = _injured_regions(context)
    if not injured:
        return
    injured_label = ", ".join(sorted(_label(region) for region in injured))
    for fact, code in _asserted_operations(context):
        if not contradicts(code, injured):
            continue
        yield Finding(
            code=ANATOMICAL_CONTRADICTION,
            severity="error",
            message=(
                f"{fact.field} asserts CPT {code}, an operation on the "
                f"{_procedure_label(code)}, in {context.source_of(fact)}; "
                f"the recorded injured body part(s) are {injured_label}. "
                "Resolve against source evidence."
            ),
            # Sorted so no ledger ordering can change the emitted contract's bytes.
            fact_ids=(fact.id, *sorted(cited)),
            category="medical",
        )


#: The registered pack. Detector class #2 is a sibling module and one more tuple entry.
RULE = Rule(
    name="anatomical_coherence",
    codes=frozenset({ANATOMICAL_CONTRADICTION}),
    detect=detect,
)
