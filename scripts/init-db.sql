-- -- Enable TimescaleDB extension
-- CREATE EXTENSION IF NOT EXISTS timescaledb;

-- -- Agent events table
-- CREATE TABLE IF NOT EXISTS agent_events (
--     id BIGSERIAL PRIMARY KEY,
--     agent_id VARCHAR(255) NOT NULL,
--     timestamp TIMESTAMPTZ NOT NULL,
--     event_type VARCHAR(50) NOT NULL,
--     event_metadata JSONB,  -- ← CHANGED FROM 'metadata' to 'event_metadata'
--     created_at TIMESTAMPTZ DEFAULT NOW()
-- );

-- -- Convert to hypertable for time-series optimization
-- SELECT create_hypertable('agent_events', 'timestamp', if_not_exists => TRUE);

-- -- Create indexes
-- CREATE INDEX IF NOT EXISTS idx_agent_events_agent_id ON agent_events(agent_id);
-- CREATE INDEX IF NOT EXISTS idx_agent_events_event_type ON agent_events(event_type);
-- CREATE INDEX IF NOT EXISTS idx_agent_events_timestamp ON agent_events(timestamp DESC);

-- -- Create composite index for common queries
-- CREATE INDEX IF NOT EXISTS idx_agent_events_agent_timestamp 
--     ON agent_events(agent_id, timestamp DESC);

-- -- Add GIN index for JSONB metadata queries
-- CREATE INDEX IF NOT EXISTS idx_agent_events_metadata ON agent_events USING GIN (event_metadata);  -- ← CHANGED

-- -- Log successful initialization
-- DO $$
-- BEGIN
--     RAISE NOTICE 'Agent Observatory database initialized successfully';
-- END $$;


-- Agent events table
CREATE TABLE IF NOT EXISTS agent_events (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_agent_events_agent_id ON agent_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_event_type ON agent_events(event_type);
CREATE INDEX IF NOT EXISTS idx_agent_events_timestamp ON agent_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_agent_timestamp ON agent_events(agent_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_metadata ON agent_events USING GIN (event_metadata);

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Agent Observatory database initialized successfully';
END
$$;