import asyncio
import aiohttp
import random
import time
import logging
import os
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
API_URL = os.getenv('API_URL', 'http://api:8000')
EVENTS_PER_BATCH = int(os.getenv('EVENTS_PER_BATCH', '100'))
BATCH_INTERVAL = int(os.getenv('BATCH_INTERVAL', '10'))  # seconds
NUM_AGENTS = int(os.getenv('NUM_AGENTS', '30'))
CONCURRENT_REQUESTS = int(os.getenv('CONCURRENT_REQUESTS', '50'))

# Agent and event types
AGENT_TYPES = [
    "gpt-researcher", "data-analyzer", "code-reviewer",
    "content-writer", "web-scraper", "image-generator",
    "audio-processor", "video-analyzer", "sentiment-analyzer",
    "translation-agent"
]

EVENT_TYPES = ["api_call", "decision", "completion", "error", "retry"]
MODELS = ["gpt-4", "gpt-3.5-turbo", "claude-3-opus", "claude-3-sonnet", "llama-2-70b"]


class ContinuousEventGenerator:
    """Generates events continuously for testing"""
    
    def __init__(self):
        self.api_url = API_URL
        self.agent_ids = [
            f"{random.choice(AGENT_TYPES)}-{i:03d}"
            for i in range(1, NUM_AGENTS + 1)
        ]
        self.total_sent = 0
        self.total_errors = 0
        self.session = None
    
    def generate_event(self) -> dict:
        """Generate a realistic event"""
        agent_id = random.choice(self.agent_ids)
        
        # 85% success rate
        success = random.random() > 0.15
        event_type = "error" if not success else random.choice(EVENT_TYPES)
        
        metadata = {
            "model": random.choice(MODELS),
            "tokens_used": random.randint(100, 2000),
            "latency_ms": random.randint(500, 3500),
            "cost_usd": round(random.uniform(0.005, 0.08), 4),
            "success": success,
            "timestamp_ms": int(time.time() * 1000)
        }
        
        if not success:
            metadata["error_code"] = random.choice([
                "timeout", "rate_limit", "invalid_input",
                "service_unavailable", "auth_failed"
            ])
            metadata["error_message"] = f"Simulated error: {metadata['error_code']}"
        
        return {
            "agent_id": agent_id,
            "event_type": event_type,
            "metadata": metadata
        }
    
    async def send_event(self, event: dict):
        """Send a single event"""
        try:
            async with self.session.post(
                f"{self.api_url}/events",
                json=event,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 201:
                    self.total_sent += 1
                    return True
                else:
                    self.total_errors += 1
                    return False
        except Exception as e:
            self.total_errors += 1
            logger.debug(f"Error sending event: {e}")
            return False
    
    async def send_batch(self, batch_size: int):
        """Send a batch of events concurrently"""
        events = [self.generate_event() for _ in range(batch_size)]
        tasks = [self.send_event(event) for event in events]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run_continuous(self):
        """Run continuous event generation"""
        logger.info("="*70)
        logger.info("CONTINUOUS EVENT GENERATOR STARTED")
        logger.info("="*70)
        logger.info(f"  API URL: {self.api_url}")
        logger.info(f"  Events per batch: {EVENTS_PER_BATCH}")
        logger.info(f"  Batch interval: {BATCH_INTERVAL} seconds")
        logger.info(f"  Number of agents: {NUM_AGENTS}")
        logger.info(f"  Concurrent requests: {CONCURRENT_REQUESTS}")
        logger.info("="*70)
        
        # Create session
        connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
        self.session = aiohttp.ClientSession(connector=connector)
        
        batch_number = 0
        
        try:
            while True:
                batch_number += 1
                batch_start = time.time()
                
                logger.info(f"\n[Batch {batch_number}] Generating {EVENTS_PER_BATCH} events...")
                
                # Send batch
                await self.send_batch(EVENTS_PER_BATCH)
                
                batch_duration = time.time() - batch_start
                events_per_sec = EVENTS_PER_BATCH / batch_duration if batch_duration > 0 else 0
                
                logger.info(
                    f"[Batch {batch_number}] Complete - "
                    f"{EVENTS_PER_BATCH} events in {batch_duration:.2f}s "
                    f"({events_per_sec:.0f} events/sec)"
                )
                logger.info(
                    f"[Stats] Total sent: {self.total_sent:,} | "
                    f"Errors: {self.total_errors} | "
                    f"Success rate: {(self.total_sent/(self.total_sent+self.total_errors)*100) if (self.total_sent+self.total_errors) > 0 else 0:.1f}%"
                )
                
                # Wait before next batch
                logger.info(f"Waiting {BATCH_INTERVAL} seconds until next batch...")
                await asyncio.sleep(BATCH_INTERVAL)
                
        except asyncio.CancelledError:
            logger.info("Generator shutting down gracefully...")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            if self.session:
                await self.session.close()
            
            logger.info("\n" + "="*70)
            logger.info("GENERATOR STOPPED")
            logger.info(f"  Total events sent: {self.total_sent:,}")
            logger.info(f"  Total errors: {self.total_errors}")
            logger.info("="*70)


async def main():
    generator = ContinuousEventGenerator()
    await generator.run_continuous()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")