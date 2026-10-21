#!/usr/bin/env python3
"""Start server.py as a real MCP stdio server and exercise it as a client."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


def _content_text(result) -> str:
    parts = []
    for item in result.content:
        parts.append(getattr(item, "text", "") or f"<{type(item).__name__}>")
    return "\n".join(parts)


def _payload(result):
    data = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if data:
        return data.get("result", data)
    try:
        return json.loads(_content_text(result))
    except json.JSONDecodeError:
        return _content_text(result)


def _clean_fixture_dataset(dataset_id: str) -> None:  # noqa: D401
    """The round-trip registers a dataset; start from a known state."""
    (ROOT / "state" / "datasets" / f"{dataset_id}.json").unlink(missing_ok=True)
    shutil.rmtree(ROOT / "work" / dataset_id, ignore_errors=True)


async def main() -> int:
    _clean_fixture_dataset("rt01")
    env = os.environ.copy()
    env.setdefault("SU_MCP_ROOT", str(ROOT))
    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "server.py")], env=env,
    )
    failures = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            info = getattr(init, "server_info", None) or init.serverInfo
            print(f"initialize   : {info.name} v{info.version}")

            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            print(f"tools/list   : {len(names)} tools -> {', '.join(names)}")
            for tool in listed.tools:
                required = (getattr(tool, "input_schema", None) or tool.inputSchema).get("required", [])
                print(f"   - {tool.name:<14} required={required}")
                if not tool.description:
                    failures.append(f"{tool.name} has no description")

            checks = [
                ("su_status", {}, lambda r: r["ok"] and r["programs_installed"] > 100),
                ("su_list_files", {"directory": "raw"},
                 lambda r: any(f["path"].endswith("line01.su") for f in r["files"]["raw"])),
                ("su_inspect", {"input_file": "raw/line01.su", "run_surange": True},
                 lambda r: r["ok"] and r["structured"]["ntr"] == 1920 and r["structured"]["ns"] == 751),
                ("su_help", {"program": "sufilter"},
                 lambda r: r["ok"] and "SUFILTER" in r["doc"]),
                ("su_search", {"keyword": "semblance", "mode": "synopsis"},
                 lambda r: r["ok"] and "VELAN" in r["result"].upper()),
                ("su_run", {"command": "sustack", "input_file": "raw/line01.su",
                            "output_file": "work/nope.su"},
                 lambda r: r["ok"] is False and r["error_type"] == "CommandNotAllowed"),
                ("su_run", {"command": "sufilter", "input_file": "raw/line01.su",
                            "output_file": "/etc/evil.su"},
                 lambda r: r["ok"] is False and r["error_type"] == "PathPolicyError"),
                ("su_pipeline", {"input_file": "raw/line01.su",
                                 "output_file": "work/mcp_prep.su", "overwrite": True,
                                 "steps": [
                                     {"command": "suwind", "params": {"tmin": 0.0, "tmax": 2.4}},
                                     {"command": "sufilter",
                                      "params": {"f": [8, 14, 90, 110], "amps": [0, 1, 1, 0]}},
                                 ]},
                 lambda r: r["ok"] and r["output_bytes"] > 0),
                ("su_preview", {"input_file": "work/mcp_prep.su",
                                "output_png": "qc/mcp_shot10.png", "fldr": 10, "gain": "agc"},
                 lambda r: r["ok"] and (ROOT / r["png"]).exists()),
                ("su_log", {"limit": 5}, lambda r: r["ok"] and len(r["entries"]) >= 1),

                # ---- v0.2: datasets, import verification, evidence ----------
                ("segy_inspect", {"input_file": "raw/line01.sgy"},
                 lambda r: r["ok"] and r["byte_order"] == "big"
                 and r["sample_format_code"] == 1 and r["traces_estimated"] == 1920),
                ("segy_inspect", {"input_file": "raw/line01_le.sgy"},
                 lambda r: r["ok"] and r["byte_order"] == "little"),
                ("segy_inspect", {"input_file": "raw/line01.su"},
                 lambda r: r["ok"] is False),
                ("dataset_import_segy",
                 {"dataset_id": "rt01", "segy_file": "raw/line01.sgy",
                  "description": "round-trip fixture"},
                 lambda r: r["ok"] and set(r["capabilities_pass"]) >= {
                     "dataset.imported", "headers.sampling_consistent",
                     "headers.trace_count_consistent"}),
                ("dataset_import_segy",
                 {"dataset_id": "rt01", "segy_file": "raw/line01.sgy"},
                 lambda r: r["ok"] is False and r["error_type"] == "DatasetError"),
                ("dataset_manifest", {"dataset_id": "rt01", "section": "capabilities"},
                 lambda r: r["ok"]
                 and r["capabilities"]["headers.sampling_consistent"]["evidence"]["ns"]["segy"] == 751
                 and r["capabilities"]["headers.parsed"]["evidence"]["outlook"]["cdp_state"] == "zero"),
                ("dataset_manifest", {"dataset_id": "rt01", "section": "artifacts"},
                 lambda r: r["ok"] and r["artifacts"]["su"]["parents"] == ["raw/line01.sgy"]),
                ("dataset_list", {},
                 lambda r: r["ok"] and any(d["dataset_id"] == "rt01" for d in r["datasets"])),
                ("dataset_register_su",
                 {"dataset_id": "rt01", "su_file": "raw/line01.su"},
                 lambda r: r["ok"] is False),

                # ---- v0.3: geometry measured, not assumed --------------------
                ("measure_apparent_velocity",
                 {"input_file": "raw/line01.su", "fldr": 20,
                  "tmin": 0.0, "tmax": 3.0, "channel_spacing_m": 50.0},
                 lambda r: r["ok"] and "slope_ms_per_channel" in r
                 and len(r["per_band"]) >= 3),
                ("geometry_analyze", {"dataset_id": "rt01"},
                 lambda r: r["ok"]
                 and r["classification"]["kind"] == "moving_receivers"
                 and r["cdp"]["level"] == "ABSENT"
                 and r["capabilities"]["geometry.coordinate_scale_resolved"] == "PASS"
                 # never evaluated, so it is absent from the manifest entirely
                 and "geometry.cmp_assigned" not in r["capabilities"]),
                ("geometry_analyze", {"dataset_id": "no_such_dataset"},
                 lambda r: r["ok"] is False),
                # ---- v0.5: the stack track, and the gate in front of it ----
                ("build_cmp", {"dataset_id": "walkaway",
                               "receiver_spacing_m": 3.125},
                 lambda r: r["ok"] is False
                 and r["error_type"] == "PrerequisiteError"
                 and "reflection.processing_feasible" in r["error"]),
                ("build_cmp", {"dataset_id": "viking",
                               "receiver_spacing_m": 25.0, "overwrite": True},
                 lambda r: r["ok"]
                 and r["capabilities"]["geometry.cmp_assigned"] == "PASS"
                 and r["capabilities"]["geometry.fold_valid"] == "PASS"
                 and r["nmo_leverage"]["verdict"] == "USABLE"
                 # the survey's own numbering survives once it is verified
                 and r["header_cdp_comparison"]["agrees"] is True),
                ("sort_cmp", {"dataset_id": "viking", "overwrite": True},
                 lambda r: r["ok"] and r["output_bytes"] > 0),
                ("pick_velocity", {"dataset_id": "viking", "n_locations": 3},
                 lambda r: r["ok"]
                 and r["capabilities"]["velocity.validated"] == "PASS"
                 and all(loc["valid"] for loc in r["locations"])
                 # the deep part of the function is held, not invented
                 and all(loc["supported_to_s"] for loc in r["locations"])),
                ("apply_nmo", {"dataset_id": "viking", "overwrite": True},
                 lambda r: r["ok"] and r["output_bytes"] > 0),
                ("su_run", {"command": "sunmo", "input_file": "raw/line01.su",
                            "output_file": "work/bypass.su"},
                 # the gate is only a gate if it cannot be walked around
                 lambda r: r["ok"] is False
                 and r["error_type"] == "CommandNotAllowed"),
                ("stack_cmp", {"dataset_id": "viking", "overwrite": True},
                 lambda r: r["ok"] and r["traces"] == 200),

                # survey_overview reads manifests only, so it has to be right about the fixtures already built
                # above
                ("survey_overview", {},
                 lambda r: r["ok"] and "viking" in r["reached_a_stack"]
                 and all("standing" in line for line in r["lines"])),
                ("survey_overview", {"dataset_ids": ["viking"]},
                 lambda r: r["ok"] and r["datasets"] == 1),

                ("export_product", {"dataset_id": "viking",
                                    "artifact": "stack", "overwrite": True},
                 lambda r: r["ok"] and r["output"].startswith("results/")
                 and r["bytes"] > 0),
                ("export_product", {"dataset_id": "viking", "artifact": "nope"},
                 lambda r: r["ok"] is False and "has no artifact" in r["error"]),

                ("dataset_forget", {"dataset_id": "viking"},
                 lambda r: r["ok"] is False
                 and r["error_type"] == "ConfirmationRequired"
                 and r["capabilities_that_would_be_lost"]),

                ("job_status", {"job_id": "nope"},
                 lambda r: r["ok"] is False and r["error_type"] == "JobError"),
                ("job_list", {}, lambda r: r["ok"] and isinstance(r["jobs"], list)),

                # ---- v0.3-C: is a reflection reachable at all? ---------------
                ("assess_reflection_feasibility",
                 {"input_file": "work/walkaway/walkaway.su", "channel": 1,
                  "run_sensitivity": False},
                 lambda r: r["ok"]
                 and set(r["branches"]) == {"predicted_mute", "template_subtraction",
                                            "slant_domain"}
                 # three verdicts, not two: "nothing there" and "could not have seen it" must not share a word
                 and r["REFLECTION_PROCESSING_FEASIBLE"] in (
                     "PASS", "FAIL", "INCONCLUSIVE")
                 and r["direct_wave"]["value"] in ("ROBUST", "FRAGILE", "ABSENT")
                 and len(r["direct_wave"]["trials"]) == 6
                 and r["branches"]["slant_domain"]["evidence_role"]
                     in ("suppression only", "suppression and slowness")),
                ("assess_reflection_feasibility",
                 {"input_file": "work/walkaway/walkaway.su", "channel": 1,
                  "fldr": 2, "run_sensitivity": False},
                 lambda r: r["ok"] is False and "exactly one" in r["error"]),
            ]

            # ---- v0.4: the worker runs out of process, so a long analysis becomes a job instead of a deadline.
            started = _payload(await session.call_tool(
                "assess_reflection_feasibility",
                {"input_file": "work/walkaway/walkaway.su", "channel": 1,
                 "run_as_job": True}))
            job_id = started.get("job_id", "")
            print(f"{'PASS' if job_id else 'FAIL'}  start_job     {json.dumps(started)[:110]}")
            if not job_id:
                failures.append("run_as_job returned no job_id")
            else:
                state = {}
                for _ in range(120):
                    state = _payload(await session.call_tool("job_status", {"job_id": job_id}))
                    if state.get("status") != "running":
                        break
                    await asyncio.sleep(1)
                good = state.get("status") == "finished"
                print(f"{'PASS' if good else 'FAIL'}  job_status    {json.dumps(state)[:110]}")
                if not good:
                    failures.append(f"job {job_id} ended as {state.get('status')}")
                else:
                    got = _payload(await session.call_tool("job_result", {"job_id": job_id}))
                    inner = got.get("result", {})
                    ok = inner.get("REFLECTION_PROCESSING_FEASIBLE") in ("PASS", "FAIL",
                                                                        "INCONCLUSIVE")
                    print(f"{'PASS' if ok else 'FAIL'}  job_result    {json.dumps(inner)[:110]}")
                    if not ok:
                        failures.append("job_result did not carry the tool payload")

            # ---- v0.4: does editing the analysis code take effect without restarting the server?
            module = ROOT / "sumcp" / "reflection.py"
            original = module.read_text(encoding="utf-8")
            marker = 'REFLECTION_VERSION = "'
            before = _payload(await session.call_tool("su_status", {}))
            try:
                edited = original.replace(
                    marker, marker + "hot-reload-probe-", 1)
                module.write_text(edited, encoding="utf-8")
                after = _payload(await session.call_tool("su_status", {}))
            finally:
                module.write_text(original, encoding="utf-8")
            restored = _payload(await session.call_tool("su_status", {}))
            live = (after["algorithm_versions"]["reflection"].startswith(
                        "hot-reload-probe-")
                    and restored["algorithm_versions"]["reflection"]
                        == before["algorithm_versions"]["reflection"])
            print(f"{'PASS' if live else 'FAIL'}  live reload   "
                  f"{before['algorithm_versions']['reflection']} -> "
                  f"{after['algorithm_versions']['reflection']} -> "
                  f"{restored['algorithm_versions']['reflection']}")
            if not live:
                failures.append("editing an analysis module needed a restart")

            for name, args, predicate in checks:
                result = await session.call_tool(name, args)
                payload = _payload(result)
                try:
                    good = bool(predicate(payload))
                except Exception as exc:                       # noqa: BLE001
                    good = False
                    payload = f"{payload} ({exc})"
                print(f"{'PASS' if good else 'FAIL'}  {name:<13} {json.dumps(payload, default=str)[:110]}")
                if not good:
                    failures.append(f"{name} {args}")

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for f in failures:
            print("  -", f)
        return 1
    print("all MCP round-trip checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
