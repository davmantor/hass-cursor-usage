"""Tests for scripts/export_cursor_auth.py — written before implementation (TDD)."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helper: locate and import the script as a module
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).parent.parent / "scripts" / "export_cursor_auth.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_cursor_auth", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def exporter():
    return _load_exporter()


# ---------------------------------------------------------------------------
# Helper: build a minimal Cursor SQLite database
# ---------------------------------------------------------------------------


def make_cursor_db(
    tmp_path: Path,
    *,
    access: str,
    refresh: str,
    include_table: bool = True,
) -> Path:
    db_path = tmp_path / "state.vscdb"
    with sqlite3.connect(db_path) as conn:
        if include_table:
            conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO ItemTable VALUES (?, ?)",
                ("cursorAuth/accessToken", access),
            )
            conn.execute(
                "INSERT INTO ItemTable VALUES (?, ?)",
                ("cursorAuth/refreshToken", refresh),
            )
    return db_path


def make_cursor_db_missing_key(tmp_path: Path) -> Path:
    """DB with ItemTable but only one of the two required keys."""
    db_path = tmp_path / "state_partial.vscdb"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable VALUES (?, ?)",
            ("cursorAuth/accessToken", "only-access"),
        )
    return db_path


def make_cursor_db_no_table(tmp_path: Path) -> Path:
    """Valid SQLite file with no ItemTable."""
    db_path = tmp_path / "state_notable.vscdb"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE Other (x INTEGER)")
    return db_path


# ---------------------------------------------------------------------------
# export_credentials
# ---------------------------------------------------------------------------


def test_export_writes_tokens_without_printing_them(tmp_path, capsys, exporter):
    db = make_cursor_db(tmp_path, access="secret-access", refresh="secret-refresh")
    output = tmp_path / "auth.json"
    exporter.export_credentials(db, output)

    # Correct JSON payload
    assert json.loads(output.read_text()) == {
        "access_token": "secret-access",
        "refresh_token": "secret-refresh",
    }

    # Permissions: owner-read-write only
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    # Tokens must not appear in stdout or stderr
    captured = capsys.readouterr()
    assert "secret-access" not in captured.out + captured.err
    assert "secret-refresh" not in captured.out + captured.err


# ---------------------------------------------------------------------------
# read_credentials
# ---------------------------------------------------------------------------


def test_read_credentials_rejects_missing_table(tmp_path, exporter):
    db = make_cursor_db_no_table(tmp_path)
    with pytest.raises(exporter.ExportError):
        exporter.read_credentials(db)


def test_read_credentials_rejects_missing_key(tmp_path, exporter):
    db = make_cursor_db_missing_key(tmp_path)
    with pytest.raises(exporter.ExportError):
        exporter.read_credentials(db)


# ---------------------------------------------------------------------------
# candidate_database_paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "platform,home,appdata,expected_suffix",
    [
        (
            "win32",
            Path("/home/user"),
            r"C:\Users\user\AppData\Roaming",
            Path(r"C:\Users\user\AppData\Roaming")
            / "Cursor"
            / "User"
            / "globalStorage"
            / "state.vscdb",
        ),
        (
            "darwin",
            Path("/Users/user"),
            None,
            Path("/Users/user")
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "globalStorage"
            / "state.vscdb",
        ),
        (
            "linux",
            Path("/home/user"),
            None,
            Path("/home/user") / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb",
        ),
    ],
)
def test_candidate_database_paths(platform, home, appdata, expected_suffix, exporter):
    paths = exporter.candidate_database_paths(home, platform, appdata)
    assert len(paths) == 1
    assert paths[0] == expected_suffix


def test_candidate_database_paths_win32_no_appdata(exporter):
    paths = exporter.candidate_database_paths(Path("/home/user"), "win32", appdata=None)
    assert paths == []


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_honors_database_and_output(tmp_path):
    db = make_cursor_db(tmp_path, access="cli-access", refresh="cli-refresh")
    output = tmp_path / "cli_out.json"

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--database",
            str(db),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert json.loads(output.read_text()) == {
        "access_token": "cli-access",
        "refresh_token": "cli-refresh",
    }
    # Tokens must not appear in CLI output
    combined = result.stdout + result.stderr
    assert "cli-access" not in combined
    assert "cli-refresh" not in combined
