# Cursor Usage — Home Assistant Integration

A custom Home Assistant integration that monitors your [Cursor](https://cursor.com) Individual subscription usage.

## Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.cursor_usage_monthly_usage` | Current monthly usage as a percentage of the included request quota |
| `sensor.cursor_usage_monthly_reset_time` | Timestamp when the monthly quota resets |
| `sensor.cursor_usage_api_error` | Error counter — non-zero when the last poll failed |

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS.
2. Restart Home Assistant.
3. Install **Cursor Usage**.
4. Go to **Settings → Devices & Services → Add Integration → Cursor Usage**.
5. Follow the setup prompts.

### Manual

1. Copy `custom_components/hass_cursor_usage/` to your HA `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration via the UI.

## Export Credentials

The integration requires a JSON credentials file containing your Cursor OAuth tokens. Cursor does not provide an official CLI export command for Individual accounts. Use the browser-based extraction method below.

> **Note:** The Individual usage and OAuth endpoints used by this integration are undocumented and unsupported by Cursor. They may change or be removed without notice.

### Browser-based extraction

1. Log in at [cursor.com](https://cursor.com) in a browser where you are already signed in to Cursor.
2. Open DevTools (F12) → **Application** → **Cookies** → `https://cursor.com`.
3. Locate the `access_token` and `refresh_token` cookie or localStorage values.
4. Save them as described in the next section.

## Manual Credentials File

Create the file at `/config/.cursor/auth.json` on your Home Assistant host with the following schema:

```json
{
  "access_token": "<Cursor OAuth access token>",
  "refresh_token": "<Cursor OAuth refresh token>"
}
```

**Security rules:**
- Set file permissions to `600` (readable only by the HA process).
- Never commit this file to version control. Add it to `.gitignore`.
- Do not paste token values into issue reports or logs.

The integration reads this file on every poll and automatically refreshes an expired `access_token` using the stored `refresh_token`. If the `refresh_token` is revoked, recreate the file with fresh tokens.

## Copy to Home Assistant

If Home Assistant runs in Docker or Home Assistant OS it cannot read the host filesystem directly. Copy the credentials file once:

```bash
#!/bin/bash
SOURCE="$HOME/.cursor/auth.json"   # adjust if needed
DEST="/config/.cursor/auth.json"

mkdir -p "$(dirname "$DEST")"
cp "$SOURCE" "$DEST"
chmod 600 "$DEST"
```

Re-run this script after re-authenticating to Cursor.

## Setup

1. Go to **Settings → Devices & Services → Add Integration → Cursor Usage**.
2. When prompted for the **Auth File Path**, enter:
   ```
   /config/.cursor/auth.json
   ```
3. Accept the default poll interval or choose a custom value (see Options).

The integration reads the credentials file on every poll. It does not persist your access token in the Home Assistant configuration database.

## Options

| Option | Default | Min | Max | Description |
|--------|---------|-----|-----|-------------|
| Update interval | 300 s | 300 s | 3600 s | How often to poll the Cursor usage API |

The minimum interval is **five minutes (300 seconds)**. Polling more frequently is not supported and risks rate-limiting or account suspension.

## Dashboard

A pre-built dashboard YAML is provided in `dashboards/cursor_usage.yaml`. To use it:

1. Go to **Settings → Dashboards → Add Dashboard**.
2. Open the three-dot menu → **Edit Dashboard**.
3. Open the three-dot menu again → **Raw configuration editor**.
4. Paste the contents of `dashboards/cursor_usage.yaml`.
5. Click **Save**.

You can also add the individual cards to any existing dashboard.

## Authentication Recovery

If the `refresh_token` expires or is revoked, the `sensor.cursor_usage_api_error` sensor will become non-zero and the other sensors will stop updating. To recover:

1. Extract fresh tokens from the Cursor browser session (see [Export Credentials](#export-credentials)).
2. Replace `/config/.cursor/auth.json` with the new values.
3. Wait for the next poll or reload the integration from **Settings → Devices & Services → Cursor Usage → Reload**.

## Unsupported API Notice

The Cursor Individual usage endpoint (`https://cursor.com/api/usage-summary`) and the OAuth token refresh endpoint (`https://api2.cursor.sh/oauth/token`) are **not documented public APIs**. Cursor may change their behavior, require additional authentication, or remove them at any time without notice. This integration is provided as-is with no warranty of continued function.

## Development

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

Runs black, isort, ruff, and other checks before each commit.

### Manual formatting

```bash
pip install black isort ruff
black custom_components/hass_cursor_usage/
isort custom_components/hass_cursor_usage/
ruff check --fix custom_components/hass_cursor_usage/
```

### Running tests

```bash
pip install -e ".[test]"
pytest tests/
```

## Credits

This integration is derived from [hass-claude-usage](https://github.com/trickv/hass-claude-usage) by [Patrick van Staveren](https://github.com/trickv), which was itself adapted from the Cursor usage API. The branching lineage is: hass-claude-usage → hass-codex-usage → hass-cursor-usage.

## License

MIT License — see [LICENSE](LICENSE) for details.
