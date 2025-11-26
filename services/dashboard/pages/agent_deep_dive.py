import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.api_client import get_api_client
from utils.formatting import *
from config import REFRESH_INTERVAL, COLORS

# Page config
st.set_page_config(page_title="Agent Deep Dive", page_icon="🔍", layout="wide")

# Auto-refresh
count = st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="deepdive_refresh")

# Header
st.title("🔍 Agent Deep Dive")
st.markdown("### Detailed Agent Analysis")

# Get API client
client = get_api_client()

try:
    # Get all agents for selector
    agents = client.get_agents()
    
    if not agents:
        st.warning("No agents found. Start sending events to register agents.")
        st.stop()
    
    # Agent selector
    col1, col2 = st.columns([3, 1])
    
    with col1:
        agent_ids = [a['agent_id'] for a in agents]
        selected_agent = st.selectbox(
            "Select Agent to Analyze",
            options=agent_ids,
            index=0
        )
    
    with col2:
        if st.button("🔄 Refresh Data"):
            st.rerun()
    
    st.markdown("---")
    
    # Fetch agent data

    agent_stats = client.get_agent_stats(selected_agent)
    agent_events = client.get_agent_events(selected_agent, limit=100)
    agent_alerts = client.get_agent_alerts(selected_agent)

    if not agent_stats:
        st.error(f"Could not load stats for agent: {selected_agent}")
        st.stop()

    # Agent Profile Card
    success_rate = agent_stats.get('success_rate', 0)
    health_status = get_health_status(success_rate)
    status_emoji = get_status_emoji(health_status)

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 30px;
        border-radius: 15px;
        margin-bottom: 20px;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h2 style="color: white; margin: 0;">🤖 {selected_agent}</h2>
                <p style="color: rgba(255,255,255,0.8); margin: 5px 0;">
                    Agent Type: {selected_agent.split('-')[0] if '-' in selected_agent else 'Unknown'}
                </p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 48px;">{status_emoji}</div>
                <div style="color: white; font-size: 18px; font-weight: bold;">
                    {health_status.upper()}
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Key Metrics Grid
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric(
            "Total Events",
            format_number(agent_stats.get('total_events', 0))
        )

    with col2:
        st.metric(
            "Success Rate",
            f"{success_rate:.1f}%",
            delta="Good" if success_rate >= 95 else "Low"
        )

    with col3:
        st.metric(
            "Avg Latency",
            format_duration(agent_stats.get('avg_latency_ms', 0))
        )

    with col4:
        st.metric(
            "Total Cost",
            format_currency(agent_stats.get('total_cost', 0))
        )

    with col5:
        st.metric(
            "Error Count",
            format_number(agent_stats.get('error_count', 0))
        )

    with col6:
        unresolved_alerts = agent_alerts.get('stats', {}).get('unresolved', 0) if agent_alerts else 0
        st.metric(
            "Active Alerts",
            unresolved_alerts,
            delta="⚠️" if unresolved_alerts > 0 else "✓"
        )

    st.markdown("---")

    # Performance Timeline (Mock data - in production, this would come from time-series queries)
    st.markdown("### 📈 Performance Timeline (Last 24 Hours)")

    # Generate mock timeline data
    hours = 24
    timeline_data = []
    base_time = datetime.now() - timedelta(hours=hours)

    for i in range(hours):
        timestamp = base_time + timedelta(hours=i)
        # Mock data with some variation
        timeline_data.append({
            'Time': timestamp.strftime('%H:00'),
            'Events': agent_stats.get('total_events', 0) // hours + (i % 5) * 10,
            'Success Rate': min(100, success_rate + (i % 3) - 1),
            'Avg Latency': agent_stats.get('avg_latency_ms', 1000) + (i % 4) * 100
        })

    df_timeline = pd.DataFrame(timeline_data)

    # Create subplots
    from plotly.subplots import make_subplots

    fig_timeline = make_subplots(
        rows=3, cols=1,
        subplot_titles=('Events per Hour', 'Success Rate (%)', 'Average Latency (ms)'),
        vertical_spacing=0.1,
        shared_xaxes=True
    )

    # Events
    fig_timeline.add_trace(
        go.Scatter(x=df_timeline['Time'], y=df_timeline['Events'],
                mode='lines+markers', name='Events',
                line=dict(color=COLORS['info'], width=2),
                marker=dict(size=6)),
        row=1, col=1
    )

    # Success Rate
    fig_timeline.add_trace(
        go.Scatter(x=df_timeline['Time'], y=df_timeline['Success Rate'],
                mode='lines+markers', name='Success Rate',
                line=dict(color=COLORS['success'], width=2),
                marker=dict(size=6)),
        row=2, col=1
    )

    # Latency
    fig_timeline.add_trace(
        go.Scatter(x=df_timeline['Time'], y=df_timeline['Avg Latency'],
                mode='lines+markers', name='Latency',
                line=dict(color=COLORS['warning'], width=2),
                marker=dict(size=6)),
        row=3, col=1
    )

    fig_timeline.update_layout(height=600, showlegend=False)
    fig_timeline.update_xaxes(title_text="Time", row=3, col=1)

    st.plotly_chart(fig_timeline, use_container_width=True)

    st.markdown("---")

    # Two column layout
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("### 📋 Recent Events")
        
        events = agent_events.get('events', [])
        
        if events:
            event_records = []
            for event in events[:50]:
                metadata = event.get('event_metadata', {})
                event_records.append({
                    'Time': format_timestamp(event.get('timestamp', '')),
                    'Type': event.get('event_type', 'unknown'),
                    'Status': '✓' if metadata.get('success', True) else '✗',
                    'Latency': format_duration(metadata.get('latency_ms', 0)),
                    'Tokens': format_number(metadata.get('tokens_used', 0)),
                    'Cost': format_currency(metadata.get('cost_usd', 0))
                })
            
            df_events = pd.DataFrame(event_records)
            
            # Style based on status
            def highlight_failures(row):
                if row['Status'] == '✗':
                    return ['background-color: #fee; color: #c00'] * len(row)
                return [''] * len(row)
            
            st.dataframe(
                df_events.style.apply(highlight_failures, axis=1),
                use_container_width=True,
                height=400
            )
        else:
            st.info("No recent events for this agent")

    with col_right:
        st.markdown("### 🎯 Statistics")
        
        # Additional stats
        if events:
            total_tokens = sum(
                e.get('event_metadata', {}).get('tokens_used', 0)
                for e in events
            )
            avg_tokens = total_tokens / len(events) if events else 0
            
            st.metric("Avg Tokens/Event", format_number(avg_tokens))
            
            # Cost efficiency
            cost_per_event = agent_stats.get('total_cost', 0) / agent_stats.get('total_events', 1)
            st.metric("Cost/Event", format_currency(cost_per_event))
            
            # Uptime (mock)
            st.metric("Uptime", "99.5%", delta="Excellent")
        
        st.markdown("---")
        st.markdown("### 🔥 Event Type Breakdown")
        
        if events:
            event_types = {}
            for event in events:
                event_type = event.get('event_type', 'unknown')
                event_types[event_type] = event_types.get(event_type, 0) + 1
            
            fig_types = go.Figure(data=[go.Pie(
                labels=list(event_types.keys()),
                values=list(event_types.values()),
                hole=.4
            )])
            
            fig_types.update_layout(height=250, showlegend=True)
            st.plotly_chart(fig_types, use_container_width=True)

    st.markdown("---")

    # Error Analysis
    st.markdown("### ⚠️ Error Analysis")

    error_events = [
        e for e in events
        if not e.get('event_metadata', {}).get('success', True)
    ]

    if error_events:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Error Type Distribution")
            
            error_types = {}
            for event in error_events:
                error_code = event.get('event_metadata', {}).get('error_code', 'unknown')
                error_types[error_code] = error_types.get(error_code, 0) + 1
            
            fig_errors = px.bar(
                x=list(error_types.keys()),
                y=list(error_types.values()),
                labels={'x': 'Error Type', 'y': 'Count'},
                color=list(error_types.values()),
                color_continuous_scale='Reds'
            )
            
            fig_errors.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig_errors, use_container_width=True)
        
        with col2:
            st.markdown("#### Recent Errors")
            
            error_records = []
            for event in error_events[:5]:
                metadata = event.get('event_metadata', {})
                error_records.append({
                    'Time': format_timestamp(event.get('timestamp', '')),
                    'Error': metadata.get('error_code', 'unknown'),
                    'Message': metadata.get('error_message', 'No message')[:40]
                })
            
            df_errors = pd.DataFrame(error_records)
            st.dataframe(df_errors, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No errors detected for this agent!")

    st.markdown("---")

    # Alerts Section
    st.markdown("### 🚨 Alerts History")

    if agent_alerts and agent_alerts.get('alerts'):
        alerts = agent_alerts['alerts']
        
        alert_records = []
        for alert in alerts[:10]:
            alert_records.append({
                'Time': format_timestamp(alert.get('triggered_at', '')),
                'Type': alert.get('alert_type', 'unknown'),
                'Severity': get_alert_emoji(alert.get('severity', 'info')) + " " + alert.get('severity', 'info').upper(),
                'Message': alert.get('message', 'No message')[:60],
                'Status': '✓ Resolved' if alert.get('resolved') else '⚠️ Active'
            })
        
        df_alerts = pd.DataFrame(alert_records)
        st.dataframe(df_alerts, use_container_width=True, hide_index=True)
        
        # Alert stats
        col1, col2, col3 = st.columns(3)
        
        stats = agent_alerts.get('stats', {})
        col1.metric("Total Alerts", stats.get('total', 0))
        col2.metric("Unresolved", stats.get('unresolved', 0))
        col3.metric("Unacknowledged", stats.get('unacknowledged', 0))
    else:
        st.success("✅ No alerts for this agent!")

    st.markdown("---")

    # Model Usage (if available)
    st.markdown("### 🤖 Model Usage")

    if events:
        models = {}
        for event in events:
            model = event.get('event_metadata', {}).get('model', 'unknown')
            if model != 'unknown':
                models[model] = models.get(model, 0) + 1
        
        if models:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                fig_models = px.pie(
                    names=list(models.keys()),
                    values=list(models.values()),
                    title="Model Distribution"
                )
                fig_models.update_layout(height=300)
                st.plotly_chart(fig_models, use_container_width=True)
            
            with col2:
                st.markdown("#### Model Stats")
                for model, count in sorted(models.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / len(events)) * 100
                    st.metric(model, f"{count} ({percentage:.1f}%)")

except Exception as e:
    st.error(f"Error loading agent data: {str(e)}")
    st.exception(e)

st.markdown("---")
st.markdown(f"Agent analysis | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
