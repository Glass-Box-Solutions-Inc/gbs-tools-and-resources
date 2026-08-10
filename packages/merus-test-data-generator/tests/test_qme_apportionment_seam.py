"""AJC-65 — the QME/AME apportionment and causation governance seam.

Apportionment is the most consequential opinion a QME writes: under LC §4663 it
decides how much of a permanent disability the employer pays for. The substrate
decided it with ``random.random() > 0.5`` between two canned sentences, drawn
independently of the percentage the impairment section had already printed, so a
single report could apportion 20% in one section and declare "no apportionment is
applicable" in another.

This suite pins both halves of the fix:

* **Governed** — when a caller puts apportionment/causation content on
  ``doc_spec.context``, the template renders that content instead of the coin
  flip, and the percentage reaches the impairment section too, so the two
  sections cannot contradict each other.
* **Ungoverned** — when it does not, the substrate's own path runs untouched.
  Byte-identical is the whole requirement here: this package is consumed by
  ``wc-synthetic-caseload-engine``, whose golden corpora pin every generated
  byte, so a seam that shifts one draw breaks four corpora.

The stream-parity tests are the load-bearing ones. A seam can render the right
words and still be wrong, by consuming a different number of ``random`` draws
than the path it replaced — every draw afterwards then answers a different
question, and the rest of the document silently rewrites itself. So the seam
*draws and discards* the coin flips it overrides, exactly as the consumer's own
``_ForcedChoice`` does, and these tests assert the stream ends where it started.
"""

from __future__ import annotations

import random
import re
from datetime import date

import pytest

from data.models import DocumentSpec, OutputFormat
from data.taxonomy import DocumentSubtype
from pdf_templates.medical.qme_ame_report import QmeAmeReport
from tests.render_baseline import build_fixture_case as _baseline_case
from tests.render_baseline import make_spec as _baseline_spec
from tests.render_baseline import render_digest

# The two sentences the substrate flips between, verbatim from the template.
_SUBSTRATE_NO_APPORTIONMENT = "No apportionment is applicable in this case."
_SUBSTRATE_ADDRESSED_ABOVE = "Apportionment has been addressed as outlined"


def _texts(flowables) -> list[str]:
    """The markup of every text-bearing flowable, in render order."""
    return [f.text for f in flowables if hasattr(f, "text")]


def _joined(flowables) -> str:
    return "\n".join(_texts(flowables))


def _spec(context=None, doc_date=date(2026, 3, 15)) -> DocumentSpec:
    return DocumentSpec(
        subtype=DocumentSubtype.QME_REPORT_INITIAL,
        title="QME Report",
        doc_date=doc_date,
        template_class="QmeAmeReport",
        output_format=OutputFormat.PDF,
        context=context if context is not None else {},
    )


def _build_seam_case():
    """A case with the same shape as the ``sample_case`` fixture.

    Module-level rather than a fixture because the seed-selection helpers below
    run at collection time, where fixtures do not exist yet.
    """
    from data.fake_data_generator import FakeDataGenerator
    from data.lifecycle_engine import CaseParameters

    return FakeDataGenerator(seed=123).generate_case_from_params(
        case_number=1,
        params=CaseParameters(
            target_stage="settlement",
            injury_type="specific",
            body_part_category="spine",
            num_body_parts=2,
            has_surgery=False,
            has_attorney=True,
            has_psych_component=False,
            complexity="standard",
        ),
    )


@pytest.fixture()
def qme(sample_case):
    return QmeAmeReport(sample_case)


@pytest.fixture()
def injury(sample_case):
    return sample_case.injuries[0] if sample_case.injuries else None


# ---------------------------------------------------------------------------
# The ungoverned path is the substrate, untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 1234])
def test_ungoverned_conclusions_still_flip_the_substrate_coin(qme, injury, seed):
    """No context, no governance: one of the two canned sentences, as before."""
    random.seed(seed)
    text = _joined(qme._build_conclusions(injury, _spec()))
    assert _SUBSTRATE_NO_APPORTIONMENT in text or _SUBSTRATE_ADDRESSED_ABOVE in text
    assert "<b>7. <b>Apportionment:</b>" not in text  # no double-wrapping


@pytest.mark.parametrize("seed", [3, 11, 808])
def test_ungoverned_causation_still_flips_entirely_or_predominantly(qme, injury, seed):
    random.seed(seed)
    text = _joined(qme._build_conclusions(injury, _spec()))
    assert ("is entirely attributable" in text) or ("is predominantly attributable" in text)


@pytest.mark.parametrize("seed", [5, 50, 500])
def test_an_absent_seam_consumes_no_draws(qme, injury, seed):
    """The stream after an ungoverned build is a pure function of the seed.

    Two builds from the same seed must leave ``random`` in the same place. A
    seam that drew *anything* on the ungoverned path — a feature probe, a
    default, a lookup — would be invisible here only if it drew the same amount
    twice, which is why this is paired with the parity tests below rather than
    trusted on its own.
    """
    random.seed(seed)
    first = _joined(qme._build_conclusions(injury, _spec()))
    tail_first = random.random()

    random.seed(seed)
    second = _joined(qme._build_conclusions(injury, _spec(context={})))
    tail_second = random.random()

    assert first == second
    assert tail_first == tail_second


@pytest.mark.parametrize(
    "context",
    [
        {"apportionment": {}},
        {"causation": {}},
        {"apportionment": {}, "causation": {}},
        {"apportionment": None, "causation": None},
        {"unrelated_key": "ignored"},
    ],
)
def test_an_empty_or_unrelated_seam_falls_through_to_the_coin_flip(qme, injury, context):
    """Present-but-empty is not governance. It must not half-render.

    The consumer puts many keys on every context and expects templates that have
    not opted in to ignore them; an empty dict arriving from a caller that
    governs nothing has to behave exactly like no dict at all.
    """
    random.seed(31337)
    ungoverned = _joined(qme._build_conclusions(injury, _spec()))
    tail_ungoverned = random.random()

    random.seed(31337)
    governed = _joined(qme._build_conclusions(injury, _spec(context=context)))
    tail_governed = random.random()

    assert governed == ungoverned
    assert tail_governed == tail_ungoverned


# ---------------------------------------------------------------------------
# Stream parity: governing the prose must not move a single later draw
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [2, 64, 777, 9001])
def test_governing_the_prose_changes_the_words_and_not_the_stream(qme, injury, seed):
    """The seam's central claim, stated as one test.

    Both assertions are needed and neither is sufficient. Stream parity alone is
    satisfied by a seam that renders nothing; changed prose alone is satisfied by
    a seam that skips the draws it replaces and silently rewrites everything
    downstream of it.
    """
    governed_context = {
        "apportionment": {
            "opinion": "Twenty-five percent of the permanent disability is apportioned "
            "to pre-existing degenerative disc disease.",
        },
        "causation": {
            "discussion": "The industrial injury is a substantial contributing cause "
            "of the current condition.",
        },
    }

    random.seed(seed)
    ungoverned = _joined(qme._build_conclusions(injury, _spec()))
    tail_ungoverned = random.random()

    random.seed(seed)
    governed = _joined(qme._build_conclusions(injury, _spec(context=governed_context)))
    tail_governed = random.random()

    assert tail_governed == tail_ungoverned, "the seam moved the RNG stream"
    assert governed != ungoverned, "the seam rendered nothing"


@pytest.mark.parametrize("seed", [13, 271])
def test_governing_only_apportionment_leaves_causation_on_its_coin_flip(qme, injury, seed):
    """The two opinions are governed independently."""
    random.seed(seed)
    ungoverned = _joined(qme._build_conclusions(injury, _spec()))
    causation_was_entirely = "is entirely attributable" in ungoverned

    random.seed(seed)
    governed = _joined(
        qme._build_conclusions(
            injury, _spec(context={"apportionment": {"register": "deferred"}})
        )
    )

    # Causation kept whichever side the coin gave it.
    assert ("is entirely attributable" in governed) is causation_was_entirely
    assert _SUBSTRATE_NO_APPORTIONMENT not in governed


def test_governing_prose_leaves_everything_after_the_conclusions_identical(qme, sample_case):
    """Nothing downstream of the governed sentences may move.

    The conclusions paragraph is expected to differ — that is the feature. The
    tail after it is the interesting part: the declaration, the signature block
    and the QME identifier are all drawn *after* the governed sentences, so any
    of them moving would mean the seam had shifted the random stream.
    """
    context = {
        "apportionment": {"opinion": "Apportionment governed by the ledger."},
        "causation": {"discussion": "Causation governed by the ledger."},
    }

    random.seed(20260809)
    plain = _texts(qme.build_story(_spec()))

    random.seed(20260809)
    governed = _texts(QmeAmeReport(sample_case).build_story(_spec(context=context)))

    def tail_after_conclusions(texts):
        idx = max(i for i, t in enumerate(texts) if "Apportionment:" in t)
        return texts[idx + 1:]

    assert tail_after_conclusions(plain) == tail_after_conclusions(governed)
    assert any("Apportionment governed by the ledger." in t for t in governed)
    assert any("Causation governed by the ledger." in t for t in governed)


# ---------------------------------------------------------------------------
# Governed content renders verbatim
# ---------------------------------------------------------------------------


def test_a_governed_opinion_renders_verbatim(qme, injury):
    opinion = (
        "Apportionment is 70% industrial and 30% nonindustrial, the nonindustrial "
        "share attributable to pre-existing spondylolisthesis documented on the "
        "1998 radiographs."
    )
    random.seed(4)
    text = _joined(
        qme._build_conclusions(injury, _spec(context={"apportionment": {"opinion": opinion}}))
    )
    assert opinion in text
    assert _SUBSTRATE_NO_APPORTIONMENT not in text
    assert _SUBSTRATE_ADDRESSED_ABOVE not in text


def test_a_governed_causation_discussion_renders_verbatim(qme, injury):
    discussion = (
        "Approximately 60% of the current condition is attributable to the "
        "industrial injury, with the remainder attributable to the natural "
        "progression of pre-existing disease."
    )
    random.seed(4)
    text = _joined(
        qme._build_conclusions(injury, _spec(context={"causation": {"discussion": discussion}}))
    )
    assert discussion in text
    assert "is entirely attributable" not in text
    assert "is predominantly attributable" not in text


@pytest.mark.parametrize("attribution", ["entirely", "predominantly", "partially"])
def test_a_governed_attribution_substitutes_into_the_substrate_sentence(
    qme, injury, attribution
):
    """The lighter knob: keep the substrate's sentence, pin only the adverb."""
    random.seed(4)
    text = _joined(
        qme._build_conclusions(
            injury, _spec(context={"causation": {"attribution": attribution}})
        )
    )
    assert f"is {attribution} attributable to the industrial injury" in text


def test_the_apportioned_register_states_both_shares_and_the_basis(qme, injury):
    random.seed(4)
    text = _joined(
        qme._build_conclusions(
            injury,
            _spec(
                context={
                    "apportionment": {
                        "register": "apportioned",
                        "nonindustrial_pct": 30,
                        "basis": "pre-existing degenerative disc disease",
                    }
                }
            ),
        )
    )
    assert "70%" in text, "the industrial share must be stated, not left to arithmetic"
    assert "30%" in text
    assert "pre-existing degenerative disc disease" in text
    assert "4663" in text


def test_the_none_register_states_no_apportionment(qme, injury):
    random.seed(4)
    text = _joined(
        qme._build_conclusions(injury, _spec(context={"apportionment": {"register": "none"}}))
    )
    assert _SUBSTRATE_NO_APPORTIONMENT in text
    assert _SUBSTRATE_ADDRESSED_ABOVE not in text


def test_the_deferred_register_defers_rather_than_opining(qme, injury):
    """A QME may lawfully decline to apportion yet; the seam must say so.

    Deferral is not "no apportionment" — it reserves the question. Collapsing
    the two would make the ledger unable to express the most common real posture
    at an initial evaluation.
    """
    random.seed(4)
    text = _joined(
        qme._build_conclusions(injury, _spec(context={"apportionment": {"register": "deferred"}}))
    )
    assert "deferred" in text.lower()
    assert _SUBSTRATE_NO_APPORTIONMENT not in text


def test_a_percentage_alone_infers_the_register(qme, injury):
    """M3 pins numbers; it should not have to also pin the word for the number."""
    random.seed(4)
    apportioned = _joined(
        qme._build_conclusions(
            injury, _spec(context={"apportionment": {"nonindustrial_pct": 20}})
        )
    )
    assert "20%" in apportioned and "80%" in apportioned

    random.seed(4)
    zero = _joined(
        qme._build_conclusions(injury, _spec(context={"apportionment": {"nonindustrial_pct": 0}}))
    )
    assert _SUBSTRATE_NO_APPORTIONMENT in zero


def test_an_explicit_opinion_outranks_a_register(qme, injury):
    """Precedence has to be stated, or two callers get two different documents."""
    random.seed(4)
    text = _joined(
        qme._build_conclusions(
            injury,
            _spec(
                context={
                    "apportionment": {
                        "register": "apportioned",
                        "nonindustrial_pct": 40,
                        "opinion": "The ledger's own sentence wins.",
                    }
                }
            ),
        )
    )
    assert "The ledger's own sentence wins." in text
    assert "60%" not in text, "the register's generated sentence must not also render"


# ---------------------------------------------------------------------------
# The percentage has to reach the impairment section, or the report contradicts
# itself exactly as it did before
# ---------------------------------------------------------------------------


def test_a_governed_percentage_reaches_the_impairment_section(sample_case):
    """The defect this ticket exists to close, asserted end to end.

    Governing only the conclusion sentence would leave ``impairment_rating_section``
    drawing its own independent percentage — the report would still contradict
    itself, just more confidently.

    Swept across seeds on purpose. The substrate's own pool is ``[0,0,0,10,15,20,25]``,
    so it prints an apportionment block for roughly three seeds in seven; a single
    lucky seed would pass this against a seam that governs nothing at all. Every
    seed must carry the block, and 35/65 is a split the substrate cannot draw.
    """
    context = {"apportionment": {"nonindustrial_pct": 35, "basis": "prior industrial injury"}}

    for seed in range(20):
        random.seed(seed)
        story = _joined(QmeAmeReport(sample_case).build_story(_spec(context=context)))

        assert "IMPAIRMENT RATING" in story
        assert "Apportionment —" in story, f"seed {seed}: impairment section printed no block"

        block = story.split("Apportionment —", 1)[1]
        assert "35" in block, f"seed {seed}: governed percentage never reached the block"
        assert "65" in block, f"seed {seed}: industrial complement missing"


def test_an_ungoverned_percentage_still_comes_from_the_substrate_draw(sample_case):
    """With nothing governed the impairment section keeps its own coin.

    Pinned across many seeds because the substrate's pool is 4/7 zeros: a single
    seed that happened to draw 0 would pass against a seam that had hard-wired 0.
    """
    seen = set()
    for seed in range(40):
        random.seed(seed)
        story = _joined(QmeAmeReport(sample_case).build_story(_spec()))
        seen.add("Apportionment —" in story)
    assert seen == {True, False}, "the ungoverned draw must still vary"


@pytest.mark.parametrize("seed", [555, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_impairment_section_ungoverned_is_the_untouched_draw(sample_case, seed):
    """``impairment_rating_section()`` with no decision is the old code.

    Other templates — the PR-4 path in ``TreatingPhysicianReport`` — call this
    with no arguments and must not shift by a single draw.
    """
    tpl = QmeAmeReport(sample_case)

    random.seed(seed)
    rendered = _joined(tpl.impairment_rating_section())
    tail = random.random()

    random.seed(seed)
    from data.ama_guides_content import generate_impairment_narrative
    drawn = random.choice([0, 0, 0, 10, 15, 20, 25])
    body_parts = sample_case.injuries[0].body_parts if sample_case.injuries else []
    specialty = (sample_case.qme_physician or sample_case.treating_physician).specialty
    narrative, _wpi, _r = generate_impairment_narrative(body_parts, specialty, drawn)
    legacy_tail = random.random()

    assert narrative.split("\n")[0] in rendered
    assert tail == legacy_tail, "the ungoverned section consumed a different number of draws"


# ---------------------------------------------------------------------------
# F1 — the governed value must not move the stream across the zero/nonzero
# boundary of the impairment narrative's own apportionment block
# ---------------------------------------------------------------------------


def _rng_trace_and_state(fn):
    """Run ``fn`` and return (result, ordered trace of every random call, state).

    The ordered trace is the instrument AJC-66 built for exactly this question.
    Final state alone records position, not order: two draws of equal
    consumption could be swapped and the state would land in the same place.
    """
    from tests.render_baseline import _TracingRandom

    with _TracingRandom() as tracer:
        result = fn()
        state = random.getstate()
    return result, list(tracer.trace), state


_APPORTIONMENT_POOL = [0, 0, 0, 10, 15, 20, 25]

#: Built once at import, because the order matters and it is easy to get wrong.
#: ``build_fixture_case()`` re-seeds ``random`` while it constructs, so building
#: a case *after* seeding silently discards the seed — an earlier version of the
#: selector below did that and observed the same drawn percentage for every seed
#: in the range, which is what a wiped seed looks like. Build the case, then
#: seed, then render.
_SEAM_CASE = _build_seam_case()
_SEAM_INJURY = _SEAM_CASE.injuries[0] if _SEAM_CASE.injuries else None


def _drawn_pct_in_story(seed, case=_SEAM_CASE):
    """The percentage the impairment section *actually* draws in a full render.

    Not the first draw at this seed. ``build_story`` consumes dozens of draws —
    history, records review, complaints, examination, diagnostics — before the
    impairment section reaches its own ``random.choice``, so reading the pool in
    a freshly seeded interpreter answers a different question. The first version
    of this helper did exactly that, and the seeds it picked for the zero/nonzero
    crossing were therefore arbitrary: the trace comparisons were still valid,
    but they could not claim to exercise the boundary they are named for.

    Observed by watching for a choice over the pool itself, which is unambiguous.
    """
    captured = []
    real_choice = random.choice

    def spy(seq):
        value = real_choice(seq)
        if list(seq) == _APPORTIONMENT_POOL:
            captured.append(value)
        return value

    random.choice = spy
    try:
        random.seed(seed)
        QmeAmeReport(case).build_story(_spec())
    finally:
        random.choice = real_choice

    assert captured, "the impairment section drew no apportionment percentage"
    return captured[0]


def _ungoverned_story_text(seed, case=None):
    """The full ungoverned document text at ``seed``.

    Always a whole ``build_story``. Reading a coin from a section builder called
    on its own is the recurring trap in this file: the section sits behind
    dozens of earlier draws, so standalone and in-document renders flip
    differently at the same seed.
    """
    random.seed(seed)
    return _joined(QmeAmeReport(case if case is not None else _SEAM_CASE).build_story(_spec()))


def _seeds_where_drawn_is(zero, limit=4):
    found = []
    for seed in range(300):
        if (_drawn_pct_in_story(seed) == 0) is zero:
            found.append(seed)
        if len(found) == limit:
            break
    assert found, f"no seed found with drawn-zero={zero}"
    return found


@pytest.mark.parametrize("seed", _seeds_where_drawn_is(zero=True))
def test_governing_a_positive_pct_over_a_drawn_zero_keeps_the_stream(seed):
    """Drawn 0, governed 35 — the classic stream-shifting shape.

    The impairment narrative's apportionment block consumes three extra draws
    when the percentage is positive and none when it is zero. If the governed
    value decided that branch, governing an apportionment would consume three
    draws the ungoverned render never made, and every draw afterwards — the
    future-medical content, the work restrictions, the conclusions' own coin
    flips, the signature identifier — would answer a different question.
    Consumption follows the *drawn* value; only the words follow the ledger.
    """
    assert _drawn_pct_in_story(seed) == 0

    def render(context):
        def _go():
            random.seed(seed)
            return _texts(QmeAmeReport(_SEAM_CASE).build_story(_spec(context=context)))

        return _rng_trace_and_state(_go)

    plain, plain_trace, plain_state = render({})
    governed, gov_trace, gov_state = render(
        {"apportionment": {"nonindustrial_pct": 35, "basis": "a prior industrial injury"}}
    )

    assert gov_trace == plain_trace, "the governed render made different random calls"
    assert gov_state == plain_state
    assert governed != plain, "the seam rendered nothing"
    assert any("35%" in t for t in governed)


@pytest.mark.parametrize("seed", _seeds_where_drawn_is(zero=False))
def test_governing_none_over_a_drawn_positive_keeps_the_stream(seed):
    """The opposite crossing: drawn positive, governed to no apportionment.

    Here the substrate *would* have consumed three draws. Suppressing the block
    must not stop it consuming them, or the stream shifts the other way.
    """
    assert _drawn_pct_in_story(seed) > 0

    def render(context):
        def _go():
            random.seed(seed)
            return _texts(QmeAmeReport(_SEAM_CASE).build_story(_spec(context=context)))

        return _rng_trace_and_state(_go)

    plain, plain_trace, plain_state = render({})
    governed, gov_trace, gov_state = render({"apportionment": {"register": "none"}})

    assert gov_trace == plain_trace, "the governed render made different random calls"
    assert gov_state == plain_state
    assert any("Apportionment \u2014" in t for t in plain), "control: the drawn block should render"
    assert not any("Apportionment \u2014" in t for t in governed), "'none' must suppress the block"


# ---------------------------------------------------------------------------
# F2 — the decision reaches BOTH sections, for every register
# ---------------------------------------------------------------------------

_DETERMINED = re.compile(r"\b\d{1,3}% of the current permanent disability is apportioned\b")


@pytest.mark.parametrize("register", ["none", "deferred"])
def test_a_reserved_register_states_no_determined_percentage_anywhere(sample_case, register):
    """A report that reserves apportionment must not assign one elsewhere.

    Swept, because the substrate draws a positive percentage for roughly three
    seeds in seven: a single seed that drew zero would pass against a seam that
    never reached the impairment section at all.
    """
    context = {"apportionment": {"register": register}}
    for seed in range(30):
        random.seed(seed)
        story = _joined(QmeAmeReport(sample_case).build_story(_spec(context=context)))
        assert not _DETERMINED.search(story), f"seed {seed}: {register!r} assigned a percentage"
        assert "Escobedo" not in story, f"seed {seed}: invented a degenerative apportionment"
        assert "genetic predisposition" not in story, f"seed {seed}: invented constitutional causation"
        if register == "deferred":
            assert "deferred" in story.lower()


def test_the_callers_basis_appears_in_both_apportionment_sections(sample_case):
    """One basis, both places — and no invented substitute in either."""
    basis = "a documented prior industrial injury to the same region"
    context = {
        "apportionment": {"register": "apportioned", "nonindustrial_pct": 30, "basis": basis},
    }
    for seed in range(20):
        random.seed(seed)
        texts = _texts(QmeAmeReport(sample_case).build_story(_spec(context=context)))
        story = "\n".join(texts)

        conclusion = [t for t in texts if "Apportionment:" in t]
        # The narrative is split on newlines into one Paragraph per line, so the
        # block is its header flowable plus the body flowable that follows it.
        header_at = [i for i, t in enumerate(texts) if "Apportionment \u2014" in t]
        assert conclusion, f"seed {seed}: no conclusion apportionment"
        assert header_at, f"seed {seed}: no impairment apportionment block"
        impairment_body = texts[header_at[0] + 1]

        assert basis in conclusion[0], f"seed {seed}: basis missing from the conclusion"
        assert basis in impairment_body, f"seed {seed}: basis missing from the impairment block"
        assert "Escobedo" not in story
        assert "genetic predisposition" not in story
        assert "70%" in impairment_body and "30%" in impairment_body


# ---------------------------------------------------------------------------
# F3 — malformed governance raises; it never silently restores randomness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block", ["apportioned", ["apportioned"], True, 30, 30.5, ("none",)]
)
def test_a_non_mapping_apportionment_block_raises(qme, injury, block):
    """Refused rather than guessed at, per the AJC-66 convention.

    Treating a malformed block as absent is the dangerous reading: it restores
    the coin flip precisely when a caller believed it had governed the document.
    """
    random.seed(4)
    with pytest.raises(ValueError, match="apportionment"):
        qme._build_conclusions(injury, _spec(context={"apportionment": block}))


@pytest.mark.parametrize("register", ["APPORTIONED", "partial", "none ", "unknown", 3, ["none"]])
def test_an_unrecognised_register_raises(qme, injury, register):
    random.seed(4)
    with pytest.raises(ValueError, match="register"):
        qme._build_conclusions(injury, _spec(context={"apportionment": {"register": register}}))


@pytest.mark.parametrize("pct", [-1, 101, 1000, 12.5, "30", float("nan")])
def test_an_out_of_range_or_non_integer_percentage_raises(qme, injury, pct):
    random.seed(4)
    with pytest.raises(ValueError, match="nonindustrial_pct"):
        qme._build_conclusions(
            injury, _spec(context={"apportionment": {"nonindustrial_pct": pct}})
        )


@pytest.mark.parametrize(
    "block",
    [
        {"register": "none", "nonindustrial_pct": 25},
        {"register": "deferred", "nonindustrial_pct": 1},
        {"register": "apportioned"},
        {"register": "apportioned", "nonindustrial_pct": 0},
    ],
)
def test_contradictory_combinations_raise(qme, injury, block):
    """A register and a percentage that disagree describe two different reports."""
    random.seed(4)
    with pytest.raises(ValueError):
        qme._build_conclusions(injury, _spec(context={"apportionment": block}))


def test_an_unknown_key_raises_rather_than_governing_nothing(qme, injury):
    """A misspelling must not look like governance while doing nothing."""
    random.seed(4)
    with pytest.raises(ValueError, match="unknown key"):
        qme._build_conclusions(
            injury, _spec(context={"apportionment": {"nonindustrial_percent": 30}})
        )


@pytest.mark.parametrize("block", ["verbatim", ["a"], 7, True])
def test_a_non_mapping_causation_block_raises(qme, injury, block):
    random.seed(4)
    with pytest.raises(ValueError, match="causation"):
        qme._build_conclusions(injury, _spec(context={"causation": block}))


@pytest.mark.parametrize(
    "block", [{"attribution": ""}, {"discussion": "   "}, {"attribution": 5}, {"nonsense": "x"}]
)
def test_malformed_causation_content_raises(qme, injury, block):
    random.seed(4)
    with pytest.raises(ValueError):
        qme._build_conclusions(injury, _spec(context={"causation": block}))


def test_ajc66_variant_content_on_the_same_context_stays_inert_here(qme, injury):
    """The two seams share a context channel and must not activate each other."""
    random.seed(31337)
    plain = _joined(qme._build_conclusions(injury, _spec()))
    random.seed(31337)
    other = _joined(
        qme._build_conclusions(injury, _spec(context={"variant_content": {"diagnostic": True}}))
    )
    assert plain == other


# ---------------------------------------------------------------------------
# F4 — the evidence, shipped
#
# The byte-level proof for this seam originally lived in a scratch script: six
# fixed-seed PDF renders hashed before and after, a 500-render digest sweep, and
# a character comparison of the fallback sentences. All of it passed, and none
# of it was committed, so none of it would ever run again — and none of it would
# have caught the governed-path stream shift that review found, because the
# scratch runs only ever compared ungoverned output.
#
# A claim is shipped only when a committed test asserts it. These do.
# ---------------------------------------------------------------------------


#: Recorded from the ungoverned QME/AME render on the AJC-66 baseline harness,
#: which pins ReportLab to invariant output and freezes the clock. Four digests
#: per case: story text, flowable geometry, an ordered trace of every random
#: call, and the PDF bytes a consumer actually ships.
#:
#: These move only when the ungoverned render moves. Re-record deliberately, in
#: the same commit as the change that justifies it, or the guard means nothing:
#:
#:     env PYTHONPATH=. env PYTHONHASHSEED=0 python3 tests/ajc72_cross_python_probe.py
#:     env PYTHONPATH=. env PYTHONHASHSEED=0 .venv/bin/python tests/ajc72_cross_python_probe.py
QME_UNGOVERNED_DIGESTS = {
    "qme:ame": {
        "rng": "b70af22432f21fbc0789cddc9eff7f26b468c013ca13e4ef15775c4fcfdefc4e",
        "story": "32047b625165fdaee143dbdbb89eb7ccc873736a39be2eb4f4006cf741a2c831",
        "text": "cf2922df3bff0eccf24f2c2d32f9bb8478c444a98e48809d578c168d64f5973e",
        "pdf": "89b100a71ea330171d28c11066eaba00b23a3a327ece997d2efcdf9fb96822cb"
    },
    "qme:none": {
        "rng": "b70af22432f21fbc0789cddc9eff7f26b468c013ca13e4ef15775c4fcfdefc4e",
        "story": "32047b625165fdaee143dbdbb89eb7ccc873736a39be2eb4f4006cf741a2c831",
        "text": "3f286f1bfe94c1473579f7106ad88defcd754962db29207ed3a2cf59dff8f9a5",
        "pdf": "f36c97cc65814dd3a82cc6d36a832df8e68a601502e6c0b535ae9603c444073d"
    },
    "qme:supplemental": {
        "rng": "b70af22432f21fbc0789cddc9eff7f26b468c013ca13e4ef15775c4fcfdefc4e",
        "story": "32047b625165fdaee143dbdbb89eb7ccc873736a39be2eb4f4006cf741a2c831",
        "text": "a1a0b16fb0638e53106d097105fa078cc3ecfbdde22628b78a5cd194e4cc8df6",
        "pdf": "ca5d33370f31e4b7133872990ee85f6bfcff051c24c42bcc69fdf4c2b9eabe80"
    }
}

_QME_VARIANTS = {"qme:none": None, "qme:ame": "ame", "qme:supplemental": "supplemental_qme"}

#: Recorded as absolute ``rng``, ``story``, ``text``, and ``pdf`` digests for
#: this test suite. The four values are stable under the pinned toolchain and both
#: interpreters used in this check, while still proving seam behavior on RNG order,
#: rendered flowables, rendered text, and shipped bytes.
_ABSOLUTE_KEYS = ("rng", "story", "text", "pdf")


def _absolute(digest: dict) -> dict:
    return {k: digest[k] for k in _ABSOLUTE_KEYS}


def _qme_digest(variant, extra_context=None):
    case = _baseline_case()
    spec = _baseline_spec("QME_REPORT_INITIAL", variant, extra_context)
    return render_digest(case, "pdf_templates.medical.qme_ame_report", "QmeAmeReport", spec)


@pytest.mark.parametrize("label", sorted(_QME_VARIANTS))
def test_ungoverned_qme_render_matches_its_recorded_digests(label):
    """The committed baseline for the default path.

    The rng trace is the one that matters here: it is an *ordered* record of
    every ``random`` call the render makes, so it catches a seam that consumed a
    different number of draws, and also one that consumed the same number in a
    different order — which a final-state comparison cannot see. The story
    fingerprint catches a restyled heading or a resized spacer that plain text
    would miss.

    Recorded against ``origin/main`` and verified equal there before this seam
    landed, which is the property that makes the numbers mean anything.
    """
    expected = QME_UNGOVERNED_DIGESTS[label]
    assert expected, f"{label} has no recorded digests; run the recorder"
    assert _absolute(_qme_digest(_QME_VARIANTS[label])) == expected


@pytest.mark.parametrize("label", sorted(_QME_VARIANTS))
def test_governance_absent_by_any_spelling_is_byte_identical(label):
    """Every "not governed" spelling renders the same document, to the byte.

    Absent, ``None`` and ``{}`` are three different inputs that must produce one
    output. Compared against a baseline computed in this same process, so all
    four digests participate — including the PDF bytes a consumer ships, which
    could not be asserted against a recorded constant.
    """
    variant = _QME_VARIANTS[label]
    baseline = _qme_digest(variant)
    assert _absolute(baseline) == QME_UNGOVERNED_DIGESTS[label]

    for extra in ({}, {"apportionment": None}, {"apportionment": {}, "causation": {}}):
        assert _qme_digest(variant, extra) == baseline, f"{label} moved on {extra!r}"


def test_governed_renders_change_the_pdf_but_not_the_rng_trace():
    """The whole thesis, on the shipped artifact rather than on flowable text.

    ``rng`` equal proves the seam consumed exactly the draws the substrate would
    have; ``pdf`` and ``text`` different prove it actually rendered something.
    Asserted for a percentage, for a suppression, and for a deferral, because
    those are the three shapes that reach the impairment section differently.
    """
    plain = _qme_digest(None)
    for governed in (
        {"apportionment": {"nonindustrial_pct": 35, "basis": "a prior industrial injury"}},
        {"apportionment": {"register": "none"}},
        {"apportionment": {"register": "deferred"}},
        {"causation": {"attribution": "partially"}},
    ):
        actual = _qme_digest(None, governed)
        assert actual["rng"] == plain["rng"], f"{governed!r} moved the random stream"
        assert actual["pdf"] != plain["pdf"], f"{governed!r} rendered nothing"
        assert actual["text"] != plain["text"], f"{governed!r} rendered nothing"


def _digest_at_seed(seed, context=None, case=None):
    """The four AJC-66 digests for one render at an arbitrary seed.

    ``render_digest`` pins its own ``RENDER_SEED``; the pass-through property
    below has to be asserted at seeds chosen for which branch they take, so the
    same four measures are taken here against a caller-supplied seed. Built from
    the harness's own pieces rather than reimplemented, so a change to what the
    baseline measures reaches this too.
    """
    import hashlib
    import tempfile
    from pathlib import Path

    from tests.render_baseline import (
        _ensure_invariant_pdfs,
        _story_fingerprint,
        _TracingRandom,
        frozen_clock,
    )

    _ensure_invariant_pdfs()
    case = case if case is not None else _SEAM_CASE
    spec = _spec(context=context)

    with frozen_clock(), _TracingRandom() as tracer:
        random.seed(seed)
        story = QmeAmeReport(case).build_story(spec)
        state_after = random.getstate()

    text = QmeAmeReport(case)._story_to_plaintext(story)
    trace_blob = "\n".join(tracer.trace) + f"\nSTATE:{state_after!r}"

    with tempfile.TemporaryDirectory() as tmp, frozen_clock():
        out = Path(tmp) / "render.pdf"
        random.seed(seed)
        QmeAmeReport(case).generate(out, spec)
        pdf_bytes = out.read_bytes()

    def sha(value):
        raw = value if isinstance(value, bytes) else value.encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    return {
        "text": sha(text),
        "story": sha(_story_fingerprint(story)),
        "rng": sha(trace_blob),
        "pdf": sha(pdf_bytes),
    }


def _seeds_reproducible_by_the_none_register(limit=3):
    """Seeds where ``register: "none"`` reproduces the substrate's own answer.

    Exact reproduction needs both draws to agree with the decision: the
    impairment percentage must have come up zero (so the substrate printed no
    apportionment block, which is what ``none`` renders) *and* the conclusion
    coin must have chosen the no-apportionment sentence (which is the sentence
    ``none`` renders, verbatim). Roughly 4/7 x 1/2 of seeds qualify.
    """
    found = []
    for seed in range(300):
        if _drawn_pct_in_story(seed) != 0:
            continue
        # Read the coin from a *full* render. Calling ``_build_conclusions``
        # directly at this seed answers a different question: build_story
        # consumes dozens of draws before the conclusions are reached, so the
        # sentence it flips to standalone is not the one the document gets.
        if _SUBSTRATE_NO_APPORTIONMENT in _ungoverned_story_text(seed):
            found.append(seed)
        if len(found) == limit:
            break
    assert found, "no seed reproduces the substrate answer via the 'none' register"
    return found


@pytest.mark.parametrize("seed", _seeds_reproducible_by_the_none_register())
def test_governing_to_the_substrates_own_answer_is_byte_identical(seed):
    """Say what it was going to say anyway and **nothing** moves.

    The strongest available statement of "additive", and the one this test used
    to only gesture at: an earlier version asserted merely that both renders
    contained the impairment heading, which is true of renders that differ in
    every other respect. All four digests are compared now — the plain text, the
    flowable geometry, the ordered rng trace, and the PDF bytes.

    Exact reproduction is only possible where the decision can express the
    substrate's own answer completely, which is why the seeds are selected
    rather than arbitrary: ``none`` renders no impairment block and the verbatim
    no-apportionment sentence, so it matches exactly when both draws agreed.
    Where reproduction is impossible — a governed percentage cannot reproduce
    the substrate's randomly chosen Escobedo or constitutional narrative — the
    property asserted instead is branch preservation, in the test below.
    """
    assert _digest_at_seed(seed, {"apportionment": {"register": "none"}}) == _digest_at_seed(seed)


@pytest.mark.parametrize("seed", [0, 3, 11, 42])
def test_governing_causation_to_its_drawn_adverb_is_byte_identical(seed):
    """The causation half of the same property, and it is exactly reproducible.

    ``attribution`` substitutes one word into the substrate's own sentence, so
    governing it to the word the coin produced must be indistinguishable from
    not governing it at all.
    """
    plain = _ungoverned_story_text(seed)
    adverb = "entirely" if "is entirely attributable" in plain else "predominantly"

    governed = {"causation": {"attribution": adverb}}
    assert _digest_at_seed(seed, governed) == _digest_at_seed(seed)


@pytest.mark.parametrize("zero", [True, False])
def test_governing_the_percentage_preserves_the_impairment_branch(zero):
    """Where exact reproduction is impossible, the branch must still be preserved.

    A governed percentage renders the caller's own basis, so it cannot reproduce
    the substrate's randomly chosen Escobedo or constitutional narrative and the
    text digest legitimately moves. What must not move is *whether* the
    impairment section states an apportionment at all, because that is the fact
    the rest of the document's draws depend on.
    """
    for seed in _seeds_where_drawn_is(zero=zero, limit=3):
        drawn = _drawn_pct_in_story(seed)
        if drawn == 0:
            governed = {"apportionment": {"register": "none"}}
        else:
            governed = {
                "apportionment": {"register": "apportioned", "nonindustrial_pct": drawn}
            }

        def build(context):
            random.seed(seed)
            return _texts(QmeAmeReport(_SEAM_CASE).build_story(_spec(context=context)))

        plain_has = any("Apportionment \u2014" in t for t in build({}))
        same_has = any("Apportionment \u2014" in t for t in build(governed))

        assert plain_has == (drawn > 0), f"seed {seed}: control disagrees with the draw"
        assert same_has == plain_has, (
            f"seed {seed}: governing to the drawn value {drawn} changed whether the "
            f"impairment section states an apportionment at all"
        )


def _story_for(extra_context):
    from tests.render_baseline import RENDER_SEED, frozen_clock

    case = _baseline_case()
    spec = _baseline_spec("QME_REPORT_INITIAL", None, extra_context)
    with frozen_clock():
        random.seed(RENDER_SEED)
        return QmeAmeReport(case).build_story(spec)


def test_the_fallback_sentences_are_the_substrates_own_words():
    """The ungoverned prose is the template's original text, not a paraphrase.

    A reworded fallback would keep every structural test green while changing
    what four golden corpora render.
    """
    from data.apportionment import SENTENCE_ADDRESSED as ADDRESSED
    from data.apportionment import SENTENCE_NONE as NONE

    assert NONE == (
        "No apportionment is applicable in this case. The entire permanent disability is "
        "attributable to the industrial injury. There is no credible evidence of pre-existing "
        "pathology contributing to the current impairment."
    )
    assert ADDRESSED == (
        "Apportionment has been addressed as outlined in the impairment rating section of this "
        "report per LC \u00a74663 and \u00a74664."
    )


def test_the_ungoverned_branch_mapping_is_pinned(sample_case):
    """Exact branch counts over a fixed seed range.

    Not a smoke test: it pins *which* seeds take *which* branch. A change that
    consumed one extra draw anywhere earlier in the document would keep the
    totals plausible while moving individual seeds, and this notices that.
    """
    no_apportionment = []
    for seed in range(60):
        random.seed(seed)
        text = _joined(QmeAmeReport(sample_case)._build_conclusions(
            sample_case.injuries[0], _spec()
        ))
        if _SUBSTRATE_NO_APPORTIONMENT in text:
            no_apportionment.append(seed)

    assert no_apportionment == PINNED_NO_APPORTIONMENT_SEEDS


#: Which seeds render "no apportionment is applicable" in the ungoverned
#: conclusions, over ``range(60)``. Recorded from origin/main before this seam
#: existed.
PINNED_NO_APPORTIONMENT_SEEDS: list[int] = [1, 5, 7, 10, 11, 12, 13, 14, 15, 17, 19, 20, 21, 23, 25, 27, 28, 29, 33, 34, 35, 36, 37, 38, 44, 46, 48, 50, 52, 54, 58, 59]


# ---------------------------------------------------------------------------
# Round 2 — the closing set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block",
    [
        {"basis": "prior industrial injury"},
        {"basis": "degenerative disc disease documented pre-injury"},
        {"register": "deferred", "nonindustrial_pct": 0},
        {"register": "deferred", "nonindustrial_pct": 25},
        {"register": "none", "nonindustrial_pct": 25},
        {"register": "apportioned"},
        {"register": "apportioned", "nonindustrial_pct": 0},
    ],
)
def test_a_non_empty_block_never_falls_back_to_the_coin_flip(qme, injury, block):
    """The last way "refuse, don't guess" could be bypassed.

    Two shapes used allowed keys to slip past validation and land back on the
    substrate's randomness:

    * ``{"basis": ...}`` alone parsed to ``None`` — a non-empty payload sitting
      in the context, unread, while both coin flips ran. It is the shape that
      most looks like governance and least is: it says what an apportionment
      rests on without saying whether there is one.
    * ``{"register": "deferred", "nonindustrial_pct": 0}`` was accepted with the
      zero silently discarded. Deferring means no percentage has been
      determined, so *any* percentage contradicts it — including zero, which
      reads as a deliberate statement and was being thrown away.

    Empty and absent stay valid ways to govern nothing; a non-empty block does
    not.
    """
    with pytest.raises(ValueError):
        qme._build_conclusions(injury, _spec(context={"apportionment": block}))


@pytest.mark.parametrize(
    "block",
    [
        {"basis": "prior industrial injury"},
        {"register": "deferred", "nonindustrial_pct": 0},
        {"register": "none", "nonindustrial_pct": 40},
        "not-a-mapping",
        {"register": "unknown"},
        {"nonindustrial_pct": 101},
    ],
)
def test_rejected_governance_consumes_no_rendering_rng(block):
    """A refused request must not advance the caller's random stream.

    Otherwise the cost of a rejected block depends on how far the render got
    before noticing — and a caller retrying after fixing its input would get a
    different document than if it had been right the first time.
    """
    spec = _spec(context={"apportionment": block})

    random.seed(9090)
    before = random.getstate()
    with pytest.raises(ValueError):
        QmeAmeReport(_SEAM_CASE).build_story(spec)
    assert random.getstate() == before, "a rejected block consumed randomness"

    random.seed(9090)
    before = random.getstate()
    with pytest.raises(ValueError):
        QmeAmeReport(_SEAM_CASE)._build_conclusions(_SEAM_INJURY, spec)
    assert random.getstate() == before, "a rejected block consumed randomness"


def test_a_full_build_parses_each_governance_block_exactly_once(monkeypatch):
    """Parse-once was the stated design; this is what makes it true.

    Both sections must render from the *same* object, not from two parses that
    happen to agree today. Counting the calls is the only assertion that holds
    a future refactor to it — an extra parse is invisible in the output right up
    until the two readings diverge.
    """
    import data.apportionment as ap
    import pdf_templates.medical.qme_ame_report as qme_mod

    calls = {"apportionment": 0, "causation": 0}
    real_ap, real_ca = ap.parse_apportionment, ap.parse_causation

    def spy_ap(context):
        calls["apportionment"] += 1
        return real_ap(context)

    def spy_ca(context):
        calls["causation"] += 1
        return real_ca(context)

    monkeypatch.setattr(qme_mod, "parse_apportionment", spy_ap)
    monkeypatch.setattr(qme_mod, "parse_causation", spy_ca)

    context = {
        "apportionment": {"register": "apportioned", "nonindustrial_pct": 30},
        "causation": {"attribution": "predominantly"},
    }
    random.seed(4242)
    QmeAmeReport(_SEAM_CASE).build_story(_spec(context=context))

    assert calls == {"apportionment": 1, "causation": 1}


def test_malformed_governance_raises_before_the_first_random_call(monkeypatch):
    """Validation happens at the top of the render, not partway down.

    Asserted by making *any* draw a failure: if the template reaches a coin flip
    before noticing the block is malformed, this raises the wrong exception and
    the test fails on the message.
    """
    import pdf_templates.medical.qme_ame_report as qme_mod

    class _Tripwire:
        def __getattr__(self, name):
            raise AssertionError(f"random.{name} was called before validation")

    monkeypatch.setattr(qme_mod, "random", _Tripwire())

    with pytest.raises(ValueError, match="apportionment"):
        QmeAmeReport(_SEAM_CASE).build_story(
            _spec(context={"apportionment": "not-a-mapping"})
        )


def test_a_preparsed_decision_is_used_rather_than_reparsed(qme, injury):
    """The standalone entry point still parses; the prepared one does not.

    Both halves matter. A builder that ignored what it was handed would silently
    re-derive, defeating parse-once; one that required it would stop working
    when called directly.
    """
    from data.apportionment import ApportionmentDecision

    prepared = ApportionmentDecision("apportioned", 45, "a prior award", None)

    # The context says something different, and must be ignored in favour of the
    # decision the caller prepared.
    spec = _spec(context={"apportionment": {"register": "none"}})
    random.seed(4)
    text = _joined(qme._build_conclusions(injury, spec, apportionment=prepared))
    assert "45%" in text and "55%" in text
    assert _SUBSTRATE_NO_APPORTIONMENT not in text

    # Called standalone, the same spec parses and yields 'none'.
    random.seed(4)
    standalone = _joined(qme._build_conclusions(injury, spec))
    assert _SUBSTRATE_NO_APPORTIONMENT in standalone
