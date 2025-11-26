-- Hourly aggregation per agent
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_agent_metrics AS
SELECT 
    agent_id,
    date_trunc('hour', timestamp) AS hour,
    COUNT(*) as event_count,
    COUNT(*) FILTER (WHERE event_type = 'error') as error_count,
    COUNT(*) FILTER (WHERE event_type = 'api_call') as api_call_count,
    AVG(CAST(event_metadata->>'tokens_used' AS INTEGER)) as avg_tokens,
    SUM(CAST(event_metadata->>'tokens_used' AS INTEGER)) as total_tokens,
    AVG(CAST(event_metadata->>'latency_ms' AS INTEGER)) as avg_latency_ms,
    SUM(CAST(event_metadata->>'cost_usd' AS NUMERIC)) as total_cost_usd
FROM agent_events
WHERE event_metadata->>'tokens_used' IS NOT NULL
GROUP BY agent_id, hour
ORDER BY hour DESC, agent_id;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_agent_hour 
    ON hourly_agent_metrics(agent_id, hour DESC);

-- Daily aggregation per agent
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_agent_metrics AS
SELECT 
    agent_id,
    date_trunc('day', timestamp) AS day,
    COUNT(*) as event_count,
    COUNT(*) FILTER (WHERE event_type = 'error') as error_count,
    COUNT(*) FILTER (WHERE event_type = 'api_call') as api_call_count,
    AVG(CAST(event_metadata->>'tokens_used' AS INTEGER)) as avg_tokens,
    SUM(CAST(event_metadata->>'tokens_used' AS INTEGER)) as total_tokens,
    AVG(CAST(event_metadata->>'latency_ms' AS INTEGER)) as avg_latency_ms,
    SUM(CAST(event_metadata->>'cost_usd' AS NUMERIC)) as total_cost_usd,
    COUNT(DISTINCT event_type) as unique_event_types
FROM agent_events
WHERE event_metadata->>'tokens_used' IS NOT NULL
GROUP BY agent_id, day
ORDER BY day DESC, agent_id;

-- Create index on daily view
CREATE INDEX IF NOT EXISTS idx_daily_metrics_agent_day 
    ON daily_agent_metrics(agent_id, day DESC);

-- Agent summary view (current state)
CREATE MATERIALIZED VIEW IF NOT EXISTS agent_summary AS
SELECT 
    agent_id,
    COUNT(*) as total_events,
    MAX(timestamp) as last_seen,
    MIN(timestamp) as first_seen,
    COUNT(DISTINCT event_type) as unique_event_types,
    COUNT(*) FILTER (WHERE event_type = 'error') as total_errors,
    ROUND(
        (COUNT(*) FILTER (WHERE event_type = 'error')::NUMERIC / COUNT(*)::NUMERIC) * 100, 
        2
    ) as error_rate_percent
FROM agent_events
GROUP BY agent_id;

-- Verify views were created
SELECT schemaname, matviewname 
FROM pg_matviews 
WHERE schemaname = 'public';

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB,
    triggered_at TIMESTAMPTZ NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(255),
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for alerts
CREATE INDEX IF NOT EXISTS idx_alerts_agent_id ON alerts(agent_id);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved);

-- Composite indexes
CREATE INDEX IF NOT EXISTS idx_alerts_agent_triggered ON alerts(agent_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alerts(agent_id, resolved) WHERE resolved = FALSE;