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
