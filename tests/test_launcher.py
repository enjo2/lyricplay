from __future__ import annotations

import os
from pathlib import Path

import pytest

from lyricplay.errors import DependencyError
from lyricplay.web import server

ROOT = Path(__file__).resolve().parents[1]


def test_run_script_is_executable() -> None:
    assert os.access(ROOT / "run.sh", os.X_OK)


def test_run_script_starts_the_web_launcher() -> None:
    script = (ROOT / "run.sh").read_text()

    assert 'exec "$PYTHON" -m lyricplay "$@"' in script


def test_launcher_starts_the_web_player(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(server, "serve", lambda **kwargs: calls.append(kwargs))

    assert server.main([]) == 0
    assert calls == [
        {
            "host": None,
            "port": None,
            "open_browser": None,
            "query": "",
        }
    ]


def test_launcher_passes_web_options_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(server, "serve", lambda **kwargs: calls.append(kwargs))

    assert (
        server.main(
            [
                "--host",
                "0.0.0.0",
                "--port",
                "9000",
                "--no-browser",
                "wish",
                "you",
                "were",
                "here",
            ]
        )
        == 0
    )
    assert calls == [
        {
            "host": "0.0.0.0",
            "port": 9000,
            "open_browser": False,
            "query": "wish you were here",
        }
    ]


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_launcher_rejects_invalid_ports(
    port: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        server.main(["--port", port])

    assert exc_info.value.code == 2
    assert "port" in capsys.readouterr().err.lower()


def test_launcher_reports_a_missing_dependency(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(**kwargs: object) -> None:
        raise DependencyError("uvicorn is not installed")

    monkeypatch.setattr(server, "serve", fail)

    assert server.main(["--no-browser"]) == 1
    assert "error: uvicorn is not installed" in capsys.readouterr().err
