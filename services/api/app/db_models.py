from sqlalchemy import Column, BigInteger, String, DateTime, JSON, Index
from sqlalchemy.sql import func
from app.database import Base


class AgentEventDB(Base):
    """
    Database model for agent events
    """
    __tablename__ = "agent_events"
    
    id = Column(BigInteger, primary_key=True, index=True)
    agent_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_metadata = Column(JSON, nullable=True)  # ← CHANGED FROM 'metadata' to 'event_metadata'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Composite index for common queries
    __table_args__ = (
        Index('idx_agent_timestamp', 'agent_id', 'timestamp'),
    )