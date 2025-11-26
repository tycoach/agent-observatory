from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text, desc
from typing import List, Optional
import redis
import json
from kafka import KafkaProducer
from kafka.errors import KafkaError

from app.config import get_settings
from app.database import get_db
from app.models import AgentEvent, AgentEventResponse
from app.db_models import AgentEventDB
from app.cache import cache
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.3.0",  
    description="Real-Time AI Agent Observability Platform with Kafka Streaming"
)

# Initialize Kafka Producer
kafka_producer = None

try:
    kafka_producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
        acks='all',  # Wait for all replicas
        retries=3,
        max_in_flight_requests_per_connection=1
    )
    print(f"Kafka producer connected to {settings.kafka_bootstrap_servers}")
except Exception as e:
    print(f" Kafka producer initialization failed: {e}")
    print("  API will work without Kafka (fallback mode)")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if kafka_producer:
        kafka_producer.flush()
        kafka_producer.close()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Agent Observatory API",
        "version": "0.3.0",
        "environment": settings.environment,
        "kafka_enabled": kafka_producer is not None
    }


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "services": {}
    }
    
    # Check database
    try:
        db.execute(text("SELECT 1"))
        health_status["services"]["database"] = "healthy"
    except Exception as e:
        health_status["services"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # Check Redis
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # Check Kafka
    if kafka_producer:
        try:
            # Try to get metadata (lightweight check)
            kafka_producer.bootstrap_connected()
            health_status["services"]["kafka"] = "healthy"
        except Exception as e:
            health_status["services"]["kafka"] = f"unhealthy: {str(e)}"
    else:
        health_status["services"]["kafka"] = "disabled"
    
    return health_status


def publish_to_kafka(event_data: dict) -> bool:
    """Publish event to Kafka topic"""
    if not kafka_producer:
        return False
    
    try:
        future = kafka_producer.send('agent-events', value=event_data)
        # Wait for send to complete (with timeout)
        record_metadata = future.get(timeout=2)
        print(f" Event sent to Kafka: topic={record_metadata.topic}, partition={record_metadata.partition}, offset={record_metadata.offset}")
        return True
    except KafkaError as e:
        print(f" Kafka publish error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error publishing to Kafka: {e}")
        return False


def invalidate_agent_cache(agent_id: str):
    """Invalidate all cache entries for an agent"""
    cache.delete_pattern(f"agent:{agent_id}:*")
    cache.delete("events:all")


@app.post("/events", response_model=AgentEventResponse, status_code=201)
async def create_event(
    event: AgentEvent,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    use_kafka: bool = Query(True, description="Use Kafka for async processing")
):
    """
    Create a new agent event
    
    - If Kafka is enabled and use_kafka=True: Publishes to Kafka for async processing
    - If Kafka is disabled: Writes directly to database (fallback)
    """
    
    # Prepare event data
    event_data = {
        "agent_id": event.agent_id,
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type,
        "metadata": event.metadata
    }
    
    # Try Kafka first (async path)
    if use_kafka and kafka_producer:
        kafka_success = publish_to_kafka(event_data)
        
        if kafka_success:
            # Return immediately - event will be processed by stream processor
            return {
                "id": 0,  # Will be assigned by processor
                "agent_id": event.agent_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "created_at": event.timestamp,
                "processing": "async"
            }
    
    # Fallback to direct database write (sync path)
    try:
        db_event = AgentEventDB(
            agent_id=event.agent_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            event_metadata=event.metadata
        )
        
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        
        # Invalidate cache in background
        background_tasks.add_task(invalidate_agent_cache, event.agent_id)
        
        # Add to recent events cache
        event_dict = {
            "id": db_event.id,
            "agent_id": db_event.agent_id,
            "timestamp": str(db_event.timestamp),
            "event_type": db_event.event_type,
            "metadata": event.metadata
        }
        background_tasks.add_task(cache.add_recent_event, event.agent_id, event_dict)
        
        return db_event
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create event: {str(e)}"
        )


   
@app.get("/events")
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get events with pagination
    Returns: {"events": [...], "count": N}
    """
    try:
        # Get events with metadata
        result = db.execute(
            text("""
                SELECT 
                    id, 
                    agent_id, 
                    timestamp, 
                    event_type, 
                    event_metadata,
                    created_at
                FROM agent_events
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset}
        ).fetchall()
        
        events = []
        for row in result:
            event = {
                "id": row[0],
                "agent_id": row[1],
                "timestamp": str(row[2]),
                "event_type": row[3],
                "event_metadata": row[4] if row[4] else {},  # Handle NULL
                "created_at": str(row[5])
            }
            events.append(event)
        
        # Return in expected format: {"events": [...], "count": N}
        return {
            "events": events,
            "count": len(events)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving events: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve events: {str(e)}"
        )
    
@app.get("/events/summary")
async def get_events_summary(db: Session = Depends(get_db)):
    """
    Get summary statistics for all events
    """
    try:
        # Get total events
        total_result = db.execute(text("SELECT COUNT(*) FROM agent_events")).fetchone()
        total_events = total_result[0] if total_result else 0
        
        # Get unique agents
        agents_result = db.execute(text("SELECT COUNT(DISTINCT agent_id) FROM agent_events")).fetchone()
        unique_agents = agents_result[0] if agents_result else 0
        
        # Get success rate
        success_result = db.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE event_metadata->>'success' = 'true') as success_count,
                COUNT(*) as total
            FROM agent_events
            WHERE event_metadata->>'success' IS NOT NULL
        """)).fetchone()
        
        success_rate = 0
        if success_result and success_result[1] > 0:
            success_rate = (success_result[0] / success_result[1]) * 100
        
        # Get total cost
        cost_result = db.execute(text("""
            SELECT COALESCE(SUM(CAST(event_metadata->>'cost_usd' AS FLOAT)), 0)
            FROM agent_events
            WHERE event_metadata->>'cost_usd' IS NOT NULL
        """)).fetchone()
        total_cost = cost_result[0] if cost_result else 0
        
        return {
            "total_events": total_events,
            "unique_agents": unique_agents,
            "success_rate": round(success_rate, 2),
            "total_cost": round(total_cost, 2)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get events summary: {str(e)}"
        )

@app.get("/events/{event_id}", response_model=AgentEventResponse)
async def get_event(event_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific event by ID"""
    event = db.query(AgentEventDB).filter(AgentEventDB.id == event_id).first()
    
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event with id {event_id} not found"
        )
    
    return event


@app.get("/agents/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    use_cache: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Get statistics for a specific agent (with caching)"""
    cache_key = f"agent:{agent_id}:stats"
    
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return {**cached, "cached": True}
    
    try:
        total_events = db.query(AgentEventDB).filter(
            AgentEventDB.agent_id == agent_id
        ).count()
        
        event_types = db.execute(
            text("""
                SELECT event_type, COUNT(*) as count
                FROM agent_events
                WHERE agent_id = :agent_id
                GROUP BY event_type
                ORDER BY count DESC
            """),
            {"agent_id": agent_id}
        ).fetchall()
        
        latest_event = db.query(AgentEventDB).filter(
            AgentEventDB.agent_id == agent_id
        ).order_by(desc(AgentEventDB.timestamp)).first()
        
        stats = {
            "agent_id": agent_id,
            "total_events": total_events,
            "event_types": [
                {"type": row[0], "count": row[1]} 
                for row in event_types
            ],
            "latest_event_timestamp": latest_event.timestamp if latest_event else None,
            "cached": False
        }
        
        if use_cache:
            cache.set(cache_key, stats, ttl=cache.AGENT_STATS_TTL)
        
        return stats
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve agent stats: {str(e)}"
        )


@app.get("/agents/{agent_id}/recent")
async def get_agent_recent_events(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get recent events for an agent"""
    cached = cache.get_recent_events(agent_id, limit)
    if cached:
        return {"agent_id": agent_id, "events": cached, "cached": True}
    
    try:
        events = db.query(AgentEventDB).filter(
            AgentEventDB.agent_id == agent_id
        ).order_by(desc(AgentEventDB.timestamp)).limit(limit).all()
        
        events_list = [
            {
                "id": e.id,
                "agent_id": e.agent_id,
                "timestamp": str(e.timestamp),
                "event_type": e.event_type,
                "metadata": e.event_metadata
            }
            for e in events
        ]
        
        return {"agent_id": agent_id, "events": events_list, "cached": False}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve recent events: {str(e)}"
        )


@app.get("/metrics/hourly")
async def get_hourly_metrics(
    agent_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get hourly metrics from materialized view"""
    cache_key = f"metrics:hourly:agent:{agent_id}:hours:{hours}"
    
    cached = cache.get(cache_key)
    if cached:
        return {"metrics": cached, "cached": True}
    
    try:
        query = """
            SELECT 
                agent_id, hour, event_count, error_count, api_call_count,
                avg_tokens, total_tokens, avg_latency_ms, total_cost_usd
            FROM hourly_agent_metrics
            WHERE hour >= NOW() - INTERVAL '%s hours'
        """
        
        if agent_id:
            query += " AND agent_id = :agent_id"
            query += " ORDER BY hour DESC"
            result = db.execute(text(query % hours), {"agent_id": agent_id}).fetchall()
        else:
            query += " ORDER BY hour DESC, agent_id"
            result = db.execute(text(query % hours)).fetchall()
        
        metrics = [
            {
                "agent_id": row[0],
                "hour": str(row[1]),
                "event_count": row[2],
                "error_count": row[3],
                "api_call_count": row[4],
                "avg_tokens": float(row[5]) if row[5] else None,
                "total_tokens": row[6],
                "avg_latency_ms": float(row[7]) if row[7] else None,
                "total_cost_usd": float(row[8]) if row[8] else None
            }
            for row in result
        ]
        
        cache.set(cache_key, metrics, ttl=300)
        
        return {"metrics": metrics, "cached": False}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve hourly metrics: {str(e)}"
        )


@app.post("/admin/refresh-views")
async def refresh_materialized_views(db: Session = Depends(get_db)):
    """Refresh all materialized views"""
    try:
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY hourly_agent_metrics"))
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY daily_agent_metrics"))
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY agent_summary"))
        db.commit()
        
        cache.delete_pattern("metrics:*")
        
        return {"status": "success", "message": "Materialized views refreshed"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh views: {str(e)}"
        )


@app.get("/cache/stats")
async def get_cache_stats():
    """Get Redis cache statistics"""
    try:
        r = redis.from_url(settings.redis_url)
        info = r.info('stats')
        
        return {
            "total_connections_received": info.get('total_connections_received'),
            "total_commands_processed": info.get('total_commands_processed'),
            "keyspace_hits": info.get('keyspace_hits'),
            "keyspace_misses": info.get('keyspace_misses'),
            "hit_rate": round(
                info.get('keyspace_hits', 0) / 
                max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1) * 100,
                2
            )
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache stats: {str(e)}"
        )
    
#============================================
# AGENTS ENDPOINTS
# ============================================

@app.get("/agents")
async def get_all_agents(db: Session = Depends(get_db)):
    """
    Get list of all unique agents
    """
    try:
        result = db.execute(text("""
            SELECT 
                agent_id,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                COUNT(*) as event_count
            FROM agent_events
            GROUP BY agent_id
            ORDER BY event_count DESC
        """)).fetchall()
        
        agents = [
            {
                "agent_id": row[0],
                "first_seen": str(row[1]),
                "last_seen": str(row[2]),
                "event_count": row[3]
            }
            for row in result
        ]
        
        return agents
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve agents: {str(e)}"
        )
    

# ============================================
# DLQ ENDPOINTS
# ============================================

@app.get("/dlq/stats")
async def get_dlq_stats():
    """Get Dead Letter Queue statistics"""
    try:
        stats = {
            "total_dlq_events": int(cache.redis_client.get('dlq:total_events') or 0),
            "permanent_failures": int(cache.redis_client.get('dlq:permanent_failures') or 0),
            "recent_failures": []
        }
        
        # Get recent failures
        recent = cache.redis_client.lrange('dlq:recent_failures', 0, 9)
        stats["recent_failures"] = [json.loads(f) for f in recent] if recent else []
        
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get DLQ stats: {str(e)}"
        )


@app.get("/dlq/events")
async def get_dlq_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Get events from Dead Letter Queue
    """
    try:
        query = """
            SELECT 
                id, agent_id, original_event, error_message, 
                retry_count, failed_at, stored_at, status
            FROM dlq_events
        """
        
        conditions = []
        params = {}
        
        if status:
            conditions.append("status = :status")
            params["status"] = status
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY stored_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        result = db.execute(text(query), params).fetchall()
        
        events = [
            {
                "id": row[0],
                "agent_id": row[1],
                "original_event": row[2],
                "error_message": row[3],
                "retry_count": row[4],
                "failed_at": str(row[5]) if row[5] else None,
                "stored_at": str(row[6]) if row[6] else None,
                "status": row[7]
            }
            for row in result
        ]
        
        return {"events": events, "count": len(events)}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve DLQ events: {str(e)}"
        )


@app.get("/dlq/events/{event_id}")
async def get_dlq_event(event_id: int, db: Session = Depends(get_db)):
    """Get specific DLQ event by ID"""
    try:
        result = db.execute(
            text("""
                SELECT 
                    id, agent_id, original_event, error_message, 
                    retry_count, failed_at, stored_at, status
                FROM dlq_events
                WHERE id = :event_id
            """),
            {"event_id": event_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="DLQ event not found")
        
        return {
            "id": result[0],
            "agent_id": result[1],
            "original_event": result[2],
            "error_message": result[3],
            "retry_count": result[4],
            "failed_at": str(result[5]) if result[5] else None,
            "stored_at": str(result[6]) if result[6] else None,
            "status": result[7]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve DLQ event: {str(e)}"
        )


@app.post("/dlq/events/{event_id}/retry")
async def retry_dlq_event(event_id: int, db: Session = Depends(get_db)):
    """
    Manually retry a failed event from DLQ
    """
    try:
        # Get the DLQ event
        result = db.execute(
            text("""
                SELECT original_event, status
                FROM dlq_events
                WHERE id = :event_id
            """),
            {"event_id": event_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="DLQ event not found")
        
        original_event = result[0]
        status = result[1]
        
        if status == "recovered":
            raise HTTPException(status_code=400, detail="Event already recovered")
        
        # Try to insert the event
        cursor = db.connection().cursor()
        cursor.execute("""
            INSERT INTO agent_events (agent_id, timestamp, event_type, event_metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            original_event['agent_id'],
            original_event['timestamp'],
            original_event['event_type'],
            json.dumps(original_event.get('metadata'))
        ))
        
        new_event_id = cursor.fetchone()[0]
        
        # Update DLQ status
        db.execute(
            text("""
                UPDATE dlq_events
                SET status = 'recovered'
                WHERE id = :event_id
            """),
            {"event_id": event_id}
        )
        
        db.commit()
        
        return {
            "status": "success",
            "message": "Event recovered successfully",
            "new_event_id": new_event_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retry event: {str(e)}"
        )


@app.delete("/dlq/events/{event_id}")
async def delete_dlq_event(event_id: int, db: Session = Depends(get_db)):
    """Delete a DLQ event"""
    try:
        result = db.execute(
            text("DELETE FROM dlq_events WHERE id = :event_id RETURNING id"),
            {"event_id": event_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="DLQ event not found")
        
        db.commit()
        
        return {"status": "success", "message": "DLQ event deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete DLQ event: {str(e)}"
        )
    
# ============================================
# ALERTS ENDPOINTS
# ============================================

@app.get("/alerts/stats")
async def get_alerts_stats():
    """Get alerts statistics"""
    try:
        # Try to get from Redis, fallback to empty if fails
        try:
            total_alerts = cache.redis_client.get('alerts:total')
        except AttributeError:
            # Redis not properly configured
            total_alerts = None
        
        stats = {
            "total_alerts": int(total_alerts) if total_alerts else 0,
            "by_type": {},
            "by_severity": {},
            "recent_count": 0
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting alerts stats: {e}")
        return {
            "total_alerts": 0,
            "by_type": {},
            "by_severity": {},
            "recent_count": 0
        }


@app.get("/alerts/recent")
async def get_recent_alerts(limit: int = Query(50, ge=1, le=100)):
    """Get recent alerts from Redis"""
    try:
        try:
            alerts_json = cache.redis_client.lrange('alerts:recent', 0, limit - 1)
            alerts = [json.loads(a) for a in alerts_json] if alerts_json else []
        except Exception:
            alerts = []
        
        return {"alerts": alerts, "count": len(alerts)}
        
    except Exception as e:
        logger.error(f"Error getting recent alerts: {e}")
        # Return empty list instead of error
        return {"alerts": [], "count": 0}


@app.get("/alerts")
async def get_alerts(
    agent_id: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    resolved: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get alerts with filtering
    """
    try:
        # Check if table exists first
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'alerts'
            )
        """)).fetchone()
        
        if not table_check or not table_check[0]:
            return {"alerts": [], "count": 0}
        
        query = """
            SELECT 
                id, agent_id, alert_type, severity, message, 
                metadata, triggered_at, acknowledged, acknowledged_at,
                acknowledged_by, resolved, resolved_at, created_at
            FROM alerts
            WHERE 1=1
        """
        
        params = {}
        
        if agent_id:
            query += " AND agent_id = :agent_id"
            params["agent_id"] = agent_id
        
        if alert_type:
            query += " AND alert_type = :alert_type"
            params["alert_type"] = alert_type
        
        if severity:
            query += " AND severity = :severity"
            params["severity"] = severity
        
        if acknowledged is not None:
            query += " AND acknowledged = :acknowledged"
            params["acknowledged"] = acknowledged
        
        if resolved is not None:
            query += " AND resolved = :resolved"
            params["resolved"] = resolved
        
        query += " ORDER BY triggered_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        result = db.execute(text(query), params).fetchall()
        
        alerts = [
            {
                "id": row[0],
                "agent_id": row[1],
                "alert_type": row[2],
                "severity": row[3],
                "message": row[4],
                "metadata": row[5],
                "triggered_at": str(row[6]),
                "acknowledged": row[7],
                "acknowledged_at": str(row[8]) if row[8] else None,
                "acknowledged_by": row[9],
                "resolved": row[10],
                "resolved_at": str(row[11]) if row[11] else None,
                "created_at": str(row[12])
            }
            for row in result
        ]
        
        return {"alerts": alerts, "count": len(alerts)}
    
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}")
        return {"alerts": [], "count": 0}


@app.get("/alerts")
async def get_alerts(
    agent_id: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    resolved: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get alerts with filtering
    """
    try:
        query = """
            SELECT 
                id, agent_id, alert_type, severity, message, 
                metadata, triggered_at, acknowledged, acknowledged_at,
                acknowledged_by, resolved, resolved_at, created_at
            FROM alerts
            WHERE 1=1
        """
        
        params = {}
        
        if agent_id:
            query += " AND agent_id = :agent_id"
            params["agent_id"] = agent_id
        
        if alert_type:
            query += " AND alert_type = :alert_type"
            params["alert_type"] = alert_type
        
        if severity:
            query += " AND severity = :severity"
            params["severity"] = severity
        
        if acknowledged is not None:
            query += " AND acknowledged = :acknowledged"
            params["acknowledged"] = acknowledged
        
        if resolved is not None:
            query += " AND resolved = :resolved"
            params["resolved"] = resolved
        
        query += " ORDER BY triggered_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        result = db.execute(text(query), params).fetchall()
        
        alerts = [
            {
                "id": row[0],
                "agent_id": row[1],
                "alert_type": row[2],
                "severity": row[3],
                "message": row[4],
                "metadata": row[5],
                "triggered_at": str(row[6]),
                "acknowledged": row[7],
                "acknowledged_at": str(row[8]) if row[8] else None,
                "acknowledged_by": row[9],
                "resolved": row[10],
                "resolved_at": str(row[11]) if row[11] else None,
                "created_at": str(row[12])
            }
            for row in result
        ]
        
        return {"alerts": alerts, "count": len(alerts)}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve alerts: {str(e)}"
        )


@app.get("/alerts/{alert_id}")
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """Get specific alert by ID"""
    try:
        result = db.execute(
            text("""
                SELECT 
                    id, agent_id, alert_type, severity, message, 
                    metadata, triggered_at, acknowledged, acknowledged_at,
                    acknowledged_by, resolved, resolved_at, created_at
                FROM alerts
                WHERE id = :alert_id
            """),
            {"alert_id": alert_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {
            "id": result[0],
            "agent_id": result[1],
            "alert_type": result[2],
            "severity": result[3],
            "message": result[4],
            "metadata": result[5],
            "triggered_at": str(result[6]),
            "acknowledged": result[7],
            "acknowledged_at": str(result[8]) if result[8] else None,
            "acknowledged_by": result[9],
            "resolved": result[10],
            "resolved_at": str(result[11]) if result[11] else None,
            "created_at": str(result[12])
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve alert: {str(e)}"
        )


@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    acknowledged_by: str = Query(..., description="Name/ID of person acknowledging"),
    db: Session = Depends(get_db)
):
    """Acknowledge an alert"""
    try:
        result = db.execute(
            text("""
                UPDATE alerts
                SET acknowledged = TRUE,
                    acknowledged_at = NOW(),
                    acknowledged_by = :acknowledged_by
                WHERE id = :alert_id AND acknowledged = FALSE
                RETURNING id
            """),
            {"alert_id": alert_id, "acknowledged_by": acknowledged_by}
        ).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail="Alert not found or already acknowledged"
            )
        
        db.commit()
        
        return {
            "status": "success",
            "message": "Alert acknowledged",
            "alert_id": alert_id,
            "acknowledged_by": acknowledged_by
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to acknowledge alert: {str(e)}"
        )


@app.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Mark an alert as resolved"""
    try:
        result = db.execute(
            text("""
                UPDATE alerts
                SET resolved = TRUE,
                    resolved_at = NOW()
                WHERE id = :alert_id AND resolved = FALSE
                RETURNING id
            """),
            {"alert_id": alert_id}
        ).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail="Alert not found or already resolved"
            )
        
        db.commit()
        
        return {
            "status": "success",
            "message": "Alert resolved",
            "alert_id": alert_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve alert: {str(e)}"
        )


@app.get("/agents/{agent_id}/alerts")
async def get_agent_alerts(
    agent_id: str,
    unresolved_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get alerts for a specific agent"""
    try:
        query = """
            SELECT 
                id, alert_type, severity, message, triggered_at, 
                acknowledged, resolved
            FROM alerts
            WHERE agent_id = :agent_id
        """
        
        if unresolved_only:
            query += " AND resolved = FALSE"
        
        query += " ORDER BY triggered_at DESC LIMIT :limit"
        
        result = db.execute(
            text(query),
            {"agent_id": agent_id, "limit": limit}
        ).fetchall()
        
        alerts = [
            {
                "id": row[0],
                "alert_type": row[1],
                "severity": row[2],
                "message": row[3],
                "triggered_at": str(row[4]),
                "acknowledged": row[5],
                "resolved": row[6]
            }
            for row in result
        ]
        
        # Get summary stats
        stats_query = """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE resolved = FALSE) as unresolved,
                COUNT(*) FILTER (WHERE acknowledged = FALSE AND resolved = FALSE) as unacknowledged
            FROM alerts
            WHERE agent_id = :agent_id
        """
        
        stats = db.execute(text(stats_query), {"agent_id": agent_id}).fetchone()
        
        return {
            "agent_id": agent_id,
            "alerts": alerts,
            "count": len(alerts),
            "stats": {
                "total": stats[0],
                "unresolved": stats[1],
                "unacknowledged": stats[2]
            }
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve agent alerts: {str(e)}"
        )


@app.get("/alerts/summary/by-type")
async def get_alerts_summary_by_type(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get alerts summary grouped by type"""
    try:
        result = db.execute(
            text("""
                SELECT 
                    alert_type,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE severity = 'critical') as critical,
                    COUNT(*) FILTER (WHERE severity = 'warning') as warning,
                    COUNT(*) FILTER (WHERE severity = 'info') as info,
                    COUNT(*) FILTER (WHERE resolved = FALSE) as unresolved
                FROM alerts
                WHERE triggered_at >= NOW() - INTERVAL '%s hours'
                GROUP BY alert_type
                ORDER BY total DESC
            """ % hours)
        ).fetchall()
        
        summary = [
            {
                "alert_type": row[0],
                "total": row[1],
                "critical": row[2],
                "warning": row[3],
                "info": row[4],
                "unresolved": row[5]
            }
            for row in result
        ]
        
        return {"summary": summary, "hours": hours}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve alerts summary: {str(e)}"
        )