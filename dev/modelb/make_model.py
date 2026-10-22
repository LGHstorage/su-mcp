"""Model B for the second-model test (results/modelb/CRITERIA.md): anticline, unconformity, normal fault."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "test_dataset/ModelB/truth"
NX, NZ, D = 801, 351, 10.0
WATER_Z, WATER_V = 300.0, 1500.0
YOUNG = [(450.0, 1650.0), (620.0, 1800.0), (None, 1950.0)]        # base depth, velocity; last layer to the unconformity
DEEP = [(1050, 2200), (1300, 2450), (1550, 2700), (1800, 3000), (2050, 3300), (2130, 4000),
        (2500, 3600), (2900, 3900), (None, 3900)]                    # base depth of each layer away from the fold
FOLD_X, FOLD_W = 2500.0, 1200.0
FAULT_X0, FAULT_Z0, FAULT_DIP, THROW = 5200.0, 600.0, 60.0, 200.0
LATERAL = 0.05


def unconformity(x):
    return 800.0 + 60.0 * np.sin(2 * np.pi * x / 3000.0)


def fold(z0, x):
    return -(100.0 + 0.15 * (z0 - 800.0)) * np.exp(-((x - FOLD_X) / FOLD_W) ** 2)


def main():
    x = np.arange(NX) * D
    z = np.arange(NZ) * D
    X, Z = np.meshgrid(x, z)
    v = np.full(X.shape, np.nan)
    v[Z < WATER_Z] = WATER_V
    zu = unconformity(X)
    young = (Z >= WATER_Z) & (Z < zu)
    top = WATER_Z
    for base, vel in YOUNG:
        b = zu if base is None else np.minimum(base, zu)
        v[young & (Z >= top) & (Z < b)] = vel
        top = base if base is not None else top
    deep = Z >= zu
    hanging = (Z > FAULT_Z0) & (X > FAULT_X0 + (Z - FAULT_Z0) / np.tan(np.radians(FAULT_DIP)))
    zeff = np.where(hanging, Z - THROW, Z)
    layer = np.zeros(X.shape, int)
    for i, (base, _) in enumerate(DEEP[:-1]):
        layer += (zeff >= base + fold(base, X)).astype(int)
    vel = np.array([vv for _, vv in DEEP], float)[layer] * (1 + LATERAL * (X - x.mean()) / (x[-1] - x[0]))
    v[deep] = vel[deep]
    assert not np.isnan(v).any()
    OUT.mkdir(parents=True, exist_ok=True)
    np.save(OUT / "modelb_vp_10m_mps.npy", v.astype(np.float32))
    (OUT / "modelb_vp_f32.bin").write_bytes(v.astype("<f4").tobytes())
    (OUT / "modelb_config.json").write_text(json.dumps({
        "criteria": "results/modelb/CRITERIA.md", "shape_nz_nx": [NZ, NX], "dx_m": D, "water": [WATER_Z, WATER_V],
        "young_layers": YOUNG, "deep_layers": DEEP, "fold_x_w": [FOLD_X, FOLD_W],
        "fault": {"x0": FAULT_X0, "z0": FAULT_Z0, "dip_deg": FAULT_DIP, "throw_m": THROW}, "lateral": LATERAL,
        "v_min": float(v.min()), "v_max": float(v.max())}, indent=1))
    print("vp", v.min(), v.max())


if __name__ == "__main__":
    main()
