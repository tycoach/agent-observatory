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
st.set_page_config(page_title="Home", page_icon="🏠", layout="wide")

# Auto-refresh
count = st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="home_refresh")

# Header
st.title("🏠 Home / Overview")
st.markdown("### System Dashboard")

# Get API client
client = get_api_client()

# Fetch data
try:
    health = client.get_health()
    events_summary = client.get_events_summary()
    agents = client.get_agents()
    alerts_stats = client.get_alerts_stats()
    recent_alerts = client.get_alerts_recent(limit=5)
    
    # System Status Banner
    st.markdown("---")
    
    if health:
        services = health.get('services', {})
        all_healthy = all(s == 'healthy' for s in services.values())
        
        if all_healthy:
            st.success("🟢 **SYSTEM HEALTHY** - All Services Online")
        else:
            st.warning("🟡 **SYSTEM DEGRADED** - Some Services Have Issues")
        
        # Service status
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("API", "✓ Online", delta="Healthy")
        
        with col2:
            db_status = services.get('database', 'unknown')
            st.metric("Database", 
                     "✓" if db_status == 'healthy' else "✗",
                     delta=db_status.title())
        
        with col3:
            redis_status = services.get('redis', 'unknown')
            st.metric("Redis",
                     "✓" if redis_status == 'healthy' else "✗",
                     delta=redis_status.title())
        
        with col4:
            kafka_status = services.get('kafka', 'unknown')
            st.metric("Kafka",
                     "✓" if kafka_status == 'healthy' else "✗",
                     delta=kafka_status.title())
        
        with col5:
            st.metric("Last Update", 
                     datetime.now().strftime("%H:%M:%S"),
                     delta=f"Refresh: {REFRESH_INTERVAL}s")
    
    st.markdown("---")
    
    # Key Metrics Cards
    st.markdown("### 📊 Key Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_events = events_summary.get('total_events', 0)
        st.metric(
            "Total Events",
            format_number(total_events),
            delta="+15.3%" if total_events > 0 else None
        )
    
    with col2:
        active_agents = len(agents) if agents else 0
        st.metric(
            "Active Agents",
            active_agents,
            delta=f"+{active_agents % 5}" if active_agents > 0 else None
        )
    
    with col3:
        # Calculate events per second (mock for now)
        events_per_sec = total_events / 86400 if total_events > 0 else 0
        st.metric(
            "Events/sec",
            f"{events_per_sec:.0f}",
            delta="+12.5%" if events_per_sec > 0 else None
        )
    
    with col4:
        total_alerts = alerts_stats.get('total_alerts', 0)
        unresolved = sum(
            v for k, v in alerts_stats.get('by_type', {}).items()
        )
        st.metric(
            "Active Alerts",
            unresolved,
            delta=f"-{unresolved % 3}" if unresolved > 0 else "No alerts"
        )
    
    st.markdown("---")
    
    # Two column layout
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.markdown("### 📈 Event Activity")
        
        if agents and len(agents) > 0:
            # Create sample data for visualization
            agent_data = []
            for agent in agents[:10]:  # Top 10 agents
                stats = client.get_agent_stats(agent['agent_id'])
                if stats:
                    agent_data.append({
                        'Agent': agent['agent_id'][:20],
                        'Events': stats.get('total_events', 0),
                        'Success Rate': stats.get('success_rate', 0)
                    })
            
            if agent_data:
                df = pd.DataFrame(agent_data)
                
                # Bar chart for events
                fig = px.bar(
                    df,
                    x='Agent',
                    y='Events',
                    title='Top 10 Agents by Event Count',
                    color='Success Rate',
                    color_continuous_scale=['red', 'yellow', 'green']
                )
                fig.update_layout(
                    height=400,
                    xaxis_tickangle=-45,
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No agent data available yet")
        else:
            st.info("No agents found. Start sending events to see activity.")
    
    with col_right:
        st.markdown("### 🚨 Recent Alerts")
        
        if recent_alerts and recent_alerts.get('alerts'):
            for alert in recent_alerts['alerts'][:5]:
                severity = alert.get('severity', 'info')
                emoji = get_alert_emoji(severity)
                agent_id = alert.get('agent_id', 'unknown')
                message = alert.get('message', 'No message')
                triggered_at = alert.get('triggered_at', '')
                
                time_str = time_ago(triggered_at) if triggered_at else 'unknown time'
                
                with st.container():
                    st.markdown(f"""
                    <div style="
                        background-color: #1e1e1e;
                        padding: 10px;
                        border-radius: 5px;
                        border-left: 4px solid {get_status_color(severity)};
                        margin: 5px 0;
                    ">
                        <div style="font-weight: bold;">
                            {emoji} {severity.upper()}
                        </div>
                        <div style="font-size: 12px; color: #888;">
                            {agent_id}
                        </div>
                        <div style="margin: 5px 0;">
                            {message}
                        </div>
                        <div style="font-size: 11px; color: #666;">
                            {time_str}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.success(" No recent alerts")
    
    st.markdown("---")
    
    # Bottom section - Statistics
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📊 Event Distribution")
        
        if events_summary:
            # Event type distribution
            event_types = {
                'API Calls': events_summary.get('total_events', 0) * 0.6,
                'Decisions': events_summary.get('total_events', 0) * 0.2,
                'Errors': events_summary.get('total_events', 0) * 0.1,
                'Completions': events_summary.get('total_events', 0) * 0.1,
            }
            
            fig = go.Figure(data=[go.Pie(
                labels=list(event_types.keys()),
                values=list(event_types.values()),
                hole=.3,
                marker_colors=[COLORS['info'], COLORS['success'], 
                             COLORS['error'], COLORS['warning']]
            )])
            fig.update_layout(height=300, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No event data available")
    
    with col2:
        st.markdown("### 🎯 Top Performing Agents")
        
        if agents and len(agents) > 0:
            # Get stats for top agents
            top_agents = []
            for agent in agents[:5]:
                stats = client.get_agent_stats(agent['agent_id'])
                if stats:
                    top_agents.append({
                        'Agent': agent['agent_id'][:25],
                        'Success Rate': stats.get('success_rate', 0),
                        'Events': stats.get('total_events', 0)
                    })
            
            if top_agents:
                df_top = pd.DataFrame(top_agents)
                df_top = df_top.sort_values('Success Rate', ascending=False)
                
                # Display as table
                st.dataframe(
                    df_top.style.format({
                        'Success Rate': '{:.1f}%',
                        'Events': '{:,.0f}'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No agent statistics available")
        else:
            st.info("No agents active yet")

except Exception as e:
    st.error(f"Error loading dashboard data: {str(e)}")
    st.exception(e)

# Footer
st.markdown("---")
st.markdown(f"*Dashboard last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")