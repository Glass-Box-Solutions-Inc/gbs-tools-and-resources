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
corpora is the measure this detector is scored against. The rule throughout is that
silence is the default and a finding requires an affirmative contradiction:

* an operation is asserted on a surface that claims to describe an operation, **and**
* the table knows that code's anatomy, **and**
* at least one injured body part is recognized, **and**
* no recognized injured part is compatible with the code's region.

Anything less — an unknown code, an uncoded operation, an injection, an unrecognized
body part, an unsegmented "back" against a cervical code — yields nothing at all. An
unknown code raises no note either: one note per unclassified code would put noise on
every case, and the table's real gap signal is recall measured over a scored corpus,
not a per-case remark.

Maintenance contract
--------------------
* Every entry is a five-digit CPT code in exactly one of the three tables below —
  operative (asserts an anatomical region), non-operative (an injection or diagnostic
  study, never an operation), or unlisted (names no anatomy it can be held to).
* Adding a code means adding it to exactly one table; the disjointness and shape of
  the tables are asserted by the suite, so a typo cannot sit here silently matching
  nothing.
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

#: Unlisted-procedure codes, which name a body area but assert no specific operation.
#:
#: An operation reached for an unlisted code precisely because it was not codeable, so
#: reading anatomy back out of one would be inference dressed as a fact. They are
#: recorded here to be excluded, never matched.
UNLISTED_CPT_CODES: frozenset[str] = frozenset(
    {
        "22899",  # Unlisted procedure, spine
        "23929",  # Unlisted procedure, shoulder
        "24999",  # Unlisted procedure, humerus or elbow
        "26989",  # Unlisted procedure, hands or fingers
        "27299",  # Unlisted procedure, pelvis or hip joint
        "27599",  # Unlisted procedure, femur or knee
        "27899",  # Unlisted procedure, leg or ankle
        "28899",  # Unlisted procedure, foot or toes
        "29999",  # Unlisted procedure, arthroscopy
        "64999",  # Unlisted procedure, nervous system
    }
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

#: Vocabulary marking a fact as describing what was injured.
_INJURY_MARKERS = frozenset(
    {
        "body",
        "part",
        "parts",
        "injury",
        "injuries",
        "injured",
        "diagnosis",
        "diagnoses",
        "complaint",
        "complaints",
    }
)

#: Field vocabulary that makes a bare five-digit value readable as a procedure code.
_CODE_FIELD_MARKERS = frozenset({"cpt", "code", "codes"})

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
    """Every anatomical region a body-part string names.

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


def contradicts(code: str, injured_regions: frozenset[str]) -> bool:
    """Whether this table affirmatively places ``code`` outside every injured region.

    False for everything the table cannot speak to: an unknown code, an injection, an
    unlisted procedure, or a case with no recognized injured part. Unknown is not wrong.
    """
    region = OPERATIVE_CPT_ANATOMY.get(code)
    if region is None or not injured_regions:
        return False
    return not any(_compatible(region, injured) for injured in injured_regions)


def _is_code_field(fact: Fact) -> bool:
    """Whether this field's own name says its value is a procedure code."""
    return bool(tokens(fact.field) & _CODE_FIELD_MARKERS)


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


def _injured_regions(context: RuleContext) -> tuple[frozenset[str], tuple[str, ...]]:
    """Recognized injured regions, and the facts that named them.

    Facts on the operation surface are excluded even when they name a body part:
    ``surgery.bodyPart`` records the part that was operated on, chosen together with
    the code, so reading it back as an injury would make the check answer itself.
    """
    regions: set[str] = set()
    cited: list[str] = []
    for fact in context.matching(_INJURY_MARKERS):
        if context.words(fact) & _OPERATION_MARKERS or not isinstance(fact.value, str):
            continue
        named = regions_named_by(fact.value)
        if named:
            regions |= named
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
                f"{_label(OPERATIVE_CPT_ANATOMY[code])}, in {context.source_of(fact)}; "
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
