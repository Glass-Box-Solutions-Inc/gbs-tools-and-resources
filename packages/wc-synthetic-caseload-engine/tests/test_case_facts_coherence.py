"""AJC-37 Phase 1 — the ledger, and the documents agreeing with it.

Every rule here is paired with a **planted positive control**: a seed built to
violate the rule, proving the check can fail. A coherence sweep that has never
been shown to go red is indistinguishable from one that greps for nothing.

The rules are deliberately stated as what a document may *claim*, not as which
strings may appear. A QME that says "no EMG study was obtained" names EMG, and
must — recording a deliberate absence is half of what makes the ledger
enforceable. The check is therefore that every mention of an absent modality
sits inside the absence sentence, not that the word is missing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from wc_caseload_engine.case_facts import (
    GOVERNED_LEDGER_FIELDS,
    IMAGING_MODALITIES,
    MODALITIES,
    MODALITY_DISPLAY,
    CaseFacts,
    derive_case_facts,
    facts_manifest_block,
)
from wc_caseload_engine.lifecycle_bridge import seed_to_case_parameters
from wc_caseload_engine.manifests import (
    CASE_FACTS_NAME,
    MANIFEST_NAME,
    generate_case,
    validate_output_tree,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import MODALITIES as SEED_MODALITIES
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate

#: Subtypes the Phase-1 registry makes fact-aware, forced into every probe case.
FACT_AWARE_PROBE_SUBTYPES = (
    "DIAGNOSTICS_IMAGING",
    "QME_COMPREHENSIVE_REPORT",
    "TREATING_PHYSICIAN_REPORT_PR2",
)

#: The one sentence shape in which an absent study may be named.
ABSENCE_SENTENCE = "no {display} study was obtained"


def _flat(text: str) -> str:
    """Extracted PDF text with wrapping removed.

    A phrase like "no EMG study was obtained" arrives as "no EMG study was\nobtained"
    once reportlab has laid it out, so every match here is made against a
    whitespace-normalized copy rather than the raw extraction.
    """
    return re.sub(r"\s+", " ", text).strip().lower()


def _seed(case_id: str, scenario: dict[str, Any], **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 4242,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
        "scenario": scenario,
        "documents": {
            "overrides": [{"subtype": s, "count": 1} for s in FACT_AWARE_PROBE_SUBTYPES],
            "format_mix": {"pdf": 1.0},
        },
        "output": {"formats": ["pdf"]},
    }
    body.update(overrides)
    return parse_case_seed(body)


def _render(seed: Any, out_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Generate a case; return (manifest, {subtype: extracted text})."""
    generate_case(seed, out_dir, case_number=1)
    case_dir = out_dir / seed.case_id
    manifest = json.loads((case_dir / MANIFEST_NAME).read_text())
    texts: dict[str, str] = {}
    for entry in manifest["documents"]:
        path = case_dir / "documents" / entry["filename"]
        texts.setdefault(entry["subtype"], "")
        texts[entry["subtype"]] += "\n" + (extract_text(path, entry["format"]) or "")
    return manifest, texts


# ---------------------------------------------------------------------------
# The ledger itself
# ---------------------------------------------------------------------------


class TestTheLedgerIsDerivedAndPublished:
    def test_the_two_modality_vocabularies_agree(self) -> None:
        """``seeds`` duplicates the tuple to avoid an import cycle; pin the copy."""
        assert tuple(SEED_MODALITIES) == tuple(MODALITIES)
        assert set(MODALITY_DISPLAY) == set(MODALITIES)

    def test_the_seed_is_authoritative_over_derivation(self) -> None:
        plan = build_case_plan(
            _seed(
                "ledger-explicit",
                {
                    "diagnostics": {
                        "performed": ["mri"],
                        "absent": [{"modality": "emg", "body_part": "shoulder"}],
                    },
                    "surgery": "performed",
                },
            )
        )
        facts = plan.case_facts
        assert facts is not None
        assert [(f.modality, f.body_part) for f in facts.performed_diagnostics] == [
            ("mri", "lumbar_spine")
        ]
        assert [(f.modality, f.body_part) for f in facts.absent_diagnostics] == [
            ("emg", "shoulder")
        ]
        assert facts.surgery.performed
        # Body-part coherent by construction: the ledger draws from the same
        # pool the operative record would, so pinning the template to it later
        # cannot contradict the template's own body-part logic.
        from wc_caseload_engine.substrate import import_substrate

        operative = import_substrate("pdf_templates.medical.operative_record")
        pool = dict(operative._select_surgical_cpts(["lumbar_spine", "shoulder"]))
        assert facts.surgery.cpt_code in pool, (
            f"{facts.surgery.cpt_code} is not in the substrate's pool for these body parts"
        )

    def test_derivation_is_pure(self) -> None:
        seed = _seed("ledger-pure", {})
        plan_a = build_case_plan(seed)
        plan_b = build_case_plan(seed)
        assert plan_a.case_facts == plan_b.case_facts

    def test_surgery_parity_with_the_substrate_coin(self) -> None:
        """A seed that says nothing must not move ``has_surgery``.

        The bridge's 35% draw gates six document *rules*. If the ledger flipped
        its own coin the plan could contain post-operative paperwork the ledger
        calls a case with no surgery, or the reverse.
        """
        from wc_caseload_engine.lifecycle_bridge import seed_to_case_parameters

        for rng_seed in range(9001, 9021):
            seed = _seed("parity", {}, rng_seed=rng_seed)
            facts = derive_case_facts(seed, build_case_plan(seed).timeline)
            assert facts.surgery.performed == seed_to_case_parameters(seed).has_surgery, (
                f"rng_seed={rng_seed}: ledger and bridge disagree about surgery"
            )

    def test_the_manifest_and_the_artifact_both_publish_the_ledger(
        self, tmp_path: Path
    ) -> None:
        seed = _seed("ledger-published", {"surgery": "performed"})
        manifest, _ = _render(seed, tmp_path)
        assert "caseFacts" in manifest
        assert manifest["caseFacts"]["surgery"]["status"] == "performed"
        artifact = tmp_path / seed.case_id / CASE_FACTS_NAME
        assert artifact.exists(), "the resolved ledger must be surfaced beside the seed"
        assert "diagnostics" in artifact.read_text()


# ---------------------------------------------------------------------------
# Ledger vs rendered text
# ---------------------------------------------------------------------------


class TestNoDocumentClaimsAnAbsentStudy:
    """Rule 1: an absent modality may appear only as a stated absence."""

    @staticmethod
    def _violations(facts: CaseFacts, texts: dict[str, str]) -> list[str]:
        bad: list[str] = []
        for modality in facts.absent_modalities():
            display = MODALITY_DISPLAY[modality]
            allowed = ABSENCE_SENTENCE.format(display=display).lower()
            for subtype, text in texts.items():
                lowered = _flat(text)
                mentions = len(re.findall(re.escape(display.lower()), lowered))
                stated = len(re.findall(re.escape(allowed), lowered))
                if mentions > stated:
                    bad.append(f"{subtype} names {display} {mentions - stated}x as performed")
        return bad

    def test_the_imaging_report_never_reports_an_absent_study(self, tmp_path: Path) -> None:
        """Scoped to the documents the Phase-1 registry actually governs.

        ``DIAGNOSTICS_IMAGING`` is fully governed: its modality comes from the
        ledger, so an absent study can never be the study it reports.

        The rule is deliberately *not* asserted over every document in the case.
        A QME's neurology exam builds an electrodiagnostic paragraph in
        ``_build_neurology_exam`` — a different method from the one this phase
        overrides — and the substrate's AMA-guides and narrative pools name
        modalities in impairment language too. Those are separate overrides, not
        this one leaking, and claiming the broader rule would be asserting a
        guarantee the code does not make. Tracked for Phase 2; see CHANGELOG.
        """
        seed = _seed(
            "absent-clean",
            {
                "diagnostics": {
                    "performed": ["mri"],
                    "absent": [{"modality": "emg", "body_part": "shoulder"}],
                }
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        _, texts = _render(seed, tmp_path)
        governed = {k: v for k, v in texts.items() if k == "DIAGNOSTICS_IMAGING"}
        assert governed, "the probe emitted no imaging report to check"
        assert not self._violations(plan.case_facts, governed)

    def test_the_qme_states_the_absence_rather_than_ignoring_it(
        self, tmp_path: Path
    ) -> None:
        """The other half: a deliberate absence is *recorded*, not merely omitted."""
        seed = _seed(
            "absent-stated",
            {
                "diagnostics": {
                    "performed": ["mri"],
                    "absent": [{"modality": "emg", "body_part": "shoulder"}],
                }
            },
        )
        _, texts = _render(seed, tmp_path)
        qme = _flat(texts.get("QME_COMPREHENSIVE_REPORT", ""))
        assert "no emg study was obtained" in qme, (
            "the QME neither cites the study nor records that it was not done"
        )

    def test_positive_control_the_rule_can_fail(self) -> None:
        """Plant a document that cites the absent study, and prove red."""
        facts = build_case_plan(
            _seed(
                "absent-control",
                {"diagnostics": {"performed": ["mri"], "absent": [{"modality": "emg"}]}},
            )
        ).case_facts
        assert facts is not None
        planted = {"QME_COMPREHENSIVE_REPORT": "EMG demonstrates chronic denervation."}
        assert self._violations(facts, planted), (
            "the sweep passed a document citing a study the ledger calls absent"
        )

    def test_the_stated_absence_itself_is_not_a_violation(self) -> None:
        facts = build_case_plan(
            _seed(
                "absent-allowed",
                {"diagnostics": {"performed": ["mri"], "absent": [{"modality": "emg"}]}},
            )
        ).case_facts
        assert facts is not None
        allowed = {"QME_COMPREHENSIVE_REPORT": "Shoulder: no EMG study was obtained; this opinion"}
        assert not self._violations(facts, allowed)


class TestTheQmeCitesOnlyPerformedStudies:
    """Rule 2: the QME's diagnostic review names the ledger's studies."""

    def test_every_performed_modality_reaches_the_qme(self, tmp_path: Path) -> None:
        seed = _seed(
            "qme-cites",
            {"diagnostics": {"performed": ["mri", {"modality": "ct", "body_part": "shoulder"}]}},
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        _, texts = _render(seed, tmp_path)
        qme = _flat(texts.get("QME_COMPREHENSIVE_REPORT", ""))
        for fact in plan.case_facts.performed_diagnostics:
            assert fact.display.lower() in qme, f"the QME does not cite {fact.display}"

    def test_positive_control_an_uncited_study_is_detectable(self) -> None:
        plan = build_case_plan(
            _seed("qme-control", {"diagnostics": {"performed": ["mri", {"modality": "ct"}]}})
        )
        assert plan.case_facts is not None
        starved = "This review considered the MRI only."
        missing = [
            f.display
            for f in plan.case_facts.performed_diagnostics
            if f.display not in starved
        ]
        assert missing == ["CT"], missing


class TestSurgeryLanguageFollowsTheLedger:
    """Rule 3: the CPT is one number, and it is the same everywhere."""

    def test_the_cpt_appears_in_both_medical_documents(self, tmp_path: Path) -> None:
        seed = _seed("surgery-on", {"surgery": "performed"})
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        cpt = plan.case_facts.surgery.cpt_code
        assert cpt
        _, texts = _render(seed, tmp_path)
        for subtype in ("QME_COMPREHENSIVE_REPORT", "TREATING_PHYSICIAN_REPORT_PR2"):
            assert cpt in _flat(texts.get(subtype, "")), f"{subtype} does not name CPT {cpt}"

    def test_the_treating_report_describes_post_operative_care(self, tmp_path: Path) -> None:
        """The defect: post-op progress reports recommending conservative care.

        Asserted on the treatment *plan* section's own language rather than on
        the absence of the word "conservative" anywhere in the file — other
        sections of the substrate template use it in senses this override does
        not govern, and claiming otherwise would be a rule the code does not
        actually enforce.
        """
        seed = _seed("surgery-postop", {"surgery": "performed"})
        _, texts = _render(seed, tmp_path)
        tpr = _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))
        assert "status post" in tpr
        assert "post-operative rehabilitation" in tpr

    def test_a_case_without_surgery_names_no_cpt(self, tmp_path: Path) -> None:
        seed = _seed("surgery-off", {"surgery": "none"})
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert not plan.case_facts.surgery.performed
        _, texts = _render(seed, tmp_path)
        assert "status post" not in _flat(texts.get("TREATING_PHYSICIAN_REPORT_PR2", ""))


class TestProvidersAreDistinctAcrossPackets:
    """Rule 4: a records packet is answered by the provider it was sent to."""

    def test_the_ledger_offers_more_than_one_provider(self) -> None:
        plan = build_case_plan(_seed("providers", {}))
        assert plan.case_facts is not None
        assert len(plan.case_facts.providers) >= 2

    def test_round_robin_distributes_packets(self) -> None:
        plan = build_case_plan(_seed("providers-rr", {}))
        assert plan.case_facts is not None
        facts = plan.case_facts
        chosen = [facts.provider_for(i) for i in range(len(facts.providers))]
        assert len({p.name for p in chosen if p}) == len(facts.providers), (
            "provider_for repeats before exhausting the roster, so two packets "
            "would carry the same attribution"
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestTheScenarioBlockRejectsIncoherentInput:
    def test_an_unknown_modality_is_refused_actionably(self) -> None:
        with pytest.raises(ValueError, match="not a diagnostic modality") as excinfo:
            _seed("bad-modality", {"diagnostics": {"performed": ["ultrasound"]}})
        assert "mri" in str(excinfo.value), "the error must list what is allowed"

    def test_a_study_cannot_be_both_performed_and_absent(self) -> None:
        with pytest.raises(ValueError, match="both performed and absent"):
            _seed("overlap", {"diagnostics": {"performed": ["mri"], "absent": ["mri"]}})

    def test_the_overlap_check_is_body_part_aware(self) -> None:
        """Performed on one region and absent on another is coherent, not a clash."""
        seed = _seed(
            "scoped",
            {
                "diagnostics": {
                    "performed": [{"modality": "mri", "body_part": "lumbar_spine"}],
                    "absent": [{"modality": "mri", "body_part": "shoulder"}],
                }
            },
        )
        assert seed.scenario.diagnostics.performed[0].body_part == "lumbar_spine"

    def test_a_bare_modality_means_the_primary_body_part(self) -> None:
        plan = build_case_plan(_seed("bare", {"diagnostics": {"performed": ["ct"]}}))
        assert plan.case_facts is not None
        assert plan.case_facts.performed_diagnostics[0].body_part == "lumbar_spine"


# ---------------------------------------------------------------------------
# ISC-89 dispatch, and doctrine x fact-aware composition
# ---------------------------------------------------------------------------


class TestDispatchAndComposition:
    def test_an_unregistered_subtype_takes_the_substrate_class(self) -> None:
        """ISC-89: the registry is opt-in, and opting out is the default."""
        from wc_caseload_engine.fact_templates import fact_aware_templates
        from wc_caseload_engine.renderer import _load_template

        registry = fact_aware_templates()
        assert "CLAIM_FORM_DWC1" not in registry
        plain, _, _ = _load_template("CLAIM_FORM_DWC1", fact_aware=True)
        assert plain.__module__.startswith("pdf_templates"), (
            "an unregistered subtype must still resolve to a substrate class"
        )

    def test_a_registered_subtype_takes_the_engine_subclass(self) -> None:
        from wc_caseload_engine.fact_templates import fact_aware_templates
        from wc_caseload_engine.renderer import _load_template

        override, _, class_name = _load_template("DIAGNOSTICS_IMAGING", fact_aware=True)
        assert override is fact_aware_templates()["DIAGNOSTICS_IMAGING"]
        assert class_name == "DiagnosticReport", (
            "the manifest's template provenance must stay the substrate class — "
            "the subclass renders the same document, it is not a fallback"
        )

    def test_the_registry_is_ignored_without_a_ledger(self) -> None:
        from wc_caseload_engine.renderer import _load_template

        plain, _, _ = _load_template("DIAGNOSTICS_IMAGING", fact_aware=False)
        assert plain.__module__.startswith("pdf_templates")

    def test_doctrine_and_fact_aware_content_compose_on_one_document(
        self, tmp_path: Path
    ) -> None:
        """Both seams fire on the same document.

        Doctrine injection wraps whatever ``_load_template`` returns, so a
        registry-covered subtype carrying a doctrine hook must render the
        ledger's content *and* the authorities addendum. Structurally it should
        hold; asserted here because "should" is not evidence.
        """
        seed = _seed(
            "composition",
            {"diagnostics": {"performed": [{"modality": "ct", "body_part": "lumbar_spine"}]}},
            lifecycle={
                "target_stage": "medical_legal",
                "eval_type": "qme",
                "doctrine_hooks": ["almaraz_guzman"],
            },
        )
        manifest, texts = _render(seed, tmp_path)

        flagged = [
            d
            for d in manifest["documents"]
            if "almaraz_guzman" in (d.get("contentFlags") or ())
            and d["subtype"] in FACT_AWARE_PROBE_SUBTYPES
        ]
        assert flagged, "no document carries both a doctrine flag and a fact-aware subtype"

        both = _flat(texts["QME_COMPREHENSIVE_REPORT"])
        assert "diagnostic review" in both, "fact-aware content missing"
        assert "guzman" in both, "doctrine marker missing"


# ---------------------------------------------------------------------------
# ISC-91 / 92 / 93 / 94
# ---------------------------------------------------------------------------


class TestClosedCoherenceRules:
    def test_isc91_an_absent_emg_appears_nowhere_in_the_qme(self, tmp_path: Path) -> None:
        """The electrodiagnostic paragraph is dropped when EMG did not happen."""
        seed = _seed(
            "isc91",
            {"diagnostics": {"performed": ["mri"], "absent": [{"modality": "emg"}]}},
        )
        _, texts = _render(seed, tmp_path)
        qme = _flat(texts.get("QME_COMPREHENSIVE_REPORT", ""))
        assert "electrodiagnostic studies" not in qme, (
            "the QME electrodiagnosed a study the ledger says was never performed"
        )
        assert "no emg study was obtained" in qme, "the absence must still be recorded"

    def test_isc91_positive_control_a_performed_emg_is_kept(self, tmp_path: Path) -> None:
        """The mirror: suppression must be conditional, not blanket."""
        seed = _seed("isc91-ctl", {"diagnostics": {"performed": ["mri", "emg"]}})
        _, texts = _render(seed, tmp_path)
        assert "emg" in _flat(texts.get("QME_COMPREHENSIVE_REPORT", "")), (
            "a performed EMG vanished from the QME"
        )

    def test_isc92_a_case_without_surgery_carries_no_surgical_language(
        self, tmp_path: Path
    ) -> None:
        seed = _seed("isc92-none", {"surgery": "none"})
        plan = build_case_plan(seed)
        assert plan.case_facts is not None and not plan.case_facts.surgery.performed
        _, texts = _render(seed, tmp_path)
        whole = _flat(" ".join(texts.values()))
        for phrase in ("status post", "post-operative rehabilitation"):
            assert phrase not in whole, f"a surgery-free case says {phrase!r}"

    def test_isc92_positive_control_surgery_reaches_the_documents(
        self, tmp_path: Path
    ) -> None:
        seed = _seed("isc92-yes", {"surgery": "performed"})
        _, texts = _render(seed, tmp_path)
        assert "status post" in _flat(" ".join(texts.values())), (
            "a surgical case never mentions the surgery"
        )

    def test_isc93_one_cpt_across_every_referencing_document(self, tmp_path: Path) -> None:
        """The operative record and both medical reports name one procedure."""
        seed = _seed(
            "isc93",
            {"surgery": "performed"},
            documents={
                "overrides": [
                    {"subtype": s, "count": 1}
                    for s in (*FACT_AWARE_PROBE_SUBTYPES, "OPERATIVE_HOSPITAL_RECORDS")
                ],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        cpt = plan.case_facts.surgery.cpt_code
        assert cpt
        _, texts = _render(seed, tmp_path)

        wanted = {
            "OPERATIVE_HOSPITAL_RECORDS",
            "QME_COMPREHENSIVE_REPORT",
            "TREATING_PHYSICIAN_REPORT_PR2",
        }
        referencing = {k: v for k, v in texts.items() if k in wanted}
        assert set(referencing) == wanted, sorted(referencing)
        for subtype, text in referencing.items():
            assert cpt in _flat(text), f"{subtype} names a different procedure than CPT {cpt}"

    def test_isc94_packets_are_answered_by_different_providers(self, tmp_path: Path) -> None:
        """The defect: every packet attributed to the treating physician."""
        seed = _seed(
            "isc94",
            {},
            documents={
                "overrides": [{"subtype": "SUBPOENAED_RECORDS_MEDICAL", "count": 3}],
                "format_mix": {"pdf": 1.0},
            },
        )
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert len(plan.case_facts.providers) >= 2, "the probe needs a roster to spread over"

        generate_case(seed, tmp_path, case_number=1)
        case_dir = tmp_path / seed.case_id
        manifest = json.loads((case_dir / MANIFEST_NAME).read_text())
        packets = [
            _flat(extract_text(case_dir / "documents" / d["filename"], d["format"]) or "")
            for d in manifest["documents"]
            if d["subtype"] == "SUBPOENAED_RECORDS_MEDICAL"
        ]
        assert len(packets) >= 2, "the probe emitted too few packets to compare"

        seen = [
            frozenset(
                p.facility.lower()
                for p in plan.case_facts.providers
                if p.facility and p.facility.lower() in text
            )
            for text in packets
        ]
        assert len({s for s in seen if s}) > 1, (
            "every packet names the same provider — the round-robin is not wired, "
            "which is the defect ISC-94 exists to close"
        )


class TestTheArtifactRoundTrips:
    def test_case_facts_yaml_loads_back(self, tmp_path: Path) -> None:
        """ISC-99 asks for a load round-trip, not just a file on disk."""
        import yaml

        seed = _seed("roundtrip", {"surgery": "performed"})
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        generate_case(seed, tmp_path, case_number=1)
        loaded = yaml.safe_load((tmp_path / seed.case_id / CASE_FACTS_NAME).read_text())
        assert loaded["surgery"]["cptCode"] == plan.case_facts.surgery.cpt_code
        assert len(loaded["diagnostics"]) == len(plan.case_facts.diagnostics)


class TestASeedWithNoScenarioBlockIsStillDeterministic:
    def test_double_derivation_without_scenario_is_identical(self) -> None:
        """ISC-87: the ledger is derived, not required to be stated."""
        body = {
            "case_id": "no-scenario",
            "rng_seed": 8123,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-04-11",
                "body_parts": [{"part": "lumbar_spine"}, {"part": "knee"}],
            },
            "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
        }
        assert "scenario" not in body
        first = build_case_plan(parse_case_seed(body)).case_facts
        second = build_case_plan(parse_case_seed(body)).case_facts
        assert first is not None and second is not None
        assert first.model_dump() == second.model_dump()
        assert first.diagnostics, "derivation produced no diagnostics at all"


# ---------------------------------------------------------------------------
# The scenario knob reaching the plan (AJC-37 review, item 1)
# ---------------------------------------------------------------------------
#
# Every test above this line used rng_seed 4242, which is exactly why the knob
# could be broken without any of them noticing: on that seed the coin happened
# to agree with the scenario. The pattern below is the fix, and it generalizes —
# for each scenario knob, one case where the underlying draw *disagrees* with
# the value the seed asked for. A knob that is never contradicted is never
# actually tested.

#: rng_seeds whose bare 35% clinical coin is known to land each way.
COIN_TRUE_SEED = 1000
COIN_FALSE_SEED = 1001


def _bare_coin(seed: Any) -> bool:
    """The substrate's 35% surgery coin, read off an otherwise untouched stream."""
    return seed.rng("clinical").random() < 0.35


def _has_surgery(seed: Any) -> bool:
    """What the planner will tell the substrate about this case."""
    return bool(seed_to_case_parameters(seed).has_surgery)


class TestScenarioSurgeryBeatsTheCoin:
    def test_the_counterfactual_fixtures_really_do_disagree(self) -> None:
        """Guard the guard: if these drift, the two tests below prove nothing."""
        assert _bare_coin(_seed("coin-t", {}, rng_seed=COIN_TRUE_SEED)) is True
        assert _bare_coin(_seed("coin-f", {}, rng_seed=COIN_FALSE_SEED)) is False

    def test_none_beats_a_coin_that_says_surgery(self) -> None:
        """Opposite-coin: coin says operate, seed says no. The seed wins."""
        seed = _seed("scenario-none", {"surgery": "none"}, rng_seed=COIN_TRUE_SEED)
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert plan.case_facts.surgery.status == "none"
        assert _has_surgery(seed) is False, (
            "the ledger says no surgery but the substrate parameters still say yes — "
            "operative documents will be planned for a case the ledger denies"
        )
        operative = [d.subtype for d in plan.documents if "OPERATIVE" in d.subtype]
        assert not operative, f"planned operative documents on a no-surgery case: {operative}"

    def test_performed_beats_a_coin_that_says_no_surgery(self) -> None:
        """Opposite-coin, the other direction: coin says no, seed says operate."""
        seed = _seed("scenario-performed", {"surgery": "performed"}, rng_seed=COIN_FALSE_SEED)
        plan = build_case_plan(seed)
        assert plan.case_facts is not None
        assert plan.case_facts.surgery.status == "performed"
        assert _has_surgery(seed) is True, (
            "the ledger asserts a surgery the substrate parameters do not — "
            "no operative document will be planned to back it up"
        )

    @pytest.mark.parametrize("rng_seed", [1000, 1001, 1002, 1003, 1004, 1005, 4242, 8123])
    def test_ledger_and_parameters_never_disagree(self, rng_seed: int) -> None:
        """The invariant behind both directions, swept over varied seeds."""
        for scenario in ({}, {"surgery": "none"}, {"surgery": "performed"}):
            seed = _seed(f"agree-{rng_seed}", scenario, rng_seed=rng_seed)
            facts = build_case_plan(seed).case_facts
            assert facts is not None
            assert (facts.surgery.status == "performed") == _has_surgery(seed), (
                f"rng_seed={rng_seed} scenario={scenario}: ledger says "
                f"{facts.surgery.status!r}, parameters say has_surgery={_has_surgery(seed)}"
            )

    def test_an_unspecified_seed_still_takes_the_coin(self) -> None:
        """The override must not become a silent default in either direction."""
        assert _has_surgery(_seed("bare-t", {}, rng_seed=COIN_TRUE_SEED)) is True
        assert _has_surgery(_seed("bare-f", {}, rng_seed=COIN_FALSE_SEED)) is False


# ---------------------------------------------------------------------------
# The manifest publishes only facts a template renders (review item 3)
# ---------------------------------------------------------------------------


class TestOnlyGovernedFactsArePublished:
    """A published fact is a promise the documents keep.

    ``wpi``, ``pd``, ``mmiDate``, ``visits``, and the per-fact body parts and
    dates are all derived and all currently unrendered, so publishing them lets
    the manifest state things its own documents contradict. They stay on the
    model for later phases; they do not reach the output.
    """

    def test_the_published_block_carries_exactly_the_governed_fields(self) -> None:
        facts = build_case_plan(_seed("governed", {"surgery": "performed"})).case_facts
        assert facts is not None
        block = facts_manifest_block(facts)
        assert set(block) == set(GOVERNED_LEDGER_FIELDS)
        for entry in block["diagnostics"]:
            assert set(entry) == set(GOVERNED_LEDGER_FIELDS["diagnostics"])
        assert set(block["surgery"]) == set(GOVERNED_LEDGER_FIELDS["surgery"])
        for provider in block["providers"]:
            assert set(provider) == set(GOVERNED_LEDGER_FIELDS["providers"])

    def test_ungoverned_facts_survive_on_the_model(self) -> None:
        """Unpublished is not underived — Phase 2 needs these."""
        facts = build_case_plan(_seed("internal", {"surgery": "performed"})).case_facts
        assert facts is not None
        assert facts.mmi_date is not None
        assert facts.visits, "visit series was dropped rather than unpublished"

    #: Ledger fields that must never be published. Every one is a *field name*,
    #: which is why the check below walks keys.
    BANNED_FIELDS = ("wpi", "pd", "mmiDate", "visits", "bodyPart")

    @staticmethod
    def _keys_of(node: Any) -> set[str]:
        """Every mapping key anywhere in a nested structure."""
        if isinstance(node, dict):
            found = set(node)
            for value in node.values():
                found |= TestOnlyGovernedFactsArePublished._keys_of(value)
            return found
        if isinstance(node, list):
            found: set[str] = set()
            for item in node:
                found |= TestOnlyGovernedFactsArePublished._keys_of(item)
            return found
        return set()

    def test_neither_output_carries_an_ungoverned_field(self, tmp_path: Path) -> None:
        """Keys, not substrings.

        This scanned the serialized JSON for each banned name as a raw
        substring until ISC-121 published ``letterTypesAllowed``, whose value
        ``pd_advance_offer`` contains "pd" and tripped it. The substring sweep
        was always a proxy for the real rule — *publishes an ungoverned field* —
        and a value that happens to spell a banned name is not a leak.

        Narrowing a guard to make one's own change pass is how guards die, so
        the planted-leak control below is not optional: it proves the key walk
        still catches what the substring sweep caught.
        """
        seed = _seed("no-leak", {"surgery": "performed"})
        manifest, _ = _render(seed, tmp_path)
        yaml_text = (tmp_path / seed.case_id / CASE_FACTS_NAME).read_text()
        published = self._keys_of(manifest["caseFacts"])
        for banned in self.BANNED_FIELDS:
            assert banned not in published, f"manifest leaks the {banned} field"
            assert f"{banned}:" not in yaml_text, f"case_facts.yaml leaks {banned}"

    def test_the_key_walk_still_catches_a_planted_leak(self) -> None:
        """The control for the test above. Without it, narrowing the check from
        substrings to keys would be indistinguishable from deleting it."""
        for banned in self.BANNED_FIELDS:
            planted = {"treatment": {"status": "ongoing"}, "surgery": [{banned: 42}]}
            assert banned in self._keys_of(planted), (
                f"the key walk cannot see a planted {banned} field"
            )


# ---------------------------------------------------------------------------
# An imaging report only ever reports an imaging modality (review item 4)
# ---------------------------------------------------------------------------


class TestImagingReportsOnlyCarryImagingModalities:
    def test_emg_is_not_an_assignable_imaging_modality(self) -> None:
        assert "emg" not in IMAGING_MODALITIES
        assert "labs" not in IMAGING_MODALITIES
        assert set(IMAGING_MODALITIES) <= set(MODALITIES)

    def test_a_forced_emg_never_reaches_the_imaging_template(self) -> None:
        """The ledger may hold an EMG; the imaging report must not be handed one."""
        seed = _seed(
            "emg-ledger",
            {"diagnostics": {"performed": [{"modality": "emg", "body_part": "lumbar_spine"}]}},
            rng_seed=5150,
        )
        facts = build_case_plan(seed).case_facts
        assert facts is not None
        assert any(f.modality == "emg" for f in facts.performed_diagnostics), (
            "fixture no longer plants an EMG; the test proves nothing"
        )
        for index in range(6):
            chosen = facts.diagnostic_for(index)
            if chosen is not None:
                assert chosen.modality in IMAGING_MODALITIES, (
                    f"imaging report {index} would be told to report {chosen.modality!r}, "
                    "which the template can only render with radiographic technique"
                )

    @pytest.mark.parametrize("modality", ["mri", "ct", "xray"])
    def test_every_accepted_modality_renders_its_own_technique(
        self, modality: str, tmp_path: Path
    ) -> None:
        """The reason emg is excluded: technique text is chosen by modality."""
        seed = _seed(
            f"tech-{modality}",
            {"diagnostics": {"performed": [{"modality": modality, "body_part": "lumbar_spine"}]}},
            rng_seed=6000 + MODALITIES.index(modality),
        )
        _, texts = _render(seed, tmp_path)
        body = _flat(texts.get("DIAGNOSTICS_IMAGING", ""))
        assert "technique" in body, "no TECHNIQUE section rendered at all"
        display = MODALITY_DISPLAY[modality].lower()
        assert display in body, f"{display} never named in a report the ledger says is {display}"


# ---------------------------------------------------------------------------
# The validator sees the ledger (review item 5)
# ---------------------------------------------------------------------------


def _tamper(path: Path, mutate: Any) -> None:
    """Rewrite a JSON file through *mutate*, leaving everything else intact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestValidateChecksTheLedger:
    """``validate --out`` treated the ledger as decoration. A fact nobody
    validates is a fact that can rot silently — the whole point of publishing
    it is that a reader can check the case against itself.
    """

    def test_a_clean_tree_passes(self, tmp_path: Path) -> None:
        seed = _seed("valid-clean", {"surgery": "performed"})
        _render(seed, tmp_path)
        report = validate_output_tree(tmp_path)
        assert report.ok, report.problems

    def test_a_missing_case_facts_block_fails(self, tmp_path: Path) -> None:
        seed = _seed("valid-noblock", {"surgery": "performed"})
        _render(seed, tmp_path)
        _tamper(tmp_path / seed.case_id / MANIFEST_NAME, lambda m: m.pop("caseFacts"))
        report = validate_output_tree(tmp_path)
        assert not report.ok
        assert any("caseFacts" in p for p in report.problems), report.problems

    def test_a_missing_yaml_artifact_fails(self, tmp_path: Path) -> None:
        seed = _seed("valid-noyaml", {"surgery": "performed"})
        _render(seed, tmp_path)
        (tmp_path / seed.case_id / CASE_FACTS_NAME).unlink()
        report = validate_output_tree(tmp_path)
        assert not report.ok
        assert any(CASE_FACTS_NAME in p for p in report.problems), report.problems

    def test_a_yaml_that_disagrees_with_the_manifest_fails(self, tmp_path: Path) -> None:
        """Two published copies of one ledger must not drift apart."""
        seed = _seed("valid-drift", {"surgery": "performed"})
        _render(seed, tmp_path)
        path = tmp_path / seed.case_id / CASE_FACTS_NAME
        path.write_text(path.read_text().replace("performed", "none"), encoding="utf-8")
        report = validate_output_tree(tmp_path)
        assert not report.ok
        assert any("disagree" in p for p in report.problems), report.problems

    def test_an_operative_document_the_ledger_denies_fails(self, tmp_path: Path) -> None:
        """The direction of the surgery rule that actually holds.

        Only one way round is enforceable from the output. An operative record
        sitting in a case whose ledger says no surgery is unambiguously wrong.
        The converse — surgery performed, therefore an operative document must
        exist — is *not* a property of this system: the substrate's walk gates
        rules on ``has_surgery`` without guaranteeing the document, and two of
        the seven demo cases resolve surgery true while emitting none. Asserting
        it would make ``validate`` red on the package's own examples.
        """
        seed = _seed(
            "valid-phantom-op",
            {"surgery": "performed"},
            documents={
                "overrides": [{"subtype": "OPERATIVE_HOSPITAL_RECORDS", "count": 1}],
                "format_mix": {"pdf": 1.0},
            },
        )
        _render(seed, tmp_path)
        manifest_path = tmp_path / seed.case_id / MANIFEST_NAME
        assert any(
            d["subtype"] == "OPERATIVE_HOSPITAL_RECORDS"
            for d in json.loads(manifest_path.read_text())["documents"]
        ), "fixture emitted no operative document; the tamper below proves nothing"

        def deny_surgery(manifest: dict[str, Any]) -> None:
            manifest["caseFacts"]["surgery"] = {
                "status": "none",
                "cptCode": None,
                "cptDescription": None,
            }

        _tamper(manifest_path, deny_surgery)
        report = validate_output_tree(tmp_path)
        assert not report.ok
        assert any("operative" in p.lower() for p in report.problems), report.problems

    def test_a_performed_surgery_with_no_cpt_fails(self, tmp_path: Path) -> None:
        seed = _seed("valid-nocpt", {"surgery": "performed"})
        _render(seed, tmp_path)

        def strip_cpt(manifest: dict[str, Any]) -> None:
            manifest["caseFacts"]["surgery"]["cptCode"] = None

        _tamper(tmp_path / seed.case_id / MANIFEST_NAME, strip_cpt)
        report = validate_output_tree(tmp_path)
        assert not report.ok
        assert any("CPT" in p for p in report.problems), report.problems

    def test_an_illegal_modality_fails(self, tmp_path: Path) -> None:
        seed = _seed("valid-badmod", {"surgery": "none"})
        _render(seed, tmp_path)

        def corrupt(manifest: dict[str, Any]) -> None:
            manifest["caseFacts"]["diagnostics"][0]["modality"] = "tricorder"

        _tamper(tmp_path / seed.case_id / MANIFEST_NAME, corrupt)
        report = validate_output_tree(tmp_path)
        assert not report.ok
        assert any("tricorder" in p for p in report.problems), report.problems

    def test_a_malformed_ledger_fails_rather_than_crashing(self, tmp_path: Path) -> None:
        seed = _seed("valid-malformed", {"surgery": "none"})
        _render(seed, tmp_path)
        _tamper(
            tmp_path / seed.case_id / MANIFEST_NAME,
            lambda m: m.__setitem__("caseFacts", "not a mapping"),
        )
        report = validate_output_tree(tmp_path)
        assert not report.ok
