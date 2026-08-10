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

import os
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
#:     python -m pytest tests/test_qme_apportionment_seam.py -k record_helper -s
QME_UNGOVERNED_DIGESTS = {
    "qme:ame": {
        "pdf": "24b1c3ac41ae2868a67b4f9ca35175b35b99f0100a84007b2d851bbca2f5f557",
        "rng": "b70af22432f21fbc0789cddc9eff7f26b468c013ca13e4ef15775c4fcfdefc4e",
        "story": "32047b625165fdaee143dbdbb89eb7ccc873736a39be2eb4f4006cf741a2c831",
        "text": "bd3f1da7316a3cbacf2e81486b2ed2f40be87f5dc705b2c5817995177443a445"
    },
    "qme:none": {
        "pdf": "77ab452c526fd3b86ebe808c1de81bcb525d459bd855741eca09f592de0dc4e0",
        "rng": "b70af22432f21fbc0789cddc9eff7f26b468c013ca13e4ef15775c4fcfdefc4e",
        "story": "32047b625165fdaee143dbdbb89eb7ccc873736a39be2eb4f4006cf741a2c831",
        "text": "3102b77fb6c98033b6f7b60abe7aa3dbe642c5740b6e69bf5f34bc866201c3af"
    },
    "qme:supplemental": {
        "pdf": "5576ae1fb661a2f14f4dbf8fc5cb5a058cebf40da8df5aff431c5cc1aea536f6",
        "rng": "b70af22432f21fbc0789cddc9eff7f26b468c013ca13e4ef15775c4fcfdefc4e",
        "story": "32047b625165fdaee143dbdbb89eb7ccc873736a39be2eb4f4006cf741a2c831",
        "text": "c118f5e1f172644100f13ff431a6ddb444ad86109d75441e5375f888387aa844"
    }
}

_QME_VARIANTS = {"qme:none": None, "qme:ame": "ame", "qme:supplemental": "supplemental_qme"}

#: ``rng`` and ``story`` are comparable in any interpreter. ``text`` and ``pdf``
#: are not, and the reason is a substrate defect, not a flaw in the guard:
#: ``data/content_pools.py`` builds two pools with ``list(set(...))``, whose
#: order follows the interpreter's string hash seed. The QME report draws from
#: those pools; the templates AJC-66 baselined do not, which is why that
#: baseline pins all four unconditionally and this one cannot.
#:
#: So the words are pinned exactly where they are meaningful — under the
#: ``PYTHONHASHSEED=0`` the consuming engine and the CI step both set — and the
#: stream and structure are pinned everywhere. Comparing hash-dependent digests
#: in an interpreter that randomises them would fail for a reason that has
#: nothing to do with this seam, and teaching people to ignore a red test is
#: worse than pinning less.
_HASH_STABLE = os.environ.get("PYTHONHASHSEED") == "0"
_ALWAYS_COMPARABLE = ("rng", "story")


def _comparable(digest: dict) -> dict:
    if _HASH_STABLE:
        return digest
    return {k: digest[k] for k in _ALWAYS_COMPARABLE}


def _qme_digest(variant, extra_context=None):
    case = _baseline_case()
    spec = _baseline_spec("QME_REPORT_INITIAL", variant, extra_context)
    return render_digest(case, "pdf_templates.medical.qme_ame_report", "QmeAmeReport", spec)


@pytest.mark.parametrize("label", sorted(_QME_VARIANTS))
def test_ungoverned_qme_render_matches_its_recorded_digests(label):
    """The committed baseline for the default path.

    Four independent digests, because each sees a class of change the others
    miss: plain text misses a restyled heading, the flowable fingerprint misses
    reordered draws of equal consumption, the rng trace says everything about
    order and nothing about layout, and the PDF is the artifact that ships.

    Recorded against ``origin/main`` and verified equal there before this seam
    landed — which is the property that makes the numbers mean anything.
    """
    expected = QME_UNGOVERNED_DIGESTS[label]
    assert expected, f"{label} has no recorded digests; run the recorder"
    assert _comparable(_qme_digest(_QME_VARIANTS[label])) == _comparable(expected)


@pytest.mark.parametrize("label", sorted(_QME_VARIANTS))
def test_governance_absent_by_any_spelling_matches_the_same_digests(label):
    """Every "not governed" spelling is the recorded default.

    Absent, ``None`` and ``{}`` are three different inputs that must produce one
    output. This is the assertion a scratch sweep could not make, because a
    scratch run comparing two ungoverned renders can only ever agree with itself.
    """
    expected = _comparable(QME_UNGOVERNED_DIGESTS[label])
    for extra in ({}, {"apportionment": None}, {"apportionment": {}, "causation": {}}):
        actual = _comparable(_qme_digest(_QME_VARIANTS[label], extra))
        assert actual == expected, f"{label} moved on {extra!r}"


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


def test_governing_to_the_substrates_own_answer_is_a_pure_pass_through():
    """Say what it was going to say anyway and the render must not move at all.

    The strongest statement of "additive": a decision that agrees with the draw
    is invisible in the output, not merely equivalent in the stream. Swept over
    both sides of the zero boundary, since the substrate's pool is 4/7 zeros and
    the two sides take different code paths through the narrative builder.
    """
    for zero in (True, False):
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

            plain = build({})
            same = build(governed)

            plain_has = any("Apportionment \u2014" in t for t in plain)
            same_has = any("Apportionment \u2014" in t for t in same)
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
