import redis
import json
from typing import Optional, Any, List
from datetime import timedelta
from app.config import get_settings

settings = get_settings()

# Redis connection pool
redis_client = redis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True
)


class CacheManager:
    """
    Manages Redis caching operations
    """
    
    # Cache TTL settings (in seconds)
    AGENT_STATUS_TTL = 60  # 1 minute
    RECENT_EVENTS_TTL = 300  # 5 minutes
    AGENT_STATS_TTL = 600  # 10 minutes
    METRICS_TTL = 1800  # 30 minutes
    
    @staticmethod
    def get(key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    @staticmethod
    def set(key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with TTL"""
        try:
            redis_client.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            return False
    
    @staticmethod
    def delete(key: str) -> bool:
        """Delete key from cache"""
        try:
            redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False
    
    @staticmethod
    def delete_pattern(pattern: str) -> int:
        """Delete all keys matching pattern"""
        try:
            keys = redis_client.keys(pattern)
            if keys:
                return redis_client.delete(*keys)
            return 0
        except Exception as e:
            print(f"Cache delete pattern error: {e}")
            return 0
    
    @staticmethod
    def increment(key: str, amount: int = 1) -> int:
        """Increment counter"""
        try:
            return redis_client.incrby(key, amount)
        except Exception as e:
            print(f"Cache increment error: {e}")
            return 0
    
    @staticmethod
    def get_recent_events(agent_id: str, limit: int = 10) -> Optional[List]:
        """Get recent events from sorted set"""
        try:
            # Get from sorted set (sorted by timestamp)
            events = redis_client.zrevrange(
                f"agent:{agent_id}:recent",
                0,
                limit - 1
            )
            return [json.loads(e) for e in events] if events else None
        except Exception as e:
            print(f"Cache get recent events error: {e}")
            return None
    
    @staticmethod
    def add_recent_event(agent_id: str, event: dict, max_size: int = 100):
        """Add event to recent events sorted set"""
        try:
            key = f"agent:{agent_id}:recent"
            score = event['timestamp'].timestamp() if hasattr(event['timestamp'], 'timestamp') else float(event['timestamp'])
            
            # Add to sorted set
            redis_client.zadd(key, {json.dumps(event, default=str): score})
            
            # Keep only recent N events
            redis_client.zremrangebyrank(key, 0, -(max_size + 1))
            
            # Set expiry
            redis_client.expire(key, CacheManager.RECENT_EVENTS_TTL)
            
        except Exception as e:
            print(f"Cache add recent event error: {e}")


# Singleton instance
cache = CacheManager()