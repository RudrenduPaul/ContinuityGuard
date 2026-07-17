"""Tests for continuityguard.ingest.ffmpeg. Ported from src/ingest/ffmpeg.test.ts."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from continuityguard.ingest.ffmpeg import (
    FRAME_BYTES,
    ClipInfo,
    check_ffmpeg_available,
    cleanup_frames,
    describe_ffmpeg_install_command,
    detect_os,
    extract_frames,
    extract_frames_from_directory,
    list_clips,
    read_raw_frame,
)

from .conftest import FIXTURE_DIR, requires_ffmpeg


def test_check_ffmpeg_available_reports_a_version_when_present():
    result = check_ffmpeg_available()
    if result.available:
        assert result.version is not None


def test_detect_os_recognizes_darwin():
    assert detect_os("darwin") == "macos"


def test_detect_os_recognizes_win32():
    assert detect_os("win32") == "windows"


def test_detect_os_falls_back_to_unknown_for_an_unrecognized_platform():
    assert detect_os("plan9") == "unknown"


def test_describe_ffmpeg_install_command_macos():
    assert describe_ffmpeg_install_command("macos") == "brew install ffmpeg"


def test_describe_ffmpeg_install_command_unknown_mentions_download_page():
    assert "ffmpeg.org" in describe_ffmpeg_install_command("unknown")


def test_list_clips_filters_by_supported_extension_and_sorts():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name in ["b.mp4", "a.mov", "ignore.txt", "c.MKV"]:
            (tmp_path / name).write_bytes(b"")
        clips = list_clips(str(tmp_path))
        assert [c.name for c in clips] == ["a.mov", "b.mp4", "c.MKV"]


def test_list_clips_raises_file_not_found_for_a_missing_directory():
    with pytest.raises(FileNotFoundError):
        list_clips("/nonexistent/path/does-not-exist-xyz")


def test_list_clips_raises_not_a_directory_for_a_file_path():
    with tempfile.TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "a-file.txt"
        file_path.write_text("not a directory")
        with pytest.raises(NotADirectoryError):
            list_clips(str(file_path))


def test_read_raw_frame_rejects_wrong_sized_files():
    with tempfile.TemporaryDirectory() as tmp:
        bad_path = Path(tmp) / "bad.rgb"
        bad_path.write_bytes(b"\x00" * 10)
        with pytest.raises(ValueError, match="Unexpected frame size"):
            read_raw_frame(str(bad_path))


def test_read_raw_frame_accepts_a_correctly_sized_file():
    with tempfile.TemporaryDirectory() as tmp:
        good_path = Path(tmp) / "good.rgb"
        good_path.write_bytes(b"\x7f" * FRAME_BYTES)
        data = read_raw_frame(str(good_path))
        assert len(data) == FRAME_BYTES


@requires_ffmpeg
class TestExtractFramesRealFixtures:
    def test_extracts_frames_from_a_real_committed_fixture(self):
        clip = ClipInfo(path=str(FIXTURE_DIR / "mei_shot01.mp4"), name="mei_shot01.mp4")
        extracted = extract_frames(clip)
        try:
            assert len(extracted.frame_paths) > 0
            frame = read_raw_frame(extracted.frame_paths[0])
            assert len(frame) == FRAME_BYTES
        finally:
            cleanup_frames([extracted])

    def test_extract_frames_from_directory_decodes_every_clip_in_order(self):
        extracted = extract_frames_from_directory(str(FIXTURE_DIR))
        try:
            names = [e.clip.name for e in extracted]
            assert names == sorted(names)
            assert len(extracted) == 8
            assert all(len(e.frame_paths) > 0 for e in extracted)
        finally:
            cleanup_frames(extracted)

    def test_extract_frames_raises_a_clear_error_for_a_corrupt_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            corrupt_path = Path(tmp) / "corrupt.mp4"
            corrupt_path.write_text("this is not a real video file")
            clip = ClipInfo(path=str(corrupt_path), name="corrupt.mp4")
            with pytest.raises(Exception):
                extract_frames(clip)

    def test_extract_frames_from_directory_cleans_up_earlier_successes_on_a_later_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # A real, decodable clip that sorts before the corrupt one.
            good_bytes = (FIXTURE_DIR / "mei_shot01.mp4").read_bytes()
            (tmp_path / "a_good.mp4").write_bytes(good_bytes)
            (tmp_path / "z_corrupt.mp4").write_text("not a real video file")

            with pytest.raises(RuntimeError, match="z_corrupt.mp4"):
                extract_frames_from_directory(str(tmp_path))
