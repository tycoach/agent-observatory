import os
import json
import time
import logging
from datetime import datetime
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import psycopg2
import redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
KAFKA_DLQ_TOPIC = os.getenv('KAFKA_DLQ_TOPIC', 'agent-events-dlq')
KAFKA_CONSUMER_GROUP = 'dlq-processor'
DATABASE_URL = os.getenv('DATABASE_URL')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

# Retry settings
MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_BASE = 5  # Exponential backoff base


class DLQProcessor:
    """
    Processes events from Dead Letter Queue
    - Attempts retry with exponential backoff
    - Stores permanently failed events
    - Logs all failures for analysis
    """
    
    def __init__(self):
        self.consumer = None
        self.db_conn = None
        self.redis_client = None
        self.total_processed = 0
        self.total_recovered = 0
        self.total_permanent_failures = 0
        
    def connect_kafka(self):
        """Connect to Kafka"""
        logger.info(f"Connecting to Kafka DLQ at {KAFKA_BOOTSTRAP_SERVERS}...")
        
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self.consumer = KafkaConsumer(
                    KAFKA_DLQ_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    group_id=KAFKA_CONSUMER_GROUP,
                    auto_offset_reset='earliest',
                    enable_auto_commit=True,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
                )
                logger.info(f"✓ Connected to DLQ topic: {KAFKA_DLQ_TOPIC}")
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
                
                # Create DLQ table if not exists
                cursor = self.db_conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dlq_events (
                        id BIGSERIAL PRIMARY KEY,
                        agent_id VARCHAR(255),
                        original_event JSONB NOT NULL,
                        error_message TEXT,
                        retry_count INTEGER,
                        failed_at TIMESTAMPTZ,
                        stored_at TIMESTAMPTZ DEFAULT NOW(),
                        status VARCHAR(50) DEFAULT 'failed'
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_dlq_agent_id ON dlq_events(agent_id);
                    CREATE INDEX IF NOT EXISTS idx_dlq_status ON dlq_events(status);
                    CREATE INDEX IF NOT EXISTS idx_dlq_stored_at ON dlq_events(stored_at DESC);
                """)
                self.db_conn.commit()
                cursor.close()
                
                logger.info("✓ Connected to database, DLQ table ready")
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
            logger.warning(f"Redis connection failed: {e}")
            return False
    
    def retry_event(self, event: dict, retry_count: int) -> bool:
        """Attempt to retry processing the event"""
        try:
            cursor = self.db_conn.cursor()
            
            cursor.execute("""
                INSERT INTO agent_events (agent_id, timestamp, event_type, event_metadata)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (
                event['agent_id'],
                event['timestamp'],
                event['event_type'],
                json.dumps(event.get('metadata'))
            ))
            
            self.db_conn.commit()
            cursor.close()
            
            logger.info(f"✓ Recovered event for {event['agent_id']} (retry {retry_count})")
            self.total_recovered += 1
            return True
            
        except Exception as e:
            logger.error(f"Retry failed: {e}")
            self.db_conn.rollback()
            return False
    
    def store_permanent_failure(self, dlq_message: dict):
        """Store permanently failed event"""
        try:
            original_event = dlq_message['original_event']
            
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO dlq_events 
                (agent_id, original_event, error_message, retry_count, failed_at, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                original_event.get('agent_id'),
                json.dumps(original_event),
                dlq_message.get('error'),
                dlq_message.get('retry_count', 0),
                dlq_message.get('failed_at'),
                'permanent_failure'
            ))
            
            self.db_conn.commit()
            cursor.close()
            
            logger.warning(f"⚠ Permanent failure stored for {original_event.get('agent_id')}")
            self.total_permanent_failures += 1
            
            # Track in Redis
            if self.redis_client:
                try:
                    self.redis_client.incr('dlq:permanent_failures')
                    self.redis_client.lpush(
                        'dlq:recent_failures',
                        json.dumps({
                            'agent_id': original_event.get('agent_id'),
                            'error': dlq_message.get('error'),
                            'timestamp': datetime.utcnow().isoformat()
                        })
                    )
                    self.redis_client.ltrim('dlq:recent_failures', 0, 99)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to store permanent failure: {e}")
            self.db_conn.rollback()
    
    def process_dlq_message(self, dlq_message: dict):
        """Process a DLQ message"""
        self.total_processed += 1
        
        original_event = dlq_message.get('original_event', {})
        retry_count = dlq_message.get('retry_count', 0)
        error = dlq_message.get('error', 'Unknown error')
        
        logger.info(f"Processing DLQ message for {original_event.get('agent_id')} (retry {retry_count})")
        
        # Check if we should retry
        if retry_count < MAX_RETRY_ATTEMPTS:
            # Exponential backoff
            delay = RETRY_DELAY_BASE * (2 ** retry_count)
            logger.info(f"Waiting {delay}s before retry...")
            time.sleep(delay)
            
            # Attempt retry
            success = self.retry_event(original_event, retry_count)
            
            if success:
                return
        
        # Max retries exceeded or retry failed - store as permanent failure
        self.store_permanent_failure(dlq_message)
    
    def print_stats(self):
        """Print processing statistics"""
        logger.info("\n" + "="*70)
        logger.info("DLQ PROCESSOR STATISTICS")
        logger.info("="*70)
        logger.info(f"  Total processed: {self.total_processed}")
        logger.info(f"  Total recovered: {self.total_recovered}")
        logger.info(f"  Permanent failures: {self.total_permanent_failures}")
        logger.info(f"  Recovery rate: {(self.total_recovered/self.total_processed*100) if self.total_processed > 0 else 0:.1f}%")
        logger.info("="*70)
    
    def run(self):
        """Main processing loop"""
        logger.info("DLQ Processor starting...")
        
        if not self.connect_kafka():
            return
        
        if not self.connect_database():
            return
        
        self.connect_redis()
        
        logger.info("✓ Monitoring Dead Letter Queue...")
        
        last_stats_time = time.time()
        
        try:
            for message in self.consumer:
                try:
                    dlq_message = message.value
                    self.process_dlq_message(dlq_message)
                    
                    # Print stats every 60 seconds
                    if time.time() - last_stats_time >= 60:
                        self.print_stats()
                        last_stats_time = time.time()
                    
                except Exception as e:
                    logger.error(f"Error processing DLQ message: {e}")
                    continue
        
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
        finally:
            self.print_stats()
            
            if self.consumer:
                self.consumer.close()
            if self.db_conn:
                self.db_conn.close()
            if self.redis_client:
                self.redis_client.close()
            
            logger.info("DLQ Processor stopped")


if __name__ == "__main__":
    processor = DLQProcessor()
    processor.run()