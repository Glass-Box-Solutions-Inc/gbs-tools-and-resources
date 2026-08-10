"""Caller-governed apportionment and causation for the QME/AME report (AJC-65).

Apportionment decides who pays for a permanent disability. Under LC §4663 it is
the most contested opinion a QME writes, and this package decided it by coin
flip — twice, independently, in the same document. ``QmeAmeReport``'s
conclusions flipped between two canned sentences; ``impairment_rating_section``
separately drew a percentage from ``[0,0,0,10,15,20,25]``. A single report could
rate 20% apportioned in one section and declare no apportionment applicable in
another.

This module is the one place that reads a caller's apportionment decision, so
the two sections cannot disagree: they render from the *same* parsed decision
rather than from two readings of the same dict.

**The contract**

::

    context["apportionment"] = {
        "register": "none" | "apportioned" | "deferred",
        "nonindustrial_pct": 30,        # int 0-100, the share apportioned away
        "basis": "pre-existing degenerative disc disease",
        "opinion": "…",                 # verbatim conclusion sentence(s)
    }
    context["causation"] = {
        "attribution": "predominantly", # the adverb only
        "discussion": "…",              # verbatim
    }

Malformed input **raises**, following the convention AJC-66 established for
``variant_content`` on this same context channel: a truthy value of the wrong
type is refused rather than guessed at. The alternative — treating a malformed
block as absent — silently restores the randomness the caller was trying to
remove, and does it most often in exactly the case where a caller believed it
had governed the document.

Absent, ``None``, and ``{}`` are *not* malformed. The consuming engine sets a
dozen keys on every context, so a key arriving empty from a caller that governs
nothing must read exactly like a key that is not there.

**One rule worth stating plainly:** once a caller governs apportionment at all,
the substrate never invents one. Every register suppresses the random
apportionment narrative in the impairment section and replaces it with the
caller's own posture — determined, deferred, or none. A governed conclusion
sitting beside an invented percentage is the defect this seam exists to remove,
so there is no combination of inputs that produces one.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTEXT_KEY = "apportionment"
CAUSATION_CONTEXT_KEY = "causation"

#: The postures a QME can take. ``deferred`` is deliberately distinct from
#: ``none``: reserving the question pending records is the most common posture at
#: an initial evaluation, and collapsing the two would leave a caller unable to
#: express it.
REGISTERS = ("none", "apportioned", "deferred")

_ALLOWED_KEYS = frozenset({"register", "nonindustrial_pct", "basis", "opinion"})
_ALLOWED_CAUSATION_KEYS = frozenset({"attribution", "discussion"})

DEFAULT_BASIS = "nonindustrial factors"

# The two sentences the template flipped between, kept verbatim so the
# ungoverned path renders exactly what it always did.
SENTENCE_NONE = (
    "No apportionment is applicable in this case. The entire permanent disability is "
    "attributable to the industrial injury. There is no credible evidence of pre-existing "
    "pathology contributing to the current impairment."
)
SENTENCE_ADDRESSED = (
    "Apportionment has been addressed as outlined in the impairment rating section of this "
    "report per LC §4663 and §4664."
)
SENTENCE_DEFERRED = (
    "Apportionment is deferred at this time pending receipt and review of the outstanding "
    "records identified in this report. I reserve the right to address apportionment under "
    "LC §4663 and §4664 in a supplemental report."
)

_LC_CITATION = "LC §4663 and §4664 — apportionment of permanent disability"


def _reject(what: str, value: object, expected: str) -> None:
    raise ValueError(
        f"context[{CONTEXT_KEY!r}] {what}: expected {expected}; got "
        f"{type(value).__name__!r} ({value!r}). A malformed governance block is "
        f"refused rather than ignored — ignoring it would silently restore the "
        f"randomness the caller was governing away."
    )


@dataclass(frozen=True)
class ApportionmentDecision:
    """One caller's apportionment posture, validated, rendered two ways.

    Both render methods are pure: they consume no randomness. That is what lets
    the impairment section keep its legacy draws keyed to the value the
    substrate *drew* while printing the value the caller *gave* — the two
    concerns are separated precisely because coupling them shifts the rng stream
    across the zero/nonzero boundary and rewrites the rest of the document.
    """

    register: str
    nonindustrial_pct: int | None = None
    basis: str | None = None
    opinion: str | None = None

    @property
    def industrial_pct(self) -> int | None:
        if self.nonindustrial_pct is None:
            return None
        return 100 - self.nonindustrial_pct

    def conclusion_sentence(self) -> str:
        """The apportionment opinion for the conclusions list."""
        if self.opinion:
            return self.opinion
        if self.register == "deferred":
            return SENTENCE_DEFERRED
        if self.register == "none":
            return SENTENCE_NONE
        basis = self.basis or DEFAULT_BASIS
        return (
            f"{self.industrial_pct}% of the permanent disability is attributable to the "
            f"industrial injury and {self.nonindustrial_pct}% is apportioned to {basis}, "
            f"per LC §4663 and §4664. This apportionment rests on the history, the records "
            f"reviewed, and the clinical findings documented in this report."
        )

    def impairment_block(self, body_parts: list[str] | None = None) -> str | None:
        """The apportionment block for the impairment narrative, or ``None``.

        ``None`` suppresses the block. That is the answer for ``none`` — there
        is nothing to apportion — and for a bare ``opinion``, which gives prose
        but no number: printing a drawn percentage beside a governed opinion is
        the contradiction this seam removes, so the section says nothing rather
        than inventing something.
        """
        if self.register == "none":
            return None
        if self.register == "deferred":
            return (
                f"\n<b>Apportionment — {_LC_CITATION}</b>\n"
                "Apportionment is deferred pending receipt and review of the outstanding "
                "records identified in this report. No apportionment percentage is "
                "determined at this time; the question is expressly reserved under Labor "
                "Code §4663 and §4664 and will be addressed in a supplemental report."
            )
        if self.nonindustrial_pct is None:
            # Governed by prose alone. See the docstring.
            return None
        region = ", ".join((body_parts or [])[:2]) or "the injured region"
        basis = self.basis or DEFAULT_BASIS
        return (
            f"\n<b>Apportionment — {_LC_CITATION}</b>\n"
            f"Per Labor Code §4663, {self.nonindustrial_pct}% of the current permanent "
            f"disability of the {region} is apportioned to {basis}. The remaining "
            f"{self.industrial_pct}% is causally related to the industrial injury. This "
            f"apportionment is based on the history, the records reviewed, and the clinical "
            f"findings documented in this report, and is stated to a reasonable degree of "
            f"medical probability."
        )


@dataclass(frozen=True)
class CausationGovernance:
    """A caller's causation content. ``discussion`` outranks ``attribution``."""

    attribution: str | None = None
    discussion: str | None = None


def _validated_text(block: dict, key: str) -> str | None:
    value = block.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _reject(f"key {key!r}", value, "a non-empty string")
    return value


def parse_apportionment(context: object) -> ApportionmentDecision | None:
    """The caller's apportionment decision, or ``None`` when ungoverned.

    Raises :class:`ValueError` on anything malformed. Pure — parsing the same
    context twice gives the same answer and consumes no randomness, which is
    what lets the conclusions and the impairment section read it independently
    and still be guaranteed to agree.
    """
    if not isinstance(context, dict) or CONTEXT_KEY not in context:
        return None
    block = context[CONTEXT_KEY]
    if block is None:
        return None
    if isinstance(block, bool) or not isinstance(block, dict):
        _reject(
            "must be a mapping",
            block,
            "a dict of {register, nonindustrial_pct, basis, opinion}, or omitted",
        )
    if not block:
        return None

    unknown = sorted(set(block) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError(
            f"context[{CONTEXT_KEY!r}] has unknown key(s) {unknown}; accepted keys are "
            f"{sorted(_ALLOWED_KEYS)}. A misspelled key would otherwise govern nothing "
            f"while looking as though it governed something."
        )

    pct = block.get("nonindustrial_pct")
    if pct is not None:
        if isinstance(pct, bool) or not isinstance(pct, int):
            _reject(
                "key 'nonindustrial_pct'",
                pct,
                "an int between 0 and 100 (a float would be truncated silently)",
            )
        if not 0 <= pct <= 100:
            raise ValueError(
                f"context[{CONTEXT_KEY!r}]['nonindustrial_pct'] must be between 0 and 100; "
                f"got {pct}. A percentage outside that range cannot be apportioned."
            )

    register = block.get("register")
    if register is not None and (
        not isinstance(register, str) or register not in REGISTERS
    ):
        raise ValueError(
            f"context[{CONTEXT_KEY!r}]['register'] must be one of {list(REGISTERS)}; got "
            f"{register!r}. An unrecognised register is refused rather than treated as "
            f"'apportioned', which would state a determined split the caller never asked for."
        )

    basis = _validated_text(block, "basis")
    opinion = _validated_text(block, "opinion")

    if register is None:
        if pct is not None:
            register = "apportioned" if pct > 0 else "none"
        elif opinion is not None:
            # Prose alone. Carries no determined percentage, so it must not read
            # as 'apportioned' — see ApportionmentDecision.impairment_block.
            register = "opinion"
        else:
            # Nothing to govern: only a basis, which alone says nothing about
            # whether anything is apportioned at all.
            return None

    if register in ("none", "deferred") and pct is not None and pct > 0:
        raise ValueError(
            f"context[{CONTEXT_KEY!r}] is contradictory: register {register!r} with "
            f"nonindustrial_pct={pct}. {register!r} states that no percentage is "
            f"determined, so a positive one cannot also be rendered — the report would "
            f"contradict itself in exactly the way this seam exists to prevent."
        )
    if register == "apportioned" and not pct:
        raise ValueError(
            f"context[{CONTEXT_KEY!r}] register 'apportioned' requires a positive "
            f"'nonindustrial_pct'; got {pct!r}. Apportioning nothing is the 'none' "
            f"register, and naming it explicitly keeps the rendered report unambiguous."
        )

    if register == "opinion":
        # Internal marker for prose-only governance. Normalised to a real
        # register so nothing downstream has to know about it.
        return ApportionmentDecision("none", None, basis, opinion)

    return ApportionmentDecision(register, pct, basis, opinion)


def parse_causation(context: object) -> CausationGovernance | None:
    """The caller's causation content, or ``None`` when ungoverned."""
    if not isinstance(context, dict) or CAUSATION_CONTEXT_KEY not in context:
        return None
    block = context[CAUSATION_CONTEXT_KEY]
    if block is None:
        return None
    if isinstance(block, bool) or not isinstance(block, dict):
        raise ValueError(
            f"context[{CAUSATION_CONTEXT_KEY!r}] must be a dict of "
            f"{{attribution, discussion}}, or omitted; got {type(block).__name__!r} "
            f"({block!r}). A malformed governance block is refused rather than ignored."
        )
    if not block:
        return None

    unknown = sorted(set(block) - _ALLOWED_CAUSATION_KEYS)
    if unknown:
        raise ValueError(
            f"context[{CAUSATION_CONTEXT_KEY!r}] has unknown key(s) {unknown}; accepted "
            f"keys are {sorted(_ALLOWED_CAUSATION_KEYS)}."
        )

    attribution = block.get("attribution")
    if attribution is not None and (
        not isinstance(attribution, str) or not attribution.strip()
    ):
        raise ValueError(
            f"context[{CAUSATION_CONTEXT_KEY!r}]['attribution'] must be a non-empty "
            f"string (the adverb, e.g. 'predominantly'); got {attribution!r}."
        )
    discussion = block.get("discussion")
    if discussion is not None and (
        not isinstance(discussion, str) or not discussion.strip()
    ):
        raise ValueError(
            f"context[{CAUSATION_CONTEXT_KEY!r}]['discussion'] must be a non-empty "
            f"string; got {discussion!r}."
        )
    if attribution is None and discussion is None:
        return None
    return CausationGovernance(attribution, discussion)


__all__ = [
    "CAUSATION_CONTEXT_KEY",
    "CONTEXT_KEY",
    "DEFAULT_BASIS",
    "REGISTERS",
    "SENTENCE_ADDRESSED",
    "SENTENCE_DEFERRED",
    "SENTENCE_NONE",
    "ApportionmentDecision",
    "CausationGovernance",
    "parse_apportionment",
    "parse_causation",
]
