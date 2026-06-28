"""Constants for Cursor Usage."""

DOMAIN = "hass_cursor_usage"

TOKEN_REFRESH_URL = "https://api2.cursor.sh/oauth/token"
USAGE_API_URL = "https://cursor.com/api/usage-summary"

DEFAULT_AUTH_FILE = "/config/.cursor/auth.json"
DEFAULT_UPDATE_INTERVAL = 300
MIN_UPDATE_INTERVAL = 300
MAX_UPDATE_INTERVAL = 3600

CONF_AUTH_FILE = "auth_file"
CONF_UPDATE_INTERVAL = "update_interval"

SENSOR_DEFINITIONS = [
    ("monthly_usage", "Monthly Usage", "%", "mdi:chart-donut", None),
    ("monthly_reset_time", "Monthly Reset Time", None, "mdi:calendar-refresh", "timestamp"),
    ("api_error", "API Error", "errors", "mdi:alert-circle", None),
    ("requests_used", "Requests Used", "requests", "mdi:counter", None),
    ("requests_limit", "Request Limit", "requests", "mdi:gauge", None),
    ("requests_remaining", "Requests Remaining", "requests", "mdi:gauge-empty", None),
    ("auto_percent_used", "Auto Model Usage", "%", "mdi:robot", None),
    ("api_percent_used", "API Usage", "%", "mdi:api", None),
    ("requests_included", "Included Requests", "requests", "mdi:check-circle", None),
    ("requests_bonus", "Bonus Requests", "requests", "mdi:gift", None),
    ("billing_cycle_start", "Billing Cycle Start", None, "mdi:calendar-start", "timestamp"),
    ("membership_type", "Membership Type", None, "mdi:card-account-details", None),
    ("is_unlimited", "Unlimited Plan", None, "mdi:infinity", None),
    ("on_demand_enabled", "On-Demand Enabled", None, "mdi:lightning-bolt", None),
]
