import os
import json
import time
import logging
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import redis
import psycopg2
from collections import deque, defaultdict
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'agent-events')
KAFKA_CONSUMER_GROUP = 'alerts-processor'
DATABASE_URL = os.getenv('DATABASE_URL')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

# Alert thresholds
ERROR_RATE_THRESHOLD = 0.2  # 20%
ERROR_WINDOW_SIZE = 100
HIGH_LATENCY_THRESHOLD = 3000  # 3 seconds
HIGH_TOKEN_THRESHOLD = 5000
COST_SPIKE_THRESHOLD = 0.5  # $0.50
COST_WINDOW = 300  # 5 minutes
INACTIVITY_THRESHOLD = 600  # 10 minutes
REPEATED_ERROR_THRESHOLD = 5  # Same error 5 times
REPEATED_ERROR_WINDOW = 600  # 10 minutes

# Alert cooldown (don't trigger same alert type for same agent within this time)
ALERT_COOLDOWN = 300  # 5 minutes


class AlertsProcessor:
    """
    Enhanced alerts processor with multiple alert types
    """
    
    def __init__(self):
        self.consumer = None
        self.producer = None
        self.db_conn = None
        self.redis_client = None
        
        # Tracking data structures
        self.agent_windows = {}  # Rolling windows per agent for error rate
        self.agent_costs = defaultdict(list)  # Cost tracking per agent
        self.agent_last_seen = {}  # Last event timestamp per agent
        self.agent_errors = defaultdict(lambda: defaultdict(list))  # Error tracking
        self.alert_cooldowns = {}  # Alert cooldown tracking
        
        # Statistics
        self.total_events_processed = 0
        self.total_alerts_triggered = 0
        self.alerts_by_type = defaultdict(int)
        
    def connect_kafka(self):
        """Connect to Kafka"""
        logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
        
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self.consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    group_id=KAFKA_CONSUMER_GROUP,
                    auto_offset_reset='latest',
                    enable_auto_commit=True,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
                )
                
                # Producer for potential alert events
                self.producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
                )
                
                logger.info(f"✓ Connected to Kafka")
                return True
            except KafkaError as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        return False
    
    def connect_database(self):
        """Connect to PostgreSQL"""
        logger.info("Connecting to database...")
        
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self.db_conn = psycopg2.connect(DATABASE_URL)
                self.db_conn.autocommit = False
                logger.info("✓ Connected to database")
                return True
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        return False
    
    def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            logger.info("✓ Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return False
    
    def can_trigger_alert(self, agent_id: str, alert_type: str) -> bool:
        """Check if alert can be triggered (respects cooldown)"""
        key = f"{agent_id}:{alert_type}"
        last_trigger = self.alert_cooldowns.get(key, 0)
        
        if time.time() - last_trigger < ALERT_COOLDOWN:
            return False
        
        self.alert_cooldowns[key] = time.time()
        return True
    
    def trigger_alert(
        self, 
        agent_id: str, 
        alert_type: str, 
        severity: str, 
        message: str, 
        metadata: dict
    ):
        """Trigger an alert and store it"""
        
        # Check cooldown
        if not self.can_trigger_alert(agent_id, alert_type):
            return
        
        try:
            alert = {
                "agent_id": agent_id,
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                "metadata": metadata,
                "triggered_at": datetime.utcnow().isoformat()
            }
            
            # Store in database
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO alerts 
                (agent_id, alert_type, severity, message, metadata, triggered_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                agent_id,
                alert_type,
                severity,
                message,
                json.dumps(metadata),
                alert['triggered_at']
            ))
            
            alert_id = cursor.fetchone()[0]
            self.db_conn.commit()
            cursor.close()
            
            alert['id'] = alert_id
            
            # Store in Redis (recent alerts)
            self.redis_client.lpush('alerts:recent', json.dumps(alert))
            self.redis_client.ltrim('alerts:recent', 0, 99)  # Keep last 100
            
            # Store per-agent alerts
            self.redis_client.lpush(f'alerts:agent:{agent_id}', json.dumps(alert))
            self.redis_client.ltrim(f'alerts:agent:{agent_id}', 0, 49)  # Keep last 50
            
            # Update counters
            self.redis_client.incr('alerts:total')
            self.redis_client.incr(f'alerts:by_type:{alert_type}')
            self.redis_client.incr(f'alerts:by_severity:{severity}')
            
            # Log alert with emoji based on severity
            emoji = {"critical": "🔴", "warning": "🟠", "info": "🟡"}.get(severity, "⚪")
            logger.warning(f"{emoji} ALERT [{severity.upper()}] {agent_id}: {message}")
            
            # Update statistics
            self.total_alerts_triggered += 1
            self.alerts_by_type[alert_type] += 1
            
        except Exception as e:
            logger.error(f"Failed to trigger alert: {e}")
            self.db_conn.rollback()
    
    # ========================================
    # Alert Type : Error Rate
    # ========================================
    def check_error_rate(self, agent_id: str, success: bool):
        """Monitor error rate"""
        if agent_id not in self.agent_windows:
            self.agent_windows[agent_id] = deque(maxlen=ERROR_WINDOW_SIZE)
        
        self.agent_windows[agent_id].append(1 if success else 0)
        
        if len(self.agent_windows[agent_id]) >= ERROR_WINDOW_SIZE:
            success_count = sum(self.agent_windows[agent_id])
            error_rate = 1 - (success_count / ERROR_WINDOW_SIZE)
            
            if error_rate >= ERROR_RATE_THRESHOLD:
                severity = "critical" if error_rate >= 0.5 else "warning"
                self.trigger_alert(
                    agent_id=agent_id,
                    alert_type="high_error_rate",
                    severity=severity,
                    message=f"Error rate: {error_rate*100:.1f}% (threshold: {ERROR_RATE_THRESHOLD*100}%)",
                    metadata={
                        "error_rate": error_rate,
                        "window_size": ERROR_WINDOW_SIZE,
                        "success_count": success_count,
                        "error_count": ERROR_WINDOW_SIZE - success_count
                    }
                )
    
    # ========================================
    # Alert Type : High Latency
    # ========================================
    def check_high_latency(self, agent_id: str, latency_ms: int):
        """Monitor high latency"""
        if latency_ms > HIGH_LATENCY_THRESHOLD:
            severity = "critical" if latency_ms > HIGH_LATENCY_THRESHOLD * 2 else "warning"
            self.trigger_alert(
                agent_id=agent_id,
                alert_type="high_latency",
                severity=severity,
                message=f"Latency: {latency_ms}ms (threshold: {HIGH_LATENCY_THRESHOLD}ms)",
                metadata={
                    "latency_ms": latency_ms,
                    "threshold": HIGH_LATENCY_THRESHOLD
                }
            )
    
    # ========================================
    # Alert Type : Cost Spike
    # ========================================
    def check_cost_spike(self, agent_id: str, cost: float, timestamp: datetime):
        """Monitor cost spikes"""
        # Add cost to tracking
        self.agent_costs[agent_id].append((timestamp, cost))
        
        # Remove old costs outside window
        cutoff_time = timestamp - timedelta(seconds=COST_WINDOW)
        self.agent_costs[agent_id] = [
            (ts, c) for ts, c in self.agent_costs[agent_id]
            if ts > cutoff_time
        ]
        
        # Calculate total cost in window
        total_cost = sum(c for _, c in self.agent_costs[agent_id])
        
        if total_cost > COST_SPIKE_THRESHOLD:
            self.trigger_alert(
                agent_id=agent_id,
                alert_type="cost_spike",
                severity="warning",
                message=f"${total_cost:.2f} spent in {COST_WINDOW//60} minutes (threshold: ${COST_SPIKE_THRESHOLD})",
                metadata={
                    "total_cost": total_cost,
                    "window_seconds": COST_WINDOW,
                    "event_count": len(self.agent_costs[agent_id]),
                    "threshold": COST_SPIKE_THRESHOLD
                }
            )
    
    # ========================================
    # Alert Type : High Token Usage
    # ========================================
    def check_high_token_usage(self, agent_id: str, tokens: int):
        """Monitor high token usage"""
        if tokens > HIGH_TOKEN_THRESHOLD:
            self.trigger_alert(
                agent_id=agent_id,
                alert_type="high_token_usage",
                severity="info",
                message=f"High token usage: {tokens} tokens (threshold: {HIGH_TOKEN_THRESHOLD})",
                metadata={
                    "tokens_used": tokens,
                    "threshold": HIGH_TOKEN_THRESHOLD
                }
            )
    
    # ========================================
    # Alert Type : Repeated Errors
    # ========================================
    def check_repeated_errors(self, agent_id: str, error_type: str, timestamp: datetime):
        """Monitor repeated errors"""
        # Track error occurrences
        self.agent_errors[agent_id][error_type].append(timestamp)
        
        # Remove old errors outside window
        cutoff_time = timestamp - timedelta(seconds=REPEATED_ERROR_WINDOW)
        self.agent_errors[agent_id][error_type] = [
            ts for ts in self.agent_errors[agent_id][error_type]
            if ts > cutoff_time
        ]
        
        # Check if threshold exceeded
        error_count = len(self.agent_errors[agent_id][error_type])
        
        if error_count >= REPEATED_ERROR_THRESHOLD:
            self.trigger_alert(
                agent_id=agent_id,
                alert_type="repeated_errors",
                severity="warning",
                message=f'"{error_type}" error occurred {error_count} times in {REPEATED_ERROR_WINDOW//60} minutes',
                metadata={
                    "error_type": error_type,
                    "occurrence_count": error_count,
                    "window_seconds": REPEATED_ERROR_WINDOW,
                    "threshold": REPEATED_ERROR_THRESHOLD
                }
            )
    
    # ========================================
    # Alert Type : Agent Inactivity
    # ========================================
    def check_agent_inactivity(self):
        """Check for inactive agents (runs periodically)"""
        current_time = datetime.utcnow()
        
        for agent_id, last_seen in list(self.agent_last_seen.items()):
            time_since_last = (current_time - last_seen).total_seconds()
            
            if time_since_last > INACTIVITY_THRESHOLD:
                self.trigger_alert(
                    agent_id=agent_id,
                    alert_type="agent_inactive",
                    severity="warning",
                    message=f"No events for {int(time_since_last//60)} minutes (threshold: {INACTIVITY_THRESHOLD//60} minutes)",
                    metadata={
                        "last_seen": last_seen.isoformat(),
                        "inactive_seconds": int(time_since_last),
                        "threshold": INACTIVITY_THRESHOLD
                    }
                )
                
                # Remove from tracking to avoid repeated alerts
                del self.agent_last_seen[agent_id]
    
    # ========================================
    # Main Processing
    # ========================================
    def process_event(self, event: dict):
        """Process single event for all alert conditions"""
        agent_id = event.get('agent_id')
        metadata = event.get('metadata', {})
        timestamp = datetime.fromisoformat(event.get('timestamp').replace('Z', '+00:00'))
        
        # Update last seen
        self.agent_last_seen[agent_id] = timestamp
        
        #  Error rate
        success = metadata.get('success', True)
        self.check_error_rate(agent_id, success)
        
        #  High latency
        if 'latency_ms' in metadata:
            self.check_high_latency(agent_id, metadata['latency_ms'])
        
        #  Cost spike
        if 'cost_usd' in metadata:
            self.check_cost_spike(agent_id, metadata['cost_usd'], timestamp)
        
        #  High token usage
        if 'tokens_used' in metadata:
            self.check_high_token_usage(agent_id, metadata['tokens_used'])
        
        #  Repeated errors
        if not success and 'error_code' in metadata:
            self.check_repeated_errors(agent_id, metadata['error_code'], timestamp)
        
        self.total_events_processed += 1
    
    def print_stats(self):
        """Print processing statistics"""
        logger.info("\n" + "="*70)
        logger.info("ALERTS PROCESSOR STATISTICS")
        logger.info("="*70)
        logger.info(f"  Events processed: {self.total_events_processed}")
        logger.info(f"  Alerts triggered: {self.total_alerts_triggered}")
        logger.info(f"  Active agents: {len(self.agent_last_seen)}")
        logger.info("\n  Alerts by type:")
        for alert_type, count in sorted(self.alerts_by_type.items()):
            logger.info(f"    {alert_type}: {count}")
        logger.info("="*70)
    
    def run(self):
        """Main processing loop"""
        logger.info("Enhanced Alerts Processor starting...")
        
        if not self.connect_kafka():
            return
        
        if not self.connect_database():
            return
        
        if not self.connect_redis():
            return
        
        logger.info("✓ Monitoring for alerts...")
        
        last_inactivity_check = time.time()
        last_stats_print = time.time()
        
        try:
            for message in self.consumer:
                try:
                    event = message.value
                    self.process_event(event)
                    
                    # Check for inactive agents every 60 seconds
                    if time.time() - last_inactivity_check >= 60:
                        self.check_agent_inactivity()
                        last_inactivity_check = time.time()
                    
                    # Print stats every 5 minutes
                    if time.time() - last_stats_print >= 300:
                        self.print_stats()
                        last_stats_print = time.time()
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
        finally:
            self.print_stats()
            
            if self.consumer:
                self.consumer.close()
            if self.producer:
                self.producer.close()
            if self.db_conn:
                self.db_conn.close()
            if self.redis_client:
                self.redis_client.close()
            
            logger.info("Alerts Processor stopped")


if __name__ == "__main__":
    processor = AlertsProcessor()
    processor.run()