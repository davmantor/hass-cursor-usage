#!/usr/bin/env python3
"""Cross-platform Cursor credential exporter.

Reads the access and refresh tokens from Cursor's local SQLite database
(state.vscdb) and writes them to a JSON file with mode 0o600.

Usage
-----
    python scripts/export_cursor_auth.py --output /path/to/auth.json
    python scripts/export_cursor_auth.py --database /explicit/path/state.vscdb \
        --output /path/to/auth.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

ACCESS_KEY = "cursorAuth/accessToken"
REFRESH_KEY = "cursorAuth/refreshToken"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExportError(Exception):
    """Raised when credentials cannot be exported."""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def candidate_database_paths(
    home: Path,
    platform: str,
    appdata: str | None = None,
) -> list[Path]:
    """Return the standard Cursor database path(s) for *platform*.

    Parameters
    ----------
    home:
        The user's home directory.
    platform:
        A ``sys.platform``-style string: ``"win32"``, ``"darwin"``, or any
        other value (treated as Linux/freedesktop).
    appdata:
        The ``%APPDATA%`` value on Windows.  Ignored on other platforms.
    """
    if platform == "win32":
        if not appdata:
            return []
        return [Path(appdata) / "Cursor" / "User" / "globalStorage" / "state.vscdb"]
    if platform == "darwin":
        return [
            home
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "globalStorage"
            / "state.vscdb"
        ]
    # Linux / other freedesktop systems
    return [home / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"]


def read_credentials(database: Path) -> tuple[str, str]:
    """Read access and refresh tokens from *database*.

    Opens the database read-only via the SQLite URI API.

    Returns
    -------
    tuple[str, str]
        ``(access_token, refresh_token)``

    Raises
    ------
    ExportError
        If the database cannot be read, ``ItemTable`` is missing, or either
        credential key is absent.
    """
    uri = f"file:{database.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            try:
                rows = dict(
                    conn.execute(
                        "SELECT key, value FROM ItemTable WHERE key IN (?, ?)",
                        (ACCESS_KEY, REFRESH_KEY),
                    )
                )
            except sqlite3.OperationalError as exc:
                raise ExportError(f"Cannot query Cursor database ({database}): {exc}") from exc
    except sqlite3.OperationalError as exc:
        raise ExportError(f"Cannot open Cursor database ({database}): {exc}") from exc

    access = rows.get(ACCESS_KEY)
    refresh = rows.get(REFRESH_KEY)
    if not access or not refresh:
        raise ExportError(
            "Cursor database does not contain both required credentials "
            f"(found: {list(rows.keys())})"
        )
    return access, refresh


def export_credentials(database: Path, output: Path) -> None:
    """Export Cursor credentials from *database* to *output* (JSON, mode 0o600).

    The write is atomic: the payload is written to a temporary file in the
    same directory, permissions are set, and the file is renamed into place.

    Prints only the source database path and the destination path — never
    the token values themselves.
    """
    print(f"Reading credentials from: {database}")

    access, refresh = read_credentials(database)

    payload = json.dumps({"access_token": access, "refresh_token": refresh}, indent=2)

    output.parent.mkdir(parents=True, exist_ok=True)

    # Write atomically: temp file in same directory → rename
    fd, tmp_name = tempfile.mkstemp(dir=output.parent, prefix=".export_cursor_auth_")
    try:
        tmp_path = Path(tmp_name)
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(payload)
        tmp_path.replace(output)
    except Exception:
        # Clean up the temp file on failure
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise

    print(f"Credentials written to:  {output}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _find_database() -> Path:
    """Locate the first existing Cursor database on the current platform."""
    home = Path.home()
    appdata = os.environ.get("APPDATA")
    candidates = candidate_database_paths(home, sys.platform, appdata)
    for path in candidates:
        if path.exists():
            return path
    searched = "\n  ".join(str(p) for p in candidates) or "(none)"
    raise ExportError(
        f"No Cursor database found.  Searched:\n  {searched}\n"
        "Use --database to specify the path explicitly."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="export_cursor_auth",
        description=("Export Cursor access/refresh tokens to a JSON file (mode 0o600)."),
    )
    parser.add_argument(
        "--database",
        metavar="PATH",
        type=Path,
        default=None,
        help=(
            "Path to Cursor's state.vscdb SQLite file.  "
            "Defaults to the standard location for the current platform."
        ),
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        type=Path,
        required=True,
        help="Destination JSON file for the exported credentials.",
    )
    args = parser.parse_args(argv)

    try:
        database = args.database if args.database is not None else _find_database()
        export_credentials(database, args.output)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
