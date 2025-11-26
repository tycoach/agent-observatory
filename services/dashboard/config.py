import os

# API Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://api:8000')

# Dashboard Configuration
REFRESH_INTERVAL = 5  # seconds
PAGE_TITLE = "Agent Observatory"
PAGE_ICON = "🔭"
LAYOUT = "wide"

# Chart Configuration
CHART_HEIGHT = 400
CHART_THEME = "plotly_dark"

# Color Scheme
COLORS = {
    'success': '#10b981',  # Green
    'warning': '#f59e0b',  # Orange
    'error': '#ef4444',    # Red
    'info': '#3b82f6',     # Blue
    'neutral': '#6b7280'   # Gray
}

# Status Emojis
STATUS_EMOJI = {
    'healthy': '🟢',
    'degraded': '🟡',
    'warning': '🟠',
    'critical': '🔴',
    'unknown': '⚫'
}

# Alert Severity
ALERT_SEVERITY_EMOJI = {
    'critical': '🔴',
    'warning': '🟠',
    'info': '🟡'
}