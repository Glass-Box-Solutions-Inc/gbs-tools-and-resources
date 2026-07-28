"""Real-entity names, and the substrate pools they come from.

Two related questions live here, and keeping them in one module is deliberate:

* *Which names must never appear in generated output?* — the curated denylist,
  shipped as package data because both the engine (which warns at runtime) and
  the anti-probes (which sweep rendered documents) have to agree on one list.
  Two copies of a safety list is one copy plus a liability.
* *Which substrate pools name real organizations?* — answered **dynamically**,
  by reading ``data/wc_constants.py`` at call time rather than by transcribing
  it. A transcribed list goes stale the first time someone adds a pool
  upstream, and the failure mode is silent: the sweep keeps passing while a new
  real name flows straight through.

The substrate's organization pools are the actual leak surface. ``Safeway
Inc.``, ``Kaiser Permanente``, ``City of Los Angeles`` and ``UPS Supply Chain
Solutions`` are all real bodies, and a fabricated WCAB filing naming one of
them is a real-world collision whatever the folder says about being synthetic.
:mod:`wc_caseload_engine.case_context` substitutes coined names on every one of
these paths; this module is what tells it — and the tests — where they are.

Deliberately *excluded* from the organization pools: ``WCAB_VENUES``,
``CA_CITIES`` and ``JUDGE_NAMES``. The first two are geography, not entities —
a California compensation case is filed at a real district office, and naming
Van Nuys is not naming a party. ``JUDGE_NAMES`` is documented in the substrate
as invented, and the names are persons rather than organizations; they are
covered by the denylist sweep like any other text.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

DENYLIST_PATH = Path(__file__).parent / "data" / "name_denylist.txt"
"""Package data — the one denylist the engine and the tests both read."""

ORGANIZATION_POOLS: Mapping[str, int | None] = {
    "INSURANCE_CARRIERS": None,
    "DEFENSE_FIRMS": None,
    "ALL_EMPLOYERS": 1,
    "MEDICAL_FACILITIES": None,
}
"""``data.wc_constants`` pools that hold names of real-world organizations.

Maps the attribute to the tuple index carrying the organization name, or
``None`` when each entry *is* the name. ``ALL_EMPLOYERS`` holds
``(industry, company, position)``, and only the company is an organization —
taking the whole tuple would put ``Warehouse Associate`` and ``Welder`` into a
list of names that must never appear in output, which is how a name probe
starts failing on ordinary prose and gets muted.

Audited exhaustively against the substrate module. Every other public name in
that file is a code, a rate, a body part, a specialty, a venue or a city — none
of which can identify an organization. Adding a pool upstream and not adding it
here is the one way this can go stale, which is why
:func:`substrate_organization_pools` fails loudly on an attribute it cannot
find rather than skipping it.
"""

ORGANIZATION_POOL_ATTRIBUTES: tuple[str, ...] = tuple(ORGANIZATION_POOLS)
"""The pool names, in declaration order."""


class OrganizationPoolError(RuntimeError):
    """Raised when a declared substrate organization pool cannot be read."""


def _names_in(pool: object, index: int | None) -> list[str]:
    """The organization names in one pool.

    Raises:
        OrganizationPoolError: when an entry does not have the shape the index
            declares. A pool that changed shape upstream must fail here rather
            than contribute nothing and let the sweep pass on an empty list.
    """
    if not isinstance(pool, Iterable) or isinstance(pool, str | Mapping):
        raise OrganizationPoolError(f"substrate pool is not a sequence: {type(pool).__name__}")

    names: list[str] = []
    for entry in pool:
        if index is None:
            if not isinstance(entry, str):
                raise OrganizationPoolError(f"expected a name, got {entry!r}")
            names.append(entry)
            continue
        if not isinstance(entry, Sequence) or isinstance(entry, str) or len(entry) <= index:
            raise OrganizationPoolError(f"expected a tuple with index {index}, got {entry!r}")
        value = entry[index]
        if not isinstance(value, str):
            raise OrganizationPoolError(f"expected a name at index {index}, got {value!r}")
        names.append(value)
    return names


@lru_cache(maxsize=1)
def substrate_organization_pools() -> Mapping[str, tuple[str, ...]]:
    """Every real-entity organization pool in the substrate, read live.

    Returns:
        ``{attribute name: names}`` for each entry in
        :data:`ORGANIZATION_POOL_ATTRIBUTES`.

    Raises:
        OrganizationPoolError: when a declared pool is missing upstream — a
            renamed constant must break the sweep, not shrink it.
    """
    from wc_caseload_engine.substrate import import_substrate

    constants = import_substrate("data.wc_constants")
    pools: dict[str, tuple[str, ...]] = {}
    for attribute, index in ORGANIZATION_POOLS.items():
        if not hasattr(constants, attribute):
            raise OrganizationPoolError(
                f"substrate data/wc_constants.py has no {attribute!r} — the organization "
                "sweep is declared against a constant that no longer exists. Update "
                "ORGANIZATION_POOLS rather than dropping the pool."
            )
        pools[attribute] = tuple(_names_in(getattr(constants, attribute), index))
    return pools


def substrate_organization_names() -> frozenset[str]:
    """The flat set of organization names the substrate can draw."""
    return frozenset(
        name for names in substrate_organization_pools().values() for name in names
    )


@lru_cache(maxsize=1)
def _denylist() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Parse the denylist file into ``(denied, allowed)``, both lowercased."""
    denied: list[str] = []
    allowed: list[str] = []
    for raw in DENYLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ALLOW "):
            allowed.append(line.removeprefix("ALLOW ").strip().lower())
        else:
            denied.append(line.lower())
    return tuple(denied), tuple(allowed)


def denied_names() -> tuple[str, ...]:
    """Names that must not appear in generated output (lowercased substrings)."""
    return _denylist()[0]


def allowed_names() -> tuple[str, ...]:
    """Known, accepted exceptions — checked, but never a failure."""
    return _denylist()[1]


def denylist_hits(text: str) -> list[str]:
    """Denylist names present in *text*, case-insensitively."""
    lowered = text.lower()
    return [name for name in denied_names() if name in lowered]


def warn_if_denylisted(value: str, *, field: str, case_id: str) -> list[str]:
    """Warn (loudly, once per hit) when a seed-declared name matches the denylist.

    Seed-supplied identities are the seeder's deliberate input and are *kept* —
    overriding them would make the seed stop being the contract, and a seed
    author naming a party is the one channel where a real name might be
    intentional. What the engine owes them is a warning rather than silence:
    ``castProvenance`` already records the field as ``seed`` rather than
    ``engine``, so a reviewer can see who chose the name, and this makes the
    collision visible at generation time instead of at publication time.

    Returns:
        The denylist names *value* matched (empty when clean).
    """
    if not value:
        return []
    hits = denylist_hits(value)
    if hits:
        log.warning(
            "cast.seed_name_on_denylist",
            case_id=case_id,
            field=field,
            value=value,
            matched=hits,
        )
    return hits


__all__ = [
    "DENYLIST_PATH",
    "ORGANIZATION_POOLS",
    "ORGANIZATION_POOL_ATTRIBUTES",
    "OrganizationPoolError",
    "allowed_names",
    "denied_names",
    "denylist_hits",
    "substrate_organization_names",
    "substrate_organization_pools",
    "warn_if_denylisted",
]
