"""AJC-37 Phase 3b — letter lifecycle, delay chains, cadence, discovery volumes.

The file opens with the ordinal-plumbing tests because they document a defect
that shipped in Phase 2 and was invisible to Phase 2's own suite. The substrate
threads ``doc_spec`` as a *parameter* to ``build_story`` and never assigns
``self.doc_spec``, so every helper here that read ``template.doc_spec.context``
returned its fallback. ``_facts_of`` survived on the ``_wc_case_facts``
instance attribute the renderer sets; ``_report_ordinal`` and ``_index_of`` had
no such fallback and were pinned at 0 for the life of the feature.

Phase 2's render test asked ``any(phrase in body for phrase in arc)``. At
ordinal 0 the first phrase of the arc *is* a phrase of the arc, so the
assertion passed while the trajectory never advanced — the vacuous-assertion
class again, and the reason the tests below count *distinct* phrases instead.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

import wc_caseload_engine.fact_templates as fact_templates
from conftest import extract_text, requires_substrate
from wc_caseload_engine.case_facts import TRAJECTORY_PHRASES
from wc_caseload_engine.fact_templates import ANCHOR_REFERENCE_MARKER
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.message_audit import DIRECTIVE_VERBS, clauses, first_word
from wc_caseload_engine.planner import (
    ATTORNEY_CADENCE_SUBTYPES,
    CADENCE_ANCHOR_SUBTYPES,
    CADENCE_MIN_LETTERS,
    DELAY_CHAIN_SUBTYPE,
    DISCOVERY_PACKET_SUBTYPES,
    EVENT_DRIVEN_LAG_DAYS,
    build_case_plan,
    event_driven_max_lag_days,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.substrate import import_substrate
from wc_caseload_engine.taxonomy import effective_taxonomy

pytestmark = requires_substrate


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _body(case_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 7100,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
        "documents": {"format_mix": {"pdf": 1.0}},
        "output": {"formats": ["pdf"]},
    }
    body.update(overrides)
    return body


def _seed(case_id: str, **overrides: Any) -> Any:
    return parse_case_seed(_body(case_id, **overrides))


def _render(seed: Any, out_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    generate_case(seed, out_dir, case_number=1)
    case_dir = out_dir / seed.case_id
    manifest = json.loads((case_dir / MANIFEST_NAME).read_text())
    texts: dict[str, str] = {}
    for entry in manifest["documents"]:
        path = case_dir / "documents" / entry["filename"]
        texts.setdefault(entry["subtype"], "")
        texts[entry["subtype"]] += "\n" + (extract_text(path, entry["format"]) or "")
    return manifest, texts


def _all_text(texts: dict[str, str]) -> str:
    return _flat("\n".join(texts.values()))


def _observed(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    """Every value the named ordinal helper actually returned during a render."""
    seen: list[int] = []
    original = getattr(fact_templates, name)

    def spy(template: Any) -> int:
        value = original(template)
        seen.append(value)
        return value

    monkeypatch.setattr(fact_templates, name, spy)
    return seen


#: The sentence each substrate letter type opens with. Pinned so a substrate
#: edit fails here loudly rather than turning the lifecycle assertions vacuous.
LETTER_MARKERS: dict[str, str] = {
    "initial_acceptance": "accepted liability for the industrial injury",
    "pd_advance_offer": "discuss a permanent disability advance with your client",
    "settlement_discussion": "initiate discussions regarding potential resolution",
    "medical_records_request": "in the process of evaluating the above-referenced claim",
    "ur_decision": "a utilization review determination has been made",
}


def _letters_present(body: str) -> set[str]:
    return {name for name, marker in LETTER_MARKERS.items() if marker in body}


# ---------------------------------------------------------------------------
# The ordinal seam — a Phase-2 defect this phase inherits
# ---------------------------------------------------------------------------


class TestOrdinalsReachTheTemplate:
    def test_the_markers_are_still_the_substrate_s_own_sentences(self) -> None:
        """If the substrate rewrites a letter, every lifecycle assertion below
        would quietly match nothing. Fail here instead."""
        source = _flat(
            __import__("inspect").getsource(
                import_substrate("pdf_templates.correspondence.adjuster_letter")
            )
        )
        for name, marker in LETTER_MARKERS.items():
            assert marker in source, (
                f"{name} no longer opens with {marker!r}; the letter-lifecycle "
                "tests are matching nothing"
            )

    def test_report_ordinal_advances_across_treating_reports(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _observed(monkeypatch, "_report_ordinal")
        seed = _seed(
            "ord-report",
            rng_seed=7502,
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _render(seed, tmp_path)
        assert seen, "no treating report rendered; the probe proves nothing"
        assert len(set(seen)) > 1, (
            f"every treating report saw report_ordinal={seen[0]}; the trajectory "
            "cannot advance, so the arc renders its first phrase forever"
        )

    def test_letter_ordinal_advances_across_adjuster_letters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _observed(monkeypatch, "_letter_ordinal")
        seed = _seed(
            "ord-letter",
            rng_seed=7503,
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _render(seed, tmp_path)
        assert seen, "no adjuster letter rendered; the probe proves nothing"
        assert len(set(seen)) > 1, (
            f"every adjuster letter saw letter_ordinal={seen[0]}; the type "
            "sequence cannot advance"
        )


# ---------------------------------------------------------------------------
# ISC-105 (carried) — the trajectory has to advance in the rendered file
# ---------------------------------------------------------------------------


class TestTheTrajectoryAdvancesOnThePage:
    def test_a_multi_report_case_renders_more_than_one_arc_phrase(
        self, tmp_path: Path
    ) -> None:
        """Phase 2 asserted ``any(phrase in body)``, which the first phrase
        alone satisfies. Counting distinct phrases is what makes it bite."""
        seed = _seed(
            "traj-advance",
            rng_seed=7502,
            documents={
                "overrides": [{"subtype": "TREATING_PHYSICIAN_REPORT_PR2", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))
        arc = TRAJECTORY_PHRASES[plan.case_facts.trajectory]
        landed = [phrase for phrase in arc if phrase.lower() in body]
        assert len(landed) > 1, (
            f"four reports rendered {len(landed)} distinct {plan.case_facts.trajectory} "
            f"phrase(s): {landed}. The arc is frozen at its first step."
        )


# ---------------------------------------------------------------------------
# ISC-121 — a case accepts the claim once
# ---------------------------------------------------------------------------


class TestAdjusterLetterLifecycle:
    def test_the_claim_is_accepted_at_most_once(self, tmp_path: Path) -> None:
        seed = _seed(
            "letter-once",
            rng_seed=7504,
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("ADJUSTER_LETTER", ""))
        assert body, "no adjuster letter text extracted"
        acceptances = body.count(LETTER_MARKERS["initial_acceptance"])
        assert acceptances <= 1, (
            f"the carrier accepted liability {acceptances} times in one file"
        )

    def test_four_letters_are_not_all_the_same_letter(self, tmp_path: Path) -> None:
        seed = _seed(
            "letter-varied",
            rng_seed=7504,
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _, texts = _render(seed, tmp_path)
        present = _letters_present(_flat(texts.get("ADJUSTER_LETTER", "")))
        assert len(present) > 1, f"four letters, one flavour: {present}"

    def test_a_denied_claim_never_sends_an_acceptance_letter(
        self, tmp_path: Path
    ) -> None:
        """The counterfactual for the same knob: the ledger withholds
        ``initial_acceptance`` when liability was denied."""
        seed = _seed(
            "letter-denied",
            rng_seed=7505,
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "claim_response": "denied",
            },
            documents={
                "overrides": [{"subtype": "ADJUSTER_LETTER", "count": 4}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert "initial_acceptance" not in plan.case_facts.adjuster_letter_types_allowed
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("ADJUSTER_LETTER", ""))
        assert body, "no adjuster letter text extracted"
        assert LETTER_MARKERS["initial_acceptance"] not in body, (
            "the carrier accepted liability on a denied claim"
        )


# ---------------------------------------------------------------------------
# ISC-119 — a delay chain: late benefits draw correspondence after them
# ---------------------------------------------------------------------------


def _plan_for(case_id: str, **overrides: Any) -> Any:
    plan = build_case_plan(_seed(case_id, **overrides))
    assert plan.case_facts is not None
    return plan


def _dates_of(plan: Any, subtype: str) -> list[Any]:
    return sorted(d.doc_date for d in plan.documents if d.subtype == subtype)


class TestDelayChains:
    def test_each_late_benefit_draws_its_own_demand_letter(self) -> None:
        plan = _plan_for(
            "chain-neg",
            rng_seed=8100,
            scenario={"adjuster": {"diligence": "negligent"}},
        )
        facts = plan.case_facts
        letters = _dates_of(plan, DELAY_CHAIN_SUBTYPE)
        assert facts.late_benefit_events, "seed drew no late benefits; probe is vacuous"
        assert len(letters) >= len(facts.late_benefit_events), (
            f"{len(facts.late_benefit_events)} late benefit(s), "
            f"{len(letters)} demand letter(s) — the delay went unanswered"
        )

    def test_every_demand_letter_post_dates_the_delay_it_chases(self) -> None:
        plan = _plan_for(
            "chain-order",
            rng_seed=8101,
            scenario={"adjuster": {"diligence": "negligent"}},
        )
        facts = plan.case_facts
        assert facts.late_benefit_events
        earliest = min(e.actual_date for e in facts.late_benefit_events)
        chain = _dates_of(plan, DELAY_CHAIN_SUBTYPE)
        # Without this the loop below is a no-op on a file with no chain in it,
        # and a passing test would mean "the feature is absent".
        assert chain, "no demand letters planned; the ordering assertion is vacuous"
        for when in chain:
            assert when >= earliest, (
                f"a demand letter dated {when} chases a delay that had not "
                f"happened yet (first late benefit {earliest})"
            )

    def test_an_attentive_adjuster_draws_a_shorter_chain(self) -> None:
        """The opposite draw of the same knob, on one seed."""
        negligent = _plan_for(
            "chain-cf", rng_seed=8102, scenario={"adjuster": {"diligence": "negligent"}}
        )
        attentive = _plan_for(
            "chain-cf", rng_seed=8102, scenario={"adjuster": {"diligence": "attentive"}}
        )
        assert len(negligent.case_facts.late_benefit_events) > len(
            attentive.case_facts.late_benefit_events
        ), "the two personas drew the same lateness; the counterfactual proves nothing"
        assert len(_dates_of(negligent, DELAY_CHAIN_SUBTYPE)) > len(
            _dates_of(attentive, DELAY_CHAIN_SUBTYPE)
        ), "correspondence density did not follow the persona"


# ---------------------------------------------------------------------------
# ISC-123/124 — the cadence decides when counsel wrote
# ---------------------------------------------------------------------------


class TestAttorneyCadenceMovesTheDates:
    def _letters(self, cadence: str, case_id: str, rng_seed: int = 8200) -> list[Any]:
        plan = _plan_for(
            case_id, rng_seed=rng_seed, scenario={"attorney": {"cadence": cadence}}
        )
        assert plan.case_facts.attorney_cadence == cadence
        return sorted(
            doc.doc_date
            for doc in plan.documents
            if doc.subtype in ATTORNEY_CADENCE_SUBTYPES
        )

    def test_thirty_day_cadence_sits_on_a_thirty_day_clock(self) -> None:
        dates = self._letters("every_30_days", "cad-30")
        assert len(dates) >= 3, f"only {len(dates)} letters; the rhythm is untestable"
        gaps = [(b - a).days for a, b in pairwise(dates)]
        assert max(gaps) <= 45, f"a 30-day cadence left a {max(gaps)}-day hole: {gaps}"

    def test_sporadic_opens_a_hole_a_reviewer_would_notice(self) -> None:
        dates = self._letters("sporadic", "cad-sp")
        assert len(dates) >= 3, f"only {len(dates)} letters; the rhythm is untestable"
        gaps = [(b - a).days for a, b in pairwise(dates)]
        assert max(gaps) >= 90, f"sporadic never went quiet: {gaps}"

    def test_every_event_driven_letter_follows_a_real_event(self) -> None:
        """The assertion the first cut of this feature would have failed.

        ``event_driven`` originally anchored to the timeline's milestones, most
        of which were filtered out, leaving one anchor and a fixed lap offset —
        a 90-day metronome that satisfied "the three cadences differ" while
        following nothing. This binds each letter to a document in the file.
        """
        plan = _plan_for(
            "cad-ev", rng_seed=8200, scenario={"attorney": {"cadence": "event_driven"}}
        )
        anchors = sorted(
            {d.doc_date for d in plan.documents if d.subtype in CADENCE_ANCHOR_SUBTYPES}
        )
        assert anchors, "no anchor documents in the file; the probe is vacuous"
        letters = sorted(
            d.doc_date for d in plan.documents if d.subtype in ATTORNEY_CADENCE_SUBTYPES
        )
        assert len(letters) >= 2
        for when in letters:
            ceiling = event_driven_max_lag_days(len(letters), len(anchors))
            assert any(0 <= (when - anchor).days <= ceiling for anchor in anchors), (
                f"a letter dated {when} follows no event in the file; nearest "
                f"anchors {[str(a) for a in anchors]}"
            )

    def test_most_event_driven_letters_land_on_the_stated_lag(self) -> None:
        """F2. The bound above is a ceiling; this is the *property*.

        A ceiling alone would be satisfied by letters scattered anywhere in a
        fifty-day band, which is not what ``event_driven`` claims to do. The
        CHANGELOG said "1-5 days" while the guard allowed 0-60 — prose tighter
        than its guard, which is the class this repair closes. Measured across
        38 cases, 179 of 218 letters land at exactly the lag; the fit accounts
        for the short tail and the lap for the long one.
        """
        lags: list[int] = []
        ceilings: list[int] = []
        for rng_seed in range(9000, 9012):
            plan = build_case_plan(
                _seed(
                    f"lag-{rng_seed}",
                    rng_seed=rng_seed,
                    lifecycle={"target_stage": "discovery", "eval_type": "qme"},
                    scenario={"attorney": {"cadence": "event_driven"}},
                )
            )
            anchors = sorted(
                {d.doc_date for d in plan.documents if d.subtype in CADENCE_ANCHOR_SUBTYPES}
            )
            letters = [
                d for d in plan.documents if d.subtype in ATTORNEY_CADENCE_SUBTYPES
            ]
            # The same threshold `_apply_attorney_cadence` uses. A file with one
            # client letter has no rhythm to impose, so the cadence leaves it
            # where the walk put it — and seed 9003 is exactly that case: one
            # letter, 100 days behind its nearest anchor, entirely correct.
            # Sampling it was my error, not the code's, and stating the coupling
            # here is what stops the sample drifting away from the guard again.
            if len(letters) < CADENCE_MIN_LETTERS:
                continue
            ceiling = event_driven_max_lag_days(len(letters), len(anchors))
            for doc in letters:
                prior = [a for a in anchors if a <= doc.doc_date]
                if prior:
                    lags.append((doc.doc_date - max(prior)).days)
                    ceilings.append(ceiling)
        assert len(lags) >= 30, f"only {len(lags)} letters sampled; too few to characterise"
        on_lag = sum(1 for lag in lags if lag == EVENT_DRIVEN_LAG_DAYS)
        assert on_lag > len(lags) // 2, (
            f"only {on_lag} of {len(lags)} letters sit at the stated "
            f"{EVENT_DRIVEN_LAG_DAYS}-day lag; 'event driven' is not describing "
            "what the dates actually do"
        )
        for lag, ceiling in zip(lags, ceilings, strict=True):
            assert lag <= ceiling, (
                f"a letter sat {lag} days behind its nearest event, past the "
                f"{ceiling}-day ceiling its own case shape allows"
            )

    def test_the_anchor_and_cadence_tables_name_real_subtypes(self) -> None:
        """A table of keys the taxonomy does not know matches nothing, and a
        cadence built on it would silently do nothing at all."""
        taxonomy = effective_taxonomy()
        for label, table in (
            ("CADENCE_ANCHOR_SUBTYPES", CADENCE_ANCHOR_SUBTYPES),
            ("ATTORNEY_CADENCE_SUBTYPES", ATTORNEY_CADENCE_SUBTYPES),
        ):
            unknown = sorted(k for k in table if not taxonomy.is_canonical(k))
            assert not unknown, f"{label} names non-canonical subtypes: {unknown}"

    def test_the_three_cadences_do_not_agree(self) -> None:
        """Opposite draws of one knob: if the dates match, nothing is honoured."""
        rhythms = {
            name: self._letters(name, "cad-cf")
            for name in ("every_30_days", "event_driven", "sporadic")
        }
        distinct = {tuple(dates) for dates in rhythms.values()}
        assert len(distinct) == 3, (
            "two cadences produced identical letter dates: "
            f"{ {name: [str(d) for d in v] for name, v in rhythms.items()} }"
        )


# ---------------------------------------------------------------------------
# ISC-126 — the ledger, the table of contents and the paper are one number
# ---------------------------------------------------------------------------


class TestDiscoveryVolumesAgree:
    """What replaces the two inertness probes ISC-126 retired.

    The probes asked "does this field change nothing?"; now that it changes
    something, the question becomes "do all three readings of it match?" — and
    that is a far stronger guard than the one it replaces.
    """

    def _case(self, tmp_path: Path) -> tuple[Any, dict[str, Any], Path]:
        seed = _seed(
            "vol",
            rng_seed=9900,
            lifecycle={"target_stage": "discovery", "eval_type": "qme"},
            scenario={
                "discovery": {
                    "subpoena_sets": 4,
                    "pages_per_set": {"min": 12, "max": 18},
                }
            },
        )
        plan = build_case_plan(seed)
        manifest, _ = _render(seed, tmp_path)
        return plan, manifest, tmp_path / seed.case_id / "documents"

    def test_the_file_holds_the_packet_count_the_seed_asked_for(
        self, tmp_path: Path
    ) -> None:
        _, manifest, _ = self._case(tmp_path)
        packets = [
            entry
            for entry in manifest["documents"]
            if entry["subtype"] in DISCOVERY_PACKET_SUBTYPES
        ]
        assert len(packets) == 4, f"asked for 4 packets, got {len(packets)}"

    def test_ledger_table_of_contents_and_paper_all_state_one_number(
        self, tmp_path: Path
    ) -> None:
        import fitz

        plan, manifest, documents = self._case(tmp_path)
        budgets = plan.case_facts.packet_pages
        assert budgets, "the ledger drew no page budget; the probe is vacuous"

        seen = 0
        for entry in manifest["documents"]:
            if entry["subtype"] not in DISCOVERY_PACKET_SUBTYPES:
                continue
            with fitz.open(documents / entry["filename"]) as document:
                paper = document.page_count
                text = _flat("".join(page.get_text() for page in document))
            stated = re.search(r"total pages:.{0,14}?(\d+)", text)
            assert stated, f"packet {seen + 1} states no page total at all"
            assert budgets[seen] == paper == int(stated.group(1)), (
                f"packet {seen + 1} disagrees with itself: ledger "
                f"{budgets[seen]}, paper {paper}, cover sheet {stated.group(1)}"
            )
            seen += 1
        assert seen == len(budgets)


# ---------------------------------------------------------------------------
# ISC-125 — an event-driven letter names the event it follows
# ---------------------------------------------------------------------------


class TestEventDrivenLettersNameTheirAnchor:
    """A date alone is not a reference.

    ISC-123/124 put the letters on the right dates; a reader still had to infer
    *why*. The rendered letter now says which document prompted it, which is the
    part a reviewer can check without recomputing the cadence.
    """

    def _rendered(
        self, case_id: str, cadence: str, tmp_path: Path
    ) -> tuple[dict[str, Any], str]:
        seed = _seed(
            case_id,
            rng_seed=8300,
            lifecycle={"target_stage": "discovery", "eval_type": "qme"},
            scenario={"attorney": {"cadence": cadence}},
        )
        manifest, texts = _render(seed, tmp_path)
        body = _flat(
            "\n".join(
                text
                for subtype, text in texts.items()
                if subtype in ATTORNEY_CADENCE_SUBTYPES
            )
        )
        return manifest, body

    def _letter_text(self, case_id: str, cadence: str, tmp_path: Path) -> str:
        return self._rendered(case_id, cadence, tmp_path)[1]

    def test_the_cited_event_is_a_document_that_is_really_in_the_file(
        self, tmp_path: Path
    ) -> None:
        """Naming *an* event is not the property; naming a *real* one is.

        A letter that cites a plausible-looking report the folder does not
        contain is worse than one that cites nothing, so the cited dates are
        checked against the manifest rather than merely counted.
        """
        manifest, body = self._rendered("anchor-real", "event_driven", tmp_path)
        cited = re.findall(rf"{ANCHOR_REFERENCE_MARKER} .+? of ([a-z]+ \d{{1,2}}, \d{{4}})", body)
        assert cited, "no citation parsed; the assertion below would be vacuous"
        real = {
            datetime.strptime(entry["documentDate"], "%Y-%m-%d").strftime("%B %d, %Y").lower()
            for entry in manifest["documents"]
            if entry["subtype"] in CADENCE_ANCHOR_SUBTYPES
        }
        assert real, "no anchor documents in the manifest; the probe proves nothing"
        unknown = sorted(set(cited) - real)
        assert not unknown, (
            f"letters cite events with no matching document in the folder: {unknown}. "
            f"Anchor documents present: {sorted(real)}"
        )

    def test_the_letter_names_the_document_that_prompted_it(
        self, tmp_path: Path
    ) -> None:
        body = self._letter_text("anchor-ref", "event_driven", tmp_path)
        assert body, "no client-letter text extracted; the grep would be vacuous"
        assert ANCHOR_REFERENCE_MARKER.lower() in body, (
            f"no event-driven letter carries {ANCHOR_REFERENCE_MARKER!r}; the "
            "letter is on the right date but says nothing about why"
        )

    def test_a_non_event_driven_file_makes_no_such_reference(
        self, tmp_path: Path
    ) -> None:
        """The positive control that makes the grep above mean something.

        Without it the assertion would pass on a marker the engine emitted
        unconditionally — proving the string exists, not that the cadence drives
        it.
        """
        body = self._letter_text("anchor-none", "every_30_days", tmp_path)
        assert body, "no client-letter text extracted; the control is vacuous"
        assert ANCHOR_REFERENCE_MARKER.lower() not in body, (
            "a thirty-day-cadence letter references an anchoring event; the "
            "reference is unconditional, so the event_driven assertion proves "
            "nothing"
        )


# ---------------------------------------------------------------------------
# ISC-148 — discovery shaping respects the document controls, loudly
# ---------------------------------------------------------------------------

#: A stage that proposes records packets, and one that proposes none.
#:
#: Measured rather than assumed: ``intake`` and ``active_treatment`` propose no
#: packets, ``discovery`` and later do. ``medical_legal`` — this module's default
#: — also proposes none, which is why every seed below states its stage.
_DISCOVERY_STAGE: dict[str, Any] = {"target_stage": "discovery", "eval_type": "qme"}
_PRE_DISCOVERY_STAGE: dict[str, Any] = {"target_stage": "intake", "eval_type": "qme"}


class TestDiscoveryShapingRespectsDocumentControls:
    """ISC-126 met the count; ISC-148 makes it stop at the controls.

    ``_shape_discovery`` ran on ``(seed, timeline, dated)`` and never saw the
    ``documents:`` block, so the stated count outranked the highest-precedence
    control in the system. Two separate defects came out of that blindness and
    both are pinned below, because a guard written for one of them passes on the
    other:

    * **The refill.** With *some* packet subtype surviving, the shaper pads to
      the declared count by cloning the last packet — past an exact
      ``documents.overrides`` count that said how many there were to be.
    * **The warning.** With *no* packet surviving, the shaper blames the
      lifecycle stage and prescribes ``target_stage: discovery`` — on a seed
      that already says ``target_stage: discovery``, so the prescribed edit is a
      no-op and the control that actually emptied the file is never named.

    The tests do not stop at "a warning was emitted": each follows the edit the
    warning prescribes and asserts the count is then met. An instruction nobody
    executes is how both of these shipped.
    """

    #: Control names a shortfall warning may name, for the negative assertions.
    _CONTROL_NAMES = ("documents.exclude", "documents.include_only", "documents.overrides")

    def _shaped(self, case_id: str, **overrides: Any) -> tuple[dict[str, int], str | None]:
        """Packet counts per subtype, and the one shortfall warning if any."""
        plan = build_case_plan(_seed(case_id, **overrides))
        counts: dict[str, int] = {}
        for document in plan.documents:
            if document.subtype in DISCOVERY_PACKET_SUBTYPES:
                counts[document.subtype] = counts.get(document.subtype, 0) + 1
        shortfall = [
            warning
            for warning in plan.warnings
            if "scenario.discovery.subpoena_sets" in warning
        ]
        assert len(shortfall) <= 1, f"more than one shortfall warning: {shortfall}"
        return counts, shortfall[0] if shortfall else None

    @staticmethod
    def _documents(**controls: Any) -> dict[str, Any]:
        return {"format_mix": {"pdf": 1.0}, **controls}

    # -- the byte-stability control, first, so the rest cannot be vacuous ----

    def test_a_seed_with_no_controls_still_gets_the_count_it_asked_for(self) -> None:
        """ISC-126's own property, restated as this class's positive control.

        Every assertion below is about a count the controls hold *down*. If the
        uncontrolled seed did not reach 3, "fewer than 3" would prove nothing.
        """
        counts, warning = self._shaped(
            "isc148-plain",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
        )
        assert sum(counts.values()) == 3, f"the uncontrolled seed holds {counts}"
        assert warning is None, f"an uncontrolled seed warned: {warning}"

    # -- shape (b): every packet subtype suppressed -------------------------

    def test_an_exclude_is_not_refilled_and_the_warning_names_the_control(self) -> None:
        counts, warning = self._shaped(
            "isc148-excl",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(exclude=["SUBPOENAED_RECORDS_MEDICAL"]),
        )
        assert "SUBPOENAED_RECORDS_MEDICAL" not in counts, (
            "documents.exclude named this subtype and the plan holds it anyway"
        )
        assert warning is not None, "the count could not be met and nothing said so"
        assert "documents.exclude" in warning, (
            f"the warning does not name the control that caused it: {warning}"
        )
        assert "SUBPOENAED_RECORDS_MEDICAL" in warning, (
            f"the warning does not name the suppressed subtype: {warning}"
        )
        assert "target_stage" not in warning, (
            "the warning prescribes a lifecycle edit on a seed that is already at "
            f"target_stage 'discovery' — following it changes nothing: {warning}"
        )

    def test_a_parent_type_exclude_is_named_as_the_cause_too(self) -> None:
        """``exclude: [DISCOVERY]`` suppresses all four packet subtypes at once.

        The subtype-key path and the parent-type path reach the same emptied
        file, and a guard bound to the subtype spelling would miss this one.
        """
        counts, warning = self._shaped(
            "isc148-ptype",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(exclude=["DISCOVERY"]),
        )
        assert sum(counts.values()) == 0
        assert warning is not None and "documents.exclude" in warning, (
            f"a parent-type exclude is not named as the cause: {warning}"
        )
        assert "DISCOVERY" in warning, (
            "the warning prescribes an edit against a key the seed does not "
            f"contain — the author wrote 'DISCOVERY', not a subtype: {warning}"
        )
        assert "target_stage" not in warning, warning

    def test_following_the_exclude_warning_delivers_the_count(self) -> None:
        """The ISC-129 discipline: execute the prescribed edit, not just read it."""
        counts, warning = self._shaped(
            "isc148-excl-fixed",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(exclude=[]),
        )
        assert sum(counts.values()) == 3, (
            f"removing the subtype from documents.exclude — the edit the warning "
            f"prescribes — still does not deliver 3 packets: {counts}"
        )
        assert warning is None, warning

    # -- shape (a): a mixed set, so the refill branch actually runs ----------

    def test_an_exact_override_count_is_not_padded_to_the_declared_count(self) -> None:
        """The refill defect, which the emptied-file seed above never reaches.

        With every proposed subtype suppressed there is nothing to clone, so
        ``packets[-1]`` is never read. This seed keeps one packet subtype alive
        under an exact ``documents.overrides`` count and suppresses the other:
        the shaper then had a donor, and cloned it past the count the override
        set.
        """
        counts, warning = self._shaped(
            "isc148-pin",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 4}},
            documents=self._documents(
                exclude=["SUBPOENAED_RECORDS_MEDICAL"],
                overrides=[{"subtype": "SUBPOENAED_RECORDS_EMPLOYMENT", "count": 2}],
            ),
        )
        assert counts == {"SUBPOENAED_RECORDS_EMPLOYMENT": 2}, (
            "documents.overrides set an exact count of 2 and the shaper padded "
            f"past it to reach subpoena_sets: {counts}"
        )
        assert warning is not None, (
            "the controls capped the count below the declared one and nothing said so"
        )
        assert "documents.overrides" in warning, (
            f"the warning does not name the count control that capped it: {warning}"
        )
        assert "documents.exclude" in warning, (
            f"the warning does not name the membership control: {warning}"
        )
        assert "suppresses SUBPOENAED_RECORDS_EMPLOYMENT" not in warning, (
            "a count of 2 is a cap, not a suppression; the warning describes the "
            f"one surviving subtype as absent: {warning}"
        )
        assert "target_stage" not in warning, warning

    def test_following_the_override_warning_delivers_the_count(self) -> None:
        counts, _ = self._shaped(
            "isc148-pin-fixed",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 4}},
            documents=self._documents(
                exclude=["SUBPOENAED_RECORDS_MEDICAL"],
                overrides=[{"subtype": "SUBPOENAED_RECORDS_EMPLOYMENT", "count": 4}],
            ),
        )
        assert counts == {"SUBPOENAED_RECORDS_EMPLOYMENT": 4}, (
            f"raising the documents.overrides count does not deliver 4: {counts}"
        )

    # -- the stage cause, undisturbed ---------------------------------------

    def test_the_lifecycle_warning_survives_when_the_stage_really_is_the_cause(
        self,
    ) -> None:
        """Both causes must stay distinguishable, so the old one is pinned too."""
        counts, warning = self._shaped(
            "isc148-stage",
            lifecycle=_PRE_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
        )
        assert sum(counts.values()) == 0
        assert warning is not None and "target_stage" in warning, (
            f"an early stage no longer prescribes advancing it: {warning}"
        )
        named = [name for name in self._CONTROL_NAMES if name in warning]
        assert not named, (
            f"the warning blames {named} on a seed with no document controls: {warning}"
        )

    def test_an_innocent_control_is_not_blamed_for_a_stage_shortfall(self) -> None:
        """``exclude`` naming a subtype the walk never proposed removed nothing.

        Attribution keyed off the *presence of a control key* rather than off
        what the control actually removed would send this author to the wrong
        line — the stage is the cause, and lifting the exclude changes nothing.
        """
        counts, warning = self._shaped(
            "isc148-innocent",
            lifecycle=_PRE_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(exclude=["SUBPOENAED_RECORDS_MEDICAL"]),
        )
        assert sum(counts.values()) == 0
        assert warning is not None and "target_stage" in warning, warning
        assert "documents.exclude" not in warning, (
            "documents.exclude is blamed for a shortfall it did not cause — the "
            f"lifecycle stage proposed no packets for it to remove: {warning}"
        )

    # -- both causes at once -------------------------------------------------

    def test_a_seed_where_both_causes_apply_names_both(self) -> None:
        """Neither edit alone works, so naming one of them is a wrong answer.

        ``target_stage: intake`` proposes no packets *and* a zero-count override
        pins the subtype at nothing. Advancing the stage leaves the override in
        force; raising the override leaves the stage with nothing to propose.
        """
        counts, warning = self._shaped(
            "isc148-both",
            lifecycle=_PRE_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(
                overrides=[{"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 0}],
            ),
        )
        assert sum(counts.values()) == 0
        assert warning is not None, "neither cause was reported"
        assert "target_stage" in warning, f"the stage cause is missing: {warning}"
        assert "documents.overrides" in warning, f"the control cause is missing: {warning}"

    @pytest.mark.parametrize(
        ("case_id", "lifecycle", "documents"),
        [
            ("isc148-half-stage", _PRE_DISCOVERY_STAGE, {"format_mix": {"pdf": 1.0}}),
            (
                "isc148-half-control",
                _DISCOVERY_STAGE,
                {
                    "format_mix": {"pdf": 1.0},
                    "overrides": [
                        {"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 0}
                    ],
                },
            ),
        ],
    )
    def test_half_of_the_both_edit_is_not_enough(
        self, case_id: str, lifecycle: dict[str, Any], documents: dict[str, Any]
    ) -> None:
        """The proof that "both" is honest rather than decorative."""
        counts, warning = self._shaped(
            case_id,
            lifecycle=lifecycle,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=documents,
        )
        assert sum(counts.values()) == 0, (
            f"one half of the prescribed pair was enough after all: {counts}"
        )
        assert warning is not None

    def test_making_both_edits_delivers_the_count(self) -> None:
        counts, warning = self._shaped(
            "isc148-both-fixed",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(
                overrides=[{"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 3}],
            ),
        )
        assert sum(counts.values()) == 3, f"both edits together still fall short: {counts}"
        assert warning is None, warning

    # -- ISC-150: the prescription is a verb-first imperative ----------------

    @pytest.mark.parametrize(
        ("case_id", "lifecycle", "documents"),
        [
            (
                "isc148-verb-excl",
                _DISCOVERY_STAGE,
                {"format_mix": {"pdf": 1.0}, "exclude": ["SUBPOENAED_RECORDS_MEDICAL"]},
            ),
            (
                "isc148-verb-pin",
                _DISCOVERY_STAGE,
                {
                    "format_mix": {"pdf": 1.0},
                    "exclude": ["SUBPOENAED_RECORDS_MEDICAL"],
                    "overrides": [
                        {"subtype": "SUBPOENAED_RECORDS_EMPLOYMENT", "count": 2}
                    ],
                },
            ),
            (
                "isc148-verb-both",
                _PRE_DISCOVERY_STAGE,
                {
                    "format_mix": {"pdf": 1.0},
                    "overrides": [
                        {"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 0}
                    ],
                },
            ),
        ],
    )
    def test_the_warning_prescribes_a_verb_first_edit(
        self, case_id: str, lifecycle: dict[str, Any], documents: dict[str, Any]
    ) -> None:
        """ISC-150. A directive hidden behind "you should" is invisible to the sweep."""
        _, warning = self._shaped(
            case_id,
            lifecycle=lifecycle,
            scenario={"discovery": {"subpoena_sets": 4}},
            documents=documents,
        )
        assert warning is not None
        opening = [first_word(clause) for clause in clauses(warning)]
        assert any(word in DIRECTIVE_VERBS for word in opening), (
            f"no clause of the warning opens with a directive verb {opening}: {warning}"
        )
        buried = [
            clause
            for clause in clauses(warning)
            if first_word(clause) in {"you", "we", "please", "kindly"}
        ]
        assert not buried, f"a directive is buried behind a hedge: {buried}"

    # -- the cross-model review round: the fix had the defect it fixed ------
    #
    # Every test below reproduces a case a GPT-family reviewer executed against
    # the first ISC-148 commit. The pattern in all of them is the same and is
    # worth naming: the first fix read `documents.overrides` through ONE of its
    # two spellings. A seed writes either `{subtype: X, count: N}` or
    # `{type: T, max: N}`, `DocumentControls` splits them into two properties,
    # and the fix consulted only `subtype_overrides` — so the control the module
    # calls highest-precedence stayed invisible through its other spelling, and
    # the original defect survived inside its own remediation.

    def test_a_type_level_zero_override_names_the_control_not_the_stage(self) -> None:
        """`{type: DISCOVERY, max: 0}` is `documents.overrides`, spelled the other way.

        Measured on the first fix: 0 packets and the lifecycle-stage sentence, on
        a seed already at `target_stage: discovery` — the exact defect ISC-148
        exists to remove, reached through the spelling the fix did not read.
        """
        counts, warning = self._shaped(
            "isc148r-typezero",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(overrides=[{"type": "DISCOVERY", "max": 0}]),
        )
        assert sum(counts.values()) == 0, counts
        assert warning is not None
        assert "target_stage" not in warning, (
            f"the stage is blamed for a control-caused shortfall: {warning}"
        )
        assert "documents.overrides" in warning, warning
        # The key the author wrote, not the four subtypes it governs — an
        # imperative naming lines the seed does not contain cannot be followed.
        assert "count for DISCOVERY" in warning, (
            f"the prescribed edit does not name the seed's own key: {warning}"
        )

    def test_following_the_type_level_warning_delivers_the_count(self) -> None:
        """Execute the prescribed edit; an instruction nobody runs is how this shipped.

        The raise has to clear the *type*, not the packet count. `max` bounds
        every DISCOVERY document, and records packets are a fraction of them —
        measured on this seed, `max: 3` yields one packet, `max: 6` two, `max:
        12` three. That is the difference between a ceiling and a pin, and it is
        why this test raises to 12 rather than to `subpoena_sets`.
        """
        counts, warning = self._shaped(
            "isc148r-typezero-fixed",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(overrides=[{"type": "DISCOVERY", "max": 12}]),
        )
        assert sum(counts.values()) == 3, (
            f"raising the documents.overrides count for DISCOVERY — the edit the "
            f"warning prescribes — does not deliver 3 packets: {counts}"
        )
        assert warning is None, warning

    def test_a_global_cap_shortfall_does_not_blame_the_stage(self) -> None:
        """`global_cap` is unattributable, which is not a licence to name the stage.

        The first fix fell back to the stage sentence whenever no per-subtype
        control matched, without consulting whether the stage was a cause. So the
        one control the docstring said would be reported "with no named control
        rather than with a wrong one" was reported with the wrongest one
        available.
        """
        _, warning = self._shaped(
            "isc148r-globalcap",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(global_cap=3),
        )
        assert warning is not None
        assert "target_stage" not in warning, (
            f"the stage is blamed for a global_cap shortfall: {warning}"
        )
        assert "documents.global_cap" in warning, (
            f"the only control that could have done it is not named: {warning}"
        )

    def test_an_exclude_naming_both_routes_prescribes_removing_both(self) -> None:
        """Sorting and taking `[0]` prescribed a no-op.

        With the parent type and the subtype both excluded, removing either alone
        leaves the other in force. The first fix named `DISCOVERY` because it
        sorts first, and following that literally still delivered nothing.
        """
        _, warning = self._shaped(
            "isc148r-bothkeys",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 3}},
            documents=self._documents(
                exclude=["DISCOVERY", "SUBPOENAED_RECORDS_MEDICAL"],
            ),
        )
        assert warning is not None
        assert "Remove DISCOVERY, SUBPOENAED_RECORDS_MEDICAL" in warning, (
            f"the warning prescribes removing only one of the two keys in force: {warning}"
        )

    def test_the_trim_does_not_slice_an_exact_override_count(self) -> None:
        """The refill respected the pin; the trim sliced straight through it.

        `resolve_document_controls` has already applied the count by the time the
        shaper runs, so `packets[:declared]` was cutting the author's own number
        down. Measured on the first fix: a pin of 2 under `subpoena_sets: 1`
        delivered 1, silently.
        """
        counts, warning = self._shaped(
            "isc148r-trim",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 1}},
            documents=self._documents(
                overrides=[{"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 2}],
            ),
        )
        assert counts.get("SUBPOENAED_RECORDS_MEDICAL") == 2, (
            f"the trim sliced through an exact documents.overrides count: {counts}"
        )
        assert warning is not None, (
            "the file holds more than subpoena_sets asked for and nothing said so"
        )
        assert "documents.overrides" in warning and "at 2" in warning, warning

    def test_the_trim_drops_no_pinned_subtype_entirely(self) -> None:
        """The severe shape: a pinned subtype vanished from the file.

        Two subtypes pinned at 2 each under `subpoena_sets: 1` kept a
        date-ordered prefix, so one subtype the author had written an explicit
        count for was dropped to zero — and no warning was emitted at all.
        """
        counts, warning = self._shaped(
            "isc148r-trim-two",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 1}},
            documents=self._documents(
                overrides=[
                    {"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 2},
                    {"subtype": "SUBPOENAED_RECORDS_EMPLOYMENT", "count": 2},
                ],
            ),
        )
        assert counts.get("SUBPOENAED_RECORDS_MEDICAL") == 2, counts
        assert counts.get("SUBPOENAED_RECORDS_EMPLOYMENT") == 2, (
            f"a subtype with an explicit count of 2 was dropped by the trim: {counts}"
        )
        assert warning is not None, "a silent overrule of the highest-precedence control"
        for key in ("SUBPOENAED_RECORDS_MEDICAL", "SUBPOENAED_RECORDS_EMPLOYMENT"):
            assert key in warning, f"{key} pinned but unnamed in the warning: {warning}"

    def test_a_positive_type_bound_is_not_cloned_past(self) -> None:
        """The refill's own blind spot, through the same second spelling.

        The reviewer proved the `max: 0` case; this is the adjacent one it did
        not reach. A synthesized packet is one more document under the type, so
        cloning to reach `subpoena_sets` breaches a ceiling the author wrote —
        the same overrule as cloning past an exact count, through the spelling
        the fix did not read.

        `max: 6` fills the DISCOVERY type to **6 of 6** on this seed — no spare
        room — so a synthesized packet would breach the cap and the donor must
        decline rather than pad to four. That "at the cap" qualifier is
        load-bearing; see the sibling test for the below-cap case, where
        declining would be wrong.
        """
        counts, warning = self._shaped(
            "isc148r-typecap",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 4}},
            documents=self._documents(overrides=[{"type": "DISCOVERY", "max": 6}]),
        )
        assert sum(counts.values()) == 2, (
            f"the refill cloned past a documents.overrides type bound of 6: {counts}"
        )
        assert warning is not None
        assert "DISCOVERY at 6" in warning, (
            f"the cap is not reported under the key the seed states it with: {warning}"
        )

    def test_a_type_ceiling_below_its_cap_still_permits_the_refill(self) -> None:
        """The opposite draw, and the one that refuted the first model.

        "There is a ceiling" and "the ceiling binds" are different questions, and
        only the second forbids a clone. Reading the packet ladder alone — `max:
        3` yields one packet, `max: 6` two, `max: 12` three — suggests a ceiling
        always binds. Counting documents *under the type* shows it does not:
        `max: 3` fills 3 of 3 and `max: 6` fills 6 of 6, but `max: 12` reaches
        only 10 of 12. With two spare, a fourth packet breaches nothing, and
        refusing it denies the seed a count both controls permit.

        The reviewer flagged the ladder as refuting the model; the headroom
        measurement is what settled it.
        """
        counts, warning = self._shaped(
            "isc148r-ceiling-headroom",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 4}},
            documents=self._documents(overrides=[{"type": "DISCOVERY", "max": 12}]),
        )
        assert sum(counts.values()) == 4, (
            "the type sits below its cap, so the refill breaches nothing and the "
            f"declared count is deliverable: {counts}"
        )
        assert warning is None, f"a deliverable count warned anyway: {warning}"

    def test_the_refill_stops_at_the_spare_room_and_says_so(self) -> None:
        """Between "no room" and "enough room" is the case that needs the arithmetic.

        `max: 12` leaves two spare on this seed and the file holds three packets,
        so a request for six is deliverable only as far as five. Filling to six
        breaches the cap; refusing outright denies two packets the control
        permits. The refill takes the spare room and the shortfall is reported.
        """
        counts, warning = self._shaped(
            "isc148r-ceiling-partial",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 6}},
            documents=self._documents(overrides=[{"type": "DISCOVERY", "max": 12}]),
        )
        assert sum(counts.values()) == 5, (
            "the refill should take the two spare slots the ceiling leaves and "
            f"stop, neither breaching the cap nor declining the room: {counts}"
        )
        assert warning is not None, "a shortfall the controls caused, unreported"
        assert "DISCOVERY at 12" in warning, warning

    def test_a_type_ceiling_does_not_forbid_the_trim(self) -> None:
        """A ceiling is not a pin, and conflating them refuses a legal trim.

        `max: 12` permits up to twelve DISCOVERY documents; it does not oblige
        the file to hold three packets. A seed asking for one should get one,
        with no overage warning — the pin machinery would have kept all three
        and complained that the override outranked the seed, about a number the
        override never required.
        """
        counts, warning = self._shaped(
            "isc148r-ceiling-trim",
            lifecycle=_DISCOVERY_STAGE,
            scenario={"discovery": {"subpoena_sets": 1}},
            documents=self._documents(overrides=[{"type": "DISCOVERY", "max": 12}]),
        )
        assert sum(counts.values()) == 1, (
            f"a type ceiling was treated as an exact count and refused the trim: {counts}"
        )
        assert warning is None, f"a legal trim warned about an overage: {warning}"
