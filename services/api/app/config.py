from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Agent Observatory"
    environment: str = "development"
    log_level: str = "info"
    
    # Database
    database_url: str
    
    # Redis
    redis_url: str
    
    # Kafka 
    kafka_bootstrap_servers: str = "redpanda:9092"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()