"""Deterministic SEG-Y diagnosis."""

from __future__ import annotations

import struct
from pathlib import Path

__all__ = ["SEGYError", "diagnose", "FORMAT_NAMES", "BYTES_PER_SAMPLE",
           "rewrite_byte_order", "TRACE_HEADER_LAYOUT"]

TEXT_BYTES = 3200
BINARY_BYTES = 400
TRACE_HEADER_BYTES = 240

# Binary header field -> (offset inside the 400-byte block, struct code)
BINARY_FIELDS = {
    "jobid": (0, "i"), "lino": (4, "i"), "reno": (8, "i"),
    "ntrpr": (12, "h"), "nart": (14, "h"),
    "hdt": (16, "H"), "dto": (18, "H"), "hns": (20, "H"), "nso": (22, "H"),
    "format": (24, "h"), "fold": (26, "h"), "tsort": (28, "h"),
    "mfeet": (54, "h"),
    "rev": (300, "H"), "fixed": (302, "h"), "nextended": (304, "h"),
}

FORMAT_NAMES = {
    1: "4-byte IBM floating point", 2: "4-byte two's complement integer",
    3: "2-byte two's complement integer", 4: "4-byte fixed point with gain (obsolete)",
    5: "4-byte IEEE floating point", 6: "8-byte IEEE floating point",
    7: "3-byte two's complement integer", 8: "1-byte two's complement integer",
    9: "8-byte two's complement integer", 10: "4-byte unsigned integer",
    11: "2-byte unsigned integer", 12: "8-byte unsigned integer",
    15: "3-byte unsigned integer", 16: "1-byte unsigned integer",
}

BYTES_PER_SAMPLE = {1: 4, 2: 4, 3: 2, 4: 4, 5: 4, 6: 8, 7: 3, 8: 1,
                    9: 8, 10: 4, 11: 2, 12: 8, 15: 3, 16: 1}

# segyread converts these without an override.
SEGYREAD_NATIVE_FORMATS = {1, 2, 3, 5, 8}

# The 240-byte trace header as (offset, item size, count).
TRACE_HEADER_LAYOUT = (
    (0, 4, 7),      # tracl .. cdpt
    (28, 2, 4),     # trid, nvs, nhs, duse
    (36, 4, 8),     # offset .. gwdep
    (68, 2, 2),     # scalel, scalco
    (72, 4, 4),     # sx, sy, gx, gy
    (88, 2, 46),    # counit .. otrav
    (180, 4, 6),    # d1, f1, d2, f2, ungpow, unscale
    (204, 4, 1),    # ntr
    (208, 2, 16),   # mark, shortpad, unass
)

TRACE_NS_OFFSET = 114        # bytes 115-116 of the trace header
TRACE_DT_OFFSET = 116        # bytes 117-118


class SEGYError(ValueError):
    """The file cannot be read as SEG-Y."""


def _unpack_binary(block: bytes, order: str) -> dict:
    out = {}
    for name, (offset, code) in BINARY_FIELDS.items():
        out[name] = struct.unpack_from(order + code, block, offset)[0]
    return out


def _plausibility(fields: dict, size: int) -> tuple:
    """Score a byte-order hypothesis; higher is better."""
    score, reasons = 0, []
    fmt, ns, dt = fields["format"], fields["hns"], fields["hdt"]
    if fmt in FORMAT_NAMES:
        score += 3
        reasons.append(f"format code {fmt} is defined")
    if 1 <= ns <= 200000:
        score += 3
        reasons.append(f"ns={ns} is plausible")
    if 1 <= dt <= 1000000:
        score += 2
        reasons.append(f"sample interval {dt} us is plausible")
    if fmt in BYTES_PER_SAMPLE and 1 <= ns <= 200000:
        stride = TRACE_HEADER_BYTES + ns * BYTES_PER_SAMPLE[fmt]
        body = size - TEXT_BYTES - BINARY_BYTES
        if body > 0 and body % stride == 0:
            score += 4
            reasons.append(f"file size divides evenly into {body // stride} traces")
    if fields["rev"] in (0, 1, 2, 256, 512):
        score += 1
    return score, reasons


def _decode_text(block: bytes) -> tuple:
    """Return (text, encoding). SEG-Y textual headers are usually EBCDIC."""
    best, best_name, best_score = "", "unknown", -1
    for name, encoding in (("ebcdic", "cp037"), ("ascii", "latin-1")):
        try:
            text = block.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        printable = sum(1 for ch in text if ch.isprintable() or ch in " \n\r")
        if printable > best_score:
            best, best_name, best_score = text, name, printable
    ratio = best_score / max(1, len(block))
    if ratio < 0.5:
        best_name = "unrecognised"
    lines = [best[i:i + 80].rstrip() for i in range(0, len(best), 80)]
    return "\n".join(lines).rstrip(), best_name


def diagnose(path) -> dict:
    """Read a SEG-Y file's headers and report what it actually is."""
    path = Path(path)
    size = path.stat().st_size
    if size < TEXT_BYTES + BINARY_BYTES + TRACE_HEADER_BYTES:
        raise SEGYError(f"File is too small to be SEG-Y ({size} bytes).")

    with open(path, "rb") as fh:
        text_block = fh.read(TEXT_BYTES)
        binary_block = fh.read(BINARY_BYTES)
        rest_head = fh.read(TRACE_HEADER_BYTES)

    candidates = {}
    for label, order in (("big", ">"), ("little", "<")):
        fields = _unpack_binary(binary_block, order)
        score, reasons = _plausibility(fields, size)
        candidates[label] = {"fields": fields, "score": score, "reasons": reasons}

    byte_order = max(candidates, key=lambda k: candidates[k]["score"])
    chosen = candidates[byte_order]
    fields = chosen["fields"]
    if chosen["score"] < 6:
        raise SEGYError(
            "Neither byte order gives a coherent binary header; this does not "
            f"look like SEG-Y (best score {chosen['score']}, format={fields['format']}, "
            f"ns={fields['hns']})."
        )

    order = ">" if byte_order == "big" else "<"
    fmt = fields["format"]
    ns = fields["hns"]
    dt_us = fields["hdt"]
    nextended = max(0, fields["nextended"])
    warnings = []

    bps = BYTES_PER_SAMPLE.get(fmt)
    stride = TRACE_HEADER_BYTES + ns * bps if bps and ns else None
    body = size - TEXT_BYTES - BINARY_BYTES - nextended * TEXT_BYTES
    ntr = None
    if stride and body > 0:
        ntr, remainder = divmod(body, stride)
        if remainder:
            warnings.append(
                f"File size leaves {remainder} trailing bytes; trace length may vary "
                "or extended headers may be miscounted."
            )
    else:
        warnings.append("Cannot estimate the trace count from the binary header.")

    # The first trace header is the independent check on the binary header.
    trace_ns = struct.unpack_from(order + "H", rest_head, TRACE_NS_OFFSET)[0]
    trace_dt = struct.unpack_from(order + "H", rest_head, TRACE_DT_OFFSET)[0]
    if trace_ns != ns:
        warnings.append(
            f"Binary header says ns={ns} but the first trace header says ns={trace_ns}; "
            "segyread needs ns= to be given explicitly."
        )
    if trace_dt != dt_us:
        warnings.append(
            f"Binary header sample interval {dt_us} us differs from the first trace "
            f"header ({trace_dt} us)."
        )

    if fmt not in FORMAT_NAMES:
        warnings.append(f"Sample format code {fmt} is not defined in the SEG-Y standard.")
    elif fmt not in SEGYREAD_NATIVE_FORMATS:
        warnings.append(
            f"segyread does not convert format {fmt} without over=1 and format=."
        )
    if fields["fixed"] == 0 and fields["rev"] in (1, 2):
        warnings.append(
            "The fixed-length trace flag is not set; traces may vary in length."
        )
    if nextended:
        warnings.append(f"{nextended} extended textual header(s) precede the traces.")
    if fields["mfeet"] not in (1, 2):
        warnings.append(
            "The measurement system field is unset; coordinate units must be "
            "confirmed from the trace headers (counit) or from the survey report."
        )
    if dt_us == 0:
        warnings.append("Sample interval is zero in the binary header.")

    text, encoding = _decode_text(text_block)
    if encoding == "unrecognised":
        warnings.append("The 3200-byte textual header is not readable as EBCDIC or ASCII.")

    return {
        "file": path.name,
        "bytes": size,
        "byte_order": byte_order,
        "byte_order_evidence": {k: {"score": v["score"], "reasons": v["reasons"]}
                                for k, v in candidates.items()},
        "revision": fields["rev"] if fields["rev"] in (0, 1, 2) else f"raw={fields['rev']}",
        "sample_format_code": fmt,
        "sample_format": FORMAT_NAMES.get(fmt, "unknown"),
        "bytes_per_sample": bps,
        "ns": ns,
        "dt_us": dt_us,
        "dt_s": dt_us / 1e6 if dt_us else None,
        "record_length_s": ns * dt_us / 1e6 if dt_us and ns else None,
        "fixed_length_flag": bool(fields["fixed"]),
        "n_extended_headers": nextended,
        "traces_estimated": ntr,
        "ensemble_fold_header": fields["fold"],
        "trace_sorting_code": fields["tsort"],
        "measurement_system": {1: "meters", 2: "feet"}.get(fields["mfeet"], "unspecified"),
        "first_trace_header": {"ns": trace_ns, "dt_us": trace_dt},
        "textual_header_encoding": encoding,
        "textual_header": text,
        "segyread_can_convert": fmt in SEGYREAD_NATIVE_FORMATS,
        "warnings": warnings,
    }


def rewrite_byte_order(src, dst) -> dict:
    """Write a copy of a SEG-Y file in the opposite byte order."""
    src, dst = Path(src), Path(dst)
    diag = diagnose(src)
    ns, bps = diag["ns"], diag["bytes_per_sample"]
    if bps is None:
        raise SEGYError(f"Unsupported sample format {diag['sample_format_code']}")
    stride = TRACE_HEADER_BYTES + ns * bps
    skip = TEXT_BYTES + BINARY_BYTES + diag["n_extended_headers"] * TEXT_BYTES

    raw = bytearray(src.read_bytes())
    # binary header: 3 int32 then int16s (SEG-Y rev 0 layout)
    for offset, size, count in ((TEXT_BYTES, 4, 3), (TEXT_BYTES + 12, 2, 194)):
        for i in range(count):
            a = offset + i * size
            raw[a:a + size] = raw[a:a + size][::-1]

    ntr = (len(raw) - skip) // stride
    for t in range(ntr):
        base = skip + t * stride
        for offset, size, count in TRACE_HEADER_LAYOUT:
            for i in range(count):
                a = base + offset + i * size
                raw[a:a + size] = raw[a:a + size][::-1]
        data = base + TRACE_HEADER_BYTES
        for i in range(ns):
            a = data + i * bps
            raw[a:a + bps] = raw[a:a + bps][::-1]
    dst.write_bytes(bytes(raw))
    return {"source": str(src), "output": str(dst),
            "from_byte_order": diag["byte_order"],
            "to_byte_order": "little" if diag["byte_order"] == "big" else "big",
            "traces": ntr}
