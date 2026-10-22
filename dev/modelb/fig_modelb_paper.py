"""Manuscript figure of the second geological model (display only).
usage: python3 dev/modelb/fig_modelb_paper.py [--dpi N] [--out PATH]   (writes papers/figs/fig7_modelb.png)
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "dev/paper"))
sys.path.insert(0, str(HERE))
from figures_paper import OUT, W, read_su, show  # noqa: E402  (also sets the rcParams of the paper figures)
from evaluate_b import load_reference  # noqa: E402

R = ROOT / "results"
T0 = 0.3
out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT / "fig7_modelb.png"
if out.exists():
    sys.exit(f"{out} already exists")
vp = np.load(ROOT / "test_dataset/ModelB/truth/modelb_vp_10m_mps.npy")
vp = vp if vp.shape[0] < vp.shape[1] else vp.T                  # (depth, distance)
ref = load_reference()["raw"]
c0, s0, dt = read_su(R / "modelb-clean_stack.su")
c2, s2, _ = read_su(R / "modelb-bn200_stack.su")
sel = slice(int(c0[0]) - 400, int(c0[-1]) - 400 + 1)

fig, ax = plt.subplots(2, 2, figsize=(W, 5.6), sharex=True)
cdp_model = 400 + np.arange(vp.shape[1] + 1)                     # 10 m cells, CDP = x / 10 m + 400
im = ax[0, 0].imshow(vp / 1000, cmap="viridis", aspect="auto", interpolation="nearest",
                     extent=[cdp_model[0], cdp_model[-1], vp.shape[0] * 0.01, 0])
ax[0, 0].set_ylabel("Depth (km)")
ax[0, 0].set_title("(a) P-wave velocity", loc="left")
ax[0, 0].tick_params(labelbottom=True)
cax = ax[0, 0].inset_axes([0.62, 0.16, 0.34, 0.05])
cb = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[2, 3, 4])
cb.set_label("P-wave velocity (km/s)", fontsize=7, labelpad=1)
cb.ax.tick_params(labelsize=7, length=2)
show(ax[0, 1], ref[sel], c0, dt, "(b) True zero-offset section", tmin=T0, ylabel=False)
show(ax[1, 0], s0, c0, dt, "(c) Released stack, clean line", tmin=T0)
show(ax[1, 1], s2, c2, dt, "(d) Released stack, noise 2.0 x", tmin=T0, ylabel=False)
ax[0, 1].tick_params(labelleft=True)
for a in ax[0]:                                                   # distance along the model, CDP = x / 10 m + 400
    top = a.secondary_xaxis("top", functions=(lambda c: (c - 400) / 100, lambda x: x * 100 + 400))
    top.set_xlabel("Distance (km)", fontsize=8, labelpad=2)
    top.tick_params(labelsize=7.5, length=2.5, pad=1)
ax[1, 1].set_ylabel(""); ax[1, 1].tick_params(labelleft=False)
ax[0, 1].set_ylabel("Two-way time (s)")
ax[0, 1].set_xlabel("")
ax[0, 0].set_xlabel("CDP")
for a in ax.ravel():
    a.set_xlim(c0[0], c0[-1])
ax[1, 1].sharey(ax[1, 0]); ax[0, 1].sharey(ax[1, 0])
fig.tight_layout()
fig.savefig(out, bbox_inches="tight")
print(out)
