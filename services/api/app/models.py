from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime


class AgentEvent(BaseModel):
    """
    Schema for incoming agent events
    """
    agent_id: str = Field(..., min_length=1, max_length=255, description="Unique identifier for the agent")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    event_type: str = Field(..., min_length=1, max_length=50, description="Type of event (e.g., api_call, error, decision)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional event metadata")
    
    @validator('event_type')
    def validate_event_type(cls, v):
        """Ensure event_type is not empty and is lowercase"""
        if not v or not v.strip():
            raise ValueError('event_type cannot be empty')
        return v.lower().strip()
    
    @validator('agent_id')
    def validate_agent_id(cls, v):
        """Ensure agent_id is not empty"""
        if not v or not v.strip():
            raise ValueError('agent_id cannot be empty')
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "gpt-researcher-001",
                "timestamp": "2025-11-10T16:30:00Z",
                "event_type": "api_call",
                "metadata": {
                    "model": "gpt-4",
                    "tokens_used": 350,
                    "latency_ms": 1200,
                    "cost_usd": 0.0105,
                    "success": True
                }
            }
        }


class AgentEventResponse(BaseModel):
    """
    Response after creating an event
    """
    id: int
    agent_id: str
    timestamp: datetime
    event_type: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class EventQueryParams(BaseModel):
    """
    Query parameters for retrieving events
    """
    agent_id: Optional[str] = None
    event_type: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)