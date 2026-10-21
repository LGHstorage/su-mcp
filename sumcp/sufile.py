"""A small, dependency-light reader for SU (Seismic Unix) files."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from . import segy as _segy

__all__ = ["HEADER_BYTES", "KEY_FORMATS", "SUFormatError", "scan", "read_gather",
           "read_traces",
           "geometry", "read_key", "read_header_columns", "detect_byte_order",
           "rewrite_byte_order"]

HEADER_BYTES = 240

# name -> (byte offset, struct code).  i = int32, h = int16, H = uint16, f = float32
KEY_FORMATS = {
    "tracl": (0, "i"), "tracr": (4, "i"), "fldr": (8, "i"), "tracf": (12, "i"),
    "ep": (16, "i"), "cdp": (20, "i"), "cdpt": (24, "i"),
    "trid": (28, "h"), "nvs": (30, "h"), "nhs": (32, "h"), "duse": (34, "h"),
    "offset": (36, "i"), "gelev": (40, "i"), "selev": (44, "i"),
    "sdepth": (48, "i"), "gdel": (52, "i"), "sdel": (56, "i"),
    "swdep": (60, "i"), "gwdep": (64, "i"),
    "scalel": (68, "h"), "scalco": (70, "h"),
    "sx": (72, "i"), "sy": (76, "i"), "gx": (80, "i"), "gy": (84, "i"),
    "counit": (88, "h"),
    "sstat": (98, "h"), "gstat": (100, "h"), "tstat": (102, "h"),
    "delrt": (108, "h"), "muts": (110, "h"), "mute": (112, "h"),
    "ns": (114, "H"), "dt": (116, "H"),
    "d1": (180, "f"), "f1": (184, "f"), "d2": (188, "f"), "f2": (192, "f"),
    "ntr": (204, "i"),
}

_NUMPY_CODE = {"<": {"i": "<i4", "h": "<i2", "H": "<u2", "f": "<f4"},
               ">": {"i": ">i4", "h": ">i2", "H": ">u2", "f": ">f4"}}
_ORDER_NAME = {"<": "little", ">": "big"}

# Keys worth reporting by default.
DEFAULT_KEYS = (
    "tracl", "fldr", "tracf", "ep", "cdp", "trid", "offset",
    "sx", "sy", "gx", "gy", "scalco", "counit", "selev", "gelev",
    "sstat", "gstat", "tstat",
    "delrt", "ns", "dt",
)


class SUFormatError(ValueError):
    """The file does not look like a fixed-length SU dataset."""


def _first_header(path: Path) -> bytes:
    with open(path, "rb") as fh:
        head = fh.read(HEADER_BYTES)
    if len(head) < HEADER_BYTES:
        raise SUFormatError(f"File is shorter than one SU trace header: {path.name}")
    return head


def _field(buf: bytes, key: str, order: str = "<"):
    offset, code = KEY_FORMATS[key]
    return struct.unpack_from(order + code, buf, offset)[0]


def detect_byte_order(path) -> tuple:
    """Work out the file's byte order from ns and the file length."""
    path = Path(path)
    head = _first_header(path)
    size = path.stat().st_size
    candidates = []
    for order in ("<", ">"):
        ns = int(_field(head, "ns", order))
        dt = int(_field(head, "dt", order))
        if not 1 <= ns <= 1_000_000:
            continue
        stride = HEADER_BYTES + 4 * ns
        divides = size % stride == 0
        plausible_dt = 1 <= dt <= 1_000_000
        score = 2 * divides + plausible_dt
        candidates.append((score, order, ns, dt, divides))
    if not candidates:
        raise SUFormatError(
            f"Neither byte order gives a plausible ns in {path.name}; "
            "this does not look like an SU file."
        )
    candidates.sort(reverse=True)
    score, order, ns, dt, divides = candidates[0]
    if not divides:
        stride = HEADER_BYTES + 4 * ns
        raise SUFormatError(
            f"File size {size} is not a multiple of the trace length {stride} "
            f"(ns={ns}, byte order {_ORDER_NAME[order]}); the file may use "
            "variable-length traces or a different format."
        )
    return order, ns, dt


def geometry(path) -> dict:
    """ns, dt, byte order and trace count, from the first header and file size."""
    path = Path(path)
    order, ns, dt_us = detect_byte_order(path)
    stride = HEADER_BYTES + 4 * ns
    size = path.stat().st_size
    ntr = size // stride
    # delrt is the recording delay in ms: after suwind tmin=1.2 the first sample is at 1.2 s, not 0.
    delrt_ms = int(_field(_first_header(path), "delrt", order))
    return {
        "byte_order": _ORDER_NAME[order],
        "_order": order,
        "delrt_ms": delrt_ms,
        "t_start_s": delrt_ms / 1000.0,
        "ns": ns,
        "dt_us": dt_us,
        "dt_s": dt_us / 1e6 if dt_us else None,
        "record_length_s": ns * dt_us / 1e6 if dt_us else None,
        "t_end_s": (delrt_ms / 1000.0 + ns * dt_us / 1e6) if dt_us else None,
        "ntr": int(ntr),
        "trace_bytes": stride,
        "file_bytes": size,
    }


def read_header_columns(path, keys, geom: dict | None = None,
                        chunk: int = 4096) -> dict:
    """Read the named header words for every trace, in one pass over the file."""
    path = Path(path)
    geom = geom or geometry(path)
    order = geom.get("_order", "<")
    ntr, stride = geom["ntr"], geom["trace_bytes"]

    unknown = [k for k in keys if k not in KEY_FORMATS]
    if unknown:
        raise KeyError(f"Unknown SU header key(s): {', '.join(unknown)}")

    out = {k: np.empty(ntr, dtype=_NUMPY_CODE[order][KEY_FORMATS[k][1]])
           for k in keys}
    block = np.empty((chunk, HEADER_BYTES), dtype=np.uint8)
    with open(path, "rb") as fh:
        index = 0
        while index < ntr:
            take = min(chunk, ntr - index)
            for j in range(take):
                fh.seek((index + j) * stride)
                block[j] = np.frombuffer(fh.read(HEADER_BYTES), dtype=np.uint8)
            for key in keys:
                offset, code = KEY_FORMATS[key]
                width = struct.calcsize(code)
                column = block[:take, offset: offset + width].copy()
                out[key][index: index + take] = column.view(
                    _NUMPY_CODE[order][code]).reshape(-1)
            index += take
    return {k: v.astype(np.float64 if KEY_FORMATS[k][1] == "f" else np.int64)
            for k, v in out.items()}


def read_key(path, key: str, geom: dict | None = None) -> np.ndarray:
    """Read one header word for every trace."""
    return read_header_columns(path, [key], geom)[key]


def _stats(values: np.ndarray) -> dict:
    unique = np.unique(values)
    out = {
        "min": int(values.min()),
        "max": int(values.max()),
        "n_unique": int(unique.size),
        "constant": bool(unique.size == 1),
    }
    if unique.size <= 12:
        out["values"] = [int(v) for v in unique]
    if unique.size > 1:
        diffs = np.diff(unique)
        step = np.unique(diffs)
        if step.size == 1:
            out["step"] = int(step[0])
    return out


def scan(path, keys=DEFAULT_KEYS) -> dict:
    """Structured summary of an SU file: sampling, key ranges, fold."""
    path = Path(path)
    geom = geometry(path)
    report = {"file": path.name, **{k: v for k, v in geom.items() if k != "_order"},
              "keys": {}}
    wanted = [k for k in keys if k in KEY_FORMATS and k not in ("ns", "dt")]
    columns = read_header_columns(path, wanted, geom)
    for key in wanted:
        report["keys"][key] = _stats(columns[key])

    delrt = report["keys"].get("delrt")
    if delrt and not delrt["constant"]:
        report["delrt_varies"] = True
        report["t_start_s"] = None      # no single start time
    cdp = report["keys"].get("cdp")
    fldr = report["keys"].get("fldr")
    report["has_cdp"] = bool(cdp and not (cdp["min"] == 0 and cdp["max"] == 0))
    report["has_shot_index"] = bool(fldr and fldr["n_unique"] > 1)
    if report["has_cdp"]:
        values = columns["cdp"]
        counts = np.bincount(values - values.min())
        counts = counts[counts > 0]
        report["fold"] = {
            "min": int(counts.min()), "max": int(counts.max()),
            "median": int(np.median(counts)), "n_bins": int(counts.size),
        }
    elif report["has_shot_index"]:
        values = columns["fldr"]
        counts = np.bincount(values - values.min())
        counts = counts[counts > 0]
        report["traces_per_shot"] = {
            "min": int(counts.min()), "max": int(counts.max()),
            "median": int(np.median(counts)), "n_shots": int(counts.size),
        }
    return report


def read_gather(path, start: int = 0, count: int = 200, geom: dict | None = None):
    """Return (samples[ntr, ns], headers dict) for a slice of traces."""
    path = Path(path)
    geom = geom or geometry(path)
    start = max(0, int(start))
    count = max(1, min(int(count), geom["ntr"] - start))
    stride = geom["trace_bytes"]
    ns = geom["ns"]
    order = geom.get("_order", "<")
    with open(path, "rb") as fh:
        fh.seek(start * stride)
        block = np.frombuffer(fh.read(count * stride), dtype=np.uint8)
    block = block.reshape(count, stride)
    samples = block[:, HEADER_BYTES:].copy().view(_NUMPY_CODE[order]["f"]).reshape(count, ns)
    headers = {}
    for key in ("tracl", "fldr", "tracf", "cdp", "offset", "sx", "gx", "delrt"):
        off, code = KEY_FORMATS[key]
        col = block[:, off: off + struct.calcsize(code)].copy()
        headers[key] = col.view(_NUMPY_CODE[order][code]).reshape(-1).astype(np.int64)
    return np.asarray(samples, dtype=np.float32), headers


def read_traces(path, indices, geom: dict | None = None,
                span_budget_bytes: int = 512 << 20):
    """Samples for an arbitrary set of trace indices, in one file open."""
    path = Path(path)
    geom = geom or geometry(path)
    idx = np.asarray(indices, dtype=np.int64)
    if idx.size == 0:
        return np.zeros((0, geom["ns"]), dtype=np.float32)
    stride, ns = geom["trace_bytes"], geom["ns"]
    dtype = _NUMPY_CODE[geom.get("_order", "<")]["f"]
    lo, hi = int(idx.min()), int(idx.max())
    with open(path, "rb") as fh:
        if (hi - lo + 1) * stride <= span_budget_bytes:
            fh.seek(lo * stride)
            block = np.frombuffer(fh.read((hi - lo + 1) * stride), dtype=np.uint8)
            block = block.reshape(-1, stride)[idx - lo]
        else:
            rows = []
            for i in idx:
                fh.seek(int(i) * stride)
                rows.append(np.frombuffer(fh.read(stride), dtype=np.uint8))
            block = np.stack(rows)
    samples = block[:, HEADER_BYTES:].copy().view(dtype).reshape(len(idx), ns)
    return np.asarray(samples, dtype=np.float32)


# The trace-header field layout lives in segy.py, which stays free of numpy so it can run anywhere.
_HEADER_LAYOUT = _segy.TRACE_HEADER_LAYOUT


def rewrite_byte_order(src, dst, chunk_traces: int = 512) -> dict:
    """Write a copy of an SU file in the opposite byte order."""
    src, dst = Path(src), Path(dst)
    geom = geometry(src)
    ns, stride, ntr = geom["ns"], geom["trace_bytes"], geom["ntr"]
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        remaining = ntr
        while remaining:
            take = min(chunk_traces, remaining)
            block = np.frombuffer(fin.read(take * stride), dtype=np.uint8)
            block = block.reshape(take, stride).copy()
            for offset, size, count in _HEADER_LAYOUT:
                end = offset + size * count
                field = block[:, offset:end].reshape(take, count, size)
                block[:, offset:end] = field[:, :, ::-1].reshape(take, size * count)
            data = block[:, HEADER_BYTES:].reshape(take, ns, 4)
            block[:, HEADER_BYTES:] = data[:, :, ::-1].reshape(take, ns * 4)
            fout.write(block.tobytes())
            remaining -= take
    return {"source": str(src), "output": str(dst),
            "from_byte_order": geom["byte_order"],
            "to_byte_order": "big" if geom["byte_order"] == "little" else "little",
            "traces": ntr}


def write_header_columns(src, dst, columns: dict, chunk_traces: int = 512,
                         keep=None) -> dict:
    """Copy an SU file, replacing several header words on every trace."""
    src, dst = Path(src), Path(dst)
    geom = geometry(src)
    order = geom.get("_order", "<")
    prepared = []
    for key, values in columns.items():
        if key not in KEY_FORMATS:
            raise KeyError(f"Unknown SU header key: {key}")
        offset, code = KEY_FORMATS[key]
        width = struct.calcsize(code)
        dtype = _NUMPY_CODE[order][code]
        values = np.asarray(values)
        if values.size != geom["ntr"]:
            raise ValueError(f"Got {values.size} values for {geom['ntr']} traces "
                             f"in {key}.")
        info = np.iinfo(np.dtype(dtype)) if code != "f" else None
        if info is not None and (values.min() < info.min or values.max() > info.max):
            raise ValueError(
                f"Values {values.min()}..{values.max()} do not fit the {key} header "
                f"word ({info.min}..{info.max}).")
        prepared.append((key, offset, width, values.astype(dtype), values))

    if keep is not None:
        keep = np.asarray(keep, dtype=bool)
        if keep.size != geom["ntr"]:
            raise ValueError(f"keep has {keep.size} entries for {geom['ntr']} traces.")

    stride = geom["trace_bytes"]
    written = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        index = 0
        while index < geom["ntr"]:
            take = min(chunk_traces, geom["ntr"] - index)
            block = np.frombuffer(fin.read(take * stride),
                                  dtype=np.uint8).reshape(take, stride).copy()
            for _key, offset, width, column, _orig in prepared:
                raw = column[index: index + take].tobytes()
                block[:, offset: offset + width] = np.frombuffer(
                    raw, dtype=np.uint8).reshape(take, width)
            if keep is not None:
                block = block[keep[index: index + take]]
            if block.size:
                fout.write(block.tobytes())
            written += block.shape[0]
            index += take
    kept = (slice(None) if keep is None else keep)
    return {
        "source": str(src), "output": str(dst),
        "keys": [k for k, *_ in prepared],
        "traces": int(written), "traces_in_source": geom["ntr"],
        "traces_dropped": int(geom["ntr"] - written),
        "byte_order": geom["byte_order"],
        "range": {k: [int(v[kept].min()), int(v[kept].max())] if written else None
                  for k, _o, _w, _c, v in prepared},
    }


def write_header_column(src, dst, key: str, values, chunk_traces: int = 512) -> dict:
    """Copy an SU file, replacing one header word on every trace."""
    src, dst = Path(src), Path(dst)
    if key not in KEY_FORMATS:
        raise KeyError(f"Unknown SU header key: {key}")
    geom = geometry(src)
    order = geom.get("_order", "<")
    offset, code = KEY_FORMATS[key]
    width = struct.calcsize(code)
    dtype = _NUMPY_CODE[order][code]

    values = np.asarray(values)
    if values.size != geom["ntr"]:
        raise ValueError(f"Got {values.size} values for {geom['ntr']} traces.")
    info = np.iinfo(np.dtype(dtype)) if code != "f" else None
    if info is not None and (values.min() < info.min or values.max() > info.max):
        raise ValueError(
            f"Values {values.min()}..{values.max()} do not fit the {key} header word "
            f"({info.min}..{info.max}).")
    column = values.astype(dtype)

    stride = geom["trace_bytes"]
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        index = 0
        while index < geom["ntr"]:
            take = min(chunk_traces, geom["ntr"] - index)
            block = np.frombuffer(fin.read(take * stride), dtype=np.uint8).reshape(take, stride).copy()
            raw = column[index: index + take].tobytes()
            block[:, offset: offset + width] = np.frombuffer(
                raw, dtype=np.uint8).reshape(take, width)
            fout.write(block.tobytes())
            index += take
    return {"source": str(src), "output": str(dst), "key": key,
            "traces": geom["ntr"], "byte_order": geom["byte_order"],
            "range": [int(values.min()), int(values.max())]}
