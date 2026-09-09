"""Speech synthesis with piper.

Rendering a whole book is measured in hours, so the pool is sized to memory as well as
cores, and every unit of work is skippable: an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


class PiperMissing(RuntimeError):
    pass


def piper_exe() -> str:
    """Find piper: next to this interpreter first, then on PATH."""
    local = Path(sys.executable).parent / "piper"
    if local.exists():
        return str(local)
    found = shutil.which("piper")
    if found:
        return found
    raise PiperMissing("piper not found -- install with: pip install piper-tts")


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found -- required to encode audio")
    return exe


@dataclass
class Job:
    text_path: Path
    out_path: Path
    title: str


def synth_one(job: Job, voice: Path, *, speed: float = 1.0, bitrate: str = "64k") -> float:
    """Render one text file to MP3. Returns duration in seconds."""
    length_scale = 1.0 / speed if speed > 0 else 1.0
    job.out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav = Path(tmp.name)
    try:
        with open(job.text_path, "rb") as fh:
            proc = subprocess.run(
                [
                    piper_exe(),
                    "-m",
                    str(voice),
                    "--length-scale",
                    f"{length_scale:.4f}",
                    "-f",
                    str(wav),
                ],
                stdin=fh,
                capture_output=True,
            )
        if proc.returncode != 0 or not wav.exists() or wav.stat().st_size == 0:
            detail = proc.stderr[-300:].decode(errors="replace")
            raise RuntimeError(f"piper failed on {job.title}: {detail}")
        subprocess.run(
            [
                ffmpeg_exe(),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(wav),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-metadata",
                f"title={job.title}",
                str(job.out_path),
            ],
            check=True,
            capture_output=True,
        )
        return duration(job.out_path)
    finally:
        wav.unlink(missing_ok=True)


def duration(path: Path) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        return 0.0
    out = subprocess.run(
        [exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def render(
    jobs: list[Job], voice: Path, *, workers: int = 2, speed: float = 1.0, on_event=None
) -> dict[Path, float]:
    """Render jobs in parallel, skipping any whose output already exists."""
    results: dict[Path, float] = {}
    pending: list[Job] = []
    for job in jobs:
        if job.out_path.exists() and job.out_path.stat().st_size > 0:
            results[job.out_path] = duration(job.out_path)
            if on_event:
                on_event("skip", job, results[job.out_path])
        else:
            pending.append(job)

    if not pending:
        return results

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(synth_one, j, voice, speed=speed): j for j in pending}
        if on_event:
            for j in pending:
                on_event("start", j, 0.0)
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                secs = fut.result()
                results[job.out_path] = secs
                if on_event:
                    on_event("done", job, secs)
            except Exception as exc:  # keep going; one bad chapter must not kill the run
                if on_event:
                    on_event("fail", job, 0.0)
                results[job.out_path] = 0.0
                print(f"  ! {job.title}: {exc}", file=sys.stderr)
    return results
