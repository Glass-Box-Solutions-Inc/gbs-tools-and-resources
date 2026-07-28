"""What a manifest asserts must be true of the files beside it.

Three findings from the cross-model release review, each the same shape: a
manifest field that describes an *intention* while reading as a statement of
fact about the output.

* **`zeroRealPii` over a detected hit.** A seed naming a real, denylisted
  organization was warned about in the log and then recorded as provenance
  ``seed`` — a value inside ``SYNTHETIC_PROVENANCE`` — so the manifest went on
  asserting ``zeroRealPii: true`` about a name the engine had itself just
  identified as real. The log line was the only evidence, and logs are not
  shipped with a corpus.
* **A non-canonical override reaching the manifest.** The engine's contract is
  that every subtype it writes is classifier vocabulary. Control keys were
  checked only by ``wc-caseload validate --spec``, never by ``generate``, and
  the check admitted substrate-only keys.
* **Track summaries describing proposals.** ``liens[]`` and ``recon{}`` counted
  the documents the lien and reconsideration machines *proposed*, before
  perspective suppression and control resolution had their say. A case that
  excluded every lien document still reported a lien track with documents in it.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from conftest import requires_substrate
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate

DENYLISTED_EMPLOYER = "Costco Wholesale"
"""A real organization, on the shipped denylist — the positive control."""

UNMAPPED_SUBSTRATE_ONLY = "BLANK_SCANNED_PAGE"
"""Substrate realism vocabulary with no classifier equivalent (must be rejected)."""

MAPPED_SUBSTRATE_ONLY = "FAX_COVER_SHEET"
"""Substrate vocabulary that *does* map — ``SUBSTRATE_TO_CANONICAL`` sends it home."""

MAPPED_SUBSTRATE_ONLY_CANONICAL = "FAX_CORRESPONDENCE"


def _seed(case_id: str, **overrides: Any) -> Any:
    """A small, valid case, plus whatever the caller is probing."""
    payload: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 5150,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-05-17",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "claim_response": "accepted",
            "eval_type": "qme",
            "resolution": {"type": "c_and_r"},
        },
        "documents": {"format_mix": {"pdf": 1.0}, "global_cap": 12},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key] = {**payload[key], **value}
        else:
            payload[key] = value
    return parse_case_seed(payload)


def _manifest(result: Any) -> dict[str, Any]:
    return json.loads((result.directory / MANIFEST_NAME).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Finding 2 — zeroRealPii may not out-vote the denylist
# ---------------------------------------------------------------------------


class TestDenylistHitDefeatsZeroRealPii:
    """A detected real name must reach the manifest, not just the log."""

    @pytest.fixture(scope="class")
    def generated(self, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
        out = tmp_path_factory.mktemp("denylisted-seed")
        seed = _seed("denylisted-employer", profile={"employer": {"name": DENYLISTED_EMPLOYER}})
        return _manifest(generate_case(seed, out))

    def test_zero_real_pii_is_false(self, generated: dict[str, Any]) -> None:
        """The claim the whole provenance block exists to make honest."""
        assert generated["provenance"]["zeroRealPii"] is False, (
            "a seed naming a denylisted organization still claimed zero real PII"
        )

    def test_the_offending_field_is_named_in_the_provenance(
        self, generated: dict[str, Any]
    ) -> None:
        """Which field, not merely that something is wrong."""
        provenance = generated["provenance"]["castProvenance"]
        assert provenance["employer"] not in {"seed", "faker", "engine"}, (
            f"employer provenance is {provenance['employer']!r}, a value that votes for "
            "zeroRealPii"
        )

    def test_the_hit_reaches_the_manifest_warnings(self, generated: dict[str, Any]) -> None:
        """A warning in a log the corpus does not ship with is not evidence."""
        warnings = generated.get("warnings", [])
        assert any(DENYLISTED_EMPLOYER.lower() in warning.lower() for warning in warnings), (
            f"no manifest warning names the denylisted employer; got {warnings}"
        )

    def test_the_seed_declared_name_is_still_kept(self, generated: dict[str, Any]) -> None:
        """Retention is deliberate: the seed is the contract, loudly."""
        assert generated["employer"] == DENYLISTED_EMPLOYER

    def test_a_clean_seed_still_claims_zero_real_pii(self, tmp_path: Path) -> None:
        """Guards the probe: if everything were false, the flag would be useless."""
        manifest = _manifest(generate_case(_seed("clean-employer"), tmp_path))
        assert manifest["provenance"]["zeroRealPii"] is True
        assert not any(
            "denylist" in warning.lower() for warning in manifest.get("warnings", [])
        )


# ---------------------------------------------------------------------------
# Finding 3 — nothing non-canonical may reach a manifest
# ---------------------------------------------------------------------------


class TestControlKeysAreCanonicalAtGenerate:
    """``validate --spec`` was the only gate; ``generate`` is the one that ships."""

    def test_an_unmapped_substrate_only_override_is_rejected(self, tmp_path: Path) -> None:
        """Rejected at generate, with a message that says what to do."""
        seed = _seed(
            "bad-override",
            documents={"overrides": [{"subtype": UNMAPPED_SUBSTRATE_ONLY, "count": 1}]},
        )
        with pytest.raises(ValueError) as excinfo:
            generate_case(seed, tmp_path)
        message = str(excinfo.value)
        assert UNMAPPED_SUBSTRATE_ONLY in message
        assert "documents.overrides" in message, "the message does not name the offending control"

    def test_a_typo_key_is_rejected(self, tmp_path: Path) -> None:
        seed = _seed(
            "typo-override",
            documents={"overrides": [{"subtype": "QME_COMPREHENSIVE_REPRT", "count": 1}]},
        )
        with pytest.raises(ValueError, match="QME_COMPREHENSIVE_REPRT"):
            generate_case(seed, tmp_path)

    def test_an_unmapped_exclude_key_is_rejected(self, tmp_path: Path) -> None:
        """Every control channel, not only overrides."""
        seed = _seed("bad-exclude", documents={"exclude": [UNMAPPED_SUBSTRATE_ONLY]})
        with pytest.raises(ValueError, match=UNMAPPED_SUBSTRATE_ONLY):
            generate_case(seed, tmp_path)

    def test_a_mapped_substrate_key_is_normalized_rather_than_rejected(
        self, tmp_path: Path
    ) -> None:
        """``SUBSTRATE_TO_CANONICAL`` already knows the answer for these."""
        seed = _seed(
            "mapped-override",
            documents={
                "format_mix": {"pdf": 1.0},
                "include_only": [MAPPED_SUBSTRATE_ONLY],
                "overrides": [{"subtype": MAPPED_SUBSTRATE_ONLY, "count": 1}],
                "global_cap": 4,
            },
        )
        manifest = _manifest(generate_case(seed, tmp_path))
        subtypes = {entry["subtype"] for entry in manifest["documents"]}
        assert MAPPED_SUBSTRATE_ONLY not in subtypes, "substrate-only vocabulary reached a manifest"
        assert MAPPED_SUBSTRATE_ONLY_CANONICAL in subtypes, "the mapped key emitted nothing"

    def test_an_alias_that_collides_with_an_exclusion_is_rejected(self) -> None:
        """N2: the schema's overlap check runs on raw keys, before aliasing.

        ``CLIENT_REPORT_ANALYSIS_LETTER`` canonicalizes to
        ``CLIENT_CORRESPONDENCE_INFORMATIONAL``, so this pair is an explicit
        include and an explicit exclude of the *same* subtype written two ways.
        The schema validator sees two different strings and passes; the resolver
        then applies the exclude and silently drops the include the seed author
        asked for. Aliasing created the collision, so aliasing has to re-check.
        """
        seed = _seed(
            "alias-collision",
            documents={
                "include_only": ["CLIENT_CORRESPONDENCE_INFORMATIONAL"],
                "exclude": ["CLIENT_REPORT_ANALYSIS_LETTER"],
            },
        )
        with pytest.raises(ValueError) as excinfo:
            build_case_plan(seed)
        message = str(excinfo.value)
        assert "CLIENT_REPORT_ANALYSIS_LETTER" in message, "the original alias is not named"
        assert "CLIENT_CORRESPONDENCE_INFORMATIONAL" in message

    def test_two_aliases_of_one_subtype_in_one_list_are_rejected(self) -> None:
        """The duplicate half of the same problem, within a single control."""
        seed = _seed(
            "alias-duplicate",
            documents={
                "exclude": ["CLIENT_REPORT_ANALYSIS_LETTER", "CLIENT_CASE_VALUATION_LETTER"],
            },
        )
        with pytest.raises(ValueError, match="CLIENT_CORRESPONDENCE_INFORMATIONAL"):
            build_case_plan(seed)

    def test_distinct_canonical_keys_are_left_alone(self) -> None:
        """Guards the check: it must not fire on keys that merely look similar."""
        seed = _seed(
            "alias-clean",
            documents={
                "include_only": ["CLIENT_CORRESPONDENCE_INFORMATIONAL", "TRIAL_BRIEF"],
                "exclude": ["DEFENSE_TRIAL_BRIEF"],
            },
        )
        build_case_plan(seed)

    def test_the_planner_refuses_to_build_a_non_canonical_document(self) -> None:
        """Fail closed at the last line of defence, not only at the front door.

        The normalization above is the fix; this is the assertion that would
        catch a *future* path into the planner that bypasses it.
        """
        seed = _seed(
            "planner-guard",
            documents={"overrides": [{"subtype": UNMAPPED_SUBSTRATE_ONLY, "count": 1}]},
        )
        with pytest.raises(ValueError, match=UNMAPPED_SUBSTRATE_ONLY):
            build_case_plan(seed)


# ---------------------------------------------------------------------------
# Finding 4 — track summaries must count what was emitted
# ---------------------------------------------------------------------------


class TestTrackSummariesCountEmittedDocuments:
    """``liens[].documentCount`` is read as a fact about the folder.

    One thing to know before reading the exclusions below: a lien *track* is not
    the ``LIENS`` document type. It runs from a lien claim through notices to a
    resolution, and the notices are ``CORRESPONDENCE`` — so ``exclude: [LIENS]``
    suppresses part of a track and leaves the rest emitting. The suppression
    probe therefore excludes the subtypes the machine actually proposed, read
    off the plan rather than transcribed, which is also the only version of this
    test that cannot rot when the lien machine's document set changes.
    """

    LIEN_SEED_LIFECYCLE: ClassVar[dict[str, Any]] = {
        "target_stage": "resolved",
        "claim_response": "accepted",
        "eval_type": "qme",
        "resolution": {"type": "c_and_r"},
        "liens": {
            "count": 1,
            "claimants": ["medical_provider"],
            "resolution": "lien_stipulation",
        },
    }

    @classmethod
    def _lien_seed(cls, case_id: str, **documents: Any) -> Any:
        return _seed(
            case_id,
            lifecycle=dict(cls.LIEN_SEED_LIFECYCLE),
            documents={"format_mix": {"pdf": 1.0}, "global_cap": 40, **documents},
        )

    @pytest.fixture(scope="class")
    def proposed_subtypes(self) -> list[str]:
        """Every subtype the lien machine proposes for this seed."""
        plan = build_case_plan(self._lien_seed("liens-proposal"))
        assert plan.lien_tracks, "the seed produced no lien track — the probe is vacuous"
        return sorted(
            {candidate.subtype for track in plan.lien_tracks for candidate in track.documents}
        )

    @pytest.fixture(scope="class")
    def suppressed(
        self, proposed_subtypes: list[str], tmp_path_factory: pytest.TempPathFactory
    ) -> dict[str, Any]:
        """The same case with every document of the lien track excluded."""
        out = tmp_path_factory.mktemp("liens-suppressed")
        seed = self._lien_seed("liens-excluded", exclude=proposed_subtypes)
        return _manifest(generate_case(seed, out))

    def test_the_case_really_has_a_lien_track(self, suppressed: dict[str, Any]) -> None:
        """Guards the assertions below against a case with no liens at all."""
        assert suppressed["liens"], "the seed produced no lien track — probe is vacuous"

    def test_no_document_of_the_track_was_emitted(
        self, suppressed: dict[str, Any], proposed_subtypes: list[str]
    ) -> None:
        emitted = [
            entry["subtype"]
            for entry in suppressed["documents"]
            if entry["subtype"] in set(proposed_subtypes)
        ]
        assert not emitted, f"exclude did not suppress the lien track: {sorted(set(emitted))}"

    def test_the_summary_reports_the_emitted_count(self, suppressed: dict[str, Any]) -> None:
        """The number a reader will take as "how many lien documents are here"."""
        for track in suppressed["liens"]:
            assert track["documentCount"] == 0, (
                f"lien track {track['index']} reports {track['documentCount']} documents "
                "while the folder holds none"
            )

    def test_the_proposal_is_still_available(self, suppressed: dict[str, Any]) -> None:
        """Suppressing the count must not destroy the information.

        What the machine proposed is worth keeping — it is the difference
        between "this case had no liens" and "this case had liens and the
        controls removed them" — so it moves to its own field rather than
        being dropped.
        """
        for track in suppressed["liens"]:
            assert track["plannedDocumentCount"] >= 1

    def test_an_unsuppressed_case_reports_a_count_its_folder_can_support(
        self, tmp_path: Path
    ) -> None:
        """The other direction: emitted is real, and never exceeds what was written."""
        manifest = _manifest(generate_case(self._lien_seed("liens-emitted"), tmp_path))
        assert manifest["liens"], "no lien track to check"
        reported = sum(int(track["documentCount"]) for track in manifest["liens"])
        assert reported > 0, "nothing emitted — the positive direction is untested"
        assert reported <= len(manifest["documents"]), (
            f"lien summaries claim {reported} documents in a case holding "
            f"{len(manifest['documents'])}"
        )
        for track in manifest["liens"]:
            assert track["documentCount"] <= track["plannedDocumentCount"], (
                "a track emitted more documents than it proposed"
            )

    def test_recon_summary_reports_emitted_documents(self, tmp_path: Path) -> None:
        """The reconsideration track, suppressed the same way."""
        seed = _seed(
            "recon-excluded",
            lifecycle={
                "target_stage": "post_recon",
                "claim_response": "accepted",
                "eval_type": "qme",
                "resolution": {"type": "findings_award"},
                "reconsideration": {
                    "enabled": True,
                    "outcome": "denied",
                    "post_recon": "affirmed_final",
                },
            },
            injury={
                "type": "specific",
                "date_of_injury": "2021-03-08",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
            documents={
                "format_mix": {"pdf": 1.0},
                "exclude": ["PETITION_RECONSIDERATION_FILED"],
                "global_cap": 40,
            },
        )
        manifest = _manifest(generate_case(seed, tmp_path))
        emitted = sum(
            1
            for entry in manifest["documents"]
            if entry["subtype"] == "PETITION_RECONSIDERATION_FILED"
        )
        assert emitted == 0, "exclude did not suppress the petition"
        recon = manifest["recon"]
        assert recon["enabled"] is True
        assert recon["documentCount"] < recon["plannedDocumentCount"], (
            "the recon summary counts a document the controls removed"
        )

    def test_a_suppressed_recon_document_leaves_no_date_behind(self, tmp_path: Path) -> None:
        """F4-residual: the dates have to agree with the count beside them.

        ``documentCount: 0`` next to a concrete ``petitionDate`` reads as "the
        petition was filed on this date and is not in the folder", which is not
        what happened — the control removed it before anything was written. The
        date the machine proposed is still worth keeping, so it moves to
        ``plannedPetitionDate``, exactly as the counts did.
        """
        seed = _seed(
            "recon-dates",
            lifecycle={
                "target_stage": "post_recon",
                "claim_response": "accepted",
                "eval_type": "qme",
                "resolution": {"type": "findings_award"},
                "reconsideration": {
                    "enabled": True,
                    "outcome": "denied",
                    "post_recon": "affirmed_final",
                },
            },
            injury={
                "type": "specific",
                "date_of_injury": "2021-03-08",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
            documents={
                "format_mix": {"pdf": 1.0},
                "exclude": ["PETITION_RECONSIDERATION_FILED"],
                "global_cap": 40,
            },
        )
        recon = _manifest(generate_case(seed, tmp_path))["recon"]

        assert recon["petitionDate"] is None, (
            "a petition the controls suppressed still reports the date it would have had"
        )
        assert recon["plannedPetitionDate"] is not None, "the proposed date was discarded"

    def test_an_emitted_recon_document_keeps_its_date(self, tmp_path: Path) -> None:
        """Guards the above: nulling dates unconditionally would also pass it."""
        seed = _seed(
            "recon-dates-kept",
            lifecycle={
                "target_stage": "post_recon",
                "claim_response": "accepted",
                "eval_type": "qme",
                "resolution": {"type": "findings_award"},
                "reconsideration": {
                    "enabled": True,
                    "outcome": "denied",
                    "post_recon": "affirmed_final",
                },
            },
            injury={
                "type": "specific",
                "date_of_injury": "2021-03-08",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
            documents={"format_mix": {"pdf": 1.0}, "global_cap": 60},
        )
        manifest = _manifest(generate_case(seed, tmp_path))
        recon = manifest["recon"]
        emitted = {entry["subtype"] for entry in manifest["documents"]}

        assert "PETITION_RECONSIDERATION_FILED" in emitted, "the petition was not emitted"
        assert recon["petitionDate"] is not None, "an emitted petition lost its date"
        assert recon["petitionDate"] == recon["plannedPetitionDate"]
