import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
from utils.api_client import get_api_client
from utils.formatting import *

from config import REFRESH_INTERVAL, COLORS


# Page config
st.set_page_config(page_title="Agents Overview", page_icon="🤖", layout="wide")

# Auto-refresh
count = st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="agents_refresh")

# Header
st.title("🤖 Agents Overview")
st.markdown("### Monitor All Agents")

# Get API client
client = get_api_client()

try:
    # Fetch agents
    agents = client.get_agents()
    alerts_stats = client.get_alerts_stats()
    
    if not agents:
        st.warning("No agents found. Start sending events to register agents.")
        st.stop()
    
    # Header metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Agents", len(agents))
    
    with col2:
        # Count healthy agents (>95% success rate)
        healthy_count = 0
        for agent in agents:
            stats = client.get_agent_stats(agent['agent_id'])
            if stats and stats.get('success_rate', 0) >= 95:
                healthy_count += 1
        st.metric("Healthy Agents", healthy_count, delta="Good" if healthy_count > 0 else None)
    
    with col3:
        # Count agents with alerts
        agents_with_alerts = 0
        for agent in agents:
            agent_alerts = client.get_agent_alerts(agent['agent_id'], unresolved_only=True)
            if agent_alerts and agent_alerts.get('count', 0) > 0:
                agents_with_alerts += 1
        st.metric("Agents with Alerts", agents_with_alerts, 
                 delta="⚠️" if agents_with_alerts > 0 else "✓")
    
    with col4:
        # Total events across all agents
        total_events = sum(
            client.get_agent_stats(a['agent_id']).get('total_events', 0)
            for a in agents
        )
        st.metric("Total Events", format_number(total_events))
    
    st.markdown("---")
    
    # Filters and Search
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        search_query = st.text_input("🔍 Search Agents", placeholder="Enter agent ID or type...")
    
    with col2:
        status_filter = st.selectbox("Status", ["All", "Healthy", "Warning", "Critical"])
    
    with col3:
        sort_by = st.selectbox("Sort by", ["Activity", "Success Rate", "Errors", "Cost"])
    
    st.markdown("---")
    
    # Fetch detailed stats for all agents
    agent_details = []
    
    with st.spinner("Loading agent details..."):
        for agent in agents:
            agent_id = agent['agent_id']
            
            # Apply search filter
            if search_query and search_query.lower() not in agent_id.lower():
                continue
            
            stats = client.get_agent_stats(agent_id)
            
            if stats:
                success_rate = stats.get('success_rate', 0)
                health_status = get_health_status(success_rate)
                
                # Apply status filter
                if status_filter != "All":
                    if status_filter == "Healthy" and health_status != "healthy":
                        continue
                    elif status_filter == "Warning" and health_status not in ["warning", "degraded"]:
                        continue
                    elif status_filter == "Critical" and health_status != "critical":
                        continue
                
                agent_details.append({
                    'agent_id': agent_id,
                    'status': health_status,
                    'total_events': stats.get('total_events', 0),
                    'success_rate': success_rate,
                    'avg_latency': stats.get('avg_latency_ms', 0),
                    'total_cost': stats.get('total_cost', 0),
                    'error_count': stats.get('error_count', 0),
                    'first_seen': agent.get('first_seen', ''),
                    'last_seen': agent.get('last_seen', '')
                })
    
    if not agent_details:
        st.info("No agents match your filters.")
        st.stop()
    
    # Sort agents
    if sort_by == "Activity":
        agent_details.sort(key=lambda x: x['total_events'], reverse=True)
    elif sort_by == "Success Rate":
        agent_details.sort(key=lambda x: x['success_rate'], reverse=True)
    elif sort_by == "Errors":
        agent_details.sort(key=lambda x: x['error_count'], reverse=True)
    elif sort_by == "Cost":
        agent_details.sort(key=lambda x: x['total_cost'], reverse=True)
    
    # Main content
    st.markdown("### 📊 All Agents")
    
    # Create agents table
    table_data = []
    for agent in agent_details:
        status_emoji = get_status_emoji(agent['status'])
        
        table_data.append({
            'Status': status_emoji,
            'Agent ID': agent['agent_id'][:40],
            'Events': format_number(agent['total_events']),
            'Success Rate': f"{agent['success_rate']:.1f}%",
            'Avg Latency': format_duration(agent['avg_latency']),
            'Total Cost': format_currency(agent['total_cost']),
            'Errors': agent['error_count'],
            'Last Seen': time_ago(agent['last_seen'])
        })
    
    df_agents = pd.DataFrame(table_data)
    
    # Display table with click interaction
    st.dataframe(
        df_agents,
        use_container_width=True,
        height=400,
        hide_index=True
    )
    
    st.markdown("---")
    
    # Visualizations
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🏥 Agent Health Heatmap")
        
        # Create heatmap data
        health_colors = {
            'healthy': COLORS['success'],
            'degraded': 'yellow',
            'warning': COLORS['warning'],
            'critical': COLORS['error'],
            'unknown': COLORS['neutral']
        }
        
        # Simple grid visualization
        grid_size = min(10, len(agent_details))
        grid_data = []
        
        for i in range(0, len(agent_details), grid_size):
            row = agent_details[i:i+grid_size]
            grid_data.append([
                health_colors.get(a['status'], COLORS['neutral'])
                for a in row
            ])
        
        # Create custom visualization
        fig_health = go.Figure()
        
        for i, row in enumerate(grid_data):
            for j, color in enumerate(row):
                idx = i * grid_size + j
                if idx < len(agent_details):
                    agent = agent_details[idx]
                    fig_health.add_trace(go.Scatter(
                        x=[j],
                        y=[i],
                        mode='markers',
                        marker=dict(
                            size=30,
                            color=color,
                            line=dict(color='white', width=2)
                        ),
                        text=agent['agent_id'][:20],
                        hovertemplate=f"<b>{agent['agent_id']}</b><br>" +
                                    f"Success: {agent['success_rate']:.1f}%<br>" +
                                    f"Events: {agent['total_events']}<br>" +
                                    "<extra></extra>",
                        showlegend=False
                    ))
        
        fig_health.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            height=300,
            margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor='rgba(0,0,0,0)'
        )
        
        st.plotly_chart(fig_health, use_container_width=True)
        
        # Legend
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.markdown(f"🟢 Healthy ({sum(1 for a in agent_details if a['status'] == 'healthy')})")
        col_b.markdown(f"🟡 Degraded ({sum(1 for a in agent_details if a['status'] == 'degraded')})")
        col_c.markdown(f"🟠 Warning ({sum(1 for a in agent_details if a['status'] == 'warning')})")
        col_d.markdown(f"🔴 Critical ({sum(1 for a in agent_details if a['status'] == 'critical')})")
    
    with col2:
        st.markdown("### 🏆 Top Performers")
        
        # Top 10 by success rate
        top_performers = sorted(agent_details, key=lambda x: x['success_rate'], reverse=True)[:10]
        
        top_data = pd.DataFrame([
            {
                'Agent': a['agent_id'][:30],
                'Success Rate': a['success_rate'],
                'Events': a['total_events']
            }
            for a in top_performers
        ])
        
        fig_top = px.bar(
            top_data,
            x='Success Rate',
            y='Agent',
            orientation='h',
            color='Success Rate',
            color_continuous_scale=['red', 'yellow', 'green'],
            text='Success Rate'
        )
        
        fig_top.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_top.update_layout(
            height=350,
            showlegend=False,
            xaxis_title="Success Rate (%)",
            yaxis_title=""
        )
        
        st.plotly_chart(fig_top, use_container_width=True)
    
    st.markdown("---")
    
    # Problem Agents Section
    st.markdown("### ⚠️ Problem Agents")
    
    problem_agents = [
        a for a in agent_details
        if a['status'] in ['warning', 'critical'] or a['error_count'] > 10
    ]
    
    if problem_agents:
        st.warning(f"Found {len(problem_agents)} agents with issues")
        
        problem_data = []
        for agent in problem_agents[:10]:
            # Get alerts for this agent
            agent_alerts = client.get_agent_alerts(agent['agent_id'], unresolved_only=True)
            alert_count = agent_alerts.get('count', 0) if agent_alerts else 0
            
            problem_data.append({
                'Agent ID': agent['agent_id'][:35],
                'Status': get_status_emoji(agent['status']) + " " + agent['status'].title(),
                'Success Rate': f"{agent['success_rate']:.1f}%",
                'Errors': agent['error_count'],
                'Active Alerts': alert_count,
                'Action': '→ View Details'
            })
        
        df_problems = pd.DataFrame(problem_data)
        st.dataframe(df_problems, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No problem agents detected!")
    
    st.markdown("---")
    
    # Statistics Row
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📈 Event Distribution")
        
        # Events by agent (top 10)
        top_by_events = sorted(agent_details, key=lambda x: x['total_events'], reverse=True)[:10]
        
        fig_events = px.bar(
            x=[a['agent_id'][:20] for a in top_by_events],
            y=[a['total_events'] for a in top_by_events],
            labels={'x': 'Agent', 'y': 'Events'},
            color=[a['total_events'] for a in top_by_events],
            color_continuous_scale='Blues'
        )
        
        fig_events.update_layout(
            height=250,
            showlegend=False,
            xaxis_tickangle=-45
        )
        
        st.plotly_chart(fig_events, use_container_width=True)
    
    with col2:
        st.markdown("### 💰 Cost Distribution")
        
        # Cost by agent (top 10)
        top_by_cost = sorted(agent_details, key=lambda x: x['total_cost'], reverse=True)[:10]
        
        fig_cost = px.pie(
            names=[a['agent_id'][:20] for a in top_by_cost],
            values=[a['total_cost'] for a in top_by_cost],
            hole=0.3
        )
        
        fig_cost.update_layout(height=250)
        st.plotly_chart(fig_cost, use_container_width=True)
    
    with col3:
        st.markdown("### ⚡ Latency Comparison")
        
        # Latency comparison (top 10)
        top_by_latency = sorted(agent_details, key=lambda x: x['avg_latency'], reverse=True)[:10]
        
        fig_latency = go.Figure()
        
        fig_latency.add_trace(go.Bar(
            x=[a['agent_id'][:20] for a in top_by_latency],
            y=[a['avg_latency'] for a in top_by_latency],
            marker_color=[
                COLORS['success'] if a['avg_latency'] < 1000
                else COLORS['warning'] if a['avg_latency'] < 2000
                else COLORS['error']
                for a in top_by_latency
            ]
        ))
        
        fig_latency.add_hline(
            y=2000,
            line_dash="dash",
            line_color="red",
            annotation_text="Target: 2000ms"
        )
        
        fig_latency.update_layout(
            height=250,
            showlegend=False,
            xaxis_tickangle=-45,
            yaxis_title="Latency (ms)"
        )
        
        st.plotly_chart(fig_latency, use_container_width=True)

except Exception as e:
    st.error(f"Error loading agents data: {str(e)}")
    st.exception(e)

# Footer
st.markdown("---")
st.markdown(f"*Showing {len(agent_details) if agent_details else 0} agents | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")