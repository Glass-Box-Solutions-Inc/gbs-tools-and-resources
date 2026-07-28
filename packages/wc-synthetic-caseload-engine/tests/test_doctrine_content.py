"""ISC-21 — seeded doctrines reach the page, in language that can be found.

ISC-21 shipped DEFERRED-VERIFY. ``lifecycle.doctrine_hooks`` validated, forced
the psych flag and landed in the manifest, and the rendered documents said
nothing about the doctrine: a caseload seeded ``[kite, escobedo]`` produced a
corpus in which neither word appeared. The criterion says the hooks "inject
matching content flags into the document plan", and half of that was true.

This file is the other half, probed at each of the three places it can fail:

* the **table** (21.1, 21.2) — fourteen hooks, each with content and with
  targets that are real classifier subtypes. A target key with a typo matches
  nothing and renders nothing, silently, which is the failure mode that made
  the original criterion unverifiable;
* the **plan** (21.3) — every hook reaches at least one planned document as a
  content flag;
* the **page** (21.4) — every hook's marker survives into extracted PDF text,
  in both registers. Text extraction is the probe because that is what a
  classifier corpus consumer actually reads.

Two guards keep those three from passing vacuously. 21.5 is the anti-criterion:
a hook-free case must render exactly what it rendered before, and the injection
code path must not be entered at all — asserted by making the wrapper factory
raise, not by inspecting output. 21.6 is determinism: the doctrine draw is a
private RNG, so two runs of a flagged case must still produce identical bytes.

**Scope limit, stated rather than skipped.** ``scanned_pdf`` is a raster and
carries no extractable text (``conftest.NON_TEXT_FORMATS``). The doctrine
section is in those files — they are rendered from the same story — but this
file probes native pdf, and the anti-sweep in 21.5 skips scanned documents for
the same reason every other text probe in this suite does.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import re
import typing
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

import pytest

from conftest import NON_TEXT_FORMATS, extract_text, iter_documents, requires_substrate
from wc_caseload_engine.case_context import build_case_cast
from wc_caseload_engine.doctrine import (
    DOCTRINE_CONTENT,
    LEGAL_HEADING,
    LEGAL_REGISTER,
    MEDICAL_HEADING,
    MEDICAL_REGISTER,
    DoctrineContent,
    content_flags_for,
)
from wc_caseload_engine.lifecycle_bridge import build_timeline
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.renderer import (
    DOCTRINE_CLASS_SUFFIX,
    doctrine_template_class,
    render_document,
)
from wc_caseload_engine.seeds import (
    DoctrineHook,
    load_caseload_spec,
    parse_case_seed,
    resolve_caseload,
)
from wc_caseload_engine.taxonomy import effective_taxonomy

ENUM_HOOKS: tuple[str, ...] = tuple(sorted(typing.get_args(DoctrineHook.__value__)))
"""The fourteen hooks the seed schema accepts, read from the type alias itself.

Read rather than transcribed: a list copied into this file would keep passing
after someone added a fifteenth hook to ``seeds.py`` without content for it,
which is precisely the drift 21.1 exists to catch.
"""

DOCTRINE_HEADINGS: tuple[str, ...] = (MEDICAL_HEADING, LEGAL_HEADING)

SAMPLE_INJURY = {
    "type": "specific",
    "date_of_injury": "2022-02-02",
    "body_parts": [
        {"part": "lumbar_spine", "icd10": "M54.5"},
        # Two impaired regions, deliberately: ``kite`` argues that impairments
        # should be added rather than combined, which needs two impairments to
        # add. A single-region seed makes ``kite`` an unsupported hook and every
        # case built here would carry a doctrine warning.
        {"part": "shoulder", "icd10": "M75.100"},
    ],
}

FLAGGED_HOOKS = ("kite", "escobedo")
"""The pair the end-to-end case is seeded with.

Chosen because their target sets overlap partially: ``AME_COMPREHENSIVE_REPORT``
is a medical target of both, ``APPORTIONMENT_WORKSHEET`` a legal target of
``escobedo`` alone. One three-document case therefore exercises a two-hook
document, a one-hook document and a no-hook document at once.
"""

MULTI_HOOK_SUBTYPE = "AME_COMPREHENSIVE_REPORT"
SINGLE_HOOK_SUBTYPE = "APPORTIONMENT_WORKSHEET"
UNFLAGGED_SUBTYPE = "CLAIM_FORM_DWC1"
"""A subtype no doctrine hook targets — the in-case control."""

CASE_SUBTYPES = (MULTI_HOOK_SUBTYPE, SINGLE_HOOK_SUBTYPE, UNFLAGGED_SUBTYPE)


def _case_seed(case_id: str, hooks: tuple[str, ...], rng_seed: int = 4242) -> Any:
    """A three-document, pdf-only case carrying *hooks*.

    ``include_only`` empties the lifecycle's own proposal and the three explicit
    overrides put it back with exactly one document each, so the case renders in
    seconds and every document in it is one this file has an expectation about.
    """
    return parse_case_seed(
        {
            "case_id": case_id,
            "rng_seed": rng_seed,
            "injury": dict(SAMPLE_INJURY),
            "lifecycle": {"doctrine_hooks": list(hooks)},
            "documents": {
                "format_mix": {"pdf": 1.0},
                "include_only": list(CASE_SUBTYPES),
                "overrides": [{"subtype": subtype, "count": 1} for subtype in CASE_SUBTYPES],
                "global_cap": len(CASE_SUBTYPES),
            },
        }
    )


def _normalized(text: str) -> str:
    """Collapse whitespace so a line-wrapped phrase still matches.

    PDF extraction returns the line breaks the layout engine chose, so a
    two-word marker like ``going and coming`` comes back split across lines
    perhaps half the time. Normalizing both sides is what makes a phrase marker
    as reliable as a statute number.
    """
    return re.sub(r"\s+", " ", text)


def _document_text(path: Path, doc_format: str) -> str:
    """Normalized text of one rendered document."""
    return _normalized(extract_text(path, doc_format))


@pytest.fixture(scope="module")
def render_context() -> tuple[Any, Any]:
    """One valid case context, reused for every direct render below."""
    seed = parse_case_seed(
        {"case_id": "doctrine-render", "rng_seed": 991, "injury": dict(SAMPLE_INJURY)}
    )
    return seed, build_case_cast(seed, build_timeline(seed))


@pytest.fixture(scope="module")
def flagged_case(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One generated case carrying :data:`FLAGGED_HOOKS`, with its manifest."""
    out = tmp_path_factory.mktemp("doctrine-flagged")
    result = generate_case(_case_seed("doctrine-flagged", FLAGGED_HOOKS), out)
    manifest = json.loads((result.directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["_directory"] = str(result.directory)
    return manifest


@pytest.fixture(scope="module")
def unflagged_case(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The same case with no doctrine hooks — the anti-criterion's subject."""
    out = tmp_path_factory.mktemp("doctrine-unflagged")
    result = generate_case(_case_seed("doctrine-unflagged", ()), out)
    manifest = json.loads((result.directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["_directory"] = str(result.directory)
    return manifest


# ---------------------------------------------------------------------------
# ISC-21.1 — the content table covers every hook
# ---------------------------------------------------------------------------


class TestContentTableIsComplete:
    """ISC-21.1: fourteen hooks, each with usable content."""

    def test_the_hook_list_under_test_is_the_whole_enum(self) -> None:
        """Guards this file: a shrunken hook list would make everything pass."""
        assert len(ENUM_HOOKS) == 14, f"the seed schema now declares {len(ENUM_HOOKS)} hooks"

    def test_every_enum_hook_has_content(self) -> None:
        assert set(DOCTRINE_CONTENT) == set(ENUM_HOOKS), (
            f"content missing for {sorted(set(ENUM_HOOKS) - set(DOCTRINE_CONTENT))}; "
            f"content for unknown hooks {sorted(set(DOCTRINE_CONTENT) - set(ENUM_HOOKS))}"
        )

    @pytest.mark.parametrize("hook", ENUM_HOOKS)
    def test_each_entry_is_usable(self, hook: str) -> None:
        content = DOCTRINE_CONTENT[hook]
        assert content.hook == hook, "the mapping key and the entry disagree"
        assert content.display.strip(), f"{hook} has no display name"
        assert content.marker.strip(), f"{hook} has no marker"
        assert content.citation.strip(), f"{hook} has no citation"
        assert content.medical_paragraphs or content.legal_paragraphs, f"{hook} has no paragraphs"
        assert content.targets, f"{hook} targets no subtype and can never render"

    @pytest.mark.parametrize("hook", ENUM_HOOKS)
    def test_every_paragraph_carries_the_marker(self, hook: str) -> None:
        """A paragraph without the marker is content no probe can find."""
        content = DOCTRINE_CONTENT[hook]
        missing = [
            paragraph[:60]
            for paragraph in (*content.medical_paragraphs, *content.legal_paragraphs)
            if content.marker not in paragraph
        ]
        assert not missing, (
            f"{hook}: {len(missing)} paragraph(s) omit {content.marker!r}: {missing}"
        )

    @pytest.mark.parametrize("hook", ENUM_HOOKS)
    def test_a_targeted_pool_is_never_empty(self, hook: str) -> None:
        """Targets without a pool are the silent half of the same failure."""
        content = DOCTRINE_CONTENT[hook]
        if content.medical_targets:
            assert content.medical_paragraphs, f"{hook} has medical targets and no medical pool"
        if content.legal_targets:
            assert content.legal_paragraphs, f"{hook} has legal targets and no legal pool"

    def test_markers_survive_a_grep(self) -> None:
        """Markers are short, punctuation-light strings by construction."""
        for hook, content in sorted(DOCTRINE_CONTENT.items()):
            assert len(content.marker) >= 4, f"{hook}: {content.marker!r} is too short to be safe"
            assert "\n" not in content.marker, f"{hook}: marker spans lines"
            assert content.marker == content.marker.strip()

    def test_content_flags_are_sorted_deduplicated_and_order_independent(self) -> None:
        """Two seeds naming the same hooks must produce the same document."""
        hooks = ["kite", "escobedo", "kite"]
        flags = content_flags_for(hooks, MULTI_HOOK_SUBTYPE)
        assert flags == ("escobedo", "kite")
        assert flags == content_flags_for(list(reversed(hooks)), MULTI_HOOK_SUBTYPE)
        assert content_flags_for(hooks, UNFLAGGED_SUBTYPE) == ()
        assert content_flags_for(["not_a_hook"], MULTI_HOOK_SUBTYPE) == ()


# ---------------------------------------------------------------------------
# A1 — paragraphs may not assert facts the seed cannot establish
# ---------------------------------------------------------------------------

BANNED_ASSERTIONS: tuple[tuple[str, str], ...] = (
    ("two distinct industrial injuries, Benson requires", "a second injury the seed cannot model"),
    ("more than one claimed date of injury", "a second date of injury"),
    ("the two dates of injury", "a second date of injury"),
    ("bracketing the two dates", "a second date of injury"),
    ("The applicant is the subject of a prior award", "a prior award as fact"),
    ("employment predates the claimed psychiatric injury by more than six months",
     "a tenure figure the paragraph cannot know"),
    ("The applicant's account places the event during a commute", "commute specifics"),
    ("the applicant described work that was directed and scheduled", "control facts as findings"),
    ("The applicant attributes the psychiatric condition primarily to a disciplinary sequence",
     "a specific disciplinary history"),
    ("is degenerative pathology documented on imaging", "imaging findings as fact"),
    ("between the two injuries", "a second injury as an established fact"),
    ("The consequence of Benson in this matter", "the doctrine as applied rather than argued"),
    # Found by the full 14-hook sweep. Every one asserted a fact its hook's
    # prerequisite does not establish, and every one was reachable by
    # auto-derivation with no warning — the same class as the entries above,
    # in the hooks the earlier rounds' enumeration missed.
    ("are placed at issue on these facts", "two specific commute exceptions as facts of record"),
    ("The applicant's employment status is disputed", "an employment-status dispute as a fact"),
    (
        "I have stated the prior impairment as a whole person figure",
        "a quantified preexisting impairment the seed cannot establish",
    ),
    (
        "the combined effect of the prior condition and the current industrial injury exceeds",
        "a preexisting condition as an established fact",
    ),
    (
        "I have described the overlap in functional terms",
        "overlap with a prior award that may not exist",
    ),
    (
        "the diagnosis, its date, the applicant",
        "a cancer diagnosis the prerequisite does not establish",
    ),
    (
        "The service history and the date of diagnosis are set out above",
        "a diagnosis date the prerequisite does not establish",
    ),
    (
        "the denial was upheld on independent medical review",
        "an IMR outcome the prerequisite does not establish (imr_outcome may be overturned)",
    ),
    (
        "separated the applicant's reaction to personnel action events",
        "personnel action events as facts of record",
    ),
    (
        "personnel action events account for the percentage of causation stated above",
        "personnel action events as facts of record",
    ),
)
"""Phrases that state extra-record facts as findings, with why each is banned.

Every entry is a phrase that shipped in the first cut of ``DOCTRINE_CONTENT``.
A ``CaseSeed`` models exactly one ``InjurySpec`` with one date of injury, no
prior award, and no disciplinary history, so a paragraph asserting any of them
describes a case the generator did not produce — and a corpus built from it
teaches a classifier to associate the doctrine with facts that are not in the
document.

The fix is register, not omission: the doctrine is *raised as a contention*
("Defendant contends...", "Where a prior award is established...") rather than
adjudicated, which is how these paragraphs read in a real file anyway.
"""


class TestParagraphsDoNotAssertUnrepresentableFacts:
    """A1: content must be true of the case the seed can actually describe."""

    @pytest.mark.parametrize(("phrase", "reason"), BANNED_ASSERTIONS, ids=lambda v: str(v)[:40])
    def test_no_shipped_paragraph_contains_a_banned_assertion(
        self, phrase: str, reason: str
    ) -> None:
        offenders = [
            f"{hook}.{register}[{index}]"
            for hook, content in sorted(DOCTRINE_CONTENT.items())
            for register, pool in (
                (MEDICAL_REGISTER, content.medical_paragraphs),
                (LEGAL_REGISTER, content.legal_paragraphs),
            )
            for index, paragraph in enumerate(pool)
            if phrase in paragraph
        ]
        assert not offenders, f"{offenders} assert {reason} ({phrase!r})"

    def test_every_hook_declares_a_prerequisite_or_is_listed_as_exempt(self) -> None:
        """A deliberate decision per hook, not an attribute that is always there.

        The previous version of this asserted ``hasattr(content, "requires")``,
        which a slots dataclass with a defaulted field satisfies unconditionally
        — it could not fail, so it did not check that anyone had *thought* about
        the new hook. The allowlist below is the thinking: adding a hook without
        a prerequisite now means editing this list and saying why.
        """
        exempt: frozenset[str] = frozenset()
        missing = sorted(
            hook
            for hook, content in DOCTRINE_CONTENT.items()
            if content.requires is None and hook not in exempt
        )
        assert not missing, (
            f"{missing} declare no prerequisite and are not listed as deliberately exempt; "
            "either give them one or add them to `exempt` with a reason"
        )
        stale = sorted(
            hook
            for hook in exempt
            if hook not in DOCTRINE_CONTENT or DOCTRINE_CONTENT[hook].requires is not None
        )
        assert not stale, f"{stale} are exempt but no longer need to be"

    def test_a_prerequisite_states_what_the_seed_must_show(self) -> None:
        for hook, content in sorted(DOCTRINE_CONTENT.items()):
            if content.requires is not None:
                assert content.requires.description.strip(), f"{hook} prerequisite has no reason"


class TestPrerequisitesGovernAutoDerivation:
    """A1: an auto-drawn hook must fit the case it lands on."""

    pytestmark = requires_substrate

    def test_death_dependency_needs_a_death_claim(self) -> None:
        from wc_caseload_engine.doctrine import hook_is_supported

        death = parse_case_seed(
            {
                "case_id": "death-seed",
                "rng_seed": 3,
                "injury": {
                    "type": "death",
                    "date_of_injury": "2022-02-02",
                    "body_parts": [{"part": "head", "icd10": "S06.0X0A"}],
                },
                "lifecycle": {"resolution": {"type": "stipulations"}},
            }
        )
        living = parse_case_seed(
            {"case_id": "living-seed", "rng_seed": 3, "injury": dict(SAMPLE_INJURY)}
        )
        assert hook_is_supported("death_dependency", death)
        assert not hook_is_supported("death_dependency", living)

    def test_a_psychiatric_doctrine_needs_a_psychiatric_injury(self) -> None:
        """N1: the prerequisite that blessed a psych argument in an orthopedic file.

        ``lc3208_3_psych`` used to ask only that the claim not be a death claim,
        so a lumbar-only case satisfied it and auto-derivation could draw it as
        *supported* — injecting "This psychiatric evaluation is framed by..."
        into an ordinary orthopedic QME with no warning at all. That is the A1
        class of defect recurring inside the layer built to prevent it, which is
        worse than the original: the warning path was the safety net, and a
        satisfied prerequisite bypasses it.
        """
        from wc_caseload_engine.doctrine import hook_is_supported

        lumbar = parse_case_seed(
            {"case_id": "lumbar-only", "rng_seed": 4, "injury": dict(SAMPLE_INJURY)}
        )
        psych = parse_case_seed(
            {
                "case_id": "psych-seed",
                "rng_seed": 4,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2022-02-02",
                    "body_parts": [
                        {"part": "lumbar_spine", "icd10": "M54.5"},
                        {"part": "psyche", "icd10": "F43.10"},
                    ],
                },
            }
        )
        assert not hook_is_supported("lc3208_3_psych", lumbar), (
            "a lumbar-only case supports a psychiatric-threshold argument"
        )
        assert hook_is_supported("lc3208_3_psych", psych)

    def test_adding_impairments_needs_two_impairments(self) -> None:
        """The same defect as N1, found in ``kite`` while auditing the README claim.

        ``kite`` asked only for a rating, so a single-region case satisfied it
        and auto-derivation could draw "impairments may be added rather than
        combined where they have a synergistic effect" into a file with one
        impairment. Unlike Benson's second *injury*, a second impaired region is
        something a seed can express, so this is a real gate rather than a
        documented approximation.
        """
        from wc_caseload_engine.doctrine import hook_is_supported

        one_region = parse_case_seed(
            {
                "case_id": "one-region",
                "rng_seed": 6,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2022-02-02",
                    "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
                },
            }
        )
        two_regions = parse_case_seed(
            {"case_id": "two-regions", "rng_seed": 6, "injury": dict(SAMPLE_INJURY)}
        )
        assert not hook_is_supported("kite", one_region)
        assert hook_is_supported("kite", two_regions)

    def test_no_auto_drawn_psych_doctrine_lands_on_a_case_without_a_psyche_claim(self) -> None:
        """The sweep the unit assertion above cannot make: the draw itself."""
        from wc_caseload_engine.seeds import CaseloadSpec, resolve_caseload

        offenders: list[str] = []
        supported_draws: list[str] = []
        psych_seeds = 0
        for rng_seed in (7, 11, 23):
            spec = CaseloadSpec.model_validate(
                {
                    "caseload_id": f"auto-psych-{rng_seed}",
                    "auto": {
                        "count": 60,
                        "distribution": "complex_litigation",
                        "rng_seed": rng_seed,
                    },
                }
            )
            for seed in resolve_caseload(spec):
                psych_parts = {part.part for part in seed.injury.body_parts}
                has_psyche = "psyche" in psych_parts
                psych_seeds += int(has_psyche)
                for hook in ("lc3208_3_psych", "gfpa"):
                    if hook not in seed.lifecycle.doctrine_hooks:
                        continue
                    if has_psyche:
                        supported_draws.append(f"{seed.case_id}: {hook}")
                    else:
                        offenders.append(f"{seed.case_id}: {hook} on {sorted(psych_parts)}")
        assert not offenders, (
            f"{len(offenders)} auto-drawn psychiatric doctrine(s) on non-psych cases: "
            f"{offenders[:10]}"
        )
        # Positive control. Without this the assertion above passes just as
        # happily if the psychiatric hooks became unreachable altogether — a
        # prerequisite tightened into "never" would read as a clean sweep.
        assert psych_seeds >= 1, (
            "the sweep drew no psych-bearing seeds at all; it cannot show the gate "
            "admits anything"
        )
        assert supported_draws, (
            "no supported psychiatric draw was observed across "
            f"{psych_seeds} psych-bearing seed(s) — the gate may now reject every case, "
            "which would make the offender check above vacuous"
        )

    def test_the_psychiatric_language_cannot_be_auto_drawn_onto_a_non_psych_case(self) -> None:
        """N1(b): these phrases are correct on a psych file, so they are not banned.

        "This psychiatric evaluation is framed by..." is exactly right in a
        psychiatric med-legal report and wrong everywhere else. Banning the text
        would delete a true sentence; the defect was the gate, not the wording.

        The claim is precisely "cannot be **auto-drawn**", not "cannot be
        reached": an explicitly seeded hook is still kept and still renders its
        language, with a warning. The prerequisite governs the draw, which is
        the channel nobody chose; it does not overrule a seed author.
        """
        from wc_caseload_engine.doctrine import hook_is_supported

        phrases = ("This psychiatric evaluation is framed by", "The diagnosis is stated")
        for phrase in phrases:
            carriers = sorted(
                hook
                for hook, content in DOCTRINE_CONTENT.items()
                if any(
                    phrase in paragraph
                    for paragraph in (*content.medical_paragraphs, *content.legal_paragraphs)
                )
            )
            assert carriers == ["lc3208_3_psych"], (
                f"{phrase!r} appears in {carriers}; it is only defensible under lc3208_3_psych"
            )

        content = DOCTRINE_CONTENT["lc3208_3_psych"]
        assert content.requires is not None
        assert "psyche" in content.requires.description, (
            "the gate on this language no longer mentions the psyche body part"
        )
        assert not hook_is_supported(
            "lc3208_3_psych",
            parse_case_seed(
                {"case_id": "ortho-only", "rng_seed": 9, "injury": dict(SAMPLE_INJURY)}
            ),
        )

    def test_auto_derived_caseloads_never_carry_an_unsupported_hook(self) -> None:
        """The draw is the channel a seed author does not control."""
        from wc_caseload_engine.doctrine import hook_is_supported
        from wc_caseload_engine.seeds import CaseloadSpec, resolve_caseload

        spec = CaseloadSpec.model_validate(
            {
                "caseload_id": "auto-doctrine",
                "auto": {"count": 60, "distribution": "complex_litigation", "rng_seed": 7},
            }
        )
        offenders = [
            f"{seed.case_id}: {hook}"
            for seed in resolve_caseload(spec)
            for hook in seed.lifecycle.doctrine_hooks
            if not hook_is_supported(hook, seed)
        ]
        assert not offenders, (
            f"{len(offenders)} auto-drawn hook(s) do not fit their case: {offenders[:10]}"
        )

    def test_an_explicitly_seeded_unsupported_hook_is_kept_and_warned(self) -> None:
        """ISC-29's rule: the seed is the contract, and the engine says so loudly."""
        seed = parse_case_seed(
            {
                "case_id": "explicit-unsupported",
                "rng_seed": 5,
                "injury": dict(SAMPLE_INJURY),
                "lifecycle": {"doctrine_hooks": ["death_dependency"]},
                "documents": {"global_cap": 6},
            }
        )
        plan = build_case_plan(seed)
        assert seed.lifecycle.doctrine_hooks == ["death_dependency"], (
            "the hook was silently dropped"
        )
        assert any("death_dependency" in warning for warning in plan.warnings), (
            f"no warning for an unsupported explicit hook; got {plan.warnings}"
        )

    def test_a_supported_explicit_hook_warns_about_nothing(self) -> None:
        """Guards the probe: a warning on every case would be noise, not signal."""
        plan = build_case_plan(_case_seed("supported-hooks", FLAGGED_HOOKS))
        assert not [w for w in plan.warnings if "doctrine" in w.lower()], plan.warnings


class TestTheDemoCaseloadsWarningsArePinned:
    """Caveat-2: two demo seeds exercise the warning path deliberately.

    ``nguyen-cr-three-liens`` names ``benson`` on a single-region case and
    ``ramirez-death-dependency`` names ``gfpa`` on a death claim with no
    psychiatric component. Both are kept-and-warned, which is the point — the
    shipped demo demonstrates the loud path rather than only the happy one.

    Pinning the exact set is what keeps that demonstration from swallowing a
    real regression: without this, a third demo case starting to warn would look
    exactly like the two that are supposed to.
    """

    pytestmark = requires_substrate

    EXPECTED: ClassVar[dict[str, tuple[str, ...]]] = {
        "nguyen-cr-three-liens": ("benson",),
        "ramirez-death-dependency": ("gfpa",),
    }

    def test_exactly_the_documented_demo_seeds_warn(self) -> None:
        from conftest import DEMO_SPEC
        from wc_caseload_engine.doctrine import unsupported_hook_warnings
        from wc_caseload_engine.seeds import load_caseload_spec, resolve_caseload

        actual: dict[str, tuple[str, ...]] = {}
        for seed in resolve_caseload(load_caseload_spec(DEMO_SPEC)):
            warned = tuple(
                hook
                for hook in seed.lifecycle.doctrine_hooks
                if unsupported_hook_warnings([hook], seed)
            )
            if warned:
                actual[seed.case_id] = warned

        assert actual == self.EXPECTED, (
            "the demo caseload's doctrine warnings changed. Each entry is a seed that "
            "deliberately names a doctrine its case cannot support (see the inline YAML "
            "comments); a new one is either a real defect or a deliberate demonstration "
            "that belongs in this list."
        )


class TestTheDoctrineShowcaseSpecCoversEveryHookCleanly:
    """AJC-36: the guide publishes this spec as the warning-free run.

    Three separate claims, each asserted on its own so a break names itself:

    1. Every one of the fourteen hooks is seeded somewhere in the spec.
    2. Every seeded hook's prerequisite is satisfied — the whole run is warning
       free, which is the property that distinguishes it from the demo.
    3. Every hook actually reaches a document that targets it. A hook can be
       supported and still land nothing (see the guide's "supported is not the
       same as rendered"), and a showcase that demonstrates no content is not a
       showcase — so the naturally-emitted flag is asserted rather than assumed.

    Asserted against the plan rather than a render: the plan already carries the
    content flags, and rendering six cases costs ~40 s for no extra signal.
    """

    pytestmark = requires_substrate

    @staticmethod
    def _seeds() -> list[Any]:
        from conftest import SHOWCASE_SPEC

        return list(resolve_caseload(load_caseload_spec(SHOWCASE_SPEC)))

    def _plans(self) -> list[tuple[str, Any]]:
        return [(seed.case_id, build_case_plan(seed)) for seed in self._seeds()]

    def test_every_hook_is_seeded_somewhere(self) -> None:
        seeded = {hook for seed in self._seeds() for hook in seed.lifecycle.doctrine_hooks}
        assert seeded == set(DOCTRINE_CONTENT), (
            "examples/doctrine-showcase.yaml is the guide's 'all fourteen doctrines' spec. "
            f"Missing: {sorted(set(DOCTRINE_CONTENT) - seeded)}; "
            f"unknown: {sorted(seeded - set(DOCTRINE_CONTENT))}."
        )

    def test_the_whole_run_is_warning_free(self) -> None:
        warned = {case_id: plan.warnings for case_id, plan in self._plans() if plan.warnings}
        assert warned == {}, (
            "the doctrine showcase is published as a zero-warning run — every case's "
            "facts are supposed to satisfy every hook it names. Either the seed drifted "
            "or a prerequisite tightened; fix the seed, do not relax the assertion."
        )

    def test_every_hook_lands_on_a_document_without_being_forced(self) -> None:
        flagged: dict[str, set[str]] = {}
        for _case_id, plan in self._plans():
            for document in plan.documents:
                for hook in document.content_flags:
                    flagged.setdefault(hook, set()).add(document.subtype)

        missing = sorted(set(DOCTRINE_CONTENT) - set(flagged))
        assert not missing, (
            f"{missing} are supported by their showcase case but reach no document that "
            "targets them, so the spec demonstrates nothing for them. Advance that case's "
            "lifecycle until a target subtype is emitted naturally — do not add a "
            "documents.overrides entry, which would itself warn."
        )

    def test_the_showcase_forces_no_subtypes(self) -> None:
        """The zero-warning claim depends on this: a forced subtype is a WARN."""
        forced = {
            seed.case_id: [o.subtype or str(o.type) for o in seed.documents.overrides]
            for seed in self._seeds()
            if seed.documents.overrides
        }
        assert forced == {}, (
            "the showcase reaches every hook through natural lifecycle emission on "
            f"purpose; these cases now force subtypes instead: {forced}."
        )


# ---------------------------------------------------------------------------
# ISC-21.2 — every target is classifier vocabulary
# ---------------------------------------------------------------------------


class TestTargetsAreCanonical:
    """ISC-21.2: a target that is not a real subtype renders nothing, quietly."""

    pytestmark = requires_substrate

    def test_the_taxonomy_under_test_is_the_whole_taxonomy(self) -> None:
        """Guards the assertion below against a shrunken taxonomy."""
        assert len(effective_taxonomy().subtypes) == 353

    def test_every_target_subtype_is_canonical(self) -> None:
        taxonomy = effective_taxonomy()
        offences = [
            f"{hook}.{register}: {subtype}"
            for hook, content in sorted(DOCTRINE_CONTENT.items())
            for register, targets in (
                (MEDICAL_REGISTER, content.medical_targets),
                (LEGAL_REGISTER, content.legal_targets),
            )
            for subtype in sorted(targets)
            if not taxonomy.is_canonical(subtype)
        ]
        assert not offences, f"{len(offences)} non-canonical doctrine target(s): {offences}"

    def test_no_hook_files_one_subtype_in_both_registers(self) -> None:
        for hook, content in sorted(DOCTRINE_CONTENT.items()):
            overlap = content.medical_targets & content.legal_targets
            assert not overlap, f"{hook} targets {sorted(overlap)} as both medical and legal"

    def test_a_subtype_has_one_register_across_all_hooks(self) -> None:
        """The invariant that lets a two-hook document carry one heading."""
        medical: set[str] = set()
        legal: set[str] = set()
        for content in DOCTRINE_CONTENT.values():
            medical |= content.medical_targets
            legal |= content.legal_targets
        assert not medical & legal, (
            f"{sorted(medical & legal)} are medical targets for one hook and legal for another"
        )

    def test_the_control_subtype_is_targeted_by_nothing(self) -> None:
        """Guards 21.5 and 21.6: the in-case control must really be a control."""
        assert not any(
            content.targets_subtype(UNFLAGGED_SUBTYPE) for content in DOCTRINE_CONTENT.values()
        )


# ---------------------------------------------------------------------------
# ISC-21.3 — the hook reaches the plan
# ---------------------------------------------------------------------------


class TestPlannerCarriesContentFlags:
    """ISC-21.3: a seeded hook becomes a content flag on a planned document."""

    pytestmark = requires_substrate

    @staticmethod
    def _target_for(content: DoctrineContent) -> str:
        """One target of *content*, chosen deterministically."""
        return sorted(content.targets)[0]

    @pytest.mark.parametrize("hook", ENUM_HOOKS)
    def test_each_hook_flags_a_planned_document(self, hook: str) -> None:
        """Forced via a per-subtype override, which wins even when lifecycle-invalid.

        Per ISC-29 an explicit ``documents.overrides`` entry emits its subtype
        whether or not the lifecycle proposed it, with a WARN. That is what lets
        this assert all fourteen hooks against one seed shape instead of hunting
        for a lifecycle that naturally emits each hook's targets.
        """
        subtype = self._target_for(DOCTRINE_CONTENT[hook])
        seed = parse_case_seed(
            {
                "case_id": f"doctrine-plan-{hook.replace('_', '-')}",
                "rng_seed": 8080,
                "injury": dict(SAMPLE_INJURY),
                "lifecycle": {"doctrine_hooks": [hook]},
                "documents": {
                    "include_only": [subtype],
                    "overrides": [{"subtype": subtype, "count": 1}],
                },
            }
        )
        plan = build_case_plan(seed)
        flagged = [
            document
            for document in plan.documents
            if document.subtype == subtype and hook in document.content_flags
        ]
        assert flagged, (
            f"{hook} never reached a planned {subtype}; "
            f"plan holds {sorted({d.subtype for d in plan.documents})}"
        )

    def test_a_document_carries_every_hook_that_targets_it(self) -> None:
        """Two hooks on one subtype produce two flags, sorted."""
        plan = build_case_plan(_case_seed("doctrine-multi", FLAGGED_HOOKS))
        by_subtype = {document.subtype: document for document in plan.documents}
        assert by_subtype[MULTI_HOOK_SUBTYPE].content_flags == ("escobedo", "kite")
        assert by_subtype[SINGLE_HOOK_SUBTYPE].content_flags == ("escobedo",)
        assert by_subtype[UNFLAGGED_SUBTYPE].content_flags == ()

    def test_flags_are_a_subset_of_the_seeded_hooks(self) -> None:
        """A document can never carry a doctrine the seed never named."""
        plan = build_case_plan(_case_seed("doctrine-subset", FLAGGED_HOOKS))
        for document in plan.documents:
            assert set(document.content_flags) <= set(FLAGGED_HOOKS)


# ---------------------------------------------------------------------------
# ISC-21.4 — the hook reaches the page
# ---------------------------------------------------------------------------


def _register_cases() -> list[tuple[str, str, str]]:
    """``(hook, register, subtype)`` for every hook in every register it uses."""
    cases: list[tuple[str, str, str]] = []
    for hook in ENUM_HOOKS:
        content = DOCTRINE_CONTENT[hook]
        for register, targets in (
            (MEDICAL_REGISTER, content.medical_targets),
            (LEGAL_REGISTER, content.legal_targets),
        ):
            if targets:
                cases.append((hook, register, sorted(targets)[0]))
    return cases


class TestRenderedDocumentsCarryTheDoctrine:
    """ISC-21.4: the marker survives into extracted PDF text, per hook."""

    pytestmark = requires_substrate

    @pytest.mark.parametrize(
        ("hook", "register", "subtype"),
        _register_cases(),
        ids=lambda value: str(value),
    )
    def test_the_marker_and_citation_reach_the_page(
        self,
        hook: str,
        register: str,
        subtype: str,
        render_context: tuple[Any, Any],
        tmp_path: Path,
    ) -> None:
        """Rendered through the engine's own dispatch, read back as text.

        Driven straight into :func:`render_document` rather than through a
        generated caseload: the unit under test is the injection, and 28 direct
        renders cost a fraction of 14 case generations while proving more —
        every hook in every register it declares.
        """
        seed, cast = render_context
        content = DOCTRINE_CONTENT[hook]
        out_path = tmp_path / f"{hook}_{register}.pdf"
        result = render_document(
            seed=seed,
            cast=cast,
            subtype=subtype,
            doc_date=date(2023, 6, 1),
            doc_format="pdf",
            index=ENUM_HOOKS.index(hook),
            out_path=out_path,
            content_flags=(hook,),
        )
        text = _document_text(result.path, result.doc_format)

        assert content.marker in text, f"{hook}: {content.marker!r} not in the rendered {subtype}"
        assert _normalized(content.citation) in text, f"{hook}: the citation did not render"
        expected_heading = MEDICAL_HEADING if register == MEDICAL_REGISTER else LEGAL_HEADING
        assert _normalized(expected_heading) in text, f"{hook}: wrong or missing section heading"
        assert result.content_flags == (hook,), "the render did not record its flags"

    def test_the_generated_case_carries_the_doctrine_end_to_end(
        self, flagged_case: dict[str, Any]
    ) -> None:
        """The other half of the wiring: planner flags reach the renderer.

        The parametrized probe above calls ``render_document`` directly, so it
        proves the injection but not that anything passes the plan's flags to
        it. This reads the files a real ``generate`` produced.
        """
        seen: dict[str, str] = {}
        for entry, path in iter_documents(flagged_case):
            if entry["format"] in NON_TEXT_FORMATS:
                continue
            seen[entry["subtype"]] = _document_text(path, entry["format"])

        assert set(seen) == set(CASE_SUBTYPES), f"case rendered {sorted(seen)}"
        for hook in FLAGGED_HOOKS:
            assert DOCTRINE_CONTENT[hook].marker in seen[MULTI_HOOK_SUBTYPE], (
                f"{hook} did not reach the two-hook document"
            )
        assert DOCTRINE_CONTENT["escobedo"].marker in seen[SINGLE_HOOK_SUBTYPE]
        assert _normalized(MEDICAL_HEADING) in seen[MULTI_HOOK_SUBTYPE]
        assert _normalized(LEGAL_HEADING) in seen[SINGLE_HOOK_SUBTYPE]

    def test_the_unflagged_document_in_a_flagged_case_stays_clean(
        self, flagged_case: dict[str, Any]
    ) -> None:
        """A hook reaches its targets and nothing else, inside the same case."""
        texts = {
            entry["subtype"]: _document_text(path, entry["format"])
            for entry, path in iter_documents(flagged_case)
            if entry["format"] not in NON_TEXT_FORMATS
        }
        control = texts[UNFLAGGED_SUBTYPE]
        for heading in DOCTRINE_HEADINGS:
            assert _normalized(heading) not in control
        for hook in FLAGGED_HOOKS:
            assert _normalized(DOCTRINE_CONTENT[hook].citation) not in control


# ---------------------------------------------------------------------------
# ISC-21.5 (Anti) — no hooks, no change
# ---------------------------------------------------------------------------


class TestNoHooksChangesNothing:
    """ISC-21.5: the hook-free path is the path that existed before ISC-21."""

    pytestmark = requires_substrate

    def test_no_planned_document_is_flagged(self) -> None:
        plan = build_case_plan(_case_seed("doctrine-none", ()))
        flagged = [
            f"{document.subtype}={document.content_flags}"
            for document in plan.documents
            if document.content_flags
        ]
        assert not flagged, f"a hook-free seed flagged {flagged}"

    def test_no_doctrine_language_reaches_a_hook_free_case(
        self, unflagged_case: dict[str, Any]
    ) -> None:
        """Sweeps the rendered case for every citation and both headings.

        Deliberately keyed to the citations and headings rather than to the
        markers. Several markers are surnames — ``Stevens``, ``Benson``,
        ``Guzman`` — and a generated cast draws surnames too, so a marker sweep
        would fail on a coincidence rather than on a regression. The citation
        lines and the section headings are strings only this module emits, which
        makes them the probe that can only fire for the right reason.
        """
        offences: list[str] = []
        swept = 0
        for entry, path in iter_documents(unflagged_case):
            if entry["format"] in NON_TEXT_FORMATS:
                continue
            text = _document_text(path, entry["format"])
            swept += 1
            for heading in DOCTRINE_HEADINGS:
                if _normalized(heading) in text:
                    offences.append(f"{entry['filename']}: heading {heading!r}")
            for hook, content in sorted(DOCTRINE_CONTENT.items()):
                if _normalized(content.citation) in text:
                    offences.append(f"{entry['filename']}: {hook} citation")
        assert swept == len(CASE_SUBTYPES), f"only {swept} documents swept"
        assert not offences, f"{len(offences)} doctrine intrusion(s): {offences}"

    def test_no_manifest_entry_carries_content_flags(
        self, unflagged_case: dict[str, Any]
    ) -> None:
        """The key is absent, not present-and-empty — byte-identical manifests."""
        carriers = [
            entry["filename"] for entry in unflagged_case["documents"] if "contentFlags" in entry
        ]
        assert not carriers, f"contentFlags written for {carriers}"
        assert unflagged_case["doctrineHooks"] == []

    def test_empty_flags_render_byte_for_byte_what_no_flags_render(
        self, render_context: tuple[Any, Any], tmp_path: Path
    ) -> None:
        """Passing ``content_flags=()`` is passing nothing."""
        seed, cast = render_context
        checksums = []
        for label, kwargs in (("implicit", {}), ("explicit", {"content_flags": ()})):
            result = render_document(
                seed=seed,
                cast=cast,
                subtype=MULTI_HOOK_SUBTYPE,
                doc_date=date(2023, 6, 1),
                doc_format="pdf",
                index=2,
                out_path=tmp_path / f"{label}.pdf",
                **kwargs,
            )
            assert result.content_flags == ()
            checksums.append(result.md5)
        assert checksums[0] == checksums[1]

    def test_the_wrapper_factory_is_not_called_without_flags(
        self, render_context: tuple[Any, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the code path, not just the output.

        Two renders through a factory that raises: the unflagged one must not
        reach it at all, the flagged one must. Asserting on bytes alone could
        not tell "the wrapper was never built" from "the wrapper was built and
        happened to append nothing".
        """
        from wc_caseload_engine import renderer as renderer_module

        def explode(*_args: Any, **_kwargs: Any) -> type:
            raise AssertionError("doctrine_template_class called for an unflagged document")

        monkeypatch.setattr(renderer_module, "doctrine_template_class", explode)
        common = {
            "seed": render_context[0],
            "cast": render_context[1],
            "subtype": MULTI_HOOK_SUBTYPE,
            "doc_date": date(2023, 6, 1),
            "doc_format": "pdf",
            "index": 4,
        }
        render_document(**common, out_path=tmp_path / "clean.pdf")

        with pytest.raises(AssertionError, match="doctrine_template_class called"):
            render_document(
                **common, out_path=tmp_path / "flagged.pdf", content_flags=("kite",)
            )

    def test_the_wrapper_factory_produces_a_distinguishable_subclass(self) -> None:
        """The factory itself, probed directly so 21.5's negative has a positive."""

        class Base:
            def build_story(self, doc_spec: Any) -> list[Any]:
                return ["base"]

        wrapped = doctrine_template_class(Base, lambda _template, _spec: ["appended"])
        assert wrapped is not Base
        assert issubclass(wrapped, Base)
        assert wrapped.__name__ == f"Base{DOCTRINE_CLASS_SUFFIX}"
        assert wrapped().build_story(None) == ["base", "appended"]
        assert Base().build_story(None) == ["base"], "the base class was mutated"


# ---------------------------------------------------------------------------
# ISC-21.6 — the manifest records it, and it is reproducible
# ---------------------------------------------------------------------------


class TestManifestAndDeterminism:
    """ISC-21.6: ``contentFlags`` iff flagged, and a flagged case is stable."""

    pytestmark = requires_substrate

    def test_content_flags_are_present_exactly_when_non_empty(
        self, flagged_case: dict[str, Any]
    ) -> None:
        by_subtype = {entry["subtype"]: entry for entry in flagged_case["documents"]}
        assert set(by_subtype) == set(CASE_SUBTYPES)
        assert by_subtype[MULTI_HOOK_SUBTYPE]["contentFlags"] == ["escobedo", "kite"]
        assert by_subtype[SINGLE_HOOK_SUBTYPE]["contentFlags"] == ["escobedo"]
        assert "contentFlags" not in by_subtype[UNFLAGGED_SUBTYPE]

    def test_the_manifest_flags_agree_with_the_plan(self, flagged_case: dict[str, Any]) -> None:
        """Manifest provenance has to describe the plan that produced it."""
        plan = build_case_plan(_case_seed("doctrine-flagged", FLAGGED_HOOKS))
        planned = {
            document.subtype: list(document.content_flags)
            for document in plan.documents
            if document.content_flags
        }
        recorded = {
            entry["subtype"]: entry["contentFlags"]
            for entry in flagged_case["documents"]
            if "contentFlags" in entry
        }
        assert planned == recorded

    def test_the_seeded_hooks_still_reach_the_case_level_field(
        self, flagged_case: dict[str, Any]
    ) -> None:
        """The pre-existing ``doctrineHooks`` field is unchanged by all of this."""
        assert flagged_case["doctrineHooks"] == list(FLAGGED_HOOKS)

    def test_a_flagged_case_regenerates_byte_for_byte(
        self, tmp_path: Path, flagged_case: dict[str, Any]
    ) -> None:
        """The doctrine draw is seeded, so two runs must agree exactly.

        The paragraph is chosen from a private ``random.Random`` rather than the
        re-seeded global stream. That is what keeps the draw independent of how
        many documents rendered before it — and this is the assertion that would
        fail the moment someone reached for the global stream instead.
        """
        first = generate_case(_case_seed("doctrine-flagged", FLAGGED_HOOKS), tmp_path / "a")
        second = generate_case(_case_seed("doctrine-flagged", FLAGGED_HOOKS), tmp_path / "b")

        first_sums = {render.path.name: render.md5 for render in first.renders}
        second_sums = {render.path.name: render.md5 for render in second.renders}
        assert first_sums == second_sums
        assert len(first_sums) == len(CASE_SUBTYPES)

        first_manifest = (first.directory / MANIFEST_NAME).read_bytes()
        second_manifest = (second.directory / MANIFEST_NAME).read_bytes()
        assert first_manifest == second_manifest

        # ...and the module-scoped case generated earlier, in another directory.
        session_sums = {
            entry["filename"]: entry["md5Checksum"] for entry in flagged_case["documents"]
        }
        assert session_sums == first_sums

    def test_a_flagged_render_differs_from_its_unflagged_self(
        self, render_context: tuple[Any, Any], tmp_path: Path
    ) -> None:
        """Guards the determinism assertion above from passing on a no-op.

        Identical checksums prove reproducibility only if flagging changes the
        file at all. Compared at the render level, holding seed, cast, index,
        subtype and date fixed, so the only variable is the flag — see
        :meth:`test_only_the_hook_count_changes_an_untargeted_document` for why
        a case-level comparison cannot make this claim.
        """
        seed, cast = render_context
        checksums: dict[str, str] = {}
        for label, flags in (("clean", ()), ("flagged", ("kite",))):
            result = render_document(
                seed=seed,
                cast=cast,
                subtype=MULTI_HOOK_SUBTYPE,
                doc_date=date(2023, 6, 1),
                doc_format="pdf",
                index=6,
                out_path=tmp_path / f"{label}.pdf",
                content_flags=flags,
            )
            checksums[label] = result.md5
        assert checksums["clean"] != checksums["flagged"], "flagging rendered no content"

    def test_a_flag_whose_hook_does_not_target_the_subtype_appends_nothing(
        self, render_context: tuple[Any, Any], tmp_path: Path
    ) -> None:
        """Injection is scoped by target set, not by the presence of a flag.

        A hook reaching a document it has no content for must produce the
        unflagged file exactly — no heading over an empty section, and no
        checksum churn on documents a seeded doctrine has nothing to say about.
        """
        seed, cast = render_context
        checksums: dict[str, str] = {}
        results: dict[str, Any] = {}
        for label, flags in (("clean", ()), ("mismatched", FLAGGED_HOOKS)):
            result = render_document(
                seed=seed,
                cast=cast,
                subtype=UNFLAGGED_SUBTYPE,
                doc_date=date(2023, 6, 1),
                doc_format="pdf",
                index=7,
                out_path=tmp_path / f"{label}.pdf",
                content_flags=flags,
            )
            checksums[label] = result.md5
            results[label] = result
        assert checksums["clean"] == checksums["mismatched"], (
            "a hook with no content for this subtype still changed the file"
        )
        # ...and the recorded provenance must agree with the file. Storing the
        # requested flags verbatim would have this document claim two doctrines
        # it does not contain a word of.
        assert results["mismatched"].content_flags == (), (
            "the render recorded flags whose language it did not inject"
        )

    @pytest.mark.parametrize(
        ("requested", "expected"),
        [
            pytest.param(("kite",), ("kite",), id="applied"),
            pytest.param(("kite", "kite"), ("kite",), id="duplicate-collapsed"),
            pytest.param(("kite", "escobedo"), ("escobedo", "kite"), id="reordered-sorted"),
            pytest.param(("escobedo", "kite"), ("escobedo", "kite"), id="already-sorted"),
            pytest.param(("not_a_hook",), (), id="unknown-dropped"),
            pytest.param(("kite", "not_a_hook"), ("kite",), id="unknown-dropped-partially"),
            # A hook that targets nothing on this subtype is covered by
            # ``test_a_flag_whose_hook_does_not_target_the_subtype_appends_nothing``
            # above: every one of the fourteen targets AME_COMPREHENSIVE_REPORT,
            # so the skip case cannot be expressed against this subtype.
        ],
    )
    def test_recorded_flags_are_the_applied_flags(
        self,
        requested: tuple[str, ...],
        expected: tuple[str, ...],
        render_context: tuple[Any, Any],
        tmp_path: Path,
    ) -> None:
        """``RenderResult.content_flags`` is provenance, so it states what happened.

        ``render_document`` is public and takes whatever a caller passes:
        duplicates, arbitrary order, hooks that do not exist, and hooks with no
        content for this subtype. Every one of those has to canonicalize the
        same way the planner's own flags do, or the manifest describes a
        document that was never rendered.
        """
        seed, cast = render_context
        result = render_document(
            seed=seed,
            cast=cast,
            subtype=MULTI_HOOK_SUBTYPE,
            doc_date=date(2023, 6, 1),
            doc_format="pdf",
            index=8,
            out_path=tmp_path / "probe.pdf",
            content_flags=requested,
        )
        assert result.content_flags == expected

    def test_a_document_with_no_applied_flags_is_byte_identical_to_an_unflagged_one(
        self, render_context: tuple[Any, Any], tmp_path: Path
    ) -> None:
        """An unknown hook must not build a wrapper that appends an empty section."""
        seed, cast = render_context
        checksums = []
        for label, flags in (("clean", ()), ("unknown", ("not_a_hook",))):
            result = render_document(
                seed=seed,
                cast=cast,
                subtype=MULTI_HOOK_SUBTYPE,
                doc_date=date(2023, 6, 1),
                doc_format="pdf",
                index=9,
                out_path=tmp_path / f"{label}.pdf",
                content_flags=flags,
            )
            checksums.append(result.md5)
        assert checksums[0] == checksums[1]

    def test_only_the_hook_count_changes_an_untargeted_document(
        self, tmp_path: Path, unflagged_case: dict[str, Any]
    ) -> None:
        """The pre-existing coupling between hook *count* and case complexity.

        ``seed_to_case_parameters`` sets the substrate's complexity to
        ``complex`` when a seed names two or more doctrine hooks, which changes
        the clinical parameters of the whole case and therefore every document
        in it — including documents no doctrine targets. That behaviour predates
        this ticket and is not content injection, but it is exactly what makes a
        naive "flagged case versus unflagged case" diff misread: the control
        document moves for a reason that has nothing to do with doctrine
        language.

        Pinned here so the coupling is a documented property rather than a trap
        the next reader rediscovers as a bug. One hook keeps the case
        ``standard`` and leaves untargeted documents byte-identical; two flip it.
        """
        from wc_caseload_engine.lifecycle_bridge import seed_to_case_parameters

        assert seed_to_case_parameters(_case_seed("doctrine-complexity", ())).complexity == (
            "standard"
        )
        assert seed_to_case_parameters(
            _case_seed("doctrine-complexity", ("escobedo",))
        ).complexity == "standard"
        assert seed_to_case_parameters(
            _case_seed("doctrine-complexity", FLAGGED_HOOKS)
        ).complexity == "complex"

        one_hook = generate_case(_case_seed("doctrine-unflagged", ("escobedo",)), tmp_path / "one")
        one_sums = {render.subtype: render.md5 for render in one_hook.renders}
        clean_sums = {
            entry["subtype"]: entry["md5Checksum"] for entry in unflagged_case["documents"]
        }

        assert one_sums[UNFLAGGED_SUBTYPE] == clean_sums[UNFLAGGED_SUBTYPE], (
            "a document no hook targets changed at equal complexity — the injection "
            "is not scoped to its targets"
        )
        for subtype in (MULTI_HOOK_SUBTYPE, SINGLE_HOOK_SUBTYPE):
            assert one_sums[subtype] != clean_sums[subtype], (
                f"{subtype} rendered no doctrine content"
            )
