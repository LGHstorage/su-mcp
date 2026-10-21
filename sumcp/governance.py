"""Evidence governance switch for evaluation deployments (baseline study 01, condition C0)."""

from __future__ import annotations

import os

__all__ = ["off", "MECHANICAL_STATUS", "MECHANICAL_ARTIFACT", "scrub", "GovernanceConfigError"]

ENV = "SU_MCP_GOVERNANCE"
EVAL_ENV = "SU_MCP_EVAL_DEPLOYMENT"
EVAL_TAG = "baseline01"


class GovernanceConfigError(RuntimeError):
    pass


def _mode() -> str:
    value = os.environ.get(ENV, "on").strip().lower() or "on"
    if value not in ("on", "off"):
        raise GovernanceConfigError(f"{ENV} must be 'on' or 'off', not {value!r}")
    if value == "off":
        missing = [k for k in (EVAL_ENV, "SU_MCP_RUNTIME", "SU_MCP_STATE") if not os.environ.get(k)]
        if os.environ.get(EVAL_ENV) != EVAL_TAG or missing:
            raise GovernanceConfigError(
                f"{ENV}=off is allowed only in the baseline01 evaluation deployment "
                f"({EVAL_ENV}={EVAL_TAG} with its own SU_MCP_RUNTIME and SU_MCP_STATE); "
                f"missing or wrong: {missing or [EVAL_ENV]}. Production never runs without governance.")
    return value


_MODE = _mode()


def off() -> bool:
    return _MODE == "off"


# capabilities whose PASS status is itself mechanical
MECHANICAL_STATUS = frozenset({"dataset.imported", "headers.parsed", "geometry.coordinate_scale_resolved"})
# capabilities whose mechanical part is "this product exists"
MECHANICAL_ARTIFACT = {
    "geometry.cmp_assigned": ("cmp", "cmp_sorted"),
    "velocity.model_available": ("velocity_model",),
    "nmo.applied": ("nmo",),
    "stack.completed": ("stack",),
}

# ---------------------------------------------------------------- reporting
SAFE_KEYS = frozenset({
    "ok", "error", "error_type", "run_id", "dataset_id", "tool", "input", "inputs", "output", "outputs",
    "output_bytes", "elapsed_s", "job_id", "started", "cmp_sorted", "model", "stack", "method",
    "artifact", "output_name", "path", "forgotten", "files", "root", "velocity_run_id",
})
PASS_THROUGH = frozenset({
    "su_status", "su_search", "su_help", "su_inspect", "su_run", "su_pipeline", "su_preview",
    "su_list_files", "segy_inspect", "conditioning_menu", "dataset_list",
})
C0_NOTICE = ("evaluation deployment: evidence governance is off (no refusals on evidence, every product adopted, "
             "no reliability reporting)")


MEASUREMENT_TOOLS = frozenset({"measure_apparent_velocity", "scan_coherence", "fit_channel_geometry",
                               "assess_reflection_feasibility", "geometry_analyze", "fit_array_geometry"})
# numbers that are themselves a verdict or a reliability statistic, not a raw measurement
EVIDENCE_NUMBERS = frozenset({
    "significance", "significance_level", "alpha", "detection_threshold", "threshold", "coverage_fraction",
    "correlation_ceiling", "half_stack_correlation", "measured_fraction", "reliability", "stability", "focus",
    "focus_min", "preservation", "preservation_min", "p_value", "contrast_min", "min_contrast", "energy_fraction",
    "in_band_energy_fraction", "leverage", "fraction", "score", "confidence"})


def _numeric(obj, depth=0):
    """Raw measurements only: numeric leaves (not booleans), without verdict-like numbers or any text."""
    if depth > 8:
        return None
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in EVIDENCE_NUMBERS or k.startswith("_"):
                continue
            n = _numeric(v, depth + 1)
            if n not in (None, {}, []):
                out[k] = n
        return out
    if isinstance(obj, (list, tuple)):
        out = [n for n in (_numeric(v, depth + 1) for v in obj) if n not in (None, {}, [])]
        return out
    return None


def _functions(locs):
    out = []
    for r in locs or []:
        fn = r.get("function") or []
        out.append({"cdp": r.get("cdp"),
                    "function": [{"t0_s": p.get("t0_s"), "v_m_s": p.get("v_m_s"),
                                  **({"semblance": p["semblance"]} if "semblance" in p else {})}
                                 for p in fn]})
    return out


def _extra(tool, result):
    if tool in ("pick_velocity", "refine_velocity"):
        return {"locations": _functions(result.get("locations"))}
    if tool in MEASUREMENT_TOOLS:
        return {"measurements": _numeric({k: v for k, v in result.items() if k not in SAFE_KEYS})}
    if tool == "build_cmp":
        keep = {}
        for k in ("bin_size_m", "n_bins", "bins", "fold", "cdp_range"):
            if k in result:
                keep[k] = result[k]
        return keep
    if tool == "condition_gathers":
        return {"operations": result.get("operations"), "pass": result.get("pass"),
                "adopted": True}
    if tool in ("dataset_manifest", "survey_overview"):
        arts = result.get("artifacts") or {}
        return {"artifacts": {k: {"path": v.get("path")} for k, v in arts.items() if isinstance(v, dict)}}
    if tool == "dataset_import_segy":
        return {k: result[k] for k in ("traces", "ns", "dt_s", "output") if k in result}
    return {}


def scrub(tool: str, result):
    """C0 reporting: products and ordinary execution status only (allowlist)."""
    if not off() or not isinstance(result, dict):
        return result
    if tool in PASS_THROUGH:
        return result
    out = {k: v for k, v in result.items() if k in SAFE_KEYS}
    out.update({k: v for k, v in _extra(tool, result).items() if v is not None})
    out["governance"] = C0_NOTICE
    return out
