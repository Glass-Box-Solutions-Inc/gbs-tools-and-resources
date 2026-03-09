# Intelligence Pipeline Integration Tests

Comprehensive end-to-end integration tests for Squeegee's intelligence system (stages 14-20).

## Test Coverage

### Pipeline Integration (`intelligence-pipeline.test.js`)

**Full Daily Run (Stages 14-16)** - 5 tests
- Complete pipeline execution (collect → synthesize → write)
- Parallel data collection from all sources
- Context data flow validation between stages
- Metrics calculation accuracy
- Stage dependency validation (fail when data missing)

**Weekly CLAUDE.md Audit (Stage 17)** - 5 tests
- Sunday execution
- Weekday skipping (Monday-Saturday)
- Force flag override
- Error handling
- Next run calculation

**Monthly Doc Quality Audit (Stage 18)** - 5 tests
- 1st of month execution
- Non-1st day skipping
- Force flag override
- Year boundary handling
- Placeholder validation (not yet implemented)

**Quarterly Research (Stage 19)** - 8 tests
- Q1/Q2/Q3/Q4 execution (Jan 1, Apr 1, Jul 1, Oct 1)
- Non-quarter skipping
- Force flag override
- Year rollover (Dec → Jan)
- Next run calculation

**Error Handling & Partial Failures** - 5 tests
- Gemini fallback when API unavailable
- Partial log write failures
- GitHub collector partial failures
- Complete collector failures
- Synthesis failures

**Configuration Validation** - 2 tests
- Required config fields
- Schedule configuration

**Total: 30 integration tests**

---

### API Integration (`intelligence-api.test.js`)

**POST /api/intelligence/run** - 6 tests
- Full pipeline execution via API
- Force flags for conditional stages
- Dry run mode
- Authentication validation
- Date format validation
- Default date handling (yesterday)

**POST /api/intelligence/collect** - 2 tests
- Data collection endpoint
- Error handling

**POST /api/intelligence/synthesize** - 2 tests
- Briefing generation from data
- Request validation

**POST /api/intelligence/audit-claude-md** - 2 tests
- CLAUDE.md compliance audit
- Error handling

**POST /api/intelligence/audit-doc-quality** - 1 test
- Not implemented placeholder

**POST /api/intelligence/research** - 2 tests
- Not implemented placeholder
- Request validation

**POST /api/intelligence/notify** - 1 test
- Not implemented placeholder

**GET /api/intelligence/status** - 3 tests
- System health check
- Gemini API key validation
- Authentication validation

**Total: 19 API tests**

---

## Test Fixtures

All fixtures located in `/tests/fixtures/`:

| File | Description | Size |
|------|-------------|------|
| `github-activity.json` | Sample GitHub commit and PR data | 3 repos, 4 commits, 1 PR |
| `gcp-logs.json` | Sample GCP deployment and error logs | 3 deployments, 2 errors |
| `station-activity.json` | Sample dev station activity | 4 sessions, 225 minutes |
| `gemini-briefing.json` | Sample Gemini-generated briefing | 3 summary points, detailed analysis |
| `claude-md-audit-report.json` | Sample CLAUDE.md audit results | 27 repos, avg score 11.2 |

---

## Running Tests

```bash
# Run all integration tests
npm test tests/integration/

# Run pipeline tests only
npm test tests/integration/intelligence-pipeline.test.js

# Run API tests only
npm test tests/integration/intelligence-api.test.js

# Run with coverage
npm run test:coverage -- tests/integration/

# Run in watch mode during development
npm test -- --watch tests/integration/
```

---

## Mock Strategy

### External Dependencies

**GitHub API (`@octokit/rest`)**
- Mocked via `vi.spyOn(githubCollector, 'collect')`
- Returns fixture data or errors

**GCP Logging (`@google-cloud/logging`)**
- Mocked via `vi.spyOn(gcpCollector, 'collect')`
- Returns fixture deployment and error logs

**Filesystem (station monitor)**
- Mocked via `vi.spyOn(stationMonitor, 'collect')`
- Returns fixture dev session data

**Gemini API (`@google/generative-ai`)**
- Mocked via `vi.spyOn(geminiSynthesizer, 'synthesize')`
- Returns fixture briefing or fallback

**Log Writer (GitHub API writes)**
- Mocked via `vi.spyOn(logWriter, 'write')`
- Simulates successful/failed writes

### Fastify API Testing

API tests use `fastify.inject()` for HTTP simulation:
- No actual HTTP server started
- Authentication middleware mocked to accept any bearer token
- Full request/response cycle validation

---

## Test Patterns

### Arrange-Act-Assert

All tests follow AAA pattern:

```javascript
it('should run audit on Sunday', async () => {
  // Arrange
  vi.spyOn(claudeMdAuditor, 'audit').mockResolvedValue(fixtureClaudeMdAudit);
  const sunday = new Date('2026-03-16');
  const context = { date: sunday, config: mockConfig };

  // Act
  const result = await stage17.run(mockConfig, context);

  // Assert
  expect(result.status).toBe('success');
  expect(context.claudeMdAudit.repos_audited).toBe(27);
});
```

### Scheduling Logic Tests

Date-based scheduling tests use specific dates:

```javascript
const sunday = new Date('2026-03-16');     // Sunday (day 0)
const monday = new Date('2026-03-10');     // Monday (day 1)
const firstOfMonth = new Date('2026-03-01'); // 1st day
const jan1 = new Date('2026-01-01');       // Q1 start
const apr1 = new Date('2026-04-01');       // Q2 start
```

### Error Handling Tests

Error scenarios tested with mock rejections:

```javascript
it('should use fallback when Gemini unavailable', async () => {
  const fallbackBriefing = { ...fixtureBriefing, fallback_used: true };
  vi.spyOn(geminiSynthesizer, 'synthesize').mockResolvedValue(fallbackBriefing);

  const result = await stage15.run(mockConfig, context);

  expect(result.status).toBe('partial');
  expect(result.fallback_used).toBe(true);
});
```

---

## Coverage Goals

- **Pipeline stages:** >80% line coverage
- **Scheduling logic:** 100% branch coverage
- **Error paths:** 100% coverage
- **API endpoints:** >85% coverage

---

## Future Enhancements

When stages 18-20 are fully implemented, add tests for:

1. **Doc Quality Auditor (Stage 18)**
   - 10-point rubric scoring
   - Registry file writing
   - PR creation logic

2. **Web Researcher (Stage 19)**
   - Multiple topic research
   - Research report consolidation
   - Output file writing

3. **Slack Notifier (Stage 20)**
   - Briefing formatting
   - Slack webhook delivery
   - Error notifications

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
