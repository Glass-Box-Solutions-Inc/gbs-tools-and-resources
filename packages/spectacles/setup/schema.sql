-- Spectacles Database Schema
-- Human-Sight Browser Automation Agent

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_version (version) VALUES ('1.0.0');

-- =============================================================================
-- TASKS - Browser automation task tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    start_url TEXT NOT NULL,
    current_state TEXT DEFAULT 'PLANNING',
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    require_approval INTEGER DEFAULT 1,
    credentials_key TEXT,
    callback_url TEXT,
    is_active INTEGER DEFAULT 1,
    metadata TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(current_state);
CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(is_active);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

-- =============================================================================
-- CHECKPOINTS - State persistence for async HITL
-- =============================================================================
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    thread_id TEXT,
    agent_state TEXT NOT NULL,
    step_index INTEGER DEFAULT 0,
    state_data TEXT,  -- JSON: full state snapshot
    browser_state TEXT,  -- JSON: URL, cookies, session
    action_history TEXT,  -- JSON: list of completed actions
    perception_context TEXT,  -- JSON: DOM/VLM results
    pending_approval TEXT,  -- JSON: approval request details
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON checkpoints(created_at);

-- =============================================================================
-- SESSIONS - Browser session management
-- =============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    task_id TEXT,
    browser_session_id TEXT,
    storage_state TEXT,  -- JSON: cookies, localStorage (encrypted)
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    end_reason TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);

-- =============================================================================
-- ACTION_HISTORY - Record of all browser actions
-- =============================================================================
CREATE TABLE IF NOT EXISTS action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    action_type TEXT NOT NULL,  -- NAVIGATE, CLICK, FILL, SELECT, SCROLL, etc.
    action_params TEXT,  -- JSON: action parameters
    target_element TEXT,  -- CSS selector or description
    result_status TEXT,  -- SUCCESS, FAILED, SKIPPED
    result_data TEXT,  -- JSON: any result data
    screenshot_path TEXT,
    perception_method TEXT,  -- DOM, VLM, HYBRID
    confidence_score REAL,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_actions_task ON action_history(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_type ON action_history(action_type);

-- =============================================================================
-- HITL_REQUESTS - Human-in-the-loop approval requests
-- =============================================================================
CREATE TABLE IF NOT EXISTS hitl_requests (
    request_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    checkpoint_id TEXT,
    request_type TEXT NOT NULL,  -- APPROVAL, CAPTCHA, CREDENTIALS, INTERVENTION
    action_description TEXT NOT NULL,
    context TEXT,  -- JSON: additional context
    screenshot_path TEXT,
    screenshot_url TEXT,  -- Slack file URL after upload
    slack_channel TEXT,
    slack_message_ts TEXT,
    slack_thread_ts TEXT,
    status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED, TIMEOUT, TUNNEL
    responded_by TEXT,  -- Slack user ID
    response_data TEXT,  -- JSON: any response data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    expires_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id),
    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_hitl_task ON hitl_requests(task_id);
CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_requests(status);

-- =============================================================================
-- AUDIT_LOG - SOC2 compliance logging
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,  -- AUTHENTICATION, BROWSER_AUTOMATION, HITL_INTERACTION, etc.
    action TEXT NOT NULL,
    status TEXT NOT NULL,  -- SUCCESS, FAILURE
    task_id TEXT,
    session_id TEXT,
    resource TEXT,
    metadata TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- =============================================================================
-- LEARNED_PATTERNS - Long-term memory (site-specific knowledge)
-- =============================================================================
CREATE TABLE IF NOT EXISTS learned_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_domain TEXT NOT NULL,
    pattern_type TEXT NOT NULL,  -- LOGIN_FLOW, FORM_STRUCTURE, NAVIGATION, ERROR_HANDLING
    pattern_data TEXT NOT NULL,  -- JSON: structured pattern data
    embedding_id TEXT,  -- Pinecone vector ID
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patterns_domain ON learned_patterns(site_domain);
CREATE INDEX IF NOT EXISTS idx_patterns_type ON learned_patterns(pattern_type);

-- =============================================================================
-- SCREENSHOTS - Screenshot metadata (files stored externally)
-- =============================================================================
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    screenshot_path TEXT NOT NULL,
    screenshot_type TEXT,  -- OBSERVATION, ERROR, HITL, COMPLETION
    has_pii_blur INTEGER DEFAULT 0,
    file_size_bytes INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    deleted_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_screenshots_task ON screenshots(task_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_expires ON screenshots(expires_at);

-- =============================================================================
-- Cleanup procedure for expired data
-- =============================================================================
-- Run periodically: DELETE FROM screenshots WHERE expires_at < CURRENT_TIMESTAMP AND deleted_at IS NULL;
-- Run periodically: DELETE FROM checkpoints WHERE expires_at < CURRENT_TIMESTAMP;
-- Run periodically: DELETE FROM audit_log WHERE created_at < datetime('now', '-90 days');
