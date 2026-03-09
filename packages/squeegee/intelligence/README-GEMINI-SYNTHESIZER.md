# Gemini Synthesizer Module

**Module:** `intelligence/gemini-synthesizer.js`
**Purpose:** Generate daily intelligence briefings from collected GitHub, GCP, and station data using Gemini 2.0 Flash

---

## Overview

The Gemini Synthesizer transforms raw intelligence data into structured, human-readable briefings using Google's Gemini AI model. It provides:

- **AI-powered analysis** — Gemini identifies patterns, anomalies, and key insights
- **Structured output** — 6 standardized sections for consistent briefings
- **Graceful fallback** — Template-based briefing if Gemini API unavailable
- **Retry logic** — Automatic retry on transient API failures
- **Token management** — Input truncation to stay within token limits

---

## API

### Main Function

```javascript
async function synthesize(date, collectedData, config)
```

**Parameters:**
- `date` (Date|string) — Date of intelligence data (YYYY-MM-DD or Date object)
- `collectedData` (Object) — Combined data from collectors
  - `github` (Object) — GitHub activity from `github-collector`
  - `gcp` (Object) — GCP logs from `gcp-collector`
  - `station` (Object) — Station activity from `station-collector`
  - `checkpoints` (Array) — Checkpoint events
- `config` (Object) — Intelligence configuration
  - `intelligence.gemini.apiKey` (string) — Gemini API key
  - `intelligence.gemini.model` (string) — Model name (default: `gemini-2.0-flash-exp`)
  - `intelligence.gemini.temperature` (number) — Temperature (default: 0.3)
  - `intelligence.gemini.max_output_tokens` (number) — Max tokens (default: 4096)

**Returns:** Promise<GeminiBriefing>

```typescript
interface GeminiBriefing {
  date: string;                       // YYYY-MM-DD
  executive_summary: string[];        // 2-3 bullet points
  repository_activity: string;        // Markdown section
  deployment_events: string;          // Markdown section
  development_activity: string;       // Markdown section
  context_checkpoints: string;        // Markdown section
  observations: string;               // Gemini analysis & recommendations
  generated_at: string;               // ISO 8601 timestamp
  model_used: string;                 // Model name or "fallback-template"
  token_count: {
    input: number;
    output: number;
  };
  fallback_used: boolean;             // true if Gemini unavailable
  error: string | null;               // Error message if partial failure
}
```

---

## Usage Examples

### Basic Usage

```javascript
const { synthesize } = require('./intelligence/gemini-synthesizer');

const collectedData = {
  github: await githubCollector.collect('2026-03-03', config),
  gcp: await gcpCollector.collect('2026-03-03', config),
  station: await stationCollector.collect(config),
  checkpoints: await loadCheckpoints()
};

const briefing = await synthesize('2026-03-03', collectedData, config);

console.log(briefing.executive_summary);
// ["42 commits across 27 repositories", "5 deployments, 2 errors logged", ...]

console.log(briefing.observations);
// "Key concerns: Failed deployment in glassy-personal-ai requires attention..."
```

### With Date Object

```javascript
const yesterday = new Date();
yesterday.setDate(yesterday.getDate() - 1);

const briefing = await synthesize(yesterday, collectedData, config);
```

### Handling Fallback

```javascript
const briefing = await synthesize('2026-03-03', collectedData, config);

if (briefing.fallback_used) {
  console.warn('Gemini API unavailable, using template-based briefing');
  console.warn('Error:', briefing.error);
}

// Briefing is still usable, just less analytical
console.log(briefing.repository_activity); // Table of repo activity
```

---

## Prompt Engineering

### System Context

The module sends a structured prompt to Gemini with:

1. **Role definition** — "You are an engineering intelligence analyst..."
2. **Date context** — The specific date being analyzed
3. **Focus areas** — What to look for (commits, deployments, anomalies, etc.)
4. **Formatted data** — All collected data in markdown tables/lists
5. **Output instructions** — Exact section structure required

### Data Formatting

Each data source is formatted into markdown for optimal Gemini comprehension:

- **GitHub:** Summary stats → Top active repos → Sample commits
- **GCP:** Deployment counts → Success/failure breakdown → Error severity distribution
- **Station:** Session counts → Tool usage → Squeegee state
- **Checkpoints:** Total events → Grouping by repo → User/phase breakdown

### Response Template

Gemini is instructed to return:

```markdown
## Executive Summary
- [2-3 key points]

## Development Highlights
[Notable commits, features, bug fixes]

## Pull Request Activity
[Merge patterns, review activity]

## Infrastructure & Operations
[Deployments, errors, performance]

## Team Activity
[Active projects, tool usage, collaboration]

## Recommendations
[Action items, follow-ups, concerns]
```

---

## Fallback Briefing

When Gemini API is unavailable (missing API key, quota exceeded, service down), the module generates a template-based briefing:

**Fallback includes:**
- Executive summary from raw data counts
- Markdown table of repository activity
- List of deployments by project
- Development activity summary
- Checkpoint events
- Warning message about fallback mode

**Example:**

```javascript
{
  date: '2026-03-03',
  executive_summary: [
    '42 commits across 27 repositories',
    '5 pull requests (3 merged)',
    '2 deployments, 1 errors logged'
  ],
  repository_activity: '| Repository | Commits | PRs | Issues |\n...',
  observations: '⚠️ This briefing was generated using a fallback template...',
  fallback_used: true,
  model_used: 'fallback-template',
  error: 'API quota exceeded'
}
```

---

## Error Handling

### Retry Strategy

1. **First attempt** — Call Gemini API
2. **On failure** — Wait 2 seconds, retry
3. **Second failure** — Wait 4 seconds, retry
4. **Third failure** — Return fallback briefing

**Retryable errors:**
- Rate limit (429)
- Server error (500)
- Timeout

**Non-retryable errors:**
- Missing API key → Immediate fallback
- Invalid request (400) → Immediate fallback
- Empty response → Immediate fallback

### Error Logging

```javascript
// Retry attempt logged
console.warn('Retry attempt 1/3 after 2000ms delay', {
  error: 'API quota exceeded',
  recoverable: true
});

// Final failure logged
console.error('Gemini synthesis failed, using fallback briefing:', error.message);
```

---

## Token Management

### Input Token Estimation

```javascript
const inputTokenEstimate = Math.ceil(prompt.length / 4);
```

**Heuristic:** ~4 characters per token (rough approximation)

### Token Limits

| Model | Max Input Tokens | Max Output Tokens |
|-------|------------------|-------------------|
| gemini-2.0-flash-exp | 1,048,576 | 8,192 |
| gemini-1.5-flash | 1,048,576 | 8,192 |
| gemini-1.5-pro | 2,097,152 | 8,192 |

**Configuration override:**

```json
{
  "intelligence": {
    "gemini": {
      "max_output_tokens": 4096
    }
  }
}
```

### Data Truncation

If collected data is very large (e.g., 1000+ commits), the formatting functions automatically truncate:

- **Commits:** Top 5 per repo
- **Repos:** Top 10 by activity
- **Checkpoints:** Top 3 per repo

---

## Testing

### Run Unit Tests

```bash
npm test tests/intelligence/gemini-synthesizer.test.js
```

### Test Coverage

The test suite covers:
- ✅ Formatting functions (all data types)
- ✅ Prompt generation
- ✅ Response parsing
- ✅ Fallback briefing generation
- ✅ Happy path (Gemini success)
- ✅ API key missing (fallback)
- ✅ API failure (retry + fallback)
- ✅ Empty response handling
- ✅ Retry logic
- ✅ Partial data handling
- ✅ Token estimation
- ✅ Large dataset handling

**Target coverage:** >80%

### Manual Testing

```bash
# Set API key
export GOOGLE_AI_API_KEY="your-api-key"

# Run synthesizer standalone
node -e "
const { synthesize } = require('./intelligence/gemini-synthesizer');
const config = require('./config/intelligence.config.json');

const mockData = {
  github: { repos: {}, summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 } },
  gcp: { deployments: [], errors: [], summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 } },
  station: { claude_code_sessions: [], cursor_active: false, squeegee_state: {} },
  checkpoints: []
};

synthesize('2026-03-03', mockData, config)
  .then(briefing => console.log(JSON.stringify(briefing, null, 2)))
  .catch(err => console.error(err));
"
```

---

## Configuration

### Required Environment Variables

```bash
# Gemini API key (loaded from Secret Manager in production)
GOOGLE_AI_API_KEY=/secrets/gemini-api-key
```

### Configuration File

**File:** `config/intelligence.config.json`

```json
{
  "intelligence": {
    "gemini": {
      "model": "gemini-2.0-flash-exp",
      "temperature": 0.3,
      "max_output_tokens": 4096,
      "api_key_secret": "gemini-api-key"
    }
  }
}
```

### Runtime Overrides

```bash
# Override model
export GEMINI_MODEL=gemini-1.5-pro

# Override temperature
export GEMINI_TEMPERATURE=0.5
```

---

## Performance

### Typical Metrics

| Data Size | Input Tokens | Output Tokens | Latency | Cost (est.) |
|-----------|--------------|---------------|---------|-------------|
| Small (1 repo, 10 commits) | ~2,000 | ~600 | 3-5s | $0.001 |
| Medium (10 repos, 100 commits) | ~8,000 | ~1,200 | 5-8s | $0.003 |
| Large (27 repos, 500 commits) | ~20,000 | ~2,000 | 8-12s | $0.008 |

**Notes:**
- Latency varies by model and API load
- Cost based on Gemini 2.0 Flash pricing ($0.00001/input token, $0.00004/output token)

---

## Troubleshooting

### Issue: "Gemini API key not configured"

**Cause:** Missing API key in config or environment

**Fix:**
```bash
# Verify secret exists
gcloud secrets versions access latest --secret=gemini-api-key

# Check Cloud Run volume mount
kubectl get service squeegee -o yaml | grep -A 10 volumeMounts
```

### Issue: "API quota exceeded"

**Cause:** Too many requests

**Fix:**
```json
{
  "intelligence": {
    "rate_limits": {
      "gemini": {
        "requests_per_minute": 30
      }
    }
  }
}
```

### Issue: "Empty response from Gemini"

**Cause:** Model returned no text (rare)

**Fix:** Module automatically uses fallback. Check model configuration:
```json
{
  "intelligence": {
    "gemini": {
      "model": "gemini-2.0-flash-exp"
    }
  }
}
```

### Issue: "Briefing quality is low"

**Cause:** Fallback template used instead of Gemini

**Fix:**
```javascript
if (briefing.fallback_used) {
  console.log('Fallback reason:', briefing.error);
  // Resolve Gemini API issue
}
```

---

## Integration with Pipeline

The gemini-synthesizer is called by `stage-15-intelligence-synthesize.js`:

```javascript
// stages/15-intelligence-synthesize.js
const { synthesize } = require('../intelligence/gemini-synthesizer');

async function run(context) {
  const { date, collectedData, config } = context;

  const briefing = await synthesize(date, collectedData, config);

  // Pass to stage 16 (log-writer)
  context.briefing = briefing;

  return {
    status: briefing.fallback_used ? 'partial' : 'success',
    briefing
  };
}
```

---

## Related Modules

| Module | Purpose |
|--------|---------|
| `github-collector.js` | Collects GitHub activity data |
| `gcp-collector.js` | Collects GCP Cloud Logging data |
| `station-collector.js` | Collects dev workstation activity |
| `log-writer.js` | Writes briefing to `adjudica-documentation/logs/` |
| `utils.js` | Shared error handling and retry logic |

---

## Future Enhancements

- [ ] Multi-day trend analysis (compare with previous days)
- [ ] Custom prompt templates per use case
- [ ] Briefing quality scoring (self-assessment)
- [ ] Gemini Search Grounding for external context
- [ ] Thinking mode support (gemini-2.0-flash-thinking-exp)
- [ ] Caching for repeated prompts

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
