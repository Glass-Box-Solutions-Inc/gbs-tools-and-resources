# Squeegee Intelligence API

REST API endpoints for Squeegee's intelligence system (stages 14-20). Provides manual triggers for intelligence collection, synthesis, audits, research, and notifications.

## Base URL

```
https://squeegee-916151540991.us-central1.run.app/api/intelligence
```

## Authentication

All endpoints require Cloud Run OIDC authentication via bearer token:

```bash
# Get authentication token
TOKEN=$(gcloud auth print-identity-token)

# Make request
curl -H "Authorization: Bearer $TOKEN" \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/status
```

## Endpoints

### 1. POST /run

Trigger full intelligence pipeline (stages 14-20).

**Request Body:**
```json
{
  "date": "2026-03-13",  // optional, defaults to yesterday
  "force": {
    "claudeMdAudit": false,    // force weekly audit
    "docQualityAudit": false,  // force monthly audit
    "research": false          // force quarterly research
  }
}
```

**Response:**
```json
{
  "status": "success",
  "date": "2026-03-13",
  "stages": [
    {
      "stage": 14,
      "name": "intelligence-collect",
      "status": "success",
      "summary": "Collected data: 42 commits, 8 deployments"
    },
    {
      "stage": 15,
      "name": "intelligence-synthesize",
      "status": "success",
      "summary": "Generated briefing (Gemini)"
    },
    {
      "stage": 16,
      "name": "intelligence-write",
      "status": "success",
      "summary": "Wrote 6 log files to adjudica-documentation"
    },
    {
      "stage": 17,
      "name": "intelligence-audit-claude",
      "status": "skipped",
      "summary": "Not Sunday (weekly audit)"
    },
    {
      "stage": 18,
      "name": "intelligence-audit-quality",
      "status": "skipped",
      "summary": "Not 1st of month (monthly audit)"
    },
    {
      "stage": 19,
      "name": "intelligence-research",
      "status": "skipped",
      "summary": "Not 1st of quarter (quarterly research)"
    },
    {
      "stage": 20,
      "name": "intelligence-notify",
      "status": "skipped",
      "summary": "Not implemented yet"
    }
  ],
  "duration_ms": 45000
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-13"}' \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/run
```

---

### 2. POST /collect

Run only data collection (stage 14).

**Request Body:**
```json
{
  "date": "2026-03-13"  // optional, defaults to yesterday
}
```

**Response:**
```json
{
  "status": "success",
  "date": "2026-03-13",
  "data": {
    "github": { /* GitHubActivityData */ },
    "gcp": { /* GCPLogData */ },
    "station": { /* StationActivityData */ },
    "checkpoints": []
  },
  "metrics": {
    "repos_active": 15,
    "total_commits": 42,
    "total_prs": 8,
    "deployments": 8,
    "errors": 3,
    "sessions": 6
  }
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-13"}' \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/collect
```

---

### 3. POST /synthesize

Generate briefing from collected data.

**Request Body:**
```json
{
  "date": "2026-03-13",
  "data": {
    "github": { /* collected data */ },
    "gcp": { /* collected data */ },
    "station": { /* collected data */ },
    "checkpoints": []
  }
}
```

**Response:**
```json
{
  "status": "success",
  "briefing": {
    "date": "2026-03-13",
    "executive_summary": ["...", "...", "..."],
    "repository_activity": "...",
    "deployment_events": "...",
    "development_activity": "...",
    "context_checkpoints": "...",
    "observations": "...",
    "generated_at": "2026-03-13T10:00:00Z",
    "model_used": "gemini-2.0-flash-exp",
    "token_count": { "input": 2000, "output": 1000 },
    "fallback_used": false,
    "error": null
  }
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d @collected-data.json \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/synthesize
```

---

### 4. POST /audit-claude-md

Run CLAUDE.md compliance audit (13-point rubric).

**Request Body:** *(none)*

**Response:**
```json
{
  "status": "success",
  "report": {
    "date": "2026-03-13",
    "repos_audited": 27,
    "summary": {
      "average_score": 10.3,
      "excellent": 15,
      "good": 8,
      "needs_work": 3,
      "critical": 1
    },
    "details": [
      {
        "repo": "adjudica-ai-app",
        "score": 13,
        "missing_points": [],
        "needs_pr": false
      },
      {
        "repo": "command-center",
        "score": 9,
        "missing_points": [11, 12, 13],
        "needs_pr": true
      }
    ]
  }
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/audit-claude-md
```

---

### 5. POST /audit-doc-quality

Run documentation quality audit (10-point rubric).

**Status:** Not implemented (returns 501)

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/audit-doc-quality
```

---

### 6. POST /research

Run best-practice web research using Gemini with search grounding.

**Status:** Not implemented (returns 501)

**Request Body:**
```json
{
  "topic": "documentation-standards",
  "date": "2026-03-13"  // optional
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"topic": "AI-readable documentation best practices"}' \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/research
```

---

### 7. POST /notify

Send briefing to Slack (manual trigger).

**Status:** Not implemented (returns 501)

**Request Body:**
```json
{
  "briefing": { /* GeminiBriefing object */ },
  "date": "2026-03-13"
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d @briefing.json \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/notify
```

---

### 8. GET /status

Get intelligence system status and health.

**Response:**
```json
{
  "status": "healthy",
  "enabled": true,
  "dry_run": false,
  "modules": {
    "github-collector": "ok",
    "gcp-collector": "ok",
    "station-monitor": "ok",
    "log-writer": "ok",
    "gemini-synthesizer": "ok",
    "claude-md-auditor": "ok",
    "doc-quality-auditor": "not_implemented",
    "web-researcher": "not_implemented",
    "slack-notifier": "not_implemented"
  },
  "last_run": {
    "date": "2026-03-13",
    "status": "success",
    "duration_ms": 45000
  },
  "next_scheduled": {
    "daily": "2026-03-14T07:00:00Z",
    "weekly_audit": "2026-03-16T07:00:00Z",
    "monthly_audit": "2026-04-01T07:00:00Z",
    "quarterly_research": "2026-04-01T07:00:00Z"
  }
}
```

**Example:**
```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://squeegee-916151540991.us-central1.run.app/api/intelligence/status
```

---

## Configuration

Intelligence system configuration is loaded from `/config/intelligence.config.json`.

### Environment Variable Overrides

| Variable | Type | Description |
|----------|------|-------------|
| `INTELLIGENCE_ENABLED` | Boolean | Master kill switch |
| `INTELLIGENCE_DRY_RUN` | Boolean | Collect/synthesize only, no writes |
| `GEMINI_MODEL` | String | Override Gemini model |
| `GEMINI_TEMPERATURE` | Number | Override temperature (0.0-2.0) |
| `GOOGLE_AI_API_KEY` | Path | Path to Gemini API key file (volume-mounted) |
| `GITHUB_TOKEN` | Path | Path to GitHub token file (volume-mounted) |

### Example: Enable Dry-Run Mode

```bash
# In Cloud Run environment variables
INTELLIGENCE_DRY_RUN=true
```

---

## Error Handling

### Error Response Format

```json
{
  "status": "failed",
  "error": "Error message here"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid input) |
| 401 | Unauthorized (missing/invalid auth token) |
| 500 | Internal Server Error |
| 501 | Not Implemented (endpoint not yet available) |
| 503 | Service Unavailable (intelligence disabled) |

---

## Rate Limiting

Rate limiting is configured per external API in `intelligence.config.json`:

```json
{
  "intelligence": {
    "rate_limits": {
      "github": {
        "requests_per_hour": 5000,
        "pause_threshold": 100,
        "pause_duration_ms": 60000
      },
      "gemini": {
        "requests_per_minute": 60,
        "retry_delay_ms": 2000
      }
    }
  }
}
```

---

## Testing

Run API tests:

```bash
npm test -- tests/api/intelligence.test.js
```

Run with coverage:

```bash
npm run test:coverage -- tests/api/intelligence.test.js
```

---

## Scheduling

Intelligence runs are triggered by Cloud Scheduler:

| Job | Schedule | Endpoint |
|-----|----------|----------|
| `squeegee-intelligence` | Daily at 7am UTC | `POST /api/intelligence/run` |

Manual triggers can be done via any of the endpoints above.

---

## Implementation Status

| Stage | Status | Endpoint |
|-------|--------|----------|
| 14 - Collect | ✅ Complete | `POST /collect` |
| 15 - Synthesize | ✅ Complete | `POST /synthesize` |
| 16 - Write | ✅ Complete | *(part of /run)* |
| 17 - Audit CLAUDE.md | ✅ Complete | `POST /audit-claude-md` |
| 18 - Audit Doc Quality | ⏳ In Progress | `POST /audit-doc-quality` |
| 19 - Web Research | ⏳ In Progress | `POST /research` |
| 20 - Notify | ⏳ In Progress | `POST /notify` |

---

## Architecture

```
┌─────────────────┐
│  Cloud Scheduler │
│  (Daily 7am UTC) │
└────────┬────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│  Fastify API: /api/intelligence/run        │
└────────────────────────────────────────────┘
         │
         ├─▶ Stage 14: Collect ──────┐
         │   - GitHub Activity        │
         │   - GCP Logs              │
         │   - Station Activity      │
         │   - Checkpoints           │
         │                           │
         ├─▶ Stage 15: Synthesize ◀─┘
         │   - Gemini 2.0 Flash
         │   - Generate Briefing
         │
         ├─▶ Stage 16: Write
         │   - Log Writer
         │   - 6 Daily Logs
         │
         ├─▶ Stage 17: Audit (Sunday)
         │   - CLAUDE.md Compliance
         │
         ├─▶ Stage 18: Audit (Monthly)
         │   - Doc Quality (10-point)
         │
         ├─▶ Stage 19: Research (Quarterly)
         │   - Web Research + Grounding
         │
         └─▶ Stage 20: Notify
             - Slack Notification
             - Hub Webhook
```

---

## Related Documentation

- [Intelligence Architecture](../../.planning/INTELLIGENCE_ARCHITECTURE.md)
- [Configuration Schema](../../.planning/INTELLIGENCE_CONFIG_SCHEMA.md)
- [Migration Plan](../../.planning/SQUEEGEE_UNIFIED_MIGRATION_PLAN.md)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
