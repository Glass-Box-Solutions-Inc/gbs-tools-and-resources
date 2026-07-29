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
from pathlib import Path
from typing import Any

import pytest

import wc_caseload_engine.fact_templates as fact_templates
from conftest import extract_text, requires_substrate
from wc_caseload_engine.case_facts import TRAJECTORY_PHRASES
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.substrate import import_substrate

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
