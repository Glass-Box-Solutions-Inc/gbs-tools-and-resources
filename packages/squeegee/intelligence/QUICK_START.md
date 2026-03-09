# GCP Collector Quick Start

**For:** Backend engineers integrating the GCP collector
**Updated:** 2026-03-03

---

## 1-Minute Setup

```bash
# Install dependencies
cd /home/vncuser/Squeegee
npm install

# Set up local credentials (development only)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Run tests
npm test
```

---

## Basic Usage

```javascript
const { collect } = require('./intelligence/gcp-collector');

const config = {
  gcp_projects: ['glassbox-squeegee', 'adjudica-internal']
};

// Collect yesterday's logs
const data = await collect('2026-03-03', config);

console.log(`Collected ${data.summary.total_deployments} deployments`);
console.log(`Collected ${data.summary.total_errors} errors`);
```

---

## Common Patterns

### Get Yesterday's Data

```javascript
const { getYesterday } = require('./intelligence/utils');

const yesterday = getYesterday(); // "2026-03-02"
const data = await collect(yesterday, config);
```

### Handle Partial Failures

```javascript
const data = await collect(date, config);

if (data.projects_failed && data.projects_failed.length > 0) {
  console.warn('Some projects failed:', data.projects_failed);
  // Continue processing with partial data
}
```

### Filter by Service

```javascript
const data = await collect(date, config);

const appDeployments = data.deployments.filter(
  d => d.service === 'adjudica-ai-app'
);
```

---

## Troubleshooting

### Error: PERMISSION_DENIED

**Cause:** Service account missing IAM permissions

**Fix:**
```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:YOUR_SA@PROJECT.iam.gserviceaccount.com" \
  --role="roles/logging.viewer"
```

### Error: Application Default Credentials not found

**Local Dev:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

**Cloud Run:**
- Ensure service account is attached to container
- Verify volume mounts in Cloud Run configuration

### Empty Results

**Check:**
1. Date range is correct (YYYY-MM-DD format)
2. Projects actually have Cloud Run services
3. Logs exist in timeframe (check GCP Console)

---

## Testing

### Run Specific Test

```bash
npm test -- tests/intelligence/gcp-collector.test.js
```

### Watch Mode

```bash
npm run test:watch
```

### Coverage Report

```bash
npm run test:coverage
open coverage/lcov-report/index.html
```

---

## Integration Checklist

- [ ] Add `gcp_projects` to `intelligence.config.json`
- [ ] Grant IAM permissions to service account
- [ ] Test with dry-run mode first
- [ ] Verify output format matches expectations
- [ ] Check logs for permission errors
- [ ] Monitor quota usage (Cloud Logging API)

---

## Support

**Documentation:** `/home/vncuser/Squeegee/intelligence/README.md`
**Architecture:** `/.planning/INTELLIGENCE_ARCHITECTURE.md`
**Config Schema:** `/.planning/INTELLIGENCE_CONFIG_SCHEMA.md`

---

*@Developed & Documented by Glass Box Solutions, Inc.*
