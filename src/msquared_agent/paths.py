from pathlib import Path
import os
import sys


def source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_root() -> Path:
    """Return the writable portable app root."""
    override = os.environ.get("MSQUARED_AGENT_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root()


def bundled_root() -> Path:
    """Return the root for bundled read-only resources."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return source_root()


def resource_path(*parts: str) -> Path:
    """Resolve a resource from the portable root, falling back to bundled data."""
    portable_path = app_root().joinpath(*parts)
    if portable_path.exists():
        return portable_path
    return bundled_root().joinpath(*parts)


def writable_path(*parts: str) -> Path:
    """Resolve a path that runtime code may create or modify."""
    path = app_root().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
