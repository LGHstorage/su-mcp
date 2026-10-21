"""Figures for the Marmousi2 oracle diagnostic (evaluation only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, VP_NPY, DT_S, truth_vrms, picked_functions  # noqa: E402
from run_oracle import agc, load_reference, OUT  # noqa: E402

QC = ROOT / "qc/marm2_oracle_diagnostic"
CDP_RANGE = (640, 1140)
T_RANGE = (0.6, 2.44)
INK, MUTED = "#1f1f1f", "#6b6b6b"
ASIS, FIXED, V2, TRUTH = "#b8573a", "#2f6db3", "#2e8b57", "#1f1f1f"


def section_panel(ax, data, cdp, title, clip_q=0.99):
    sel = (cdp >= CDP_RANGE[0]) & (cdp <= CDP_RANGE[1])
    d = agc(np.asarray(data, float)[sel])
    n = d.shape[1]
    t = np.arange(n) * DT_S
    tm = (t >= T_RANGE[0]) & (t <= T_RANGE[1])
    clip = float(np.quantile(np.abs(d[:, tm]), clip_q))
    ax.imshow(d[:, tm].T, cmap="gray", vmin=-clip, vmax=clip, aspect="auto",
              extent=(cdp[sel].min() / 100, cdp[sel].max() / 100, t[tm][-1], t[tm][0]),
              interpolation="bilinear")
    ax.set_title(title, fontsize=10.5, color=INK, loc="left")
    ax.tick_params(labelsize=9, colors=MUTED)
    for s in ax.spines.values():
        s.set_color("#c8c8c8")


def sections(metrics):
    st = np.load(OUT / "oracle_stacks.npz")
    ref = load_reference()["raw"]
    er_cdp = np.arange(ref.shape[0]) + 400
    corr = lambda k: metrics[k]["reference"]["0.7-2.4s"]["best_lag_pm20ms"]
    panels = [
        (ref, er_cdp, "(a) Truth zero-offset section (exploding reflector)"),
        (st["t0fix_near_offset_200m"], st["t0fix_near_cdp"],
         f"(b) Raw 200 m near-offset traces, no processing   r = {corr('t0fix_near_offset_200m'):.2f}"),
        (st["asis_picked_s1.5"], st["cdp"],
         f"(c) SU-MCP v0.14 stack, benchmark as delivered   r = {corr('asis_picked_s1.5'):.2f}"),
        (st["t0fix_picked_s1.5"], st["cdp"],
         f"(d) SU-MCP v0.14 stack, time zero corrected   r = {corr('t0fix_picked_s1.5'):.2f}"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9.2), sharex=True, sharey=True,
                             constrained_layout=True)
    for ax, (d, c, title) in zip(axes.ravel(), panels):
        section_panel(ax, d, c, title)
    for ax in axes[1]:
        ax.set_xlabel("CMP midpoint (km)", fontsize=10, color=INK)
    for ax in axes[:, 0]:
        ax.set_ylabel("Zero-offset two-way time (s)", fontsize=10, color=INK)
    fig.suptitle("Marmousi2 benchmark, original 126 x 96 acquisition, 0.6-2.44 s. "
                 "All panels 0.2 s RMS gain; (c) shifted -150 ms onto the corrected time axis.\n"
                 "r = median per-trace correlation with (a), 0.7-2.4 s, best lag within 20 ms",
                 fontsize=10.5, color=INK)
    QC.mkdir(parents=True, exist_ok=True)
    fig.savefig(QC / "sections_truth_vs_stack.png", dpi=170)
    plt.close(fig)


def velocities():
    vp = np.load(VP_NPY)
    runs = {"as delivered (150 ms late)": (ROOT / "results/marm2_matched_pair/original_window_processing.json", ASIS, "o"),
            "time zero corrected": (OUT / "t0fix_processing.json", FIXED, "s"),
            "v2 benchmark": (ROOT / "results/marm2_v2/v2_2p6_processing.json", V2, "D")}
    picks = {k: picked_functions(p) for k, (p, _, _) in runs.items()}
    cdps = picks["time zero corrected"][0]
    t = np.linspace(0.05, 2.45, 200)
    fig, axes = plt.subplots(1, len(cdps), figsize=(15, 5.6), sharey=True, constrained_layout=True)
    for ax, c in zip(axes, cdps):
        x = c * 10.0
        xs = np.arange(max(4000, x - 1050), min(12000, x + 1050) + 1, 100)
        band = np.array([truth_vrms(xx, t, vp) for xx in xs])
        ax.fill_betweenx(t, band.min(0), band.max(0), color="#d9d9d9", lw=0,
                         label="truth Vrms, columns within half-spread")
        ax.plot(truth_vrms(x, t, vp), t, color=TRUTH, lw=1.6, label="truth Vrms, this column")
        for name, (_, color, marker) in runs.items():
            pc, tn, vn = picks[name]
            i = pc.index(c)
            tt = np.array(tn[i]); vv = np.array(vn[i])
            keep = tt <= 2.45
            ax.plot(vv[keep], tt[keep], color=color, lw=1.4, marker=marker, ms=6,
                    mec="white", mew=1.0, label=f"SU-MCP pick, {name}")
        ax.axvline(1400, color=MUTED, lw=0.9, ls=":")
        ax.axvline(1500, color=MUTED, lw=0.9, ls="--")
        ax.set_title(f"CMP {c} ({x/1000:.2f} km)", fontsize=10.5, color=INK, loc="left")
        ax.set_xlim(1300, 3300)
        ax.set_xlabel("Velocity (m/s)", fontsize=10, color=INK)
        ax.tick_params(labelsize=9, colors=MUTED)
        ax.grid(True, color="#ececec", lw=0.6)
        for s in ax.spines.values():
            s.set_color("#c8c8c8")
    axes[0].set_ylim(2.45, 0.05)
    axes[0].set_ylabel("Zero-offset two-way time (s)", fontsize=10, color=INK)
    axes[0].text(1405, 2.4, "scan floor", rotation=90, fontsize=8, color=MUTED, va="bottom")
    axes[0].text(1505, 2.4, "water", rotation=90, fontsize=8, color=MUTED, va="bottom")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, fontsize=9, frameon=False,
               bbox_to_anchor=(0.5, -0.13))
    fig.suptitle("Stacking velocity against the truth Vrms proxy. Picks from the 150 ms late v1 record sit on the "
                 "1400 m/s scan floor down to 0.88 s; after the time-zero repair they leave it.",
                 fontsize=10.5, color=INK)
    fig.savefig(QC / "velocity_truth_vs_picks.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def sections_v1_v2(metrics):
    st = np.load(OUT / "oracle_stacks.npz")
    ref = load_reference()["raw"]
    er_cdp = np.arange(ref.shape[0]) + 400
    corr = lambda k: metrics[k]["reference"]["0.7-2.4s"]["best_lag_pm20ms"]
    panels = [
        (ref, er_cdp, "(a) Truth zero-offset section (exploding reflector)"),
        (st["asis_picked_s1.5"], st["cdp"],
         f"(b) SU-MCP v0.14 stack, v1 benchmark as delivered   r = {corr('asis_picked_s1.5'):.2f}"),
        (st["v2_near_offset_200m"], st["v2_near_cdp"],
         f"(c) v2 benchmark, raw 200 m near-offset traces   r = {corr('v2_near_offset_200m'):.2f}"),
        (st["v2_picked_s1.5"], st["cdp"],
         f"(d) SU-MCP v0.14 stack, v2 benchmark   r = {corr('v2_picked_s1.5'):.2f}"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9.2), sharex=True, sharey=True,
                             constrained_layout=True)
    for ax, (d, c, title) in zip(axes.ravel(), panels):
        section_panel(ax, d, c, title)
    for ax in axes[1]:
        ax.set_xlabel("CMP midpoint (km)", fontsize=10, color=INK)
    for ax in axes[:, 0]:
        ax.set_ylabel("Zero-offset two-way time (s)", fontsize=10, color=INK)
    fig.suptitle("Marmousi2, 126 x 96 acquisition, 0.6-2.44 s, same model and 10 Hz source. "
                 "v2 repairs only the time zero and the absorbing boundary.\n"
                 "All panels 0.2 s RMS gain; (b) shifted -150 ms. r = median per-trace correlation "
                 "with (a), 0.7-2.4 s, best lag within 20 ms",
                 fontsize=10.5, color=INK)
    fig.savefig(QC / "sections_v1_vs_v2.png", dpi=170)
    plt.close(fig)


def main():
    metrics = json.loads((OUT / "oracle_metrics.json").read_text())
    sections(metrics)
    sections_v1_v2(metrics)
    velocities()
    print("figures written")


if __name__ == "__main__":
    main()
