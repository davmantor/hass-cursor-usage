# Codex Usage Notes

This project is a Home Assistant custom integration for Codex usage monitoring.

## Current Design

- The integration domain is `hass_codex_usage`.
- Setup asks for the Codex OAuth auth file path, normally `~/.codex/auth.json` on the Home Assistant host.
- The integration reads the auth file at each poll and does not copy access tokens into the Home Assistant config entry.
- Usage is fetched from `https://chatgpt.com/backend-api/wham/usage`.
- The parser accepts both direct `wham/usage` style fields and Codex app-server `rateLimits` style fields.

## Constraints

- Do not replace this with OpenAI API-key billing usage; Codex subscription usage is separate from API usage.
- Avoid hardcoding an internal OpenAI OAuth client flow unless Codex exposes a stable public flow for this use case.
- Keep changes surgical and verify with syntax/lint checks when possible.
