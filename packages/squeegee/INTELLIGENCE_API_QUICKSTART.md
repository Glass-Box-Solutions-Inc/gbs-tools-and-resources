# Intelligence API Quick Start

Fast-track guide for using Squeegee's Intelligence API.

## Local Development

### 1. Setup Environment

```bash
# Clone and install
cd /home/vncuser/Squeegee
npm install

# Create config (if not exists)
cp config/intelligence.config.json config/intelligence.local.json

# Edit for local testing
nano config/intelligence.local.json
```

### 2. Configure for Local Testing

**Minimal config for local development:**

```json
{
  "intelligence": {
    "enabled": true,
    "repos": ["Squeegee"],  // Test with single repo
    "gcp_projects": ["glassbox-squeegee"],
    "docs_repo": "your-username/test-docs-repo",
    "gemini": {
      "model": "gemini-2.0-flash-exp",
      "temperature": 0.3,
      "max_output_tokens": 2048
    },
    "dry_run": true  // IMPORTANT: Don't write to production
  }
}
```

### 3. Set Environment Variables

```bash
# Create a .env file (not committed)
cat > .env << EOF
INTELLIGENCE_DRY_RUN=true
GOOGLE_AI_API_KEY=/path/to/gemini-key.txt
GITHUB_TOKEN=/path/to/github-token.txt
NODE_ENV=development
LOG_LEVEL=debug
EOF

# Load environment
export $(cat .env | xargs)
```

### 4. Start Server

```bash
npm run dev
# Server runs on http://localhost:8080
```

### 5. Test Endpoints (No Auth in Local)

```bash
# Get status
curl http://localhost:8080/api/intelligence/status | jq

# Collect data (dry-run)
curl -X POST http://localhost:8080/api/intelligence/collect \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-13"}' | jq

# Full run (dry-run)
curl -X POST http://localhost:8080/api/intelligence/run \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-13"}' | jq
```

---

## Production Usage

### 1. Get Auth Token

```bash
# Get Cloud Run OIDC token
TOKEN=$(gcloud auth print-identity-token)

# Set base URL
BASE_URL="https://squeegee-916151540991.us-central1.run.app/api/intelligence"
```

### 2. Common Commands

**Check system status:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/status | jq
```

**Trigger daily run:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-13"}' \
  $BASE_URL/run | jq
```

**Force CLAUDE.md audit:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force": {"claudeMdAudit": true}}' \
  $BASE_URL/run | jq
```

**Collect only (no synthesis):**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-12"}' \
  $BASE_URL/collect | jq > collected-data.json
```

**Run audit independently:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/audit-claude-md | jq
```

### 3. Monitor Runs

**Check last run status:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/status | jq '.last_run'
```

**Check next scheduled runs:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/status | jq '.next_scheduled'
```

---

## Run Tests

```bash
# Run all intelligence tests
npm test -- tests/api/intelligence.test.js

# Run with coverage
npm run test:coverage -- tests/api/intelligence.test.js

# Watch mode
npm run test:watch -- tests/api/intelligence.test.js
```

---

## Common Workflows

### Workflow 1: Backfill Historical Data

```bash
#!/bin/bash
TOKEN=$(gcloud auth print-identity-token)
BASE_URL="https://squeegee-916151540991.us-central1.run.app/api/intelligence"

# Backfill last 7 days
for i in {1..7}; do
  DATE=$(date -d "$i days ago" +%Y-%m-%d)
  echo "Backfilling $DATE..."

  curl -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"date\": \"$DATE\"}" \
    $BASE_URL/run

  sleep 60  # Rate limit: 1 per minute
done
```

### Workflow 2: Audit All Repos

```bash
TOKEN=$(gcloud auth print-identity-token)
BASE_URL="https://squeegee-916151540991.us-central1.run.app/api/intelligence"

# Run audit
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/audit-claude-md | jq '.report.summary'

# Extract repos needing PRs
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/audit-claude-md | \
  jq -r '.report.details[] | select(.needs_pr == true) | .repo'
```

### Workflow 3: Custom Research Topic

```bash
TOKEN=$(gcloud auth print-identity-token)
BASE_URL="https://squeegee-916151540991.us-central1.run.app/api/intelligence"

# Run research (when implemented)
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topic": "AI-readable documentation best practices"}' \
  $BASE_URL/research
```

---

## Configuration Quick Reference

### Enable/Disable Intelligence

```bash
# Via environment variable (no file edit needed)
export INTELLIGENCE_ENABLED=false

# Or edit config
nano config/intelligence.config.json
# Set: "enabled": false
```

### Change Gemini Model

```bash
# Via environment variable
export GEMINI_MODEL=gemini-1.5-pro

# Or edit config
nano config/intelligence.config.json
# Set: "model": "gemini-1.5-pro"
```

### Dry-Run Mode

```bash
# Enable dry-run (no GitHub writes)
export INTELLIGENCE_DRY_RUN=true

# Or edit config
nano config/intelligence.config.json
# Set: "dry_run": true
```

---

## Troubleshooting

### "Configuration not available"

```bash
# Check config file exists
ls -la config/intelligence.config.json

# Check JSON syntax
cat config/intelligence.config.json | jq
```

### "Missing required secret: GITHUB_TOKEN"

```bash
# Check environment variable
echo $GITHUB_TOKEN

# Check secret file exists (Cloud Run)
ls -la /secrets/github-pat-glassbox
```

### "Gemini API error"

```bash
# Check API key loaded
curl -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/status | jq '.modules."gemini-synthesizer"'

# Should be "ok", not "missing_api_key"
```

### "Intelligence disabled"

```bash
# Check configuration
curl -H "Authorization: Bearer $TOKEN" \
  $BASE_URL/status | jq '.enabled'

# Should be true
```

---

## Advanced Usage

### Collect → Synthesize → Write (Manual Pipeline)

```bash
TOKEN=$(gcloud auth print-identity-token)
BASE_URL="https://squeegee-916151540991.us-central1.run.app/api/intelligence"

# Step 1: Collect
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-13"}' \
  $BASE_URL/collect > collected.json

# Step 2: Synthesize
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @collected.json \
  $BASE_URL/synthesize > briefing.json

# Step 3: Notify (when implemented)
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @briefing.json \
  $BASE_URL/notify
```

### Custom Date Range Analysis

```bash
#!/bin/bash
# Collect data for date range and aggregate

TOKEN=$(gcloud auth print-identity-token)
BASE_URL="https://squeegee-916151540991.us-central1.run.app/api/intelligence"

START_DATE="2026-03-01"
END_DATE="2026-03-07"

# Collect all dates
for DATE in $(seq -f "%F" $(date -d "$START_DATE" +%s) 86400 $(date -d "$END_DATE" +%s)); do
  echo "Collecting $DATE..."
  curl -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"date\": \"$DATE\"}" \
    $BASE_URL/collect >> weekly-data.jsonl
done

# Aggregate metrics
cat weekly-data.jsonl | jq -s '[.[] | .metrics] | {
  total_commits: (map(.total_commits) | add),
  total_prs: (map(.total_prs) | add),
  total_deployments: (map(.deployments) | add)
}'
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Daily Intelligence Run

on:
  schedule:
    - cron: '0 7 * * *'  # 7am UTC daily
  workflow_dispatch:

jobs:
  intelligence:
    runs-on: ubuntu-latest
    steps:
      - name: Authenticate to GCP
        uses: google-github-actions/auth@v1
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Get OIDC token
        id: token
        run: echo "TOKEN=$(gcloud auth print-identity-token)" >> $GITHUB_OUTPUT

      - name: Trigger intelligence run
        run: |
          curl -X POST \
            -H "Authorization: Bearer ${{ steps.token.outputs.TOKEN }}" \
            -H "Content-Type: application/json" \
            -d '{"date": "'$(date -d yesterday +%Y-%m-%d)'"}' \
            https://squeegee-916151540991.us-central1.run.app/api/intelligence/run
```

---

## Monitoring

### Cloud Logging Queries

```bash
# View intelligence API logs
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=squeegee \
  AND jsonPayload.url=~\"/api/intelligence\"" \
  --limit 50 \
  --format json

# View only errors
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=squeegee \
  AND jsonPayload.url=~\"/api/intelligence\" \
  AND severity>=ERROR" \
  --limit 20
```

### Metrics Dashboard

Key metrics to monitor:
- Intelligence run success rate
- Stage execution time
- Gemini API token usage
- GitHub API rate limit remaining
- Briefing generation failures

---

## Related Documentation

- [Full API Reference](src/api/README.md)
- [Intelligence Architecture](../.planning/INTELLIGENCE_ARCHITECTURE.md)
- [Configuration Schema](../.planning/INTELLIGENCE_CONFIG_SCHEMA.md)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
