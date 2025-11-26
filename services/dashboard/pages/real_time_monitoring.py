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
from config  import REFRESH_INTERVAL, COLORS

# Page config
st.set_page_config(page_title="Real-Time Monitoring", page_icon="📊", layout="wide")

# Auto-refresh every 2 seconds for real-time feel
count = st_autorefresh(interval=2000, key="monitoring_refresh")

# Header
st.title("📊 Real-Time Monitoring")
st.markdown("### Live System Activity")

# Get API client
client = get_api_client()

# Control panel
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.markdown(f"**Auto-refresh:** Every 2 seconds | **Last update:** {datetime.now().strftime('%H:%M:%S')}")

with col2:
    refresh_rate = st.selectbox("Refresh Rate", ["2s", "5s", "10s", "30s"], index=0)

with col3:
    if st.button("🔄 Refresh Now"):
        st.rerun()

st.markdown("---")

try:
    # Fetch recent events - handle different response formats
    events_data = client.get_events(limit=100)
    
    # Handle both list and dict responses
    if isinstance(events_data, dict):
        events = events_data.get('events', [])
    elif isinstance(events_data, list):
        events = events_data
    else:
        events = []
    
    events_summary = client.get_events_summary()
    if not events_summary:
        events_summary = {"total_events": 0, "success_rate": 0}
    
    alerts_stats = client.get_alerts_stats()
    if not alerts_stats:
        alerts_stats = {"total_alerts": 0}
    
    # Current metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_events = events_summary.get('total_events', 0)
        st.metric(
            "Total Events",
            format_number(total_events),
            delta=f"+{len(events)}" if events else "0"
        )
    
    with col2:
        # Calculate success rate from recent events
        if events:
            success_count = 0
            for e in events:
                metadata = e.get('event_metadata', {})
                if isinstance(metadata, dict):
                    if metadata.get('success', True):
                        success_count += 1
            
            success_rate = (success_count / len(events)) * 100 if len(events) > 0 else 0
        else:
            success_rate = 0
        
        st.metric(
            "Success Rate",
            f"{success_rate:.1f}%",
            delta="Good" if success_rate >= 95 else "Low"
        )
    
    with col3:
        # Calculate average latency
        if events:
            latencies = []
            for e in events:
                metadata = e.get('event_metadata', {})
                if isinstance(metadata, dict):
                    latency = metadata.get('latency_ms', 0)
                    if latency:
                        latencies.append(latency)
            
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
        else:
            avg_latency = 0
            latencies = []
        
        st.metric(
            "Avg Latency",
            format_duration(avg_latency),
            delta="Normal" if avg_latency < 2000 else "High"
        )
    
    with col4:
        # Calculate events per second (approximation)
        events_per_sec = len(events) / 60 if events else 0
        st.metric(
            "Events/sec",
            f"{events_per_sec:.1f}",
            delta=f"+{int(events_per_sec * 0.1)}"
        )
    
    with col5:
        active_alerts = alerts_stats.get('total_alerts', 0)
        st.metric(
            "Active Alerts",
            active_alerts,
            delta="⚠️" if active_alerts > 0 else "✓"
        )
    
    st.markdown("---")
    
    # Main content - Two columns
    col_left, col_right = st.columns([3, 1])
    
    with col_left:
        # Live Event Stream
        st.markdown("### 🔴 Live Event Stream")
        st.markdown("*Showing last 100 events*")
        
        if events:
            # Create DataFrame for events
            event_records = []
            for event in events[:100]:
                metadata = event.get('event_metadata', {})
                if not isinstance(metadata, dict):
                    metadata = {}
                
                event_records.append({
                    'Time': format_timestamp(event.get('timestamp', '')),
                    'Agent': str(event.get('agent_id', 'unknown'))[:30],
                    'Type': str(event.get('event_type', 'unknown')),
                    'Status': '✓' if metadata.get('success', True) else '✗',
                    'Latency': format_duration(metadata.get('latency_ms', 0)),
                    'Cost': format_currency(metadata.get('cost_usd', 0))
                })
            
            df_events = pd.DataFrame(event_records)
            
            # Style the dataframe
            def highlight_status(row):
                if row['Status'] == '✗':
                    return ['background-color: #fee; color: #c00'] * len(row)
                return [''] * len(row)
            
            st.dataframe(
                df_events.style.apply(highlight_status, axis=1),
                use_container_width=True,
                height=400
            )
        else:
            st.info("No events yet. Waiting for data...")
    
    with col_right:
        # Success Rate Gauge
        st.markdown("### ✓ Success Rate")
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=success_rate,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Current"},
            delta={'reference': 95, 'increasing': {'color': COLORS['success']}},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': COLORS['info']},
                'steps': [
                    {'range': [0, 70], 'color': COLORS['error']},
                    {'range': [70, 85], 'color': COLORS['warning']},
                    {'range': [85, 95], 'color': 'yellow'},
                    {'range': [95, 100], 'color': COLORS['success']}
                ],
                'threshold': {
                    'line': {'color': "white", 'width': 4},
                    'thickness': 0.75,
                    'value': 95
                }
            }
        ))
        fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)
        
        # Error count
        if events:
            error_count = len(events) - success_count
            st.metric("Errors (Last 100)", error_count)
        else:
            st.metric("Errors (Last 100)", 0)
    
    # Rest of the code remains the same...
    st.markdown("---")
    
    # Charts Row
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### ⚡ Latency Distribution")
        
        if events and latencies:
            fig_latency = go.Figure()
            
            fig_latency.add_trace(go.Histogram(
                x=latencies,
                nbinsx=20,
                marker_color=COLORS['info'],
                name='Latency'
            ))
            
            # Add percentile lines
            p50 = pd.Series(latencies).quantile(0.50)
            p95 = pd.Series(latencies).quantile(0.95)
            p99 = pd.Series(latencies).quantile(0.99)
            
            fig_latency.add_vline(x=p50, line_dash="dash", line_color="green", 
                                 annotation_text="P50")
            fig_latency.add_vline(x=p95, line_dash="dash", line_color="yellow",
                                 annotation_text="P95")
            fig_latency.add_vline(x=p99, line_dash="dash", line_color="red",
                                 annotation_text="P99")
            
            fig_latency.update_layout(
                xaxis_title="Latency (ms)",
                yaxis_title="Count",
                showlegend=False,
                height=300
            )
            
            st.plotly_chart(fig_latency, use_container_width=True)
            
            # Show percentiles
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("P50", format_duration(p50))
            col_b.metric("P95", format_duration(p95))
            col_c.metric("P99", format_duration(p99))
        else:
            st.info("Waiting for latency data...")
    
    with col2:
        st.markdown("### 🎯 Event Type Distribution")
        
        if events:
            # Count event types
            event_types = {}
            for event in events:
                event_type = event.get('event_type', 'unknown')
                event_types[event_type] = event_types.get(event_type, 0) + 1
            
            fig_types = go.Figure(data=[go.Pie(
                labels=list(event_types.keys()),
                values=list(event_types.values()),
                hole=.3,
                marker_colors=[COLORS['info'], COLORS['success'], 
                             COLORS['warning'], COLORS['error']]
            )])
            
            fig_types.update_layout(height=300, showlegend=True)
            st.plotly_chart(fig_types, use_container_width=True)
        else:
            st.info("Waiting for event data...")
    
    st.markdown("---")
    
    # Bottom Row - Cost and Token Analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 💰 Cost Analysis")
        
        if events:
            # Calculate costs
            costs = []
            for e in events:
                metadata = e.get('event_metadata', {})
                if isinstance(metadata, dict):
                    cost = metadata.get('cost_usd', 0)
                    if cost:
                        costs.append(cost)
            
            if costs:
                total_cost = sum(costs)
                avg_cost = total_cost / len(costs)
                
                col_a, col_b, col_c = st.columns(3)
                
                col_a.metric("Total (100 events)", format_currency(total_cost))
                col_b.metric("Average per Event", format_currency(avg_cost))
                col_c.metric("Projected/Day", format_currency(total_cost * 144))
                
                # Cost timeline
                fig_cost = go.Figure()
                fig_cost.add_trace(go.Scatter(
                    y=costs[:50],  # Last 50
                    mode='lines+markers',
                    marker=dict(color=COLORS['warning'], size=6),
                    line=dict(color=COLORS['warning'], width=2),
                    name='Cost per Event'
                ))
                
                fig_cost.update_layout(
                    xaxis_title="Event Sequence",
                    yaxis_title="Cost (USD)",
                    showlegend=False,
                    height=200
                )
                
                st.plotly_chart(fig_cost, use_container_width=True)
            else:
                st.info("No cost data available")
        else:
            st.info("Waiting for cost data...")
    
    with col2:
        st.markdown("### 🎫 Token Usage")
        
        if events:
            # Calculate token usage
            tokens = []
            for e in events:
                metadata = e.get('event_metadata', {})
                if isinstance(metadata, dict):
                    token_count = metadata.get('tokens_used', 0)
                    if token_count:
                        tokens.append(token_count)
            
            if tokens:
                total_tokens = sum(tokens)
                avg_tokens = total_tokens / len(tokens)
                
                col_a, col_b, col_c = st.columns(3)
                
                col_a.metric("Total Tokens", format_number(total_tokens))
                col_b.metric("Average", format_number(avg_tokens))
                col_c.metric("Max", format_number(max(tokens)))
                
                # Token distribution
                fig_tokens = go.Figure()
                fig_tokens.add_trace(go.Box(
                    y=tokens,
                    marker_color=COLORS['info'],
                    name='Token Distribution'
                ))
                
                fig_tokens.update_layout(
                    yaxis_title="Tokens",
                    showlegend=False,
                    height=200
                )
                
                st.plotly_chart(fig_tokens, use_container_width=True)
            else:
                st.info("No token data available")
        else:
            st.info("Waiting for token data...")
    
    # Top Errors Section
    st.markdown("---")
    st.markdown("### ⚠️ Recent Errors")
    
    if events:
        error_events = []
        for e in events:
            metadata = e.get('event_metadata', {})
            if isinstance(metadata, dict):
                if not metadata.get('success', True):
                    error_events.append(e)
        
        if error_events:
            error_records = []
            for event in error_events[:10]:
                metadata = event.get('event_metadata', {})
                if not isinstance(metadata, dict):
                    metadata = {}
                
                error_records.append({
                    'Time': format_timestamp(event.get('timestamp', '')),
                    'Agent': str(event.get('agent_id', 'unknown'))[:35],
                    'Type': str(event.get('event_type', 'unknown')),
                    'Error Code': str(metadata.get('error_code', 'unknown')),
                    'Error Message': str(metadata.get('error_message', 'No message'))[:50]
                })
            
            df_errors = pd.DataFrame(error_records)
            st.dataframe(df_errors, use_container_width=True, hide_index=True)
        else:
            st.success(" No errors in recent events!")
    else:
        st.info("No error data available")

except Exception as e:
    st.error(f"Error loading monitoring data: {str(e)}")
    st.exception(e)

# Footer
st.markdown("---")
st.markdown(f"*Real-time monitoring - Updates every 2 seconds*")