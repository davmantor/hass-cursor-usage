"""Constants for Codex Usage integration."""

DOMAIN = "hass_codex_usage"

# API
USAGE_API_URL = "https://chatgpt.com/backend-api/wham/usage"

# Defaults
DEFAULT_AUTH_FILE = "~/.codex/auth.json"
DEFAULT_UPDATE_INTERVAL = 300  # seconds

# Config keys
CONF_AUTH_FILE = "auth_file"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ACCOUNT_NAME = "account_name"
CONF_SUBSCRIPTION_LEVEL = "subscription_level"

# Sensor definitions: (key, name, unit, icon, device_class)
SENSOR_DEFINITIONS = [
    ("session_usage_percent", "Session Usage", "%", "mdi:timer-sand", None),
    (
        "session_reset_time",
        "Session Reset Time",
        None,
        "mdi:timer-refresh",
        "timestamp",
    ),
    ("week_usage_percent", "Weekly Usage", "%", "mdi:calendar-week", None),
    ("week_usage_pace", "Weekly Usage Pace", "%", "mdi:speedometer", None),
    ("week_reset_time", "Weekly Reset Time", None, "mdi:calendar-clock", "timestamp"),
    ("credits_balance", "Credits Balance", "credits", "mdi:credit-card-outline", None),
    ("credits_enabled", "Credits Enabled", None, "mdi:toggle-switch", None),
    ("rate_limit_reached", "Rate Limit Reached", None, "mdi:alert-circle", None),
    ("api_error", "API Error", "errors", "mdi:alert-circle", None),
]
