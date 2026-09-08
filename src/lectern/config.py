"""Configuration: where the library lives, which voice to use, which AI provider.

The library defaults to the external drive because the system disk is chronically
short of space, and audio is large. The drive is removable, so every consumer must
tolerate ``library_root`` being absent -- see :func:`require_library`.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("LECTERN_CONFIG", Path.home() / ".config/lectern/config.toml"))

# Default to the XDG data directory. Audio is large, so a machine with a roomier
# volume should point `library.root` at it in config.toml (or set LECTERN_LIBRARY).
_XDG = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
_DEFAULT_ROOT = _XDG / "lectern/library"

DEFAULT_VOICE_DIR = Path.home() / ".local/share/piper-voices"
DEFAULT_VOICE = "en_US-lessac-medium"


class LibraryUnavailable(RuntimeError):
    """The library root is not reachable -- typically the external drive is unmounted."""


@dataclass
class Config:
    library_root: Path
    inbox: Path
    voice_dir: Path
    voice: str
    workers: int
    ai: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.library_root / "library.db"

    def available(self) -> bool:
        """True when the library root exists or can be created."""
        try:
            self.library_root.mkdir(parents=True, exist_ok=True)
            return os.access(self.library_root, os.W_OK)
        except OSError:
            return False

    def free_bytes(self) -> int:
        target = self.library_root
        while not target.exists() and target != target.parent:
            target = target.parent
        return shutil.disk_usage(target).free


def _default_library_root() -> Path:
    return _DEFAULT_ROOT


def _default_workers() -> int:
    """Pick a worker count that respects both cores and free memory.

    Each piper process costs roughly 1 GB resident; oversubscribing memory on a
    machine that is already tight is worse than finishing slowly.
    """
    cores = os.cpu_count() or 2
    by_cores = max(1, min(4, cores - 1))
    try:
        with open("/proc/meminfo") as fh:
            avail_kb = next(
                int(line.split()[1]) for line in fh if line.startswith("MemAvailable")
            )
        by_mem = max(1, avail_kb // (1024 * 1024))  # ~1 GB per worker
    except (OSError, StopIteration, ValueError):
        by_mem = by_cores
    return max(1, min(by_cores, by_mem))


def load(path: Path | None = None) -> Config:
    path = Path(path) if path else CONFIG_PATH
    raw: dict = {}
    if path.is_file():
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)

    lib = raw.get("library", {})
    tts = raw.get("tts", {})
    root = Path(os.environ.get("LECTERN_LIBRARY", lib.get("root") or _default_library_root()))

    return Config(
        library_root=root.expanduser(),
        inbox=Path(lib.get("inbox", Path.home() / "Lectern Inbox")).expanduser(),
        voice_dir=Path(tts.get("voice_dir", DEFAULT_VOICE_DIR)).expanduser(),
        voice=tts.get("voice", DEFAULT_VOICE),
        workers=int(tts.get("workers") or _default_workers()),
        ai=raw.get("ai", {"default": "claude", "providers": {"claude": {"kind": "cli"}}}),
    )


def require_library(cfg: Config) -> None:
    if not cfg.available():
        raise LibraryUnavailable(
            f"library root {cfg.library_root} is not writable.\n"
            "If it lives on the external drive, mount the drive and retry; "
            "or set LECTERN_LIBRARY to another location."
        )


def voice_path(cfg: Config, voice: str | None = None) -> Path:
    name = voice or cfg.voice
    p = Path(name)
    if not p.is_absolute():
        p = cfg.voice_dir / name
    if p.suffix != ".onnx":
        p = p.with_suffix(".onnx")
    return p
