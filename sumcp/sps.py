"""SPS: the acquisition geometry the survey wrote down next to the tape."""

from __future__ import annotations

import re
from pathlib import Path

SPS_VERSION = "sps-0.3"

__all__ = ["SPS_VERSION", "SPSError", "parse_spec", "read_file",
           "read_set", "FALLBACK_SPECS", "ROLE_PATTERNS"]


class SPSError(ValueError):
    """The file is not a readable SPS set, and says why."""


# A declared field is mapped to a role by the first pattern that matches its name, case-insensitively.
ROLE_PATTERNS = {
    "SR": [
        ("point", r"point\s*number|station\s*number|^point$|^station$"),
        ("point_index", r"point\s*index|station\s*index"),
        ("line", r"line\s*name|line\s*number|^line$"),
        ("x", r"easting|x\s*coord|^x$"),
        ("y", r"northing|y\s*coord|^y$"),
        ("elevation", r"surface\s*elevation|elevation"),
        ("depth", r"point\s*depth|source\s*depth|depth"),
        ("static", r"static"),
        ("code", r"point\s*code|station\s*code"),
    ],
    "X": [
        ("record", r"field\s*record\s*number|record\s*number"),
        ("record_increment", r"field\s*record\s*increment|record\s*increment"),
        ("tape", r"field\s*tape"),
        ("instrument", r"instrument"),
        ("source_line", r"line\s*name|line\s*number|^line$"),
        ("source_point", r"point\s*number|^point$"),
        ("source_index", r"point\s*index"),
        ("from_channel", r"from\s*channel"),
        ("to_channel", r"to\s*channel"),
        ("channel_increment", r"channel\s*increment"),
        ("receiver_line", r"line\s*name|line\s*number|^line$"),
        ("from_receiver", r"from\s*receiver"),
        ("to_receiver", r"to\s*receiver"),
        ("receiver_index", r"receiver\s*index"),
    ],
}

# Published SPS revision 2.1 columns, used only when the file declares none.
FALLBACK_SPECS = {
    "SR": [("code_id", 1, 1), ("line", 2, 17), ("point", 18, 25),
           ("point_index", 26, 26), ("code", 27, 28), ("static", 29, 32),
           ("depth", 33, 36), ("datum", 37, 40), ("uphole", 41, 42),
           ("water_depth", 43, 46), ("x", 47, 55), ("y", 56, 65),
           ("elevation", 66, 71), ("day", 72, 74), ("time", 75, 80)],
    "X": [("code_id", 1, 1), ("tape", 2, 7), ("record", 8, 11),
          ("record_increment", 12, 12), ("instrument", 13, 13),
          ("source_line", 14, 29), ("source_point", 30, 37),
          ("source_index", 38, 38), ("from_channel", 39, 42),
          ("to_channel", 43, 46), ("channel_increment", 47, 47),
          ("receiver_line", 48, 63), ("from_receiver", 64, 71),
          ("to_receiver", 72, 79), ("receiver_index", 80, 80)],
}

_COLS = re.compile(r"(\d+)\s*-\s*(\d+)")


def _role_of(name: str, kind: str, taken: set) -> str | None:
    """First unused role whose pattern matches this declared field name."""
    low = name.strip().lower()
    for role, pattern in ROLE_PATTERNS[kind]:
        if role in taken:
            continue
        if re.search(pattern, low):
            return role
    return None


def parse_spec(lines, kind: str) -> dict:
    """Read the column layout a file declares in its H records."""
    kind = "X" if kind.upper() == "X" else "SR"
    fields, taken, seen = [], set(), 0
    for line in lines:
        if not line[:1].upper() == "H":
            continue
        body = line[3:] if len(line) > 3 else ""
        m = _COLS.search(body)
        if not m:
            continue
        name = body[:m.start()].strip()
        if not name or name.lower().startswith("definition of field"):
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo < 1 or hi < lo or hi > 200:
            continue
        seen += 1
        role = _role_of(name, kind, taken)
        if role is None:
            continue
        taken.add(role)
        fields.append((role, lo, hi, name))
    if fields:
        return {"fields": fields, "source": "declared", "declared_lines": seen}
    return {"fields": [(r, a, b, r) for r, a, b in FALLBACK_SPECS[kind]],
            "source": "fallback", "declared_lines": seen}


def _number(text: str):
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_file(path, kind: str | None = None) -> dict:
    """Read one SPS/RPS/XPS file into records, using its own declared layout."""
    path = Path(path)
    try:
        text = path.read_text(encoding="latin-1")
    except OSError as exc:
        raise SPSError(f"{path.name} could not be read: {exc}") from exc
    lines = text.splitlines()
    data = [l for l in lines if l[:1].upper() in ("S", "R", "X")]
    if not data:
        raise SPSError(f"{path.name} holds no S, R or X record lines.")
    letters = sorted({l[:1].upper() for l in data})
    if len(letters) > 1:
        raise SPSError(f"{path.name} mixes record types {letters}; an SPS file "
                       f"holds one type.")
    letter = letters[0]
    if kind and kind.upper() != letter:
        raise SPSError(f"{path.name} holds {letter} records, not {kind.upper()}.")
    spec = parse_spec(lines, letter)

    records, bad = [], []
    for n, line in enumerate(data, start=1):
        row = {"_line": n}
        for role, lo, hi, _name in spec["fields"]:
            row[role] = line[lo - 1:hi]
        records.append(row)

    out = {"algorithm_version": SPS_VERSION, "path": str(path),
           "record_type": letter, "n_records": len(records),
           "layout": {"source": spec["source"],
                      "header_lines_with_columns": spec["declared_lines"],
                      "fields": [{"role": r, "cols": [a, b], "declared_as": n}
                                 for r, a, b, n in spec["fields"]]},
           "records": records, "warnings": bad}
    return out


def _as_points(read: dict, what: str) -> dict:
    """Turn S or R records into {(line, point): {...}} with numeric coordinates."""
    have = {f["role"] for f in read["layout"]["fields"]}
    missing = [k for k in ("point", "x", "y") if k not in have]
    if missing:
        raise SPSError(
            f"{Path(read['path']).name} declares no column for {', '.join(missing)}. "
            f"A {what} record without a point number and a position cannot place "
            f"anything. Declared: "
            f"{', '.join(f['role'] for f in read['layout']['fields'])}.")
    points, problems = {}, []
    for row in read["records"]:
        pt = _number(row.get("point", ""))
        x = _number(row.get("x", ""))
        y = _number(row.get("y", ""))
        line = (row.get("line") or "").strip()
        if pt is None or x is None or y is None:
            problems.append({"line": row["_line"], "why": "point, easting or "
                             "northing is blank or not a number"})
            continue
        key = (line, int(round(pt)))
        if key in points:
            problems.append({"line": row["_line"],
                             "why": f"point {key[1]} on line '{key[0]}' is "
                                    f"declared more than once"})
            continue
        points[key] = {"x": x, "y": y, "line": line, "point": int(round(pt)),
                       "elevation": _number(row.get("elevation", "")),
                       "static_ms": _number(row.get("static", "")),
                       "depth": _number(row.get("depth", "")),
                       "index": (row.get("point_index") or "").strip()}
    return {"points": points, "problems": problems}


def read_set(s_path, r_path, x_path) -> dict:
    """Read an S/R/X set and return sources, receivers and relations."""
    s = read_file(s_path)
    r = read_file(r_path)
    x = read_file(x_path)
    for got, want, name in ((s["record_type"], "S", "source"),
                            (r["record_type"], "R", "receiver"),
                            (x["record_type"], "X", "relation")):
        if got != want:
            raise SPSError(f"The file given as the {name} file holds "
                           f"{got} records, not {want}.")
    sources = _as_points(s, "source")
    receivers = _as_points(r, "receiver")

    have = {f["role"] for f in x["layout"]["fields"]}
    need = ("record", "source_point", "from_channel", "to_channel",
            "from_receiver", "to_receiver")
    missing = [k for k in need if k not in have]
    if missing:
        raise SPSError(
            f"{Path(x['path']).name} declares no column for {', '.join(missing)}. "
            f"Without a field record, a source point and a channel-to-receiver "
            f"range there is no relation to follow.")

    relations, problems = [], []
    for row in x["records"]:
        rec = _number(row.get("record", ""))
        sp = _number(row.get("source_point", ""))
        c1 = _number(row.get("from_channel", ""))
        c2 = _number(row.get("to_channel", ""))
        r1 = _number(row.get("from_receiver", ""))
        r2 = _number(row.get("to_receiver", ""))
        if None in (rec, sp, c1, c2, r1, r2):
            problems.append({"line": row["_line"],
                             "why": "a required relation field is blank or not "
                                    "a number"})
            continue
        step = _number(row.get("channel_increment", "")) or 1.0
        relations.append({
            "_line": row["_line"],
            "record": int(round(rec)),
            "source_line": (row.get("source_line") or "").strip(),
            "source_point": int(round(sp)),
            "from_channel": int(round(c1)), "to_channel": int(round(c2)),
            "channel_increment": int(round(step)) or 1,
            "receiver_line": (row.get("receiver_line") or "").strip(),
            "from_receiver": int(round(r1)), "to_receiver": int(round(r2)),
        })
    return {
        "algorithm_version": SPS_VERSION,
        "sources": sources["points"], "receivers": receivers["points"],
        "relations": relations,
        "layouts": {"S": s["layout"], "R": r["layout"], "X": x["layout"]},
        "counts": {"S": s["n_records"], "R": r["n_records"], "X": x["n_records"],
                   "sources_usable": len(sources["points"]),
                   "receivers_usable": len(receivers["points"]),
                   "relations_usable": len(relations)},
        "problems": {"S": sources["problems"], "R": receivers["problems"],
                     "X": problems},
        "paths": {"S": str(s_path), "R": str(r_path), "X": str(x_path)},
    }
