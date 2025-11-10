"""Tests for OutputFormatter."""

import json

from rich.progress import Progress

from cli.utils.output import OutputFormatter


def test_output_formatter_json_success(capsys):
    formatter = OutputFormatter(json_mode=True)
    formatter.success("ok", data={"value": 42})

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["data"]["value"] == 42


def test_progress_spinner_behaviour():
    formatter = OutputFormatter(json_mode=False, quiet=False, no_color=True)
    with formatter.progress_spinner("Working...") as progress:
        assert isinstance(progress, Progress)


def test_progress_spinner_noop_in_json_mode():
    formatter = OutputFormatter(json_mode=True)
    with formatter.progress_spinner("Ignored") as progress:
        assert progress is None
