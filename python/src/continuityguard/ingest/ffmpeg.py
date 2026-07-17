"""
CG01 -- clip/frame ingestion.

ContinuityGuard depends on a system `ffmpeg` install rather than bundling a
static per-platform binary. A static ffmpeg build is materially larger than
this package's own dependency footprint (commonly 50-80MB+ per platform
depending on included codecs) and ffmpeg's licensing terms shift between
LGPL and GPL depending on which codecs/filters are compiled in -- a real
legal-review cost this project is not taking on. ffmpeg is a near-ubiquitous
developer tool already (commonly pre-installed, or one `brew install
ffmpeg` / `apt install ffmpeg` away), so this keeps the package small and
its own licensing surface simple: ContinuityGuard's code never
redistributes ffmpeg binaries or inherits their licensing obligations.

Security note: every ffmpeg invocation in this module passes an explicit
argument list to `subprocess` (never `shell=True`, never string
concatenation into a shell command). Clip paths and directory paths --
values that can originate from untrusted caller input -- are passed as
individual argv elements, so shell metacharacters in a filename (spaces,
`;`, `$()`, backticks, etc.) are never interpreted by a shell; they reach
ffmpeg as literal argument bytes, exactly as Python's subprocess module
guarantees for a list-form command with no shell.

Ported from src/ingest/ffmpeg.ts.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Frame sample rate used for CG01 decode -- 2.3 fps, matching the plan's
# "roughly 2-3 fps sample rate is fine" guidance for shot-level QA sampling.
DEFAULT_SAMPLE_FPS = 2.3

# Frames are decoded to headerless raw RGB24 at a fixed square size rather
# than PNG. This is a deliberate simplification: it lets both scoring
# modules (consistency.py, physics.py) read a frame as a fixed-length byte
# buffer with zero image-decoding dependency, instead of pulling in a PNG
# parser just to get back to raw pixels a moment later. The fixed 224x224
# size also matches the embedding model's expected input dimensions (see
# continuityguard/score/consistency.py), so one decode pass serves both
# scoring paths.
FRAME_SIZE = 224
FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3

_SUPPORTED_CLIP_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


@dataclass(frozen=True)
class FfmpegCheckResult:
    available: bool
    version: Optional[str] = None


def check_ffmpeg_available() -> FfmpegCheckResult:
    """Checks whether `ffmpeg` is reachable on PATH. Never raises -- callers
    use the boolean result to decide whether to continue or print an
    install command and exit."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        return FfmpegCheckResult(available=False)
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return FfmpegCheckResult(available=False)
    if result.returncode != 0:
        return FfmpegCheckResult(available=False)
    first_line = result.stdout.split("\n", 1)[0] if result.stdout else ""
    version = None
    prefix = "ffmpeg version "
    if first_line.startswith(prefix):
        version = first_line[len(prefix) :].split(" ", 1)[0]
    return FfmpegCheckResult(available=True, version=version)


def detect_os(platform: Optional[str] = None) -> str:
    import sys

    plat = platform or sys.platform
    if plat == "darwin":
        return "macos"
    if plat == "win32":
        return "windows"
    if plat.startswith("linux"):
        if shutil.which("apt-get"):
            return "debian"
        if shutil.which("dnf") or shutil.which("yum"):
            return "redhat"
        return "debian"
    return "unknown"


def describe_ffmpeg_install_command(os_name: Optional[str] = None) -> str:
    """Returns the exact, copy-pasteable install command for the detected OS."""
    os_name = os_name or detect_os()
    if os_name == "macos":
        return "brew install ffmpeg"
    if os_name == "debian":
        return "sudo apt update && sudo apt install -y ffmpeg"
    if os_name == "redhat":
        return "sudo dnf install -y ffmpeg"
    if os_name == "windows":
        return "winget install ffmpeg (or: choco install ffmpeg)"
    return "install ffmpeg via your OS package manager, or see https://ffmpeg.org/download.html"


def build_missing_ffmpeg_message(os_name: Optional[str] = None) -> str:
    return "\n".join(
        [
            "ContinuityGuard requires ffmpeg, and it was not found on PATH.",
            f"Install it with:  {describe_ffmpeg_install_command(os_name)}",
            "Then re-run your scan. ContinuityGuard never bundles ffmpeg itself --",
            'see README "Requirements" for why.',
        ]
    )


@dataclass(frozen=True)
class ClipInfo:
    path: str
    name: str


def list_clips(directory: str) -> List[ClipInfo]:
    """Lists clip files (by extension) directly inside a directory, sorted
    for deterministic scan ordering. Does not recurse into subdirectories."""
    directory_path = Path(directory)
    if not directory_path.exists():
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{directory}'")
    if not directory_path.is_dir():
        raise NotADirectoryError(f"[Errno 20] Not a directory: '{directory}'")
    entries = [
        entry
        for entry in directory_path.iterdir()
        if entry.is_file() and entry.suffix.lower() in _SUPPORTED_CLIP_EXTENSIONS
    ]
    entries.sort(key=lambda entry: entry.name)
    return [ClipInfo(path=str(entry), name=entry.name) for entry in entries]


@dataclass
class ExtractedFrames:
    clip: ClipInfo
    frame_dir: str
    # Paths to headerless raw RGB24 frame files, FRAME_SIZE x FRAME_SIZE, in
    # temporal order. Read with `read_raw_frame`.
    frame_paths: List[str] = field(default_factory=list)


def extract_frames(
    clip: ClipInfo, fps: Optional[float] = None, work_dir: Optional[str] = None
) -> ExtractedFrames:
    """
    Decodes a single clip into sampled raw RGB24 frames via ffmpeg, at
    DEFAULT_SAMPLE_FPS unless overridden. Frames are written to a fresh
    temp directory the caller is responsible for cleaning up (or use
    `extract_frames_from_directory`, which cleans up automatically).

    If ffmpeg fails (a corrupt file, an unsupported codec, a zero-byte
    file, etc.) and this call created its own temp directory (no
    `work_dir` override was passed in), that now-orphaned temp directory
    is removed before the error is re-raised, rather than left behind on
    disk.
    """
    fps = DEFAULT_SAMPLE_FPS if fps is None else fps
    owns_frame_dir = work_dir is None
    frame_dir = work_dir or tempfile.mkdtemp(prefix="continuityguard-frames-")

    try:
        _run_ffmpeg(
            [
                "-y",
                "-i",
                clip.path,
                "-vf",
                f"fps={fps},scale={FRAME_SIZE}:{FRAME_SIZE}",
                "-c:v",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-f",
                "image2",
                "-loglevel",
                "error",
                str(Path(frame_dir) / "frame_%04d.rgb"),
            ]
        )

        frame_paths = sorted(
            str(entry)
            for entry in Path(frame_dir).iterdir()
            if entry.name.startswith("frame_") and entry.name.endswith(".rgb")
        )
        return ExtractedFrames(clip=clip, frame_dir=frame_dir, frame_paths=frame_paths)
    except Exception:
        if owns_frame_dir:
            shutil.rmtree(frame_dir, ignore_errors=True)
        raise


def extract_frames_from_directory(
    directory: str, fps: Optional[float] = None
) -> List[ExtractedFrames]:
    """
    Decodes every clip in a directory into sampled frames. Returns one
    ExtractedFrames entry per clip. Callers should call `cleanup_frames`
    when done to remove the temp directories.

    If ffmpeg fails to decode any single clip (a corrupt file, an
    unsupported codec, a zero-byte file, etc.), this raises a clear error
    naming the offending clip, and first cleans up the temp frame
    directories already created for clips that decoded successfully
    earlier in the loop, so one bad clip in a batch never leaks temp
    storage.
    """
    clips = list_clips(directory)
    results: List[ExtractedFrames] = []
    for clip in clips:
        try:
            results.append(extract_frames(clip, fps=fps))
        except Exception as error:
            cleanup_frames(results)
            raise RuntimeError(f'Failed to decode "{clip.name}" with ffmpeg: {error}') from error
    return results


def read_raw_frame(frame_path: str) -> bytes:
    """Reads a headerless raw RGB24 frame file back into a bytes object of
    length FRAME_BYTES (FRAME_SIZE * FRAME_SIZE * 3, row-major, RGB)."""
    data = Path(frame_path).read_bytes()
    if len(data) != FRAME_BYTES:
        raise ValueError(
            f"Unexpected frame size for {frame_path}: got {len(data)} bytes, "
            f"expected {FRAME_BYTES}"
        )
    return data


def cleanup_frames(extracted: List[ExtractedFrames]) -> None:
    for entry in extracted:
        shutil.rmtree(entry.frame_dir, ignore_errors=True)


def _run_ffmpeg(args: List[str]) -> None:
    """Runs ffmpeg with an explicit argument list -- never a shell string --
    so no filename or path, however untrusted, is ever interpreted as shell
    syntax. Raises RuntimeError with ffmpeg's stderr on a non-zero exit."""
    result = subprocess.run(
        ["ffmpeg", *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"ffmpeg exited with code {result.returncode}: {stderr}")
