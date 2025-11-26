# 🔭 Agent Observatory

> **A Production-Grade Real-Time Data Engineering Platform for AI Agent Monitoring**

Agent Observatory is a comprehensive observability platform designed to monitor, analyze, and track AI agent performance in real-time. Built with modern data engineering principles, it handles high-throughput event streaming, provides actionable insights, and scales horizontally to billions of records.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io/)
[![Kafka](https://img.shields.io/badge/Kafka-Redpanda-purple.svg)](https://redpanda.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Scaling](#-scaling)
- [API Documentation](#-api-documentation)
- [Dashboard](#-dashboard)
- [Performance](#-performance)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

### Core Capabilities
- **Real-Time Event Streaming** - Kafka-based pipeline processing thousands of events per second
- **Multi-Consumer Architecture** - Parallel processing for database writes, analytics, and alerting
- **Dead Letter Queue (DLQ)** - Automatic retry logic with exponential backoff for failed events
- **Advanced Alerting** - 7 alert types with configurable thresholds and severity levels
- **Interactive Dashboard** - Real-time Streamlit dashboard with auto-refresh
- **Horizontal Scalability** - Scale to 10+ processors and handle billions of records
- **Time-Series Optimization** - TimescaleDB for efficient historical data queries
- **Intelligent Caching** - Redis-powered caching with automatic invalidation

### Monitoring & Analytics
- **Agent Performance Tracking** - Monitor success rates, latency, cost, and token usage
- **Real-Time Metrics** - Live event stream with 2-second refresh
- **Cost Analysis** - Track spending across models and agents
- **Anomaly Detection** - Automated alerts for errors, latency spikes, and cost anomalies
- **Historical Analysis** - Time-series queries with materialized views

### Production-Ready
- **Fault Tolerance** - DLQ handles failures gracefully with retry mechanisms
- **Health Checks** - Comprehensive health monitoring for all services
- **Observability** - Structured logging and metric tracking
- **Data Integrity** - At-least-once delivery guarantees via Kafka
- **High Availability** - Containerized services with automatic restart

---

## 🏗️ Architecture

![Architecture](images\architecture.png)

```
┌─────────────────────────────────────────────────────────────────┐
│                    EVENT GENERATION LAYER                        │
│  • Containerized Event Generator (Automated)                    │
│  • External AI Agents (Production Integration)                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓ HTTP POST /events
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                               │
│  • FastAPI (Async)                                              │
│  • Kafka Producer                                               │
│  • Response Time: ~5ms                                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓ Kafka Message
┌─────────────────────────────────────────────────────────────────┐
│                    MESSAGE BROKER (Kafka/Redpanda)              │
│  • Topic: agent-events (10 partitions)                         │
│  • Persistent storage                                           │
│  • At-least-once delivery                                       │
└─────┬──────────────┬──────────────┬────────────────────────────┘
      │              │              │
      ↓              ↓              ↓
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Database │  │Analytics │  │ Alerts   │
│ Consumer │  │ Consumer │  │ Consumer │
│ (5x)     │  │          │  │          │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │
     ↓             ↓             ↓
┌─────────────────────────────────────────────┐
│  STORAGE LAYER                              │
│  • PostgreSQL + TimescaleDB                 │
│  • Redis Cache                              │
│  • Materialized Views                       │
└──────────────────┬──────────────────────────┘
                   │
                   ↓ API Queries
┌─────────────────────────────────────────────┐
│  VISUALIZATION LAYER                        │
│  • Streamlit Dashboard                      │
│  • Real-Time Monitoring                     │
│  • Agent Analytics                          │
│  • Alert Management                         │
└─────────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: Events sent to API via HTTP POST
2. **Publishing**: API publishes to Kafka instantly (non-blocking)
3. **Distribution**: Kafka distributes across 10 partitions
4. **Processing**: 5 consumers process in parallel (batches of 500)
5. **Storage**: PostgreSQL stores events, Redis caches hot data
6. **Analytics**: Real-time metrics computed and cached
7. **Alerting**: Alert consumers monitor and trigger alerts
8. **Visualization**: Dashboard displays real-time updates

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern async web framework for API layer
- **Python 3.11** - Core programming language
- **Kafka-Python** - Kafka client library
- **Psycopg2** - PostgreSQL adapter
- **Redis-Py** - Redis client

### Data Storage
- **PostgreSQL 16** - Primary database
- **TimescaleDB** - Time-series optimization
- **Redis 7** - Caching and real-time metrics

### Streaming
- **Redpanda** - Kafka-compatible streaming platform
- **Kafka Protocol** - Message broker protocol

### Frontend
- **Streamlit** - Interactive dashboard framework
- **Plotly** - Interactive visualizations
- **Pandas** - Data manipulation

### Infrastructure
- **Docker & Docker Compose** - Containerization and orchestration
- **Redpanda Console** - Kafka UI and monitoring

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker + Docker Compose** (Linux)
- **Python 3.11+** (for local development)
- **4GB RAM minimum** (8GB+ recommended for scaled deployment)

### Installation

1. **Clone the repository**
```bash
   git clone https://github.com/yourusername/agent-observatory.git
   cd agent-observatory
```

2. **Create environment file**
```bash
   cp .env.example .env
```

   Edit `.env` with your configuration:
```env
   DATABASE_URL=postgresql://observatory:your_password@your_host:5432/agent_observatory
   REDIS_URL=redis://redis:6379/0
   LOG_LEVEL=info
   ENVIRONMENT=development
```

3. **Start the services**
```bash
   # Start core services (API, Redis, Redpanda)
   docker-compose up -d

   # Start with streaming pipeline (Phase 3)
   docker-compose --profile phase3 up -d

   # Start with continuous event generator
   docker-compose --profile phase3 --profile testing up -d
```

4. **Verify services are running**
```bash
   docker-compose ps
```

   Expected output:
```
   ✓ redis (healthy)
   ✓ redpanda (healthy)
   ✓ api (running)
   ✓ stream-processor (running)
   ✓ dashboard (running)
   ✓ console (running)
```

5. **Access the dashboard**
   
   Open your browser: **http://localhost:8501**

### Accessing Services

| Service | URL | Description |
|---------|-----|-------------|
| **Dashboard** | http://localhost:8501 | Real-time monitoring dashboard |
| **API** | http://localhost:8000 | FastAPI backend |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |
| **Redpanda Console** | http://localhost:8080 | Kafka monitoring interface |

---

## 📁 Project Structure
```
agent-observatory/
├── services/
│   ├── api/                      # FastAPI application
│   │   ├── app/
│   │   │   ├── main.py          # API endpoints
│   │   │   ├── models.py        # Pydantic models
│   │   │   ├── database.py      # Database connection
│   │   │   └── cache.py         # Redis cache manager
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── stream-processor/         # Database consumer
│   │   ├── processor.py         # Batch event processor
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── consumers/                # Additional consumers
│   │   ├── analytics_consumer.py # Real-time analytics
│   │   ├── alerts_consumer.py   # Alert monitoring
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── dlq-processor/           # Dead Letter Queue handler
│   │   ├── processor.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── ingestion/               # Event generation
│   │   ├── event_generator.py  # Manual event generator
│   │   ├── continuous_generator.py # Automated generator
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── dashboard/               # Streamlit dashboard
│       ├── app.py               # Main dashboard app
│       ├── pages/
│       │   ├── Home.py
│       │   ├── Real_Time_Monitoring.py
│       │   ├── Agents_Overview.py
│       │   └── Agent_Deep_Dive.py
│       ├── utils/
│       │   ├── api_client.py    # API client library
│       │   └── formatting.py    # Formatting utilities
│       ├── config.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── scripts/
│   ├── init-db.sql             # Database initialization
│   ├── script.sql               # Table creation and Index Script
│   
│   
│
├── docker-compose.yml           # Service orchestration
├── .env.example                 # Environment template
├── .gitignore
├── README.md
└── LICENSE
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:
```env
# Database Configuration
DATABASE_URL=postgresql://user:password@host:5432/agent_observatory

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# Application Settings
LOG_LEVEL=info
ENVIRONMENT=development

# Event Generator Settings (optional)
EVENTS_PER_BATCH=100
BATCH_INTERVAL=10
NUM_AGENTS=30
CONCURRENT_REQUESTS=50
```

### Scaling Configuration

Edit `docker-compose.yml` to adjust:
```yaml
services:
  event-generator:
    environment:
      EVENTS_PER_BATCH: 100      # Events per batch
      BATCH_INTERVAL: 10         # Seconds between batches
      NUM_AGENTS: 30             # Number of unique agents
      CONCURRENT_REQUESTS: 50    # Parallel requests

  stream-processor:
    # Scale with: docker-compose --profile phase3 up -d --scale stream-processor=5
    environment:
      BATCH_SIZE: 500            # Events per batch insert
      BATCH_TIMEOUT: 2           # Seconds before forcing batch
```

### Alert Thresholds

Configure in `services/consumers/alerts_consumer.py`:
```python
# Alert thresholds
ERROR_RATE_THRESHOLD = 0.20          # 20% error rate
HIGH_LATENCY_THRESHOLD = 3000        # 3 seconds
COST_SPIKE_THRESHOLD = 0.5           # $0.50 in 5 minutes
HIGH_TOKEN_THRESHOLD = 5000          # Tokens per request
REPEATED_ERROR_THRESHOLD = 5         # Same error 5 times
INACTIVITY_THRESHOLD = 600           # 10 minutes no activity
```

---

## 📊 Scaling

### Horizontal Scaling

#### Scale Stream Processors

Process more events by adding processors:
```bash
# Scale to 5 processors
docker-compose --profile phase3 up -d --scale stream-processor=5

# Scale to 10 processors
docker-compose --profile phase3 up -d --scale stream-processor=10
```

#### Add Kafka Partitions

Improve distribution:
```bash
# Add partitions (must match or exceed processor count)
docker exec -it agent_observatory_redpanda rpk topic add-partitions agent-events --num 10
```

#### Increase Event Generation

Test high throughput:
```yaml
# docker-compose.yml
event-generator:
  environment:
    EVENTS_PER_BATCH: 500
    BATCH_INTERVAL: 5
    CONCURRENT_REQUESTS: 100
```

### Performance Benchmarks

| Configuration | Throughput | Latency | Daily Capacity |
|---------------|------------|---------|----------------|
| **1 processor, 1 partition** | ~100 events/sec | 10-20s | ~8.6M events |
| **5 processors, 10 partitions** | ~500 events/sec | 5-10s | ~43M events |
| **10 processors, 20 partitions** | ~1,000 events/sec | 3-5s | ~86M events |

**Time to 1 Billion Events:**
- 1 processor: ~115 days
- 5 processors: ~23 days
- 10 processors: ~11 days
- 20+ processors (optimized): ~5-7 days

---

## 📡 API Documentation

### Core Endpoints

#### Create Event
```http
POST /events
Content-Type: application/json

{
  "agent_id": "gpt-researcher-001",
  "event_type": "api_call",
  "metadata": {
    "model": "gpt-4",
    "tokens_used": 500,
    "latency_ms": 1200,
    "cost_usd": 0.02,
    "success": true
  }
}

Response: 201 Created
{
  "id": 0,
  "agent_id": "gpt-researcher-001",
  "timestamp": "2025-11-26T16:00:00",
  "event_type": "api_call",
  "created_at": "2025-11-26T16:00:01"
}
```

#### Get Events
```http
GET /events?limit=100&offset=0

Response: 200 OK
{
  "events": [...],
  "count": 100
}
```

#### Get Events Summary
```http
GET /events/summary

Response: 200 OK
{
  "total_events": 10500,
  "unique_agents": 42,
  "success_rate": 94.5,
  "total_cost": 125.50
}
```

#### Get Agents
```http
GET /agents

Response: 200 OK
[
  {
    "agent_id": "gpt-researcher-001",
    "first_seen": "2025-11-26T10:00:00",
    "last_seen": "2025-11-26T16:00:00",
    "event_count": 250
  },
  ...
]
```

#### Get Agent Stats
```http
GET /agents/{agent_id}/stats

Response: 200 OK
{
  "total_events": 250,
  "success_rate": 96.8,
  "avg_latency_ms": 1245,
  "total_cost": 5.50,
  "error_count": 8
}
```

### Full API Documentation

Interactive Swagger docs: **http://localhost:8000/docs**

---

## 🎨 Dashboard

### Pages Overview

#### 1. 🏠 Home / Overview
- System health status
- Key metrics (total events, agents, success rate, alerts)
- Top performing agents
- Recent alerts feed
- Event distribution charts

#### 2. 📊 Real-Time Monitoring
- Live event stream (auto-refresh every 2s)
- Success rate gauge
- Latency distribution histogram
- Event type breakdown
- Cost analysis
- Token usage metrics
- Recent errors log

#### 3. 🤖 Agents Overview
- Searchable agents table
- Agent health heatmap
- Top performers by success rate
- Problem agents identification
- Event distribution by agent
- Cost and latency comparison

#### 4. 🔍 Agent Deep Dive
- Select specific agent for analysis
- 24-hour performance timeline
- Recent events table
- Error analysis breakdown
- Alert history
- Model usage statistics
- Cost efficiency metrics

### Dashboard Features

- **Auto-Refresh**: Configurable refresh rates (2s, 5s, 10s, 30s)
- **Interactive Charts**: Zoom, pan, hover tooltips
- **Responsive Design**: Works on desktop and tablet
- **Real-Time Updates**: Server-sent events for live data
- **Dark Theme**: Easy on the eyes for long monitoring sessions

---

## 🎯 Performance

### Current Metrics (as of project completion)

- **Total Events Processed**: 3,495+
- **Unique Agents Tracked**: 62
- **Total Cost Monitored**: $148.02
- **Success Rate**: 100%
- **Average Throughput**: 80-100 events/minute
- **End-to-End Latency**: <20 seconds
- **API Response Time**: ~5ms
- **Kafka Lag**: <100 messages

### Optimization Features

1. **Batch Processing**: 500 events per database transaction
2. **Connection Pooling**: Reused database connections
3. **Redis Caching**: 60-second TTL for hot data
4. **Materialized Views**: Pre-aggregated analytics
5. **Indexing**: Strategic indexes on frequently queried columns
6. **Async I/O**: Non-blocking API operations

---

## 💻 Development

### Local Development Setup

1. **Install dependencies**
```bash
   # API
   cd services/api
   pip install -r requirements.txt

   # Dashboard
   cd services/dashboard
   pip install -r requirements.txt
```

2. **Run services individually**
```bash
   # API
   cd services/api
   uvicorn app.main:app --reload --port 8000

   # Dashboard
   cd services/dashboard
   streamlit run app.py
```

3. **Run tests**
```bash
   # Test event creation
   python scripts/populate-dashboard-data.py

   # Test alerts
   python scripts/test-alerts.py

   # Test DLQ
   python scripts/test-dlq.py
```

### Adding New Features

#### Add a New API Endpoint

Edit `services/api/app/main.py`:
```python
@app.get("/your-endpoint")
async def your_endpoint():
    # Your logic here
    return {"data": "value"}
```

#### Add a New Dashboard Page

Create `services/dashboard/pages/5_Your_Page.py`:
```python
import streamlit as st

st.set_page_config(page_title="Your Page", layout="wide")
st.title("Your Page Title")

# Your dashboard logic here
```

#### Add a New Consumer

1. Create `services/consumers/your_consumer.py`
2. Add to `docker-compose.yml`
3. Rebuild and deploy

---

## 🐛 Troubleshooting

### Common Issues

#### Services Not Starting
```bash
# Check logs
docker-compose logs [service-name]

# Common fixes
docker-compose down
docker-compose build
docker-compose up -d
```

#### Dashboard Shows No Data

1. Verify API is accessible:
```bash
   curl http://localhost:8000/health
```

2. Check DATABASE_URL matches between services:
```bash
   docker-compose exec api env | grep DATABASE
   docker-compose exec stream-processor env | grep DATABASE
```

3. Verify events in database:
```bash
   docker-compose exec postgres psql -U observatory -d agent_observatory -c "SELECT COUNT(*) FROM agent_events;"
```

#### High Kafka Lag

Check in Redpanda Console (http://localhost:8080):
- Consumer Groups → agent-event-processor
- Check lag per partition

**Solutions:**
```bash
# Scale processors
docker-compose --profile phase3 up -d --scale stream-processor=5

# Add partitions
docker exec -it agent_observatory_redpanda rpk topic add-partitions agent-events --num 10
```

#### Generator High Error Rate

Check API logs:
```bash
docker-compose logs api --tail=50
```

Reduce load:
```yaml
# docker-compose.yml
event-generator:
  environment:
    EVENTS_PER_BATCH: 20
    BATCH_INTERVAL: 15
    CONCURRENT_REQUESTS: 10
```

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/yourusername/agent-observatory/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/agent-observatory/discussions)

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide for Python code
- Add docstrings to all functions and classes
- Include unit tests for new features
- Update documentation for API changes
- Test with Docker Compose before submitting

---



---

## 🙏 Acknowledgments

- **FastAPI** - Modern web framework
- **Redpanda** - Kafka-compatible streaming platform
- **Streamlit** - Dashboard framework
- **TimescaleDB** - Time-series database extension
- **Plotly** - Interactive visualizations

---

## 📧 Contact

**Project Link**: [https://github.com/tycoach/agent-observatory](https://github.com/tycoach/agent-observatory)

---

<div align="center">

**⭐ Star this repo if you find it useful! ⭐**

Made with ❤️ by [Taiwo Hassan]

</div>