"""Path confinement."""

from __future__ import annotations

from pathlib import Path

from . import config

__all__ = ["PathPolicyError", "safe_input_path", "safe_output_path", "as_rel"]


class PathPolicyError(ValueError):
    """Raised when a requested path leaves the project sandbox."""


def _contained(path: Path, roots) -> bool:
    return any(path == r or path.is_relative_to(r) for r in roots)


def _describe(roots) -> str:
    return ", ".join(r.name + "/" for r in roots)


def _resolve(name: str) -> Path:
    """Resolve an agent-supplied path."""
    if not name or not str(name).strip():
        raise PathPolicyError("Empty path.")
    candidate = Path(name)
    if candidate.is_absolute():
        # Absolute paths are accepted only if they land inside the project; this keeps "/home/me/su-mcp/raw/x.su"
        # working without opening /etc.
        return candidate.resolve()
    head = candidate.parts[0] if candidate.parts else ""
    base = config.DIR_ALIASES.get(head)
    if base is not None:
        return (base.joinpath(*candidate.parts[1:])).resolve()
    return (config.ROOT / candidate).resolve()


def safe_input_path(name: str) -> Path:
    """Resolve a readable path inside raw/, work/, results/ or qc/."""
    path = _resolve(name)
    roots = [d.resolve() for d in config.READABLE_DIRS]
    if not _contained(path, roots):
        raise PathPolicyError(
            f"Input path is outside the project ({_describe(config.READABLE_DIRS)}): {name}"
        )
    return path


def safe_output_path(name: str, *, overwrite: bool = False) -> Path:
    """Resolve a writable path inside work/, results/ or qc/."""
    path = _resolve(name)
    roots = [d.resolve() for d in config.WRITABLE_DIRS]
    if not _contained(path, roots):
        raise PathPolicyError(
            f"Output path is not writable ({_describe(config.WRITABLE_DIRS)}): {name}"
        )
    if path.is_dir():
        raise PathPolicyError(f"Output path is a directory: {name}")
    if path.exists() and not overwrite:
        raise PathPolicyError(
            f"Output already exists: {as_rel(path)} (pass overwrite=true to replace it)"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def as_rel(path: Path) -> str:
    """The name the agent uses, for logs and tool output."""
    resolved = Path(path).resolve()
    for alias, base in config.DIR_ALIASES.items():
        try:
            return str(Path(alias) / resolved.relative_to(base.resolve()))
        except ValueError:
            continue
    try:
        return str(resolved.relative_to(config.ROOT))
    except ValueError:
        return str(resolved)
