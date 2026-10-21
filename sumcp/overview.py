"""Where the survey stands."""

from __future__ import annotations

from . import evidence

OVERVIEW_VERSION = "overview-0.3"

__all__ = ["OVERVIEW_VERSION", "TRACK", "survey"]

# The stack track in order.
TRACK = [
    ("dataset.imported", "dataset_import_segy", "import the SEG-Y"),
    ("headers.parsed", "dataset_import_segy", "read the trace headers"),
    ("geometry.coordinate_scale_resolved", "geometry_analyze",
     "apply scalco and read counit"),
    ("geometry.receiver_positions_trustworthy", "fit_array_geometry",
     "test the receiver coordinates against the arrivals"),
    ("geometry.acquisition_classified", "fit_array_geometry",
     "name the acquisition geometry from that test"),
    ("reflection.processing_feasible", "assess_reflection_feasibility",
     "decide whether a reflection is detectable at all"),
    ("geometry.cmp_assigned", "build_cmp", "assign CMP bins"),
    ("geometry.fold_valid", "build_cmp", "grade the bins on NMO leverage"),
    ("velocity.validated", "pick_velocity", "pick and validate a velocity model"),
    ("nmo.applied", "apply_nmo", "apply NMO"),
    ("stack.completed", "stack_cmp", "stack"),
]

_REACHED = "reached a stack"


def _evidence_line(entry: dict) -> str:
    """One readable line of why a capability stands where it does."""
    if entry is None:
        return "never evaluated"
    facts = entry.get("evidence", {})
    for key in ("reason", "cause"):
        if facts.get(key):
            return str(facts[key])
    notes = [n for n in (entry.get("notes") or []) if n]
    if notes:
        return notes[0]
    for key in ("verdict", "level"):
        if key in facts:
            return f"{key}={facts[key]}"
    return entry.get("status", "UNKNOWN")


def _call(tool: str, dataset_id: str) -> str:
    """The next action as something that can actually be typed."""
    if tool == "fit_array_geometry":
        return (f'fit_array_geometry(["{dataset_id}", ...every other line '
                f'that shares this array])')
    return f"{tool}({dataset_id})"


def _failures_on_track(caps: dict) -> list:
    """Every FAIL anywhere on the track, not only the one blocking now."""
    return [{"capability": name, "because": _evidence_line(caps[name])}
            for name, _, _ in TRACK
            if name in caps and caps[name]["status"] == evidence.FAIL]


def _standing(manifest: dict) -> dict:
    caps = manifest.get("capabilities", {})
    refusals = _failures_on_track(caps)
    done = []
    for name, tool, what in TRACK:
        entry = caps.get(name)
        if entry is not None and entry["status"] == evidence.PASS:
            done.append(name)
            continue
        status = entry["status"] if entry else "not evaluated"
        out = {
            "reached": done[-1] if done else None,
            "steps_passed": len(done),
            "steps_total": len(TRACK),
            "blocked_on": name,
            "blocked_status": status,
            "because": _evidence_line(entry),
            "next_action": _call(tool, manifest["dataset_id"]),
            "next_action_does": what,
            # A FAIL is a finished answer; an unevaluated capability is a question nobody asked yet.
            "refused": bool(refusals),
            "unmeasured": entry is None,
        }
        if refusals:
            out["refusals"] = refusals
            if not (entry and entry["status"] == evidence.FAIL):
                out["note"] = (
                    "Blocked on an unanswered question, but a later step on "
                    "the track was already measured and refused; see "
                    "'refusals'. Answering the block does not undo that.")
        return out
    return {"reached": _REACHED, "steps_passed": len(TRACK),
            "steps_total": len(TRACK), "blocked_on": None,
            "refused": bool(refusals),
            **({"refusals": refusals} if refusals else {})}


def _open_questions(manifest: dict) -> list:
    """Whatever the recorded evidence itself said was not settled."""
    out = []
    for name, entry in manifest.get("capabilities", {}).items():
        for note in entry.get("evidence", {}).get("unresolved", []) or []:
            out.append({"from": name, "note": note})
        facts = entry.get("evidence", {})
        for key in ("what_would_answer_it", "velocity_note"):
            if facts.get(key):
                out.append({"from": name, "note": facts[key]})
    return out


def _groups(manifests: dict) -> list:
    """Lines that were fitted together share an array; say so once."""
    seen, groups = set(), []
    for dataset_id, manifest in manifests.items():
        entry = manifest.get("capabilities", {}).get(
            "geometry.array_geometry_resolved")
        if not entry:
            continue
        members = tuple(sorted(entry.get("evidence", {}).get("lines_used", [])))
        if len(members) < 2 or members in seen:
            continue
        seen.add(members)
        facts = entry.get("evidence", {})
        groups.append({
            "lines": list(members),
            "verdict": facts.get("verdict"),
            "cause": facts.get("cause"),
            "spacing_scale": (facts.get("spacing_scale") or {}).get("value"),
            "channel_delay_ms": (facts.get("channel_delay_ms") or {}).get("value"),
            "fitted_on": facts.get("lines_fitted"),
            "note": ("These lines were fitted jointly, so what is established "
                     "for one is established for the array they share -- and "
                     "only for that."),
        })
    return groups


def survey(dataset_ids=None) -> dict:
    """Read every manifest and report where the survey stands."""
    ids = list(dataset_ids) if dataset_ids else evidence.list_datasets()
    manifests, lines, unreadable = {}, [], []
    for dataset_id in ids:
        try:
            manifests[dataset_id] = evidence.load(dataset_id)
        except Exception as exc:                     # a bad manifest is a fact
            unreadable.append({"dataset_id": dataset_id, "error": str(exc)})
    for dataset_id, manifest in manifests.items():
        caps = manifest.get("capabilities", {})
        acquisition = (caps.get("geometry.acquisition_classified", {})
                       .get("evidence", {}))
        lines.append({
            "dataset_id": dataset_id,
            "description": manifest.get("description", ""),
            "source": manifest.get("source", {}).get("path"),
            "acquisition": acquisition.get("candidate") or acquisition.get("kind"),
            "acquisition_status": acquisition.get("status"),
            "standing": _standing(manifest),
            "failed": [name for name, e in caps.items()
                       if e["status"] == evidence.FAIL],
            "open_questions": _open_questions(manifest),
            "updated": manifest.get("updated"),
        })
    lines.sort(key=lambda r: (-r["standing"]["steps_passed"], r["dataset_id"]))

    reached = [r["dataset_id"] for r in lines
               if r["standing"]["reached"] == _REACHED]
    refused = [{"dataset_id": r["dataset_id"],
                "at": item["capability"],
                "because": item["because"]}
               for r in lines
               for item in r["standing"].get("refusals", [])]
    return {
        "algorithm_version": OVERVIEW_VERSION,
        "datasets": len(lines),
        "reached_a_stack": reached,
        "refused": refused,
        "arrays": _groups(manifests),
        "lines": lines,
        "unreadable": unreadable,
        "how_to_read": (
            "'standing' is the furthest step on the stack track a line has "
            "passed and the recorded reason it stopped. A line under 'refused' "
            "was measured and found wanting -- that is an answer, not a "
            "failure; one merely 'unmeasured' is a question nobody has asked "
            "yet, and next_action is the call that asks it."),
    }
