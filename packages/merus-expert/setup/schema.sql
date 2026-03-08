-- MerusCase Matter Automation Framework - Database Schema
-- Version: 1.0.0
-- SQLite Database for knowledge base, sessions, and audit logging

-- ==============================================================================
-- SCHEMA VERSION TRACKING
-- ==============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT INTO schema_version (version, description)
VALUES ('1.0.0', 'Initial schema for MerusCase matter automation framework')
ON CONFLICT(version) DO NOTHING;

-- ==============================================================================
-- SESSIONS - Agent session tracking
-- ==============================================================================

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_phase TEXT NOT NULL DEFAULT 'INITIALIZATION' CHECK(
        agent_phase IN ('INITIALIZATION', 'READY', 'EXECUTING', 'EXPLORATION', 'COMPLETED', 'ERROR')
    ),
    current_workflow TEXT,
    workflow_step INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    metadata TEXT,  -- JSON
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active, last_active_at);
CREATE INDEX IF NOT EXISTS idx_sessions_phase ON sessions(agent_phase);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

-- ==============================================================================
-- MATTERS - Matter creation tracking
-- ==============================================================================

CREATE TABLE IF NOT EXISTS matters (
    matter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    meruscase_matter_id TEXT,  -- MerusCase's internal ID
    matter_type TEXT NOT NULL CHECK(
        matter_type IN ('immigration', 'workers_comp', 'family_law', 'personal_injury', 'general',
                        'Immigration', 'Workers'' Compensation', 'Family Law', 'Personal Injury', 'General')
    ),
    primary_party TEXT NOT NULL,
    case_type TEXT,
    jurisdiction TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(
        status IN ('pending', 'in_progress', 'success', 'failed', 'needs_review')
    ),
    meruscase_url TEXT,
    screenshot_path TEXT,
    error_message TEXT,
    custom_fields TEXT,  -- JSON
    metadata TEXT,  -- JSON
    dry_run INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matters_session ON matters(session_id);
CREATE INDEX IF NOT EXISTS idx_matters_status ON matters(status);
CREATE INDEX IF NOT EXISTS idx_matters_type ON matters(matter_type);
CREATE INDEX IF NOT EXISTS idx_matters_meruscase_id ON matters(meruscase_matter_id);
CREATE INDEX IF NOT EXISTS idx_matters_created ON matters(created_at);

-- ==============================================================================
-- AUDIT LOG - SOC2 compliance audit trail
-- ==============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    event_id TEXT PRIMARY KEY,
    session_id TEXT,
    event_category TEXT NOT NULL CHECK(
        event_category IN ('AUTHENTICATION', 'MATTER_OPERATIONS', 'CREDENTIAL_ACCESS',
                          'BROWSER_AUTOMATION', 'SECURITY_EVENTS', 'DATA_ACCESS')
    ),
    event_type TEXT NOT NULL,  -- login_attempt, matter_submitted, etc.
    action TEXT NOT NULL,       -- create, navigate, fill_form, submit, etc.
    actor TEXT DEFAULT 'merus_agent',
    resource TEXT,              -- URL or resource identifier
    status TEXT NOT NULL CHECK(
        status IN ('SUCCESS', 'FAILURE', 'WARNING', 'PENDING')
    ),
    screenshot_path TEXT,
    ip_address TEXT,
    user_agent TEXT DEFAULT 'MerusAgent/1.0',
    metadata TEXT,              -- JSON
    soc2_control TEXT,          -- e.g., 'CC6.6', 'CC6.8'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retention_until TIMESTAMP,  -- Auto-delete after retention period
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(event_category);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_retention ON audit_log(retention_until);
CREATE INDEX IF NOT EXISTS idx_audit_status ON audit_log(status);

-- ==============================================================================
-- KNOWLEDGE BASE - Form fields and selectors
-- ==============================================================================

CREATE TABLE IF NOT EXISTS form_fields (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_name TEXT NOT NULL,
    field_label TEXT NOT NULL,
    case_type TEXT,  -- NULL for universal fields, specific for case-type fields
    css_selector TEXT,
    xpath TEXT,
    input_type TEXT CHECK(
        input_type IN ('text', 'select', 'date', 'checkbox', 'radio', 'textarea', 'number', 'email', 'phone')
    ),
    confidence_score REAL DEFAULT 1.0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(field_name, case_type)
);

CREATE INDEX IF NOT EXISTS idx_form_fields_name ON form_fields(field_name);
CREATE INDEX IF NOT EXISTS idx_form_fields_case_type ON form_fields(case_type);
CREATE INDEX IF NOT EXISTS idx_form_fields_success ON form_fields(success_count DESC);

-- ==============================================================================
-- DROPDOWN OPTIONS - Cached dropdown values
-- ==============================================================================

CREATE TABLE IF NOT EXISTS dropdown_options (
    option_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dropdown_name TEXT NOT NULL,  -- case_type, attorney, office, etc.
    option_value TEXT NOT NULL,
    option_text TEXT NOT NULL,
    display_order INTEGER,
    is_active INTEGER DEFAULT 1,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(dropdown_name, option_value)
);

CREATE INDEX IF NOT EXISTS idx_dropdown_name ON dropdown_options(dropdown_name);
CREATE INDEX IF NOT EXISTS idx_dropdown_active ON dropdown_options(is_active);

-- ==============================================================================
-- NAVIGATION PATHS - Learned navigation sequences
-- ==============================================================================

CREATE TABLE IF NOT EXISTS navigation_paths (
    path_id INTEGER PRIMARY KEY AUTOINCREMENT,
    path_name TEXT UNIQUE NOT NULL,  -- e.g., "new_case", "case_details"
    steps TEXT NOT NULL,  -- JSON array of navigation steps
    selectors TEXT NOT NULL,  -- JSON array of selectors
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_navigation_success ON navigation_paths(success_count DESC);
CREATE INDEX IF NOT EXISTS idx_navigation_last_used ON navigation_paths(last_used_at);

-- ==============================================================================
-- SCREENSHOT METADATA - Screenshot tracking and cleanup
-- ==============================================================================

CREATE TABLE IF NOT EXISTS screenshot_metadata (
    screenshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    screenshot_path TEXT NOT NULL,
    step_key TEXT NOT NULL,
    description TEXT,
    page_url TEXT,
    file_size_kb REAL,
    resolution TEXT,  -- e.g., "1920x1080"
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- Auto-delete after retention period (24 hours)
    metadata TEXT,  -- JSON
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_screenshots_session ON screenshot_metadata(session_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_expires ON screenshot_metadata(expires_at);
CREATE INDEX IF NOT EXISTS idx_screenshots_timestamp ON screenshot_metadata(timestamp);

-- ==============================================================================
-- CASE TYPE FIELDS - Case type specific field mappings
-- ==============================================================================

CREATE TABLE IF NOT EXISTS case_type_fields (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_type TEXT NOT NULL,
    field_name TEXT NOT NULL,
    is_required INTEGER DEFAULT 0,
    field_order INTEGER,
    default_value TEXT,
    validation_pattern TEXT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(case_type, field_name)
);

CREATE INDEX IF NOT EXISTS idx_case_type_mapping ON case_type_fields(case_type);

-- ==============================================================================
-- WORKFLOW RETRIES - Retry tracking for error handling
-- ==============================================================================

CREATE TABLE IF NOT EXISTS workflow_retries (
    retry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    matter_id INTEGER NOT NULL,
    workflow_step TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    screenshot_path TEXT,
    retry_count INTEGER DEFAULT 1,
    resolved INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_retries_matter ON workflow_retries(matter_id);
CREATE INDEX IF NOT EXISTS idx_retries_resolved ON workflow_retries(resolved);
CREATE INDEX IF NOT EXISTS idx_retries_session ON workflow_retries(session_id);

-- ==============================================================================
-- KNOWLEDGE ELEMENTS - Comprehensive UI element discovery
-- ==============================================================================

CREATE TABLE IF NOT EXISTS knowledge_elements (
    element_id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url TEXT NOT NULL,
    element_type TEXT NOT NULL CHECK(
        element_type IN ('input', 'select', 'button', 'link', 'form', 'table', 'modal')
    ),
    element_selector TEXT NOT NULL,  -- CSS selector
    element_label TEXT,
    element_role TEXT,  -- what this element does
    matter_type TEXT,   -- which matter types use this
    is_required INTEGER DEFAULT 0,
    discovery_session_id TEXT,
    embedding_id TEXT,  -- Pinecone vector ID (optional)
    metadata TEXT,  -- JSON
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_page ON knowledge_elements(page_url);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_elements(element_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_matter_type ON knowledge_elements(matter_type);

-- ==============================================================================
-- CHAT CONVERSATIONS - Conversational data collection
-- ==============================================================================

CREATE TABLE IF NOT EXISTS chat_conversations (
    conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    state TEXT NOT NULL DEFAULT 'greeting',
    collected_data TEXT,  -- JSON of collected matter data
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_session ON chat_conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_state ON chat_conversations(state);

-- ==============================================================================
-- CHAT MESSAGES - Conversation history
-- ==============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata TEXT,  -- JSON
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages(role);

-- ==============================================================================
-- BATCH IMPORT - Batch matter creation and document upload
-- ==============================================================================

CREATE TABLE IF NOT EXISTS batch_jobs (
    job_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    case_type TEXT DEFAULT 'Workers'' Compensation',
    total_folders INTEGER DEFAULT 0,
    total_files INTEGER DEFAULT 0,
    processed_folders INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    failed_folders INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK(
        status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')
    ),
    current_folder TEXT,
    error_message TEXT,
    dry_run INTEGER DEFAULT 1,
    include_case_number INTEGER DEFAULT 0,
    delay_between_uploads REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_created ON batch_jobs(created_at);

CREATE TABLE IF NOT EXISTS batch_tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    folder_name TEXT NOT NULL,
    client_name TEXT NOT NULL,
    case_number TEXT,
    total_files INTEGER DEFAULT 0,
    matter_id TEXT,
    meruscase_url TEXT,
    status TEXT DEFAULT 'pending' CHECK(
        status IN ('pending', 'creating_matter', 'uploading_documents', 'completed', 'failed', 'skipped')
    ),
    uploaded_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    error_message TEXT,
    screenshot_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES batch_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_batch_tasks_job ON batch_tasks(job_id);
CREATE INDEX IF NOT EXISTS idx_batch_tasks_status ON batch_tasks(status);

CREATE TABLE IF NOT EXISTS batch_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    file_type TEXT,
    upload_status TEXT DEFAULT 'pending' CHECK(
        upload_status IN ('pending', 'uploading', 'success', 'failed', 'skipped')
    ),
    meruscase_doc_id TEXT,
    error_message TEXT,
    uploaded_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES batch_tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_batch_documents_task ON batch_documents(task_id);
CREATE INDEX IF NOT EXISTS idx_batch_documents_status ON batch_documents(upload_status);

-- ==============================================================================
-- CLEANUP & MAINTENANCE VIEWS
-- ==============================================================================

-- View: Expired screenshots for cleanup
CREATE VIEW IF NOT EXISTS v_expired_screenshots AS
SELECT
    screenshot_id,
    session_id,
    screenshot_path,
    expires_at,
    CAST((julianday('now') - julianday(expires_at)) * 24 AS INTEGER) as hours_expired
FROM screenshot_metadata
WHERE expires_at < datetime('now');

-- View: Expired audit logs for cleanup
CREATE VIEW IF NOT EXISTS v_expired_audit_logs AS
SELECT
    event_id,
    session_id,
    event_type,
    retention_until,
    CAST((julianday('now') - julianday(retention_until)) AS INTEGER) as days_expired
FROM audit_log
WHERE retention_until < datetime('now');

-- View: Session summary statistics
CREATE VIEW IF NOT EXISTS v_session_summary AS
SELECT
    s.session_id,
    s.agent_phase,
    s.started_at,
    s.ended_at,
    COUNT(DISTINCT m.matter_id) as matters_created,
    COUNT(DISTINCT a.event_id) as audit_events,
    COUNT(DISTINCT sc.screenshot_id) as screenshots_captured,
    MAX(m.updated_at) as last_matter_update
FROM sessions s
LEFT JOIN matters m ON s.session_id = m.session_id
LEFT JOIN audit_log a ON s.session_id = a.session_id
LEFT JOIN screenshot_metadata sc ON s.session_id = sc.session_id
GROUP BY s.session_id;

-- ==============================================================================
-- TRIGGERS - Automated maintenance
-- ==============================================================================

-- Trigger: Update matters.updated_at on any change
CREATE TRIGGER IF NOT EXISTS trg_matters_updated_at
AFTER UPDATE ON matters
FOR EACH ROW
BEGIN
    UPDATE matters SET updated_at = CURRENT_TIMESTAMP WHERE matter_id = NEW.matter_id;
END;

-- Trigger: Update sessions.last_active_at on activity
CREATE TRIGGER IF NOT EXISTS trg_sessions_last_active
AFTER UPDATE ON sessions
FOR EACH ROW
WHEN NEW.is_active = 1
BEGIN
    UPDATE sessions SET last_active_at = CURRENT_TIMESTAMP WHERE session_id = NEW.session_id;
END;

-- ==============================================================================
-- INITIAL DATA
-- ==============================================================================

-- Common dropdown option placeholders (will be populated during first run)
INSERT OR IGNORE INTO dropdown_options (dropdown_name, option_value, option_text, display_order) VALUES
('case_status', 'open', 'Open', 1),
('case_status', 'pending', 'Pending', 2),
('case_status', 'closed', 'Closed', 3),
('case_status', 'archived', 'Archived', 4);

-- ==============================================================================
-- SCHEMA VALIDATION
-- ==============================================================================

-- Verify all tables created
SELECT
    'Schema validation' as check_type,
    COUNT(*) as table_count,
    'Expected: 13 tables' as expected
FROM sqlite_master
WHERE type = 'table' AND name NOT LIKE 'sqlite_%';

-- Verify all indexes created
SELECT
    'Index validation' as check_type,
    COUNT(*) as index_count,
    'Expected: 30+ indexes' as expected
FROM sqlite_master
WHERE type = 'index' AND name NOT LIKE 'sqlite_%';

-- ==============================================================================
-- END OF SCHEMA
-- ==============================================================================
