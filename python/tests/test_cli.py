"""Tests for continuityguard.cli. Ported from src/cli.test.ts."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from continuityguard import cli as cli_module
from continuityguard.ingest.ffmpeg import FfmpegCheckResult
from continuityguard.scan import TOOL_VERSION

from .conftest import FIXTURE_DIR, requires_ffmpeg


def test_build_parser_registers_the_scan_subcommand_with_json_fps_out_options():
    parser = cli_module.build_parser()
    assert parser.prog == "continuityguard"
    args = parser.parse_args(["scan", "some-dir", "--json", "--fps", "1.5", "--out", "x.json"])
    assert args.directory == "some-dir"
    assert args.json is True
    assert args.fps == 1.5
    assert args.out == "x.json"


def test_reports_the_tool_version():
    assert TOOL_VERSION == "0.1.0"


def test_returns_exit_code_1_with_the_install_command_when_ffmpeg_is_not_on_path(capsys):
    with mock.patch.object(
        cli_module, "check_ffmpeg_available", return_value=FfmpegCheckResult(available=False)
    ):
        code = cli_module.run_scan("some-dir", out="./report.json")
    assert code == 1
    captured = capsys.readouterr()
    assert "ffmpeg" in captured.err


@requires_ffmpeg
def test_returns_exit_code_1_and_an_actionable_message_when_no_clips_are_found(capsys):
    with tempfile.TemporaryDirectory() as empty_dir:
        code = cli_module.run_scan(empty_dir, out="./continuityguard-report.json")
        assert code == 1
        captured = capsys.readouterr()
        assert "No supported video clips found" in captured.err


@requires_ffmpeg
def test_returns_exit_code_1_with_directory_not_found_for_a_nonexistent_path(capsys):
    missing_dir = str(Path(tempfile.gettempdir()) / "cg-does-not-exist-py-test")
    code = cli_module.run_scan(missing_dir, out="./continuityguard-report.json")
    assert code == 1
    captured = capsys.readouterr()
    assert "Directory not found" in captured.err
    assert "No supported video clips found" not in captured.err


@requires_ffmpeg
def test_returns_exit_code_1_with_not_a_directory_when_the_path_is_a_file(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "a-file-not-a-directory.txt"
        file_path.write_text("not a directory")
        code = cli_module.run_scan(str(file_path), out="./continuityguard-report.json")
        assert code == 1
        captured = capsys.readouterr()
        assert "Not a directory" in captured.err


@requires_ffmpeg
def test_scans_the_real_committed_fixtures_end_to_end_and_writes_a_json_report(capsys):
    with tempfile.TemporaryDirectory() as out_dir:
        out_path = Path(out_dir) / "continuityguard-report.json"
        code = cli_module.run_scan(str(FIXTURE_DIR), out=str(out_path))
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out != ""

        written = json.loads(out_path.read_text())
        assert written["clips_scanned"] == 8
        assert written["network_calls_made"] == 0
        assert any(
            f["clip"] == "kenji_shot02.mp4"
            for f in written["character_consistency"]["flagged_shots"]
        )
        assert any(
            f["clip"] == "action-discontinuity.mp4"
            for f in written["physics_plausibility"]["flagged_shots"]
        )


@requires_ffmpeg
def test_prints_the_full_json_report_to_stdout_when_json_is_set_without_writing_a_file(capsys):
    code = cli_module.run_scan(
        str(FIXTURE_DIR), json_output=True, out="./should-not-be-written.json"
    )
    assert code == 0
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed["clips_scanned"] == 8
    assert not Path("./should-not-be-written.json").exists()


@requires_ffmpeg
def test_returns_exit_code_1_with_a_clean_error_message_when_a_clip_is_corrupt(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        corrupt_path = Path(tmp) / "corrupt.mp4"
        corrupt_path.write_text("this is not a real video file")
        code = cli_module.run_scan(tmp, out=str(Path(tmp) / "report.json"))
        assert code == 1
        captured = capsys.readouterr()
        assert "ContinuityGuard scan failed" in captured.err
        assert "corrupt.mp4" in captured.err


@requires_ffmpeg
def test_passes_a_custom_fps_value_through_to_frame_extraction(capsys):
    with tempfile.TemporaryDirectory() as out_dir:
        out_path = Path(out_dir) / "report.json"
        code = cli_module.run_scan(str(FIXTURE_DIR), out=str(out_path), fps=1)
        assert code == 0
        written = json.loads(out_path.read_text())
        assert written["frames_extracted"] > 0
