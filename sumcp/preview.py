"""QC images."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import sufile  # noqa: E402

__all__ = ["render", "MAX_TRACES"]

MAX_TRACES = 1200          # beyond this the panel is decimated for plotting
MAX_SAMPLES = 4000


def _select(path, geom, fldr=None, cdp=None, start=0, count=None):
    """Trace indices to plot, and a label describing the selection."""
    if fldr is not None or cdp is not None:
        key = "fldr" if fldr is not None else "cdp"
        wanted = int(fldr if fldr is not None else cdp)
        values = sufile.read_key(path, key, geom)
        idx = np.flatnonzero(values == wanted)
        if idx.size == 0:
            raise ValueError(f"No traces with {key}={wanted} in this file.")
        return idx, f"{key}={wanted}"
    total = geom["ntr"]
    start = max(0, int(start))
    count = total - start if count is None else int(count)
    count = max(1, min(count, total - start))
    return np.arange(start, start + count), f"traces {start}-{start + count - 1}"


def _gather(path, geom, indices):
    """Read the selected traces (contiguous fast path, otherwise one by one)."""
    if indices.size and indices[-1] - indices[0] + 1 == indices.size:
        data, headers = sufile.read_gather(path, int(indices[0]), int(indices.size), geom)
        return data, headers
    rows, heads = [], {k: [] for k in ("tracl", "fldr", "tracf", "cdp", "offset", "sx", "gx", "delrt")}
    for i in indices:
        d, h = sufile.read_gather(path, int(i), 1, geom)
        rows.append(d[0])
        for k in heads:
            heads[k].append(int(h[k][0]))
    return np.asarray(rows, dtype=np.float32), {k: np.asarray(v) for k, v in heads.items()}


def render(path, out_png, *, fldr=None, cdp=None, start=0, count=None,
           perc=99.0, title=None, mode="image", gain="none"):
    """Write a QC PNG of an SU file and return a small description of it."""
    path = Path(path)
    out_png = Path(out_png)
    geom = sufile.geometry(path)
    indices, label = _select(path, geom, fldr=fldr, cdp=cdp, start=start, count=count)

    decimated = False
    if indices.size > MAX_TRACES:
        step = int(np.ceil(indices.size / MAX_TRACES))
        indices = indices[::step]
        decimated = True

    data, headers = _gather(path, geom, indices)
    data = np.nan_to_num(data, copy=False)

    tstep = 1
    if data.shape[1] > MAX_SAMPLES:
        tstep = int(np.ceil(data.shape[1] / MAX_SAMPLES))
        data = data[:, ::tstep]

    if gain == "agc":
        window = max(5, int(round(0.5 / ((geom["dt_s"] or 0.004) * tstep))))
        kernel = np.ones(window) / window
        envelope = np.apply_along_axis(
            lambda r: np.convolve(np.abs(r), kernel, mode="same"), 1, data)
        data = data / (envelope + 1e-12 * np.abs(data).max())

    finite = data[np.isfinite(data)]
    clip = float(np.percentile(np.abs(finite), perc)) if finite.size else 1.0
    if clip <= 0:
        clip = float(np.abs(finite).max()) or 1.0

    dt = (geom["dt_s"] or 0.004) * tstep
    # The panel may not start at zero: suwind/suvcat set delrt (ms).
    t0 = float(np.median(headers["delrt"])) / 1000.0
    tmax = t0 + data.shape[1] * dt

    fig, ax = plt.subplots(figsize=(min(16, 4 + data.shape[0] / 90), 7), dpi=110)
    if mode == "wiggle" and data.shape[0] <= 120:
        scale = 0.9 / clip
        taxis = t0 + np.arange(data.shape[1]) * dt
        for j in range(data.shape[0]):
            trace = np.clip(data[j] * scale, -1.5, 1.5) + j
            ax.plot(trace, taxis, color="k", linewidth=0.4)
            ax.fill_betweenx(taxis, j, trace, where=trace > j, color="k", linewidth=0)
        ax.set_xlim(-1, data.shape[0])
        ax.set_ylim(tmax, t0)
        ax.set_xlabel("Trace number in panel")
    else:
        ax.imshow(data.T, cmap="gray_r", aspect="auto", vmin=-clip, vmax=clip,
                  extent=[0, data.shape[0], tmax, t0], interpolation="nearest")
        ax.set_xlabel("Trace number in panel")
    ax.set_ylabel("Time (s)")

    subtitle = (f"{path.name} | {label} | {data.shape[0]} traces | "
                f"dt={dt * 1000:.3g} ms | t0={t0:.3g} s")
    if decimated:
        subtitle += " | decimated"
    ax.set_title(title or subtitle, fontsize=10)
    ax.grid(False)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)

    return {
        "png": str(out_png),
        "selection": label,
        "traces_plotted": int(data.shape[0]),
        "samples_plotted": int(data.shape[1]),
        "decimated": decimated,
        "clip_value": clip,
        "clip_percentile": perc,
        "mode": mode,
        "gain": gain,
        "t_start_s": t0,
        "t_end_s": tmax,
        "offset_range": [int(headers["offset"].min()), int(headers["offset"].max())],
    }
