from datetime import datetime
from typing import Union
import streamlit as st
from config import STATUS_EMOJI, ALERT_SEVERITY_EMOJI, COLORS

def format_number(num: Union[int, float], precision: int = 0) -> str:
    """Format number with thousand separators"""
    if precision > 0:
        return f"{num:,.{precision}f}"
    return f"{int(num):,}"

def format_percentage(value: float, precision: int = 1) -> str:
    """Format as percentage"""
    return f"{value:.{precision}f}%"

def format_currency(value: float, precision: int = 2) -> str:
    """Format as USD currency"""
    return f"${value:,.{precision}f}"

def format_duration(ms: Union[int, float]) -> str:
    """Format milliseconds to readable duration"""
    if ms < 1000:
        return f"{int(ms)}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"

def format_timestamp(timestamp: str) -> str:
    """Format ISO timestamp to readable format"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp

def get_status_emoji(status: str) -> str:
    """Get emoji for status"""
    return STATUS_EMOJI.get(status.lower(), '⚪')

def get_alert_emoji(severity: str) -> str:
    """Get emoji for alert severity"""
    return ALERT_SEVERITY_EMOJI.get(severity.lower(), '⚪')

def get_health_status(success_rate: float) -> str:
    """Determine health status from success rate"""
    if success_rate >= 95:
        return 'healthy'
    elif success_rate >= 85:
        return 'degraded'
    elif success_rate >= 70:
        return 'warning'
    else:
        return 'critical'

def get_status_color(status: str) -> str:
    """Get color for status"""
    color_map = {
        'healthy': COLORS['success'],
        'degraded': COLORS['warning'],
        'warning': COLORS['warning'],
        'critical': COLORS['error'],
        'unknown': COLORS['neutral']
    }
    return color_map.get(status.lower(), COLORS['neutral'])

def create_metric_card(title: str, value: str, delta: str = None, emoji: str = "📊"):
    """Create a metric card"""
    st.markdown(f"""
        <div style="
            background-color: #1e1e1e;
            padding: 20px;
            border-radius: 10px;
            border-left: 4px solid {COLORS['info']};
            margin: 10px 0;
        ">
            <div style="font-size: 14px; color: #888; margin-bottom: 5px;">
                {emoji} {title}
            </div>
            <div style="font-size: 32px; font-weight: bold; color: white;">
                {value}
            </div>
            {f'<div style="font-size: 14px; color: {COLORS["success"] if "+" in str(delta) else COLORS["error"]}; margin-top: 5px;">{delta}</div>' if delta else ''}
        </div>
    """, unsafe_allow_html=True)

def time_ago(timestamp: str) -> str:
    """Convert timestamp to 'time ago' format"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo)
        diff = now - dt
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return f"{int(seconds)} seconds ago"
        elif seconds < 3600:
            return f"{int(seconds/60)} minutes ago"
        elif seconds < 86400:
            return f"{int(seconds/3600)} hours ago"
        else:
            return f"{int(seconds/86400)} days ago"
    except:
        return timestamp