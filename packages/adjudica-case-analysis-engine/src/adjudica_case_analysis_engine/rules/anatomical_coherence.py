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

Restraint cuts the other way too, and the second failure mode is quieter. A body part
merely *mentioned* is not one that was injured: ``injury.mechanism`` reading "lifting
to shoulder height", or a diagnosis reading "no shoulder injury", would enter the
injured set and clear a shoulder operation on a wrist case. Anatomy is therefore read
from fields whose own names claim to say what was injured, and denials near a mention
disqualify it. A false negative is invisible where a false positive announces itself.

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
from adjudica_case_analysis_engine.text import split_words, tokens

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

#: Leaf-field vocabulary naming an injured body part outright.
#:
#: Selection is on the field's own name, not on any ancestor: an ``injury`` ancestor
#: covers ``injury.mechanism`` too, and "lifting to shoulder height" would then enter
#: the injured set and clear a shoulder operation on a wrist case. Masking a real
#: contradiction is the costlier failure, because a false negative is invisible.
_BODY_PART_FIELD_MARKERS = frozenset(
    {"body", "part", "parts", "site", "sites", "region", "regions", "injured"}
)

#: Leaf-field vocabulary for clinical prose that may name anatomy affirmatively.
_CLINICAL_PROSE_FIELD_MARKERS = frozenset(
    {"diagnosis", "diagnoses", "complaint", "complaints", "condition", "conditions"}
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

#: Words that make a nearby anatomical mention a denial rather than an assertion.
_NEGATIONS_BEFORE = frozenset(
    {"no", "not", "denies", "denied", "deny", "without", "negative", "absent", "none", "never"}
)
_NEGATIONS_AFTER = frozenset({"ruled", "excluded", "negative", "resolved"})
_NEGATION_WINDOW = 4

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


def _anatomy_matches(text: str) -> tuple[tuple[str, int, int], ...]:
    """Each anatomical region named by ``text``, with the word span that named it.

    Matching is on whole word-token sequences, never raw substrings, so "background"
    is not a back and "secondhand" is not a hand. The longest phrase wins and consumes
    its words: "low back" is the lumbar spine, and must not also register as the
    unsegmented spine, or a wrong-segment contradiction would be masked.
    """
    words = _words(text)
    if not words:
        return ()
    claimed = [False] * len(words)
    found: list[tuple[str, int, int]] = []
    for phrase, region in _ALIAS_WORDS:
        span = len(phrase)
        for start in range(len(words) - span + 1):
            if any(claimed[start : start + span]):
                continue
            if words[start : start + span] == phrase:
                found.append((region, start, start + span))
                claimed[start : start + span] = [True] * span
    return tuple(found)


def regions_named_by(text: str) -> frozenset[str]:
    """Every anatomical region a string names, whether or not it claims one."""
    return frozenset(region for region, _, _ in _anatomy_matches(text))


def _negated(words: tuple[str, ...], start: int, end: int) -> bool:
    """Whether a denial sits close enough to this mention to be about it."""
    before = words[max(0, start - _NEGATION_WINDOW) : start]
    after = words[end : end + _NEGATION_WINDOW]
    return bool(set(before) & _NEGATIONS_BEFORE or set(after) & _NEGATIONS_AFTER)


def regions_asserted_by(text: str) -> frozenset[str]:
    """Every anatomical region a string claims as injured.

    Naming a region is not claiming it: "No shoulder injury" and "shoulder ruled out"
    both name the shoulder in order to exclude it. Counting those as injured parts
    would clear a shoulder operation on a wrist case, which is precisely the
    contradiction this pack exists to find. The window is deliberately narrow so a
    denial elsewhere in the same sentence does not discard an affirmative mention —
    "Wrist sprain; no shoulder injury" still asserts the wrist.
    """
    words = _words(text)
    return frozenset(
        region for region, start, end in _anatomy_matches(text) if not _negated(words, start, end)
    )


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


def _names_injured_anatomy(fact: Fact) -> bool:
    """Whether this fact's own field claims to say which body part was injured."""
    return bool(tokens(fact.field) & (_BODY_PART_FIELD_MARKERS | _CLINICAL_PROSE_FIELD_MARKERS))


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
        claimed = regions_asserted_by(fact.value)
        if claimed:
            regions |= claimed
            cited.append(fact.id)
    return frozenset(regions), tuple(cited)


def _asserted_operations(context: RuleContext) -> Iterator[tuple[Fact, str]]:
    """Every procedure code asserted as this case's operation, in ledger order."""
    for fact in context.matching(_OPERATION_MARKERS):
        if _declares_uncoded(context, fact):
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
            fact_ids=(fact.id, *cited),
            category="medical",
        )


#: The registered pack. Detector class #2 is a sibling module and one more tuple entry.
RULE = Rule(
    name="anatomical_coherence",
    codes=frozenset({ANATOMICAL_CONTRADICTION}),
    detect=detect,
)
