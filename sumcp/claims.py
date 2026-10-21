"""Evidence classes: what a number is, not just what it equals."""

from __future__ import annotations

OBSERVED = "OBSERVED"
DERIVED = "DERIVED"
ASSUMED = "ASSUMED"
HYPOTHESIZED = "HYPOTHESIZED"

CLASSES = (OBSERVED, DERIVED, ASSUMED, HYPOTHESIZED)

# weakest wins when a derivation combines inputs
_RANK = {OBSERVED: 0, DERIVED: 1, ASSUMED: 2, HYPOTHESIZED: 3}

__all__ = ["OBSERVED", "DERIVED", "ASSUMED", "HYPOTHESIZED", "CLASSES",
           "ORIGINS", "ORIGIN_HEADERS", "ORIGIN_MEASUREMENT",
           "ORIGIN_ACQUISITION_LOG", "ORIGIN_NAVIGATION", "ORIGIN_CALLER",
           "ORIGIN_DEFAULT", "ORIGIN_UNSTATED",
           "claim", "observed", "derived", "assumed", "hypothesized",
           "weakest", "value_of", "is_established"]


# WHERE a value came from, which is a different question from how strongly it is established.
ORIGIN_HEADERS = "TRACE_HEADERS"          # read out of the file itself
ORIGIN_MEASUREMENT = "MEASURED_HERE"      # computed from the samples
ORIGIN_ACQUISITION_LOG = "ACQUISITION_LOG"   # observer log / survey report
ORIGIN_NAVIGATION = "NAVIGATION"          # a positioning file
ORIGIN_CALLER = "CALLER"                  # a number the caller supplied
ORIGIN_DEFAULT = "DEFAULT"                # a constant in this code
ORIGIN_UNSTATED = "UNSTATED"              # nobody said

ORIGINS = (ORIGIN_HEADERS, ORIGIN_MEASUREMENT, ORIGIN_ACQUISITION_LOG,
           ORIGIN_NAVIGATION, ORIGIN_CALLER, ORIGIN_DEFAULT, ORIGIN_UNSTATED)


def claim(value, evidence_class: str, source: str, origin: str = ORIGIN_UNSTATED,
          **extra) -> dict:
    if evidence_class not in CLASSES:
        raise ValueError(f"evidence_class must be one of {CLASSES}")
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}")
    out = {"value": value, "class": evidence_class, "source": source,
           "origin": origin}
    out.update(extra)
    return out


def observed(value, source: str, origin: str = ORIGIN_UNSTATED, **extra) -> dict:
    return claim(value, OBSERVED, source, origin, **extra)


def assumed(value, source: str, origin: str = ORIGIN_UNSTATED, **extra) -> dict:
    return claim(value, ASSUMED, source, origin, **extra)


def hypothesized(value, source: str, origin: str = ORIGIN_UNSTATED,
                 **extra) -> dict:
    return claim(value, HYPOTHESIZED, source, origin, **extra)


def derived(value, source: str, inputs=(), origin: str = ORIGIN_UNSTATED,
            **extra) -> dict:
    """A derived value is never stronger than the weakest thing it came from."""
    cls = weakest([DERIVED] + [c.get("class", HYPOTHESIZED) for c in inputs])
    if origin == ORIGIN_UNSTATED and inputs:
        origins = {c.get("origin", ORIGIN_UNSTATED) for c in inputs}
        origins.discard(ORIGIN_UNSTATED)
        if len(origins) == 1:
            origin = origins.pop()
    out = claim(value, cls, source, origin, **extra)
    if inputs:
        out["from"] = [c.get("source", "?") for c in inputs]
    return out


def weakest(classes) -> str:
    classes = list(classes) or [DERIVED]
    return max(classes, key=lambda c: _RANK.get(c, _RANK[HYPOTHESIZED]))


def value_of(c):
    return c["value"] if isinstance(c, dict) and "value" in c else c


def is_established(c) -> bool:
    """Only OBSERVED and DERIVED may support a capability PASS."""
    return isinstance(c, dict) and c.get("class") in (OBSERVED, DERIVED)
