# Home Assistant Cursor Usage Integration Design

## Objective

Create a separate `hass-cursor-usage` repository derived from `hass-codex-usage` that monitors the monthly included usage of one Cursor Individual account in Home Assistant. The first version targets Individual accounts, including student plans, and deliberately exposes only monthly utilization, the billing-cycle reset time, and integration health.

Cursor does not document an Individual-account usage API. This integration will use Cursor's current private OAuth and dashboard endpoints. The README must state that these endpoints can change without notice.

## Repository and Integration Identity

- Repository name: `hass-cursor-usage`
- Home Assistant domain: `hass_cursor_usage`
- Display name: `Cursor Usage`
- Initial version: `1.0.0`
- Default branch: `main`
- Integration class: cloud polling
- Supported account count: one Cursor Individual account per Home Assistant instance

The derived repository will retain the HACS-compatible structure, config flow, options flow, dashboard example, tests, validation workflows, and branding assets. All Codex-specific names, paths, entity IDs, URLs, documentation, and artwork will be replaced with Cursor equivalents.

## Architecture

The integration consists of five bounded components:

1. A config flow that validates a Cursor credentials file and creates one config entry.
2. An authentication module that reads, validates, refreshes, and atomically persists OAuth credentials.
3. A polling coordinator that obtains an authenticated Cursor web session and fetches the current usage summary.
4. A parser that converts the private API response into a stable internal data model.
5. A sensor platform that exposes the stable model as Home Assistant entities.

The integration will not perform an interactive Cursor login. Credential acquisition remains an explicit setup step outside Home Assistant.

## Credentials and Setup

The config flow asks for a credentials-file path. The default is:

```text
/config/.cursor/auth.json
```

The file schema is:

```json
{
  "access_token": "<Cursor OAuth access token>",
  "refresh_token": "<Cursor OAuth refresh token>"
}
```

Unknown fields are preserved when refreshed credentials are written back. The integration never copies either token into the Home Assistant config entry and never logs a token, derived cookie, or complete credential payload.

`refresh_token` is required. `access_token` may be absent because the integration can obtain one during its first update. The config flow rejects a file without a non-empty refresh token.

The repository includes `scripts/export_cursor_auth.py`. It reads these keys from Cursor desktop's VS Code-style `state.vscdb` database:

- `cursorAuth/accessToken`
- `cursorAuth/refreshToken`

The exporter supports standard Windows, macOS, and Linux Cursor desktop database locations, accepts an explicit database path override, writes the JSON file with mode `0600`, and prints no credential values. The README also documents manual JSON creation for installations where the database cannot be accessed automatically.

The user copies the exported file to the Home Assistant host. Keeping that copy current is unnecessary during normal operation because the integration refreshes and persists the tokens itself. A fresh export is required after Cursor revokes or permanently rejects the refresh token.

## Authentication Flow

At every update, the coordinator reads the credentials file so an externally replaced file is picked up without reconfiguring Home Assistant.

The authentication module decodes the access-token JWT only to inspect its `exp` and `sub` claims. It does not treat unverified claims as authorization decisions. If the access token is missing, invalid, expired, or expires within five minutes, the integration refreshes it with:

```text
POST https://api2.cursor.sh/oauth/token
```

The JSON body contains `grant_type=refresh_token`, Cursor's current desktop OAuth client ID, and the stored refresh token. Returned access, refresh, and ID tokens are merged into the existing credential document. The result is saved with an atomic same-directory replacement while preserving restrictive file permissions.

For the dashboard request, the integration extracts the user identifier from the access token's `sub` claim and builds the URL-encoded `WorkosCursorSessionToken` value in Cursor's `<user-id>::<access-token>` format. It then requests:

```text
GET https://cursor.com/api/usage-summary
```

If the request returns HTTP 401 or 403 and a refresh has not already occurred during that update, the coordinator refreshes once and retries once. It never loops refresh attempts.

## Usage Parsing

The parser reads the Individual-account plan object from `individualUsage.plan` and the billing-cycle end from `billingCycleEnd`.

Monthly usage percentage is selected in this order:

1. A finite numeric `totalPercentUsed` value.
2. A computed `used / limit * 100` value when both fields are finite numbers and `limit` is greater than zero.

The parser does not clamp values above 100 because over-limit usage is meaningful. It rejects negative, Boolean, non-finite, and malformed numeric values. When neither source is valid, it omits the metric instead of reporting zero.

The reset value is parsed as a timezone-aware timestamp. Missing or invalid reset values are omitted. Missing metrics make only their corresponding sensors unavailable; a valid partial response remains usable.

## Sensors

Version 1 exposes exactly three entities:

| Translation key | Suggested entity ID | Value |
| --- | --- | --- |
| `monthly_usage` | `sensor.cursor_usage_monthly_usage` | Monthly included usage in percent |
| `monthly_reset_time` | `sensor.cursor_usage_monthly_reset_time` | Billing-cycle end timestamp |
| `api_error` | `sensor.cursor_usage_api_error` | `0` after a successful update, `1` after a failed update |

The percentage sensor uses measurement state class. The reset sensor uses timestamp device class. All sensors belong to one service device named `Cursor Usage`, optionally including display-only account metadata if it can be safely obtained from the token.

The dashboard example contains a monthly-usage history graph and an entities card for current usage, reset time, and API status.

## Polling and Options

The default update interval is 300 seconds. The options flow permits 300 through 3600 seconds. A five-minute minimum avoids unnecessary load on a private endpoint with no published rate-limit contract. Changing the option updates the coordinator interval without reloading the integration.

## Failure Handling

Failures are classified as follows:

- Unreadable or temporarily malformed credential files: transient update failure. This allows atomic external replacement without forcing reauthentication.
- Missing refresh token during initial configuration: config-flow validation error.
- Permanently rejected, revoked, or expired refresh token: Home Assistant authentication failure requiring a new exported file.
- HTTP 401 or 403 after one refresh retry: Home Assistant authentication failure.
- HTTP 429, HTTP 5xx, timeouts, connection errors, invalid JSON, or an invalid top-level response: transient update failure.
- Valid response with a missing metric: successful partial update with that sensor unavailable.

No error message contains response cookies, authorization headers, tokens, or raw credential contents.

## Testing and Validation

Unit tests cover:

- Valid and invalid credential documents.
- JWT expiry detection and refresh thresholds.
- Refresh request construction.
- Token merging, unknown-field preservation, permission preservation, and atomic persistence.
- Session-cookie derivation for supported subject formats.
- Direct and computed monthly utilization.
- Billing-cycle timestamp parsing.
- Missing, malformed, negative, Boolean, non-finite, zero-limit, partial, and over-100-percent values.
- Refresh-once behavior after HTTP 401 or 403.
- Permanent versus transient error classification.
- Assurance that token values do not appear in raised error messages.

Repository verification includes:

- `pytest`
- Ruff
- Black check
- isort check
- Python compilation
- JSON validation
- hassfest
- HACS validation

The existing workflows will be updated to trigger on `main`, matching the actual default branch. Before release, a maintainer performs one live Individual-account response-shape check. Only field names, types, and parser results may be recorded; credentials and raw personally identifying response data must not be committed or logged.

## Documentation

The README covers:

- HACS and manual installation.
- Credential export on Windows, macOS, and Linux.
- Manual credential-file creation.
- Copying the credentials file to Home Assistant.
- Adding and configuring the integration.
- Sensor definitions and dashboard installation.
- Authentication recovery after token rejection.
- The private, unsupported nature of Cursor's Individual usage and OAuth endpoints.

## Explicit Non-Goals

Version 1 does not include:

- Teams or Enterprise Admin API support.
- Model, request, or token breakdowns.
- Spending, overage, credit, or invoice sensors.
- Browser automation or cookie-database scraping in Home Assistant.
- Interactive OAuth login inside Home Assistant.
- A companion proxy service.
- Multiple Cursor accounts.

These features require separate designs if requested later.

## Completion Criteria

The work is complete when:

1. The derived repository contains no functional Codex references.
2. The credential exporter produces a mode-`0600` file without printing secrets.
3. The integration refreshes credentials and retrieves an Individual usage summary.
4. The three specified sensors behave correctly for full, partial, and failed updates.
5. All local tests and configured validation workflows pass.
6. A sanitized live check confirms the current Individual response maps to monthly usage and reset time.
