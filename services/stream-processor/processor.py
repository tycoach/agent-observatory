import os
import json
import time
import logging
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import psycopg2
from psycopg2.extras import execute_values
import redis

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'agent-events')
KAFKA_DLQ_TOPIC = os.getenv('KAFKA_DLQ_TOPIC', 'agent-events-dlq')
KAFKA_CONSUMER_GROUP = os.getenv('KAFKA_CONSUMER_GROUP', 'agent-event-processor')
DATABASE_URL = os.getenv('DATABASE_URL')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

# Batch processing settings
BATCH_SIZE = 1000 ##you can configure to your design
BATCH_TIMEOUT = 5  # seconds

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


class EventProcessor:
    """
    Kafka consumer with DLQ support
    """
    
    def __init__(self):
        self.consumer = None
        self.producer = None  # For DLQ
        self.db_conn = None
        self.redis_client = None
        self.event_batch = []
        self.last_batch_time = time.time()
        
    def connect_kafka(self):
        """Connect to Kafka consumer and producer"""
        logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
        
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                # Consumer
                self.consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    group_id=KAFKA_CONSUMER_GROUP,
                    auto_offset_reset='earliest',
                    enable_auto_commit=False,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    max_poll_records=500,
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=10000
                )
                
                # Producer for DLQ
                self.producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
                    acks='all',
                    retries=3
                )
                
                logger.info(f"✓ Connected to Kafka, subscribed to topic: {KAFKA_TOPIC}")
                return True
            except KafkaError as e:
                logger.error(f"Kafka connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Exiting.")
                    return False
    
    def connect_database(self):
        """Connect to PostgreSQL"""
        logger.info("Connecting to database...")
        
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.db_conn = psycopg2.connect(DATABASE_URL)
                self.db_conn.autocommit = False
                logger.info("✓ Connected to database")
                return True
            except Exception as e:
                logger.error(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Exiting.")
                    return False
    
    def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            logger.info("✓ Connected to Redis")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Continuing without cache.")
            return False
    
    def send_to_dlq(self, event: dict, error: str, retry_count: int = 0):
        """Send failed event to Dead Letter Queue"""
        try:
            dlq_message = {
                "original_event": event,
                "error": str(error),
                "retry_count": retry_count,
                "failed_at": datetime.utcnow().isoformat(),
                "processor_id": os.getenv('HOSTNAME', 'unknown')
            }
            
            self.producer.send(KAFKA_DLQ_TOPIC, value=dlq_message)
            self.producer.flush()
            
            logger.warning(f"Event sent to DLQ: {event.get('agent_id')} - {error}")
            
            # Track DLQ metrics in Redis
            if self.redis_client:
                try:
                    self.redis_client.incr('dlq:total_events')
                    self.redis_client.incr(f'dlq:by_error:{type(error).__name__}')
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
    
    def process_batch_with_retry(self, max_attempts: int = MAX_RETRIES):
        """Process batch with retry logic"""
        if not self.event_batch:
            return True
        
        for attempt in range(max_attempts):
            try:
                cursor = self.db_conn.cursor()
                
                # Prepare batch insert
                insert_query = """
                    INSERT INTO agent_events (agent_id, timestamp, event_type, event_metadata)
                    VALUES %s
                    RETURNING id, agent_id, timestamp, event_type, created_at
                """
                
                values = [
                    (
                        event['agent_id'],
                        event['timestamp'],
                        event['event_type'],
                        json.dumps(event.get('metadata')) if event.get('metadata') else None
                    )
                    for event in self.event_batch
                ]
                
                # Batch insert
                execute_values(cursor, insert_query, values, page_size=100)
                inserted = cursor.fetchall()
                
                # Commit transaction
                self.db_conn.commit()
                
                logger.info(f"✓ Batch processed: {len(inserted)} events inserted (attempt {attempt + 1})")
                
                # Invalidate cache for affected agents
                if self.redis_client:
                    agent_ids = set(event['agent_id'] for event in self.event_batch)
                    for agent_id in agent_ids:
                        try:
                            pattern = f"agent:{agent_id}:*"
                            keys = self.redis_client.keys(pattern)
                            if keys:
                                self.redis_client.delete(*keys)
                        except Exception as e:
                            logger.warning(f"Cache invalidation failed for {agent_id}: {e}")
                
                # Commit Kafka offsets
                self.consumer.commit()
                
                # Clear batch
                self.event_batch = []
                self.last_batch_time = time.time()
                
                cursor.close()
                
                return True
                
            except psycopg2.errors.UniqueViolation as e:
                # Duplicate event - skip and continue
                logger.warning(f"Duplicate event detected, skipping batch: {e}")
                self.db_conn.rollback()
                self.event_batch = []
                return True
                
            except psycopg2.errors.InvalidTextRepresentation as e:
                # Data format error - send to DLQ
                logger.error(f"Data format error: {e}")
                self.db_conn.rollback()
                
                for event in self.event_batch:
                    self.send_to_dlq(event, e, attempt + 1)
                
                self.event_batch = []
                return True
                
            except Exception as e:
                logger.error(f"✗ Batch processing failed (attempt {attempt + 1}/{max_attempts}): {e}")
                self.db_conn.rollback()
                
                if attempt < max_attempts - 1:
                    logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    # Max retries exceeded - send all to DLQ
                    logger.error("Max retries exceeded. Sending batch to DLQ")
                    for event in self.event_batch:
                        self.send_to_dlq(event, e, max_attempts)
                    
                    self.event_batch = []
                    return False
    
    def should_process_batch(self):
        """Determine if batch should be processed"""
        batch_full = len(self.event_batch) >= BATCH_SIZE
        batch_timeout = (time.time() - self.last_batch_time) >= BATCH_TIMEOUT
        return batch_full or (batch_timeout and len(self.event_batch) > 0)
    
    def run(self):
        """Main processing loop"""
        logger.info("Stream processor starting...")
        
        # Connect to services
        if not self.connect_kafka():
            return
        
        if not self.connect_database():
            return
        
        self.connect_redis()  # Optional
        
        logger.info("✓ All connections established. Starting to consume events...")
        
        try:
            for message in self.consumer:
                try:
                    event = message.value
                    
                    # Validate event
                    if not all(k in event for k in ['agent_id', 'timestamp', 'event_type']):
                        logger.warning(f"Invalid event format: {event}")
                        self.send_to_dlq(event, "Invalid event format: missing required fields", 0)
                        continue
                    
                    # Add to batch
                    self.event_batch.append(event)
                    
                    # Process batch if conditions met
                    if self.should_process_batch():
                        self.process_batch_with_retry()
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    try:
                        self.send_to_dlq(message.value, e, 0)
                    except:
                        pass
                    continue
            
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            # Process remaining events
            if self.event_batch:
                logger.info("Processing remaining events before shutdown...")
                self.process_batch_with_retry()
            
            # Cleanup
            if self.consumer:
                self.consumer.close()
            if self.producer:
                self.producer.flush()
                self.producer.close()
            if self.db_conn:
                self.db_conn.close()
            if self.redis_client:
                self.redis_client.close()
            
            logger.info("Stream processor stopped")


if __name__ == "__main__":
    processor = EventProcessor()
    processor.run()