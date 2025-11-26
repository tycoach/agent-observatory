import streamlit as st
from config import PAGE_TITLE, PAGE_ICON, LAYOUT

# Page configuration
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=LAYOUT,
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stMetric {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 10px;
    }
    .stButton>button {
        width: 100%;
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px;
    }
    </style>
""", unsafe_allow_html=True)

# Main page
st.title(" Agent Observatory")
st.markdown("### Real-Time Agent Monitoring Dashboard")
st.markdown("---")

st.info(" **Select a page from the sidebar to get started**")

# Quick overview
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ###  Home
    - System health overview
    - Key metrics at a glance
    - Recent alerts summary
    """)

with col2:
    st.markdown("""
    ### Real-Time Monitoring
    - Live event stream
    - Performance metrics
    - Cost tracking
    """)

with col3:
    st.markdown("""
    ###  Agents Overview
    - All agents status
    - Performance comparison
    - Agent health monitoring
    """)

st.markdown("---")

# System info
from utils.api_client import get_api_client

try:
    client = get_api_client()
    health = client.get_health()
    
    if health:
        st.success(" System is online and healthy")
        
        col1, col2, col3, col4 = st.columns(4)
        
        services = health.get('services', {})
        
        with col1:
            db_status = services.get('database', 'unknown')
            st.metric("Database", db_status.upper(), 
                     delta="✓" if db_status == "healthy" else "✗")
        
        with col2:
            redis_status = services.get('redis', 'unknown')
            st.metric("Redis", redis_status.upper(),
                     delta="✓" if redis_status == "healthy" else "✗")
        
        with col3:
            kafka_status = services.get('kafka', 'unknown')
            st.metric("Kafka", kafka_status.upper(),
                     delta="✓" if kafka_status == "healthy" else "✗")
        
        with col4:
            st.metric("API", "ONLINE", delta="✓")
    else:
        st.warning(" Cannot reach API")
        
except Exception as e:
    st.error(f" System health check failed: {str(e)}")