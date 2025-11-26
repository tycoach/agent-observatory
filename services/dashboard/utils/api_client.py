import requests
from typing import Optional, Dict, List
import streamlit as st
from config import API_BASE_URL

class APIClient:
    """Client for interacting with Agent Observatory API"""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request"""
        try:
            response = self.session.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Return empty dict instead of showing error
            return {}
    
    def _post(self, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make POST request"""
        try:
            response = self.session.post(
                f"{self.base_url}{endpoint}",
                json=data,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {}
    
    # Health endpoints
    def get_health(self) -> Dict:
        """Get system health"""
        return self._get("/health")
    
    # Event endpoints
    def get_events(self, limit: int = 100, offset: int = 0) -> Dict:
        """Get events"""
        result = self._get("/events", params={"limit": limit, "offset": offset})
        # Ensure it returns expected format
        if not isinstance(result, dict):
            return {"events": [], "count": 0}
        if "events" not in result:
            result["events"] = []
        return result
    
    def get_events_summary(self) -> Dict:
        """Get events summary"""
        result = self._get("/events/summary")
        # Return default structure if empty
        if not result:
            return {"total_events": 0, "unique_agents": 0}
        return result
    
    # Agent endpoints
    def get_agents(self) -> List[Dict]:
        """Get all agents"""
        result = self._get("/agents")
        # Return empty list if not a list
        if not isinstance(result, list):
            return []
        return result
    
    def get_agent_stats(self, agent_id: str) -> Dict:
        """Get stats for specific agent"""
        result = self._get(f"/agents/{agent_id}/stats")
        # Return default stats if empty
        if not result:
            return {
                "total_events": 0,
                "success_rate": 0,
                "avg_latency_ms": 0,
                "total_cost": 0,
                "error_count": 0
            }
        return result
    
    def get_agent_events(self, agent_id: str, limit: int = 50) -> Dict:
        """Get events for specific agent"""
        result = self._get(f"/agents/{agent_id}/events", params={"limit": limit})
        if not isinstance(result, dict):
            return {"events": [], "count": 0}
        if "events" not in result:
            result["events"] = []
        return result
    
    def get_agent_alerts(self, agent_id: str, unresolved_only: bool = False) -> Dict:
        """Get alerts for specific agent"""
        result = self._get(
            f"/agents/{agent_id}/alerts",
            params={"unresolved_only": unresolved_only}
        )
        if not isinstance(result, dict):
            return {"alerts": [], "count": 0, "stats": {"total": 0, "unresolved": 0, "unacknowledged": 0}}
        return result
    
    # Alert endpoints
    def get_alerts_stats(self) -> Dict:
        """Get alerts statistics"""
        result = self._get("/alerts/stats")
        if not result:
            return {"total_alerts": 0, "by_type": {}, "by_severity": {}, "recent_count": 0}
        return result
    
    def get_alerts_recent(self, limit: int = 50) -> Dict:
        """Get recent alerts"""
        result = self._get("/alerts/recent", params={"limit": limit})
        if not isinstance(result, dict):
            return {"alerts": [], "count": 0}
        if "alerts" not in result:
            result["alerts"] = []
        return result
    
    def get_alerts(self, **kwargs) -> Dict:
        """Get alerts with filters"""
        result = self._get("/alerts", params=kwargs)
        if not isinstance(result, dict):
            return {"alerts": [], "count": 0}
        return result
    
    def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> Dict:
        """Acknowledge an alert"""
        return self._post(
            f"/alerts/{alert_id}/acknowledge?acknowledged_by={acknowledged_by}"
        )
    
    def resolve_alert(self, alert_id: int) -> Dict:
        """Resolve an alert"""
        return self._post(f"/alerts/{alert_id}/resolve")
    
    # Analytics endpoints
    def get_analytics_timespan(self, hours: int = 24) -> Dict:
        """Get analytics for timespan"""
        return self._get("/analytics/timespan", params={"hours": hours})
    
    # DLQ endpoints
    def get_dlq_stats(self) -> Dict:
        """Get DLQ statistics"""
        result = self._get("/dlq/stats")
        if not result:
            return {"total_dlq_events": 0, "permanent_failures": 0, "recent_failures": []}
        return result
    
    def get_dlq_events(self, limit: int = 100) -> Dict:
        """Get DLQ events"""
        result = self._get("/dlq/events", params={"limit": limit})
        if not isinstance(result, dict):
            return {"events": [], "count": 0}
        return result


# Create global client instance
@st.cache_resource
def get_api_client():
    """Get cached API client instance"""
    return APIClient()