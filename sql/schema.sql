-- AI Question Answering Schema for AWS Infrastructure
-- Uses Aurora (PostgreSQL) for persistent storage and ElastiCache (Redis) for caching

-- Table to store question history and responses
CREATE TABLE IF NOT EXISTS question_history (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model VARCHAR(100) NOT NULL DEFAULT 'SmolLM2-135M-Instruct',
    response_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_session_id VARCHAR(255)
);

-- PostgreSQL indexes (CREATE INDEX syntax, not inline INDEX)
CREATE INDEX IF NOT EXISTS idx_question_history_created_at ON question_history(created_at);
CREATE INDEX IF NOT EXISTS idx_question_history_session_id ON question_history(user_session_id);

-- Table to cache frequently asked questions and their answers
CREATE TABLE IF NOT EXISTS question_cache (
    id SERIAL PRIMARY KEY,
    question_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 hash of the question
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model VARCHAR(100) NOT NULL,
    hit_count INTEGER DEFAULT 1,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- PostgreSQL indexes for question_cache
CREATE INDEX IF NOT EXISTS idx_question_cache_question_hash ON question_cache(question_hash);
CREATE INDEX IF NOT EXISTS idx_question_cache_last_accessed ON question_cache(last_accessed);

-- Table for API usage metrics and monitoring
CREATE TABLE IF NOT EXISTS api_metrics (
    id SERIAL PRIMARY KEY,
    endpoint VARCHAR(50) NOT NULL,
    response_time_ms INTEGER,
    status_code INTEGER NOT NULL,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- PostgreSQL indexes for api_metrics
CREATE INDEX IF NOT EXISTS idx_api_metrics_endpoint_created ON api_metrics(endpoint, created_at);
CREATE INDEX IF NOT EXISTS idx_api_metrics_created_at ON api_metrics(created_at);