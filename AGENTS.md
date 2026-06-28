# Cursor Usage — Integration Notes

This project is a Home Assistant custom integration for monitoring Cursor Individual subscription usage.

## Current Design

- Integration domain: `hass_cursor_usage`.
- Setup asks for the path to a Cursor OAuth credentials file, default `/config/.cursor/auth.json`.
- The integration reads the credentials file on every poll; it does not copy tokens into the HA config entry or database.
- Usage is fetched from `https://cursor.com/api/usage-summary` using a WorkOS session cookie (`WorkosCursorSessionToken`).
- When the `access_token` is near expiry the integration refreshes it via `https://api2.cursor.sh/oauth/token` and writes the new token back to the file in place.

## Credentials File Schema

```json
{
  "access_token": "<Cursor OAuth access token>",
  "refresh_token": "<Cursor OAuth refresh token>"
}
```

## Constraints

- **No secrets in version control.** The credentials file must never be committed. Add it to `.gitignore` and keep file permissions at `600`.
- **Unsupported API.** The Individual usage and OAuth endpoints are not documented public Cursor APIs. They may change or be removed at any time without notice. Do not assume stable field names or response shapes.
- **Minimum poll interval is 300 seconds (five minutes).** Do not lower this; it risks rate-limiting or account suspension.
- Do not replace the integration's usage endpoint with the Cursor API billing/API-key endpoint; Individual subscription usage is separate from paid API usage.
- Keep changes surgical; verify with syntax and lint checks before each task completion.

## Repository operation constraint

Do not create Git commits, tags, GitHub repositories, add remotes, or push unless the user explicitly requests that specific operation.

## Verified follow-up work (outside v1)

- Add repository topics to satisfy HACS topic validation (e.g. `home-assistant`, `hacs`, `integration`, `cursor`).
- Verify the usage API response shape on the target Home Assistant host after first live deployment.
- Investigate whether Cursor will publish stable public endpoints; adopt them when available.
- Add Cursor trademark artwork to `custom_components/hass_cursor_usage/brand/` only after verifying redistribution terms.
