"""Assemble rendered chapters into a single M4B audiobook with chapter markers.

Separate MP3s play anywhere, but only a chaptered M4B gives what "navigate smoothly"
actually means: one file that remembers your position and lets you jump by chapter.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..tts import duration, ffmpeg_exe


@dataclass
class Track:
    path: Path
    title: str
    seconds: float


def _ffmetadata(tracks: list[Track], *, title: str, author: str) -> str:
    lines = [";FFMETADATA1", f"title={title}", f"album={title}"]
    if author:
        lines += [f"artist={author}", f"album_artist={author}"]
    lines.append("genre=Audiobook")
    start_ms = 0
    for tr in tracks:
        end_ms = start_ms + int(tr.seconds * 1000)
        lines += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            # '=' and newlines are the delimiters ffmetadata cares about.
            "title=" + tr.title.replace("=", "-").replace("\n", " "),
        ]
        start_ms = end_ms
    return "\n".join(lines) + "\n"


def build_m4b(tracks: list[Track], out_path: Path, *, title: str, author: str = "",
              bitrate: str = "64k", cover: Path | None = None) -> Path:
    tracks = [t for t in tracks if t.path.exists() and t.path.stat().st_size > 0]
    if not tracks:
        raise RuntimeError("no rendered audio to assemble")
    for tr in tracks:
        if tr.seconds <= 0:
            tr.seconds = duration(tr.path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        listing = tmp / "concat.txt"
        listing.write_text(
            "".join(f"file '{t.path.as_posix()}'\n" for t in tracks), encoding="utf-8"
        )
        meta = tmp / "meta.txt"
        meta.write_text(_ffmetadata(tracks, title=title, author=author), encoding="utf-8")

        cmd = [
            ffmpeg_exe(), "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-i", str(meta),
            "-map_metadata", "1",
            "-c:a", "aac", "-b:a", bitrate,
            "-movflags", "+faststart",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"m4b assembly failed: {proc.stderr[-500:]}")
    return out_path


def read_chapters(m4b: Path) -> list[tuple[float, str]]:
    """Read back embedded chapter markers -- used to verify what we wrote."""
    exe = shutil.which("ffprobe")
    if not exe:
        return []
    import json

    out = subprocess.run(
        [exe, "-v", "error", "-print_format", "json", "-show_chapters", str(m4b)],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []
    return [
        (float(c.get("start_time", 0)), c.get("tags", {}).get("title", ""))
        for c in data.get("chapters", [])
    ]
