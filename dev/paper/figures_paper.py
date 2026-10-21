"""Figures of the manuscript, from the input data and released products (display only; English text only)."""
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dev/marm2_oracle"))
from common import read_segy, truth_vrms  # noqa: E402
from run_oracle import load_reference  # noqa: E402

OUT = ROOT / "figures"
DPI = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 170
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9, "axes.linewidth": 0.6,
                     "savefig.dpi": DPI})
R = ROOT / "results"
CLEAN = ROOT / "test_dataset/Marm2_v2/marm2_known_truth_v2_2p6s.sgy"
DT = 0.002
T0 = 0.5                                    # display start of Marmousi sections (water layer above)
W = 7.4                                     # full page width, inches
RED, BLUE = "#D55E00", "#0072B2"


def read_su(path):
    raw = np.fromfile(path, dtype="u1")
    for order in (">", "<"):
        ns = int(np.frombuffer(raw[114:116].tobytes(), dtype=order + "u2")[0])
        dt = int(np.frombuffer(raw[116:118].tobytes(), dtype=order + "u2")[0]) * 1e-6
        stride = 240 + 4 * ns
        if 0 < ns < 100000 and raw.size % stride == 0:
            tr = raw.reshape(-1, stride)
            cdp = tr[:, 20:24].copy().view(order + "i4").ravel()
            data = tr[:, 240:].copy().view(order + "f4").reshape(-1, ns).astype(float)
            return cdp, np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0), dt
    raise ValueError(path)


def agc(x, dt, win_s=0.2):
    n = max(3, int(round(win_s / dt)) | 1)
    k = np.ones(n) / n
    env = np.sqrt(np.apply_along_axis(lambda r: np.convolve(r * r, k, "same"), 1, x) + 1e-30)
    return x / env


def show(ax, data, x, dt, title, xlabel="CDP", win=0.2, tmax=None, tmin=0.0, clip=98, ylabel=True, gain=True,
         t_first=0.0):
    a = agc(data, dt, win) if gain else data
    c = np.percentile(np.abs(a), clip) or 1.0
    ax.imshow(a.T, cmap="gray_r", vmin=-c, vmax=c, aspect="auto",
              extent=[x[0], x[-1], t_first + data.shape[1] * dt, t_first], interpolation="bilinear")
    ax.set_ylim(tmax if tmax is not None else t_first + data.shape[1] * dt, tmin)
    ax.set_title(title, loc="left")
    ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel("Two-way time (s)")
    else:
        ax.tick_params(labelleft=False)


def line(path):
    d = read_segy(path)
    d["fldr"] = np.frombuffer(d["raw_headers"][:, 8:12].tobytes(), dtype=">i4").astype(int)
    d["data"] = d["data"].astype(float)
    return d


def shot(d, fldr=63):
    k = np.flatnonzero(d["fldr"] == fldr)
    o = np.abs(d["offset"][k])
    i = np.argsort(o)
    return o[i], d["data"][k][i]


def cmp_gather(d, cdp, half=0):
    k = np.flatnonzero(np.abs(d["cdp"] - cdp) <= half)
    o = np.abs(d["offset"][k])
    i = np.argsort(o)
    return o[i], d["data"][k][i], k[i]


MODEL = json.loads((R / "v015-v2_velocity_model.json").read_text())["locations"]


def v_at(cdp, t):
    """Stacking velocity of the clean-line model at a CDP (linear between the analysed locations)."""
    cs = np.array([m["cdp"] for m in MODEL], float)
    vs = np.array([np.interp(t, [p["t0_s"] for p in m["function"]], [p["v_m_s"] for p in m["function"]])
                   for m in MODEL])
    return np.array([np.interp(cdp, cs, vs[:, j]) for j in range(t.size)])


def nmo(g, off, v, smute=1.5):
    ns = g.shape[1]
    t0 = np.arange(ns) * DT
    out = np.zeros_like(g)
    for i, x in enumerate(off):
        tx = np.sqrt(t0 ** 2 + (x / v) ** 2)
        tr = np.interp(tx, t0, g[i], right=0.0)
        tr[tx > smute * np.maximum(t0, 1e-6)] = 0.0
        out[i] = tr
    return out


def semblance(g, off, vels, win=21):
    ns = g.shape[1]
    t0 = np.arange(ns) * DT
    k = np.ones(win)
    S = np.zeros((vels.size, ns))
    for j, v in enumerate(vels):
        c = np.zeros_like(g)
        for i, x in enumerate(off):
            tx = np.sqrt(t0 ** 2 + (x / v) ** 2)
            tr = np.interp(tx, t0, g[i], right=0.0)
            tr[tx > 1.5 * np.maximum(t0, 1e-6)] = 0.0
            c[i] = tr
        live = np.maximum((c != 0).sum(0), 1)
        num = np.convolve(c.sum(0) ** 2, k, "same")
        den = np.convolve(live * (c ** 2).sum(0), k, "same") + 1e-30
        S[j] = num / den
    return S


def ref_for(cdp):
    er = load_reference()["raw"]
    return er[max(int(cdp[0]) - 400, 0):int(cdp[-1]) - 400 + 1]


def fig_chain():
    d = line(CLEAN)
    t = np.arange(d["ns"]) * DT
    C = 637                                 # analysis location with the best-supported picks (results model)
    so, sg = shot(d)
    co, cg, _ = cmp_gather(d, C)
    po, pg, _ = cmp_gather(d, C, half=2)
    vels = np.arange(1300.0, 3001.0, 25.0)
    S = semblance(pg, po, vels)
    v = v_at(C, t)
    fig = plt.figure(figsize=(W, 6.9))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.25, 1.0], hspace=0.38, wspace=0.12)
    a = fig.add_subplot(gs[0, 0]); b = fig.add_subplot(gs[0, 1]); c = fig.add_subplot(gs[0, 2])
    e = fig.add_subplot(gs[0, 3])
    show(a, sg, so, DT, "(a) Shot gather", "Offset (m)")
    show(b, cg, co, DT, f"(b) CMP gather", "Offset (m)", ylabel=False)
    c.imshow(S.T, cmap="magma_r", aspect="auto", extent=[vels[0], vels[-1], t[-1], 0], vmin=0, vmax=np.percentile(S, 99.5))
    c.plot(truth_vrms(C * 10.0, t), t, color="white", lw=2.2)
    c.plot(truth_vrms(C * 10.0, t), t, color=BLUE, lw=1.0, label="true rms")
    m = min(MODEL, key=lambda q: abs(q["cdp"] - C))
    meas = [p for p in m["function"] if not p.get("held")]
    held = meas[-1:] + [p for p in m["function"] if p.get("held")]
    c.plot([p["v_m_s"] for p in meas], [p["t0_s"] for p in meas], "o-", color="black", ms=3, lw=0.9,
           mfc="white", label="picked")
    c.plot([p["v_m_s"] for p in held[:1]] * 2, [held[0]["t0_s"], t[-1]], "--", color="black", lw=0.9,
           label="held below last pick")
    c.set_title("(c) Velocity analysis", loc="left")
    c.set_xlabel("Velocity (m/s)")
    c.tick_params(labelleft=False)
    c.legend(loc="upper right", fontsize=6.5, frameon=True, framealpha=0.9, borderaxespad=0.3)
    show(e, nmo(cg, co, v), co, DT, "(d) After moveout", "Offset (m)", ylabel=False)
    cs, st, _ = read_su(R / "v016-v2_stack.su")
    f = fig.add_subplot(gs[1, :2]); g = fig.add_subplot(gs[1, 2:])
    show(f, st, cs, DT, "(e) Released stack", tmin=T0)
    show(g, ref_for(cs), cs, DT, "(f) True zero-offset section", tmin=T0, ylabel=False)
    for ax in (f, g):
        ax.axvline(C, color=RED, lw=0.7, ymax=0.04)
    fig.savefig(OUT / "fig2_processing_chain.png", bbox_inches="tight")
    plt.close(fig)


def fig_velocity():
    cs, st, _ = read_su(R / "v016-v2_stack.su")
    t = np.arange(st.shape[1]) * DT
    picked = np.array([v_at(c, t) for c in cs])
    true = np.array([truth_vrms(c * 10.0, t) for c in cs])
    fig, ax = plt.subplots(1, 2, figsize=(W, 2.9), sharey=True)
    kw = dict(cmap="viridis", aspect="auto", extent=[cs[0], cs[-1], t[-1], 0], vmin=1450, vmax=2600)
    ax[0].imshow(picked.T, **kw)
    im = ax[1].imshow(true.T, **kw)
    for m in MODEL:
        tp = [p["t0_s"] for p in m["function"] if not p.get("held")]
        ax[0].plot([m["cdp"]] * len(tp), tp, "o", ms=2.2, color="white", mec="black", mew=0.4)
    ax[0].set_title("(a) Picked stacking velocity", loc="left")
    ax[1].set_title("(b) True rms velocity", loc="left")
    for a in ax:
        a.set_xlabel("CDP"); a.set_ylim(2.6, 0)
    ax[0].set_ylabel("Two-way time (s)")
    fig.colorbar(im, ax=ax, label="Velocity (m/s)", fraction=0.035, pad=0.02)
    fig.savefig(OUT / "fig3_velocity_model.png", bbox_inches="tight")
    plt.close(fig)


def lmo(off, g, v=1500.0, t_lo=-0.08, t_hi=0.32):
    n = int(round((t_hi - t_lo) / DT))
    tt = t_lo + np.arange(n) * DT
    t = np.arange(g.shape[1]) * DT
    return np.array([np.interp(tt + x / v, t, g[i], left=0.0, right=0.0) for i, x in enumerate(off)]), t_lo


def fig_timezero():
    dc = line(CLEAN)
    dl = line(ROOT / "test_dataset/Marm2_ladder_heldout/delay_060ms.sgy")
    c, s, dt = read_su(R / "ho-delay060_stack.su")
    k = int(round(0.058 / dt))
    sh = np.zeros_like(s); sh[:, :-k] = s[:, k:]
    ref = ref_for(c)
    sel = (c >= 700) & (c <= 1000)
    fig = plt.figure(figsize=(W, 5.6))
    gs = fig.add_gridspec(2, 6, height_ratios=[0.62, 1.0], hspace=0.5, wspace=0.45)
    for j, (d, name) in enumerate(((dc, "(a) Clean line, direct arrival flattened"),
                                   (dl, "(b) Data 60 ms late, direct arrival flattened"))):
        ax = fig.add_subplot(gs[0, 3 * j:3 * j + 3])
        o, g = shot(d)
        near = o <= 900
        f, t_lo = lmo(o[near], g[near])
        show(ax, f, o[near], DT, name, "Offset (m)", t_first=t_lo, tmin=-0.08, tmax=0.32, gain=False, clip=99.5,
             ylabel=(j == 0))
        ax.axhline(0.0, color=RED, lw=0.8)
        if j == 0:
            ax.set_ylabel("Time after moveout (s)")
    kw = dict(tmin=0.6, tmax=2.0)
    a0 = fig.add_subplot(gs[1, 0:2]); a1 = fig.add_subplot(gs[1, 2:4]); a2 = fig.add_subplot(gs[1, 4:6])
    show(a0, ref[sel], c[sel], dt, "(c) True section", **kw)
    show(a1, s[sel], c[sel], dt, "(d) Released stack", ylabel=False, **kw)
    show(a2, sh[sel], c[sel], dt, "(e) Shifted by 58 ms", ylabel=False, **kw)
    for a in (a0, a1, a2):
        for tm in (0.93, 1.29, 1.62):
            a.axhline(tm, color=RED, lw=0.7)
    fig.savefig(OUT / "fig4_time_origin.png", bbox_inches="tight")
    plt.close(fig)


def half_stacks(d, lo, hi):
    t = np.arange(d["ns"]) * DT
    cd = np.arange(lo, hi + 1)
    h1 = np.zeros((cd.size, d["ns"])); h2 = np.zeros_like(h1)
    for i, c in enumerate(cd):
        o, g, _ = cmp_gather(d, c)
        if o.size < 4:
            continue
        n = nmo(g, o, v_at(c, t))
        h1[i] = n[0::2].mean(0); h2[i] = n[1::2].mean(0)
    return cd, h1, h2


def fig_noise():
    d = line(ROOT / "test_dataset/Marm2_ladder_heldout/bandnoise_1p50x.sgy")
    o, g = shot(d)
    cd, h1, h2 = half_stacks(d, 700, 1000)
    c1, s1, _ = read_su(R / "ho-bnoise1p50_stack.su")
    c3, s3, _ = read_su(R / "v019-ho-bn300_stack.su")
    fig = plt.figure(figsize=(W, 5.9))
    gs = fig.add_gridspec(2, 6, height_ratios=[1.0, 0.95], hspace=0.42, wspace=0.3)
    a = fig.add_subplot(gs[0, 0:2]); b = fig.add_subplot(gs[0, 2:4]); c = fig.add_subplot(gs[0, 4:6])
    show(a, g, o, DT, "(a) Shot gather, noise 1.5 x", "Offset (m)")
    kw = dict(tmin=0.6, tmax=2.0)
    show(b, h1, cd, DT, "(b) Half-stack, odd traces", ylabel=False, **kw)
    show(c, h2, cd, DT, "(c) Half-stack, even traces", ylabel=False, **kw)
    a.set_ylim(2.6, 0)
    e = fig.add_subplot(gs[1, 0:3]); f = fig.add_subplot(gs[1, 3:6])
    show(e, s1, c1, DT, "(d) Stack, noise 1.5 x", tmin=T0)
    show(f, s3, c3, DT, "(e) Stack, noise 3.0 x", tmin=T0, ylabel=False)
    fig.savefig(OUT / "fig5_band_noise.png", bbox_inches="tight")
    plt.close(fig)


def fig_statics():
    d = line(ROOT / "test_dataset/Marm2_ladder_heldout5/statics_24ms.sgy")
    sol = json.loads((R / "v022-h5-st24_residual_statics_p1.json").read_text())
    s_src = {v["sx"]: v["static_ms"] for v in sol["shots"].values()}
    s_rec = {v["gx"]: v["static_ms"] for v in sol["stations"].values()}
    t = np.arange(d["ns"]) * DT
    C = 843
    o, g, k = cmp_gather(d, C)
    st = np.array([s_src.get(int(d["sx"][i]), 0.0) + s_rec.get(int(d["gx"][i]), 0.0) for i in k]) / 1000.0
    gc = np.array([np.interp(t + s, t, tr, left=0.0, right=0.0) for tr, s in zip(g, st)])   # corrected(t) = recorded(t + static)
    v = v_at(C, t)
    c1, s1, _ = read_su(R / "v0220/stacks/v022-h5-st24_stack1.su")
    c2, s2, _ = read_su(R / "v022-h5-st24_stack.su")
    so, sg = shot(d)
    fig = plt.figure(figsize=(W, 6.2))
    gs = fig.add_gridspec(2, 6, height_ratios=[1.05, 0.95], hspace=0.42, wspace=0.3)
    a = fig.add_subplot(gs[0, 0:2]); b = fig.add_subplot(gs[0, 2:4]); c = fig.add_subplot(gs[0, 4:6])
    show(a, sg, so, DT, "(a) Shot gather", "Offset (m)")
    kw = dict(tmin=0.6, tmax=2.4)
    show(b, nmo(g, o, v), o, DT, "(b) CMP gather", "Offset (m)", ylabel=False, **kw)
    show(c, nmo(gc, o, v), o, DT, "(c) Statics applied", "Offset (m)", ylabel=False, **kw)
    e = fig.add_subplot(gs[1, 0:3]); f = fig.add_subplot(gs[1, 3:6])
    show(e, s1, c1, DT, "(d) Stack before the correction", tmin=T0)
    show(f, s2, c2, DT, "(e) Stack after the correction", tmin=T0, ylabel=False)
    fig.savefig(OUT / "fig6_residual_statics.png", bbox_inches="tight")
    plt.close(fig)


def fig_migration():
    c, s, dt = read_su(R / "v031-v2_stack.su")
    cm, m, _ = read_su(R / "v031-v2_mig_phase_shift_smooth.su")
    ref = np.load(R / "migration_reference/er_mig_true_blend.npz")["section"].astype(float)
    sel = slice(int(cm[0]) - 400, int(cm[-1]) - 400 + 1)
    fig, ax = plt.subplots(2, 2, figsize=(W, 5.6), sharex=True, sharey=True)
    show(ax[0, 0], s, c, dt, "(a) Released stack", tmin=T0)
    show(ax[0, 1], ref_for(c), c, dt, "(b) True zero-offset section", tmin=T0, ylabel=False)
    show(ax[1, 0], m, cm, dt, "(c) Released time migration", tmin=T0)
    show(ax[1, 1], ref[sel], cm, dt, "(d) True-velocity migration", tmin=T0, ylabel=False)
    for a in ax[0]:
        a.set_xlabel("")
    fig.tight_layout()
    fig.savefig(OUT / "fig7_migration.png", bbox_inches="tight")
    plt.close(fig)


def fig_viking():
    c1, s1, dt = read_su(R / "v031-vikfull_stack.su")
    cm, m, _ = read_su(R / "v031-vikfull_mig_phase_shift_smooth.su")
    fig = plt.figure(figsize=(W, 8.8))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.95])
    a = fig.add_subplot(gs[0, :]); b = fig.add_subplot(gs[1, :], sharex=a)
    kw = dict(win=0.5, clip=96, tmax=5.8, tmin=0.3)
    show(a, s1, c1, dt, "(a) Released stack", **kw)
    show(b, m, cm, dt, "(b) Released time migration", **kw)
    lo, hi = 1300, 1800
    for ax_ in (a, b):
        ax_.add_patch(plt.Rectangle((lo, 1.6), hi - lo, 1.8, fill=False, ec=RED, lw=0.9, zorder=5))
    z1 = (c1 >= lo) & (c1 <= hi); zm = (cm >= lo) & (cm <= hi)
    p = fig.add_subplot(gs[2, 0]); q = fig.add_subplot(gs[2, 1], sharey=p)
    kz = dict(win=0.5, clip=97, tmin=1.6, tmax=3.4)
    show(p, s1[z1], c1[z1], dt, "(c) Stack, outlined window", **kz)
    show(q, m[zm], cm[zm], dt, "(d) Migration, outlined window", ylabel=False, **kz)
    fig.tight_layout()
    fig.savefig(OUT / "fig8_viking.png")
    plt.close(fig)


def fig_poland():
    c, s, dt = read_su(R / "v033b-poland_stack.su")
    fig, ax = plt.subplots(figsize=(W, 3.8))
    show(ax, s, c, dt, "", win=0.4, clip=97, tmax=3.0)
    fig.tight_layout()
    fig.savefig(OUT / "fig9_poland.png")
    plt.close(fig)


FIGS = {"chain": fig_chain, "velocity": fig_velocity, "timezero": fig_timezero, "noise": fig_noise,
        "statics": fig_statics, "migration": fig_migration, "viking": fig_viking, "poland": fig_poland}
if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    names = [a for a in sys.argv[1:] if a in FIGS] or list(FIGS)
    for n in names:
        FIGS[n]()
        print("made", n, flush=True)
