# Squeegee Intelligence Modules

**Status:** Development (Week 2 - All Modules Complete)

This directory contains the intelligence curation modules migrated from Spectacles (Python) to Squeegee (Node.js).

---

## Modules

| Module | Status | Description |
|--------|--------|-------------|
| `github-collector.js` | ✅ Complete | Collects GitHub activity (commits, PRs, issues, CI runs) |
| `gcp-collector.js` | ✅ Complete | Collects GCP Cloud Logging data (deployments, errors) |
| `station-collector.js` | ✅ Complete | Collects dev workstation activity from GCS bucket |
| `station-monitor.js` | ✅ Complete | Collects dev workstation activity from local files |
| `log-writer.js` | ✅ Complete | Writes intelligence logs to adjudica-documentation |
| `gemini-synthesizer.js` | ✅ Complete | Generates daily briefings using Gemini 2.5 Flash |
| `slack-notifier.js` | ✅ Complete | Sends briefings to Slack via Block Kit webhooks |
| `claude-md-auditor.js` | ✅ Complete | Audits repos for CLAUDE.md compliance (13-point) |
| `doc-quality-auditor.js` | ✅ Complete | Audits docs for quality (10-point rubric) |
| `web-researcher.js` | ✅ Complete | Performs web research using Gemini search grounding |
| `morning-run.js` | ✅ Complete | Orchestrates daily intelligence pipeline |
| `utils.js` | ✅ Complete | Shared utilities and error classes |

---

## Station Collector Implementation

### Module: `station-collector.js`

**Purpose:** Collect development station activity (Claude Code sessions, Cursor, VS Code) from GCS bucket. Reads JSON log files stored daily by workstation monitors.

**Key Features:**
- GCS bucket integration (`@google-cloud/storage`)
- Graceful degradation on missing files or permission errors
- Sensitive data sanitization (tokens, paths, credentials)
- Session processing with duration calculation
- Batch collection for multiple dates
- List available dates for backfill operations

### Usage

```javascript
const { collect, listAvailableDates, collectBatch } = require('./intelligence/station-collector');

const config = {
  storage: {
    gcs_bucket: 'glassbox-dev-activity',
    gcs_prefix: 'station/'
  }
};

// Collect single day
const data = await collect('2026-03-03', config);

console.log(data);
// {
//   date: '2026-03-03',
//   sessions: [
//     {
//       type: 'claude-code',
//       project: 'my-project',
//       start: '2026-03-03T09:00:00Z',
//       end: '2026-03-03T10:30:00Z',
//       duration_minutes: 90,
//       commands: 45,
//       files_edited: 12
//     }
//   ],
//   summary: {
//     total_sessions: 2,
//     active_hours: 2.5,
//     projects_touched: ['my-project', 'other-project'],
//     by_tool: { 'claude-code': 1, 'cursor': 1 },
//     total_commands: 65,
//     total_files_edited: 17
//   },
//   source: {
//     type: 'gcs',
//     bucket: 'glassbox-dev-activity',
//     path: 'station/2026-03-03.json',
//     found: true
//   }
// }

// List available dates
const dates = await listAvailableDates(config, {
  startDate: '2026-03-01',
  endDate: '2026-03-31'
});
// ['2026-03-03', '2026-03-02', '2026-03-01']

// Batch collect
const batch = await collectBatch(['2026-03-01', '2026-03-02', '2026-03-03'], config);
// Aggregated data with by_date breakdown
```

### GCS Bucket Structure

```
gs://glassbox-dev-activity/
└── station/
    ├── 2026-03-01.json
    ├── 2026-03-02.json
    └── 2026-03-03.json
```

**File Format:**
```json
{
  "sessions": [
    {
      "type": "claude-code",
      "project": "/home/user/my-project",
      "start": "2026-03-03T09:00:00Z",
      "end": "2026-03-03T10:30:00Z",
      "commands": 45,
      "files_edited": 12,
      "agent": "opus-4.5",
      "model": "claude-opus-4-5-20251101"
    }
  ]
}
```

### IAM Requirements

```bash
# Service account needs storage.objectViewer on the bucket
gcloud storage buckets add-iam-policy-binding gs://glassbox-dev-activity \
  --member="serviceAccount:squeegee-intelligence@glassbox-squeegee.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

### Data Sanitization

The module automatically redacts sensitive information:

**Commands:**
- `--token`, `--password`, `--secret`, `--api-key` arguments
- Bearer tokens
- GitHub PATs (`ghp_...`)

**Paths:**
- Paths containing `/secrets/`
- Paths containing `/.env`
- Paths containing `/credentials/`
- Paths containing `/service-account`

### Error Handling

The station collector follows **graceful degradation**:

1. **File Not Found:** Returns empty structure with `source.found: false`
2. **Malformed JSON:** Logs warning, returns empty structure
3. **Permission Denied:** Logs warning, returns empty structure (via safeExecute)
4. **GCS Server Errors:** 5xx errors are marked as recoverable

### Test Coverage

**41 test cases implemented:**
- ✅ Command sanitization (tokens, Bearer, PATs)
- ✅ Path sanitization (secrets, env files, credentials)
- ✅ Session processing (durations, missing fields, ongoing sessions)
- ✅ Summary calculation (hours, projects, tool counts)
- ✅ GCS download and parse
- ✅ Date object vs string input
- ✅ Missing file handling
- ✅ Malformed JSON handling
- ✅ Permission denied handling
- ✅ List available dates
- ✅ Batch collection
- ✅ GCSStorageError properties

---

## GCP Collector Implementation

### Module: `gcp-collector.js`

**Purpose:** Collect Cloud Run deployment events and error logs from GCP Cloud Logging across all configured GCP projects.

**Key Features:**
- Cross-project log querying
- Graceful degradation on permission errors
- Automatic pagination handling
- Filters for Cloud Run deployments (v1 and v2 API)
- Error severity filtering (ERROR and above)

### Usage

```javascript
const { collect } = require('./intelligence/gcp-collector');

const config = {
  gcp_projects: [
    'glassbox-squeegee',
    'glassbox-spectacles',
    'adjudica-internal',
    'glassy-personal-ai',
    'command-center-gbs',
    'glass-box-hub'
  ]
};

const data = await collect('2026-03-03', config);

console.log(data);
// {
//   deployments: [
//     {
//       project: 'adjudica-internal',
//       service: 'adjudica-ai-app',
//       revision: 'adjudica-ai-app-00042',
//       status: 'success',
//       timestamp: '2026-03-03T10:30:00Z'
//     }
//   ],
//   errors: [
//     {
//       project: 'adjudica-internal',
//       service: 'adjudica-ai-app',
//       severity: 'ERROR',
//       message: 'Database connection timeout',
//       timestamp: '2026-03-03T11:00:00Z'
//     }
//   ],
//   summary: {
//     total_deployments: 5,
//     total_errors: 2,
//     projects_monitored: 6
//   },
//   projects_failed: [] // Only present if failures occurred
// }
```

### IAM Requirements

The Squeegee service account requires the following IAM roles on each monitored GCP project:

```bash
# Service account
export SA_EMAIL="squeegee-intelligence@glassbox-squeegee.iam.gserviceaccount.com"

# Grant logging.viewer role to each project
for PROJECT in glassbox-squeegee glassbox-spectacles adjudica-internal glassy-personal-ai command-center-gbs glass-box-hub; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/logging.viewer"
done
```

**Required Permissions:**
- `logging.logEntries.list`
- `logging.logs.list`

### Authentication

**Local Development:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

**Cloud Run (Production):**
- Uses Application Default Credentials (ADC)
- Service account attached to Cloud Run container
- No environment variables needed

### Error Handling

The GCP collector follows a **graceful degradation** strategy:

1. **Per-Project Errors:** If one project fails (e.g., `PERMISSION_DENIED`), other projects continue processing
2. **Partial Data:** Returns all successfully collected data + `projects_failed` array
3. **Empty Results:** Returns empty arrays if no logs in timeframe (not an error)
4. **Quota Exceeded:** Logs warning, includes project in `projects_failed`, continues

**Error Types:**
- `PERMISSION_DENIED` → Missing IAM permissions
- `QUOTA_EXCEEDED` → Cloud Logging API quota hit
- `NOT_FOUND` → Project doesn't exist or logging disabled
- `INTERNAL` → GCP API transient error

### Testing

**Run all tests:**
```bash
npm test
```

**Run with coverage:**
```bash
npm run test:coverage
```

**Watch mode:**
```bash
npm run test:watch
```

**Test Coverage Requirements:**
- Branches: ≥80%
- Functions: ≥80%
- Lines: ≥80%
- Statements: ≥80%

**Test Cases Implemented:**
- ✅ Happy path (multiple projects)
- ✅ Partial failure (one project fails)
- ✅ Empty results (no logs in timeframe)
- ✅ Pagination handling
- ✅ Filter accuracy
- ✅ Missing metadata fields
- ✅ Date object vs string input
- ✅ Deployment status variations
- ✅ Error log formats (string vs object)
- ✅ Console logging verification

---

## Dependencies

### Production
```json
{
  "@google-cloud/logging": "^11.0.0",
  "@google-cloud/storage": "^7.0.0",
  "@octokit/rest": "^20.0.0",
  "@octokit/plugin-retry": "^6.0.0",
  "@octokit/plugin-throttling": "^8.0.0"
}
```

### Development
```json
{
  "jest": "^29.7.0"
}
```

---

## Architecture Reference

See:
- [Intelligence Architecture](../.planning/INTELLIGENCE_ARCHITECTURE.md)
- [Configuration Schema](../.planning/INTELLIGENCE_CONFIG_SCHEMA.md)
- [Squeegee Migration Plan](../.planning/SQUEEGEE_UNIFIED_MIGRATION_PLAN.md)

---

## Gemini Synthesizer Implementation

### Module: `gemini-synthesizer.js`

**Purpose:** Generate daily intelligence briefings from collected GitHub, GCP, and station data using Gemini 2.5 Flash.

**Key Features:**
- Gemini 2.5 Flash integration (default model)
- Structured prompt generation from collected data
- Retry logic with exponential backoff
- Graceful fallback to template-based briefings
- Token estimation and logging

### Usage

```javascript
const { synthesize } = require('./intelligence/gemini-synthesizer');

const collectedData = {
  github: { /* from github-collector */ },
  gcp: { /* from gcp-collector */ },
  station: { /* from station-collector */ },
  checkpoints: []
};

const config = {
  intelligence: {
    gemini: {
      model: 'gemini-2.5-flash',  // or 'gemini-2.5-pro' for complex analysis
      temperature: 0.3,
      max_output_tokens: 8192,
      apiKey: process.env.GOOGLE_AI_API_KEY
    }
  }
};

const briefing = await synthesize('2026-03-03', collectedData, config);

console.log(briefing);
// {
//   date: '2026-03-03',
//   executive_summary: ['...', '...'],
//   repository_activity: '...',
//   deployment_events: '...',
//   development_activity: '...',
//   observations: '...',
//   generated_at: '2026-03-03T12:00:00.000Z',
//   model_used: 'gemini-2.5-flash',
//   token_count: { input: 2500, output: 800 },
//   fallback_used: false,
//   error: null
// }
```

### Briefing Sections

The synthesizer generates structured briefings with:

1. **Executive Summary** — 2-3 sentences on key activity
2. **Development Highlights** — Notable commits and features
3. **Pull Request Activity** — Merge patterns, review activity
4. **Infrastructure & Operations** — Deployments, errors
5. **Team Activity** — Projects, tool usage
6. **Recommendations** — Action items, follow-ups

### Fallback Mode

If Gemini API is unavailable, the synthesizer generates a template-based briefing from raw data. Fallback briefings include a warning notice and `fallback_used: true`.

### Configuration

```json
{
  "intelligence": {
    "gemini": {
      "model": "gemini-2.5-flash",
      "temperature": 0.3,
      "max_output_tokens": 8192,
      "api_key_secret": "gemini-api-key"
    }
  }
}
```

**Available Models:**
- `gemini-2.5-flash` — Fast, cost-effective (recommended for daily briefings)
- `gemini-2.5-pro` — Higher reasoning capability (for complex analysis)

---

## Morning Run Pipeline Implementation

### Module: `morning-run.js`

**Purpose:** Orchestrate the daily intelligence collection, synthesis, and publishing pipeline.

**Key Features:**
- Parallel collection from GitHub, GCP, and station activity
- Gemini 2.5 Flash briefing synthesis
- Automatic log writing to adjudica-documentation
- Slack notification delivery
- Dry run mode for testing
- Batch processing for backfill operations
- Stage skipping for selective execution
- CLI support with argument parsing

### Usage

```javascript
const { run, runBatch } = require('./intelligence/morning-run');

// Run pipeline for yesterday (default)
const result = await run();

// Run for specific date
const result = await run({ date: '2026-03-03' });

// Dry run (skip writes and notifications)
const result = await run({ dryRun: true });

// Skip specific stages
const result = await run({ skipStages: ['notify'] });

// Batch processing (backfill)
const batchResult = await runBatch([
  '2026-03-01',
  '2026-03-02',
  '2026-03-03'
]);
```

### CLI Usage

```bash
# Run for yesterday
node intelligence/morning-run.js

# Run for specific date
node intelligence/morning-run.js --date 2026-03-03

# Dry run mode
node intelligence/morning-run.js --dry-run

# Skip stages
node intelligence/morning-run.js --skip notify
node intelligence/morning-run.js --skip write,notify

# Help
node intelligence/morning-run.js --help
```

### Pipeline Stages

1. **collect** — Parallel collection from all sources
   - GitHub: commits, PRs, issues, CI runs
   - GCP: Cloud Run deployments, error logs
   - Station: Claude Code/Cursor sessions

2. **synthesize** — Generate briefing with Gemini 2.5 Flash
   - Structured prompt from collected data
   - Executive summary, highlights, recommendations
   - Fallback to template if API unavailable

3. **write** — Commit logs to adjudica-documentation
   - `logs/commits/YYYY/MM/YYYY-MM-DD.md`
   - `logs/pull_requests/YYYY/MM/YYYY-MM-DD.md`
   - `logs/deployments/YYYY/MM/YYYY-MM-DD.md`
   - `logs/analysis/YYYY/MM/YYYY-MM-DD.md`

4. **notify** — Send briefing to Slack #main

### Pipeline Result

```javascript
{
  date: '2026-03-03',
  success: true,
  stages: {
    collect: { success: true, duration_ms: 4500 },
    synthesize: { success: true, duration_ms: 2100 },
    write: { success: true, duration_ms: 1800 },
    notify: { success: true, duration_ms: 300 }
  },
  collected: {
    github: { commits: 12, prs: 3, issues: 1, ci_runs: 8 },
    gcp: { deployments: 2, errors: 0, projects_monitored: 6 },
    station: { sessions: 4, active_hours: 6.5, projects_touched: 3 }
  },
  briefing: {
    generated: true,
    model_used: 'gemini-2.5-flash',
    fallback_used: false
  },
  written: {
    commits: true,
    prs: true,
    deployments: true,
    analysis: true
  },
  notification: { success: true, channel: '#main' },
  duration_ms: 8700,
  errors: []
}
```

### Test Coverage

**26 test cases implemented:**
- ✅ Full pipeline execution
- ✅ Date handling (default yesterday, specific date)
- ✅ Dry run mode
- ✅ Stage skipping
- ✅ Graceful error handling per stage
- ✅ Error aggregation
- ✅ Batch processing
- ✅ Duration tracking
- ✅ Integration with all modules

---

## Next Steps (Week 2)

1. **Audit Modules:** Implement `claude-md-auditor.js` and `doc-quality-auditor.js`
2. **Web Research:** Implement `web-researcher.js` with Gemini search grounding
3. **Cloud Run Deployment:** Configure Cloud Scheduler for daily 6am UTC runs

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
