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
from datetime import date

import pytest

from data.models import DocumentSpec, OutputFormat
from data.taxonomy import DocumentSubtype
from pdf_templates.medical.qme_ame_report import QmeAmeReport

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


def test_governing_prose_leaves_the_rest_of_the_report_identical(qme, sample_case):
    """A surgical diff: only the governed sentences move, nowhere else."""
    context = {
        "apportionment": {"opinion": "Apportionment governed by the ledger."},
        "causation": {"discussion": "Causation governed by the ledger."},
    }

    random.seed(20260809)
    plain = _texts(qme.build_story(_spec()))

    random.seed(20260809)
    governed = _texts(QmeAmeReport(sample_case).build_story(_spec(context=context)))

    assert len(plain) == len(governed)
    differing = [i for i, (a, b) in enumerate(zip(plain, governed)) if a != b]
    assert len(differing) == 1, f"expected only the conclusions block to move, got {differing}"
    assert "Apportionment governed by the ledger." in governed[differing[0]]
    assert "Causation governed by the ledger." in governed[differing[0]]


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
                        "register": "none",
                        "nonindustrial_pct": 40,
                        "opinion": "The ledger's own sentence wins.",
                    }
                }
            ),
        )
    )
    assert "The ledger's own sentence wins." in text
    assert _SUBSTRATE_NO_APPORTIONMENT not in text


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


def test_impairment_section_default_argument_is_the_untouched_draw(sample_case):
    """``impairment_rating_section()`` called with no argument is the old code.

    Other templates (the PR-4 path in ``TreatingPhysicianReport``) call this with
    no arguments and must not shift by one draw.
    """
    tpl = QmeAmeReport(sample_case)

    random.seed(555)
    default = _joined(tpl.impairment_rating_section())
    tail_default = random.random()

    # Peek at the value the substrate would draw, then rewind. Reading it by
    # drawing it would advance the stream by one and the comparison would be
    # against a different starting position — which is the very confusion the
    # draw-and-discard exists to prevent.
    random.seed(555)
    state = random.getstate()
    would_draw = random.choice([0, 0, 0, 10, 15, 20, 25])
    random.setstate(state)

    explicit = _joined(tpl.impairment_rating_section(apportionment_pct=would_draw))
    tail_explicit = random.random()

    assert explicit == default, "governing to the drawn value must be a pure pass-through"
    assert tail_explicit == tail_default
