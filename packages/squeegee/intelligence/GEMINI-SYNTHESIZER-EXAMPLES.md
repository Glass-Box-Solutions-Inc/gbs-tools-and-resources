# Gemini Synthesizer - Usage Examples

**Quick reference for common gemini-synthesizer scenarios**

---

## Example 1: Basic Daily Briefing

```javascript
const { synthesize } = require('./intelligence/gemini-synthesizer');
const githubCollector = require('./intelligence/github-collector');
const gcpCollector = require('./intelligence/gcp-collector');
const stationCollector = require('./intelligence/station-collector');

// Load configuration
const config = {
  intelligence: {
    repos: ['adjudica-ai-app', 'glassy-personal-ai', 'Squeegee'],
    gcp_projects: ['glassbox-squeegee', 'glassy-personal-ai'],
    gemini: {
      apiKey: process.env.GOOGLE_AI_API_KEY,
      model: 'gemini-2.0-flash-exp',
      temperature: 0.3,
      max_output_tokens: 4096
    }
  }
};

// Collect data
const date = '2026-03-03';
const github = await githubCollector.collect(date, config);
const gcp = await gcpCollector.collect(date, config);
const station = await stationCollector.collect(config);
const checkpoints = []; // Load from queue

// Generate briefing
const briefing = await synthesize(date, { github, gcp, station, checkpoints }, config);

console.log(briefing.executive_summary);
// ["42 commits across 3 repositories", "5 deployments, 2 errors logged"]

console.log(briefing.observations);
// "Key concerns: Failed deployment in glassy-personal-ai at 14:32 UTC..."
```

---

## Example 2: Handling Fallback Mode

```javascript
const briefing = await synthesize('2026-03-03', collectedData, config);

if (briefing.fallback_used) {
  // Log warning to monitoring system
  console.warn('⚠️ Gemini API unavailable, fallback briefing generated');
  console.warn('Reason:', briefing.error);

  // Send alert to Slack
  await sendSlackAlert({
    channel: '#alerts',
    message: `Gemini API failed: ${briefing.error}`,
    severity: 'warning'
  });

  // Briefing is still usable, just template-based
  console.log('Fallback briefing contains:');
  console.log('- Executive summary:', briefing.executive_summary.length, 'points');
  console.log('- Repository table:', briefing.repository_activity.includes('|'));
  console.log('- Deployment events:', briefing.deployment_events.length > 0);
}
```

---

## Example 3: Custom Prompt for Specific Analysis

```javascript
const { formatPrompt } = require('./intelligence/gemini-synthesizer');

// Build custom prompt
const data = {
  date: '2026-03-03',
  github: { /* data */ },
  gcp: { /* data */ },
  station: { /* data */ },
  checkpoints: []
};

const basePrompt = formatPrompt(data);

// Add custom instructions
const customPrompt = basePrompt + `\n\n**ADDITIONAL FOCUS:**
- Identify any security-related commits (auth, permissions, secrets)
- Flag deployments that failed after 5pm UTC (off-hours)
- Highlight unusually high token usage in Claude Code sessions

Include a "Security & Operations" section in your response.`;

// Call Gemini manually with custom prompt
const genAI = new GoogleGenerativeAI(config.intelligence.gemini.apiKey);
const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash-exp' });
const result = await model.generateContent(customPrompt);
const responseText = result.response.text();

console.log(responseText);
```

---

## Example 4: Testing with Mock Data

```javascript
// Create minimal mock data for testing
const mockData = {
  github: {
    repos: {
      'test-repo': {
        commits: [
          { sha: 'abc123', message: 'feat: add feature', author: 'Alice' },
          { sha: 'def456', message: 'fix: bug fix', author: 'Bob' }
        ],
        pull_requests: [
          { number: 42, title: 'Add tests', state: 'merged', author: 'Alice', labels: [] }
        ],
        issues: [],
        ci_runs: []
      }
    },
    summary: { total_commits: 2, total_prs: 1, total_issues: 0, total_ci_runs: 0 }
  },
  gcp: {
    deployments: [
      { project: 'test-project', service: 'test-service', status: 'success', revision: 'rev1', timestamp: '2026-03-03T10:00:00Z' }
    ],
    errors: [],
    summary: { total_deployments: 1, total_errors: 0, projects_monitored: 1 }
  },
  station: {
    claude_code_sessions: [],
    cursor_active: false,
    squeegee_state: {}
  },
  checkpoints: []
};

const briefing = await synthesize('2026-03-03', mockData, config);

console.log('Generated briefing:', briefing.date);
console.log('Fallback used?', briefing.fallback_used);
console.log('Token usage:', briefing.token_count);
```

---

## Example 5: Multi-Day Comparison (Manual)

```javascript
// Collect data for multiple days
const dates = ['2026-03-01', '2026-03-02', '2026-03-03'];
const briefings = [];

for (const date of dates) {
  const github = await githubCollector.collect(date, config);
  const gcp = await gcpCollector.collect(date, config);
  const station = await stationCollector.collect(config);

  const briefing = await synthesize(date, { github, gcp, station, checkpoints: [] }, config);
  briefings.push(briefing);
}

// Compare trends
console.log('Commit trends:');
briefings.forEach(b => {
  const commitCount = b.executive_summary[0].match(/(\d+) commits/)?.[1] || 0;
  console.log(`${b.date}: ${commitCount} commits`);
});

// Identify spikes
const commitCounts = briefings.map(b =>
  parseInt(b.executive_summary[0].match(/(\d+) commits/)?.[1] || 0)
);
const avgCommits = commitCounts.reduce((a, b) => a + b, 0) / commitCounts.length;
const maxCommits = Math.max(...commitCounts);

if (maxCommits > avgCommits * 1.5) {
  console.log('⚠️ Commit spike detected:', maxCommits, 'vs avg', avgCommits);
}
```

---

## Example 6: Error Recovery Flow

```javascript
const { synthesize } = require('./intelligence/gemini-synthesizer');
const { retryWithBackoff } = require('./intelligence/utils');

async function generateBriefingWithRecovery(date, data, config) {
  try {
    // Attempt 1: Try with primary model
    const briefing = await synthesize(date, data, config);

    if (!briefing.fallback_used) {
      return { status: 'success', briefing };
    }

    // Attempt 2: If fallback used, try with alternative model
    console.log('Primary model failed, trying gemini-1.5-flash...');
    const altConfig = {
      ...config,
      intelligence: {
        ...config.intelligence,
        gemini: {
          ...config.intelligence.gemini,
          model: 'gemini-1.5-flash'
        }
      }
    };

    const altBriefing = await synthesize(date, data, altConfig);

    if (!altBriefing.fallback_used) {
      return { status: 'recovered', briefing: altBriefing };
    }

    // Attempt 3: Use fallback gracefully
    return { status: 'fallback', briefing: altBriefing };

  } catch (error) {
    console.error('Fatal error generating briefing:', error);
    throw error;
  }
}

// Usage
const result = await generateBriefingWithRecovery('2026-03-03', collectedData, config);

if (result.status === 'success') {
  console.log('✅ Briefing generated successfully');
} else if (result.status === 'recovered') {
  console.log('⚠️ Briefing generated with fallback model');
} else {
  console.log('❌ Using template-based briefing');
}
```

---

## Example 7: Token Usage Monitoring

```javascript
const briefings = [];
const tokenUsage = {
  total_input: 0,
  total_output: 0,
  total_cost: 0
};

// Gemini 2.0 Flash pricing (as of Jan 2025)
const PRICE_PER_INPUT_TOKEN = 0.00001;
const PRICE_PER_OUTPUT_TOKEN = 0.00004;

for (let day = 1; day <= 30; day++) {
  const date = `2026-03-${String(day).padStart(2, '0')}`;
  const briefing = await synthesize(date, collectedData, config);

  briefings.push(briefing);

  if (!briefing.fallback_used) {
    tokenUsage.total_input += briefing.token_count.input;
    tokenUsage.total_output += briefing.token_count.output;
    tokenUsage.total_cost +=
      (briefing.token_count.input * PRICE_PER_INPUT_TOKEN) +
      (briefing.token_count.output * PRICE_PER_OUTPUT_TOKEN);
  }
}

console.log('Monthly token usage:');
console.log('- Input tokens:', tokenUsage.total_input.toLocaleString());
console.log('- Output tokens:', tokenUsage.total_output.toLocaleString());
console.log('- Estimated cost: $' + tokenUsage.total_cost.toFixed(2));
console.log('- Fallback rate:',
  briefings.filter(b => b.fallback_used).length / briefings.length * 100 + '%'
);
```

---

## Example 8: Custom Section Extraction

```javascript
const { parseBriefing } = require('./intelligence/gemini-synthesizer');

// Generate briefing
const briefing = await synthesize('2026-03-03', collectedData, config);

// Extract specific section
const recommendationsSection = briefing.observations;

// Parse recommendations into actionable items
const actionItems = recommendationsSection
  .split('\n')
  .filter(line => line.trim().startsWith('-'))
  .map(line => line.replace(/^-\s*/, '').trim());

console.log('Action items for today:');
actionItems.forEach((item, i) => {
  console.log(`${i + 1}. ${item}`);
});

// Create GitHub issues for critical items
const criticalKeywords = ['urgent', 'critical', 'failed', 'error'];
const criticalItems = actionItems.filter(item =>
  criticalKeywords.some(keyword => item.toLowerCase().includes(keyword))
);

for (const item of criticalItems) {
  await createGitHubIssue({
    title: `[Intelligence Alert] ${item.substring(0, 50)}...`,
    body: `**Source:** Daily intelligence briefing for ${briefing.date}\n\n${item}`,
    labels: ['intelligence', 'urgent']
  });
}
```

---

## Example 9: Integration with Slack Notifications

```javascript
const { synthesize } = require('./intelligence/gemini-synthesizer');

async function postDailyBriefingToSlack(date, data, config) {
  const briefing = await synthesize(date, data, config);

  // Build Slack message
  const slackMessage = {
    channel: '#daily-intelligence',
    blocks: [
      {
        type: 'header',
        text: {
          type: 'plain_text',
          text: `📊 Intelligence Briefing - ${briefing.date}`
        }
      },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: '*Executive Summary:*\n' + briefing.executive_summary.map(s => `• ${s}`).join('\n')
        }
      },
      {
        type: 'divider'
      },
      {
        type: 'section',
        fields: [
          {
            type: 'mrkdwn',
            text: `*Model:*\n${briefing.model_used}`
          },
          {
            type: 'mrkdwn',
            text: `*Tokens:*\n${briefing.token_count.input + briefing.token_count.output}`
          }
        ]
      }
    ]
  };

  if (briefing.fallback_used) {
    slackMessage.blocks.push({
      type: 'context',
      elements: [
        {
          type: 'mrkdwn',
          text: `⚠️ Fallback mode: ${briefing.error}`
        }
      ]
    });
  }

  // Add link to full briefing
  slackMessage.blocks.push({
    type: 'actions',
    elements: [
      {
        type: 'button',
        text: {
          type: 'plain_text',
          text: 'View Full Briefing'
        },
        url: `https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/logs/analysis/${briefing.date.substring(0, 4)}/${briefing.date.substring(5, 7)}/${briefing.date}.md`
      }
    ]
  });

  await postToSlack(slackMessage);
}
```

---

## Example 10: Dry Run / Testing Mode

```javascript
// Test synthesizer without consuming API quota
const { formatPrompt, generateFallbackBriefing } = require('./intelligence/gemini-synthesizer');

// Dry run mode: generate prompt but don't call Gemini
const dryRun = process.env.DRY_RUN === 'true';

const data = {
  date: '2026-03-03',
  github: await githubCollector.collect('2026-03-03', config),
  gcp: await gcpCollector.collect('2026-03-03', config),
  station: await stationCollector.collect(config),
  checkpoints: []
};

if (dryRun) {
  // Just generate the prompt
  const prompt = formatPrompt(data);
  console.log('Prompt length:', prompt.length, 'characters');
  console.log('Estimated input tokens:', Math.ceil(prompt.length / 4));
  console.log('\n--- Prompt Preview (first 500 chars) ---');
  console.log(prompt.substring(0, 500));

  // Generate fallback briefing for comparison
  const fallback = generateFallbackBriefing(data);
  console.log('\n--- Fallback Briefing ---');
  console.log(JSON.stringify(fallback, null, 2));

} else {
  // Real run
  const briefing = await synthesize('2026-03-03', data, config);
  console.log('Briefing generated:', briefing.date);
}
```

---

## Common Patterns

### Pattern 1: Defensive Data Collection

```javascript
// Always provide default empty data to prevent crashes
const safeCollectedData = {
  github: collectedData.github || { repos: {}, summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 } },
  gcp: collectedData.gcp || { deployments: [], errors: [], summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 } },
  station: collectedData.station || { claude_code_sessions: [], cursor_active: false, squeegee_state: {} },
  checkpoints: collectedData.checkpoints || []
};

const briefing = await synthesize(date, safeCollectedData, config);
```

### Pattern 2: Conditional API Key Check

```javascript
// Check for API key before attempting synthesis
const apiKey = config.intelligence?.gemini?.apiKey || process.env.GOOGLE_AI_API_KEY;

if (!apiKey) {
  console.warn('Gemini API key not configured, will use fallback');
}

const briefing = await synthesize(date, collectedData, config);

if (briefing.fallback_used && !apiKey) {
  console.log('Expected fallback due to missing API key');
} else if (briefing.fallback_used) {
  console.warn('Unexpected fallback despite API key present:', briefing.error);
}
```

### Pattern 3: Progressive Enhancement

```javascript
// Start with minimal briefing, enhance if Gemini available
let briefing = generateFallbackBriefing({ date, ...collectedData });

try {
  const geminiBriefing = await synthesize(date, collectedData, config);
  if (!geminiBriefing.fallback_used) {
    briefing = geminiBriefing; // Use enhanced version
  }
} catch (error) {
  console.warn('Gemini enhancement failed, using fallback:', error);
}

return briefing;
```

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
