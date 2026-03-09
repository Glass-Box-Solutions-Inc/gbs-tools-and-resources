/**
 * Gemini Daily Briefing Synthesizer
 *
 * Generates daily intelligence briefings from collected GitHub, GCP, and station data
 * using Gemini 2.5 Flash. Includes retry logic and graceful fallback to template-based
 * briefings if Gemini API is unavailable.
 *
 * Model: gemini-2.5-flash (default) — faster, cost-effective for daily summaries
 *        gemini-2.5-pro — available for complex analysis tasks
 *
 * Required API key: GOOGLE_AI_API_KEY (loaded from Secret Manager)
 *
 * @file gemini-synthesizer.js
 * @module intelligence/gemini-synthesizer
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { GoogleGenerativeAI } = require('@google/generative-ai');
const { GeminiAPIError, retryWithBackoff, formatDate } = require('./utils');

/**
 * Format GitHub activity data into prompt section
 * @param {Object} githubData - GitHub activity data from github-collector
 * @returns {string} - Formatted markdown section
 */
function formatGitHubActivity(githubData) {
  const { repos, summary } = githubData;

  let section = `### GitHub Activity\n\n`;
  section += `**Summary:**\n`;
  section += `- Total Commits: ${summary.total_commits}\n`;
  section += `- Total PRs: ${summary.total_prs}\n`;
  section += `- Total Issues: ${summary.total_issues}\n`;
  section += `- Total CI Runs: ${summary.total_ci_runs}\n`;
  section += `- Active Repos: ${Object.keys(repos).length}\n\n`;

  // Top repos by activity
  const repoActivity = Object.entries(repos)
    .map(([repo, data]) => ({
      repo,
      commits: data.commits.length,
      prs: data.pull_requests.length,
      total: data.commits.length + data.pull_requests.length
    }))
    .filter(r => r.total > 0)
    .sort((a, b) => b.total - a.total)
    .slice(0, 10);

  if (repoActivity.length > 0) {
    section += `**Top Active Repos:**\n`;
    for (const { repo, commits, prs } of repoActivity) {
      section += `- **${repo}**: ${commits} commits, ${prs} PRs\n`;
    }
    section += '\n';
  }

  // Recent commits (sample from top repos)
  const topRepoWithCommits = Object.entries(repos)
    .filter(([_, data]) => data.commits.length > 0)
    .sort((a, b) => b[1].commits.length - a[1].commits.length)[0];

  if (topRepoWithCommits) {
    const [repo, data] = topRepoWithCommits;
    section += `**Sample Commits from ${repo}:**\n`;
    for (const commit of data.commits.slice(0, 5)) {
      const shortSha = commit.sha.substring(0, 7);
      section += `- [\`${shortSha}\`] ${commit.message}\n`;
    }
    section += '\n';
  }

  return section;
}

/**
 * Format GCP activity data into prompt section
 * @param {Object} gcpData - GCP activity data from gcp-collector
 * @returns {string} - Formatted markdown section
 */
function formatGCPActivity(gcpData) {
  const { deployments, errors, summary } = gcpData;

  let section = `### GCP Activity\n\n`;
  section += `**Summary:**\n`;
  section += `- Total Deployments: ${summary.total_deployments || 0}\n`;
  section += `- Total Errors: ${summary.total_errors || 0}\n`;
  section += `- Projects Monitored: ${summary.projects_monitored || 0}\n\n`;

  // Deployment breakdown
  if (deployments && deployments.length > 0) {
    const successCount = deployments.filter(d => d.status === 'success').length;
    const failureCount = deployments.filter(d => d.status === 'failed').length;

    section += `**Deployments:**\n`;
    section += `- Successful: ${successCount}\n`;
    section += `- Failed: ${failureCount}\n\n`;

    // Group by project
    const byProject = {};
    for (const deployment of deployments) {
      if (!byProject[deployment.project]) {
        byProject[deployment.project] = [];
      }
      byProject[deployment.project].push(deployment);
    }

    section += `**By Project:**\n`;
    for (const [project, projectDeployments] of Object.entries(byProject)) {
      section += `- **${project}**: ${projectDeployments.length} deployments\n`;
    }
    section += '\n';
  }

  // Error breakdown
  if (errors && errors.length > 0) {
    // Group by severity
    const bySeverity = {};
    for (const error of errors) {
      const severity = error.severity || 'ERROR';
      bySeverity[severity] = (bySeverity[severity] || 0) + 1;
    }

    section += `**Errors by Severity:**\n`;
    for (const [severity, count] of Object.entries(bySeverity)) {
      section += `- ${severity}: ${count}\n`;
    }
    section += '\n';
  }

  return section;
}

/**
 * Format station activity data into prompt section
 * @param {Object} stationData - Station activity data from station-collector
 * @returns {string} - Formatted markdown section
 */
function formatStationActivity(stationData) {
  const { claude_code_sessions = [], cursor_active = false, squeegee_state = {} } = stationData;

  let section = `### Development Station Activity\n\n`;
  section += `**Summary:**\n`;
  section += `- Claude Code Sessions: ${claude_code_sessions.length}\n`;
  section += `- Cursor Active: ${cursor_active ? 'Yes' : 'No'}\n`;

  if (squeegee_state.last_run) {
    section += `- Last Squeegee Run: ${squeegee_state.last_run}\n`;
    section += `- Repos Processed: ${squeegee_state.repos_processed || 0}\n`;
  }
  section += '\n';

  // Claude Code sessions
  if (claude_code_sessions.length > 0) {
    section += `**Claude Code Sessions:**\n`;
    for (const session of claude_code_sessions) {
      section += `- **${session.project_name}**: ${session.memory_files_count} memory files, ~${session.estimated_tokens.toLocaleString()} tokens\n`;
    }
    section += '\n';
  }

  return section;
}

/**
 * Format checkpoint events into prompt section
 * @param {Array} checkpoints - Checkpoint events
 * @returns {string} - Formatted markdown section
 */
function formatCheckpoints(checkpoints) {
  if (!checkpoints || checkpoints.length === 0) {
    return `### Context Checkpoints\n\nNo checkpoint events recorded.\n\n`;
  }

  let section = `### Context Checkpoints\n\n`;
  section += `**Total Events:** ${checkpoints.length}\n\n`;

  // Group by repo
  const byRepo = {};
  for (const checkpoint of checkpoints) {
    if (!byRepo[checkpoint.repo]) {
      byRepo[checkpoint.repo] = [];
    }
    byRepo[checkpoint.repo].push(checkpoint);
  }

  section += `**By Repository:**\n`;
  for (const [repo, repoCheckpoints] of Object.entries(byRepo)) {
    section += `\n**${repo}** (${repoCheckpoints.length} checkpoints):\n`;
    for (const checkpoint of repoCheckpoints.slice(0, 3)) {
      section += `- User: ${checkpoint.user}, Context: ${checkpoint.context_pct}%`;
      if (checkpoint.phase) section += `, Phase: ${checkpoint.phase}`;
      section += '\n';
    }
    if (repoCheckpoints.length > 3) {
      section += `  *(and ${repoCheckpoints.length - 3} more)*\n`;
    }
  }
  section += '\n';

  return section;
}

/**
 * Build complete Gemini prompt from collected data
 * @param {Object} data - Collected intelligence data
 * @param {string} data.date - Date string (YYYY-MM-DD)
 * @param {Object} data.github - GitHub activity data
 * @param {Object} data.gcp - GCP activity data
 * @param {Object} data.station - Station activity data
 * @param {Array} data.checkpoints - Checkpoint events
 * @returns {string} - Complete prompt
 */
function formatPrompt(data) {
  const { date, github, gcp, station, checkpoints } = data;

  const prompt = `You are an engineering intelligence analyst for Glass Box Solutions, Inc.
Analyze the following day's development activity and generate a concise daily briefing.

**Date:** ${date}

**Focus Areas:**
- Notable commits and features
- Pull request activity and merge patterns
- Deployment events and issues
- Development station usage patterns
- Anomalies or concerns

---

## Activity Data

${formatGitHubActivity(github)}

${formatGCPActivity(gcp)}

${formatStationActivity(station)}

${formatCheckpoints(checkpoints)}

---

## Instructions

Generate a structured intelligence briefing with the following sections:

1. **Executive Summary** — 2-3 sentences capturing the day's key activity
2. **Development Highlights** — Notable commits, features, and bug fixes
3. **Pull Request Activity** — Merge patterns, review activity, opened/closed PRs
4. **Infrastructure & Operations** — Deployment events, errors, and performance
5. **Team Activity** — Active projects, tool usage, collaboration patterns
6. **Recommendations** — Action items, follow-ups, or concerns

**Format:** Use clear markdown with headers (##), bullet points, and concise language.
**Tone:** Professional, analytical, and actionable.
**Length:** Aim for ~500-800 words total.

Generate the briefing now:`;

  return prompt;
}

/**
 * Generate a template-based fallback briefing (no Gemini)
 * @param {Object} data - Collected intelligence data
 * @returns {Object} - Briefing object
 */
function generateFallbackBriefing(data) {
  const { date, github, gcp, station, checkpoints } = data;

  // Build executive summary from raw data
  const executiveSummary = [
    `${github.summary.total_commits} commits across ${Object.keys(github.repos).length} repositories`,
    `${github.summary.total_prs} pull requests (${github.summary.total_prs - github.summary.total_issues} merged)`,
    `${gcp.summary.total_deployments || 0} deployments, ${gcp.summary.total_errors || 0} errors logged`
  ];

  // Simple repository activity table
  let repoActivity = `| Repository | Commits | PRs | Issues |\n|------------|---------|-----|--------|\n`;
  const topRepos = Object.entries(github.repos)
    .filter(([_, data]) => data.commits.length > 0 || data.pull_requests.length > 0)
    .sort((a, b) => (b[1].commits.length + b[1].pull_requests.length) - (a[1].commits.length + a[1].pull_requests.length))
    .slice(0, 10);

  for (const [repo, data] of topRepos) {
    repoActivity += `| ${repo} | ${data.commits.length} | ${data.pull_requests.length} | ${data.issues.length} |\n`;
  }

  // Deployment events
  let deploymentEvents = '';
  if (gcp.deployments && gcp.deployments.length > 0) {
    deploymentEvents = `**Total Deployments:** ${gcp.deployments.length}\n\n`;
    const byProject = {};
    for (const deployment of gcp.deployments) {
      if (!byProject[deployment.project]) byProject[deployment.project] = [];
      byProject[deployment.project].push(deployment);
    }
    for (const [project, deployments] of Object.entries(byProject)) {
      deploymentEvents += `- **${project}**: ${deployments.length} deployments\n`;
    }
  } else {
    deploymentEvents = '*No deployments on this date.*';
  }

  // Development activity
  let devActivity = `**Claude Code Sessions:** ${station.claude_code_sessions?.length || 0}\n`;
  devActivity += `**Cursor Active:** ${station.cursor_active ? 'Yes' : 'No'}\n\n`;
  if (station.claude_code_sessions && station.claude_code_sessions.length > 0) {
    for (const session of station.claude_code_sessions) {
      devActivity += `- ${session.project_name}: ${session.memory_files_count} files\n`;
    }
  }

  // Context checkpoints
  let contextCheckpoints = '';
  if (checkpoints && checkpoints.length > 0) {
    contextCheckpoints = `**Total Checkpoints:** ${checkpoints.length}\n\n`;
    const uniqueRepos = [...new Set(checkpoints.map(c => c.repo))];
    contextCheckpoints += `**Repositories:** ${uniqueRepos.join(', ')}\n`;
  } else {
    contextCheckpoints = '*No checkpoint events.*';
  }

  return {
    date,
    executive_summary: executiveSummary,
    repository_activity: repoActivity,
    deployment_events: deploymentEvents,
    development_activity: devActivity,
    context_checkpoints: contextCheckpoints,
    observations: '⚠️ *This briefing was generated using a fallback template due to Gemini API unavailability. For AI-generated analysis and recommendations, resolve the Gemini API issue.*',
    generated_at: new Date().toISOString(),
    model_used: 'fallback-template',
    token_count: { input: 0, output: 0 },
    fallback_used: true,
    error: null
  };
}

/**
 * Parse Gemini response into structured briefing
 * @param {string} responseText - Gemini response markdown
 * @returns {Object} - Parsed briefing sections
 */
function parseBriefing(responseText) {
  // Extract sections from markdown using headers
  const sections = {
    executive_summary: [],
    repository_activity: '',
    deployment_events: '',
    development_activity: '',
    context_checkpoints: '',
    observations: ''
  };

  // Simple regex-based extraction
  const lines = responseText.split('\n');
  let currentSection = null;
  let buffer = [];

  for (const line of lines) {
    // Check for section headers
    if (line.match(/^##\s*Executive Summary/i)) {
      currentSection = 'executive_summary';
      buffer = [];
    } else if (line.match(/^##\s*Development Highlights/i)) {
      if (currentSection === 'executive_summary') {
        sections.executive_summary = buffer.filter(l => l.trim().startsWith('-')).map(l => l.replace(/^-\s*/, ''));
      }
      currentSection = 'development_highlights';
      buffer = [];
    } else if (line.match(/^##\s*Pull Request/i)) {
      if (currentSection === 'development_highlights') {
        sections.repository_activity += buffer.join('\n') + '\n\n';
      }
      currentSection = 'pull_requests';
      buffer = [];
    } else if (line.match(/^##\s*Infrastructure|^##\s*Operations/i)) {
      if (currentSection === 'pull_requests') {
        sections.repository_activity += buffer.join('\n');
      }
      currentSection = 'infrastructure';
      buffer = [];
    } else if (line.match(/^##\s*Team Activity/i)) {
      if (currentSection === 'infrastructure') {
        sections.deployment_events = buffer.join('\n');
      }
      currentSection = 'team_activity';
      buffer = [];
    } else if (line.match(/^##\s*Recommendations/i)) {
      if (currentSection === 'team_activity') {
        sections.development_activity = buffer.join('\n');
      }
      currentSection = 'recommendations';
      buffer = [];
    } else {
      // Accumulate lines for current section
      buffer.push(line);
    }
  }

  // Handle last section
  if (currentSection === 'recommendations') {
    sections.observations = buffer.join('\n');
  }

  // If executive summary is empty, create a generic one
  if (sections.executive_summary.length === 0) {
    sections.executive_summary = ['Daily development activity captured and analyzed.'];
  }

  return sections;
}

/**
 * Generate daily intelligence briefing using Gemini
 * @param {Date|string} date - Date of the intelligence data
 * @param {Object} collectedData - Combined intelligence data
 * @param {Object} collectedData.github - GitHub activity
 * @param {Object} collectedData.gcp - GCP logs
 * @param {Object} collectedData.station - Station activity
 * @param {Array} collectedData.checkpoints - Checkpoint events
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - GeminiBriefing object
 */
async function synthesize(date, collectedData, config) {
  // Convert date to string if Date object
  const dateStr = date instanceof Date ? formatDate(date) : date;

  console.log(`Generating intelligence briefing for ${dateStr}`);

  // Check for API key
  const apiKey = config.intelligence?.gemini?.apiKey || process.env.GOOGLE_AI_API_KEY;
  if (!apiKey) {
    console.error('Gemini API key not configured, using fallback briefing');
    return generateFallbackBriefing({ date: dateStr, ...collectedData });
  }

  // Prepare data object
  const data = {
    date: dateStr,
    github: collectedData.github || { repos: {}, summary: { total_commits: 0, total_prs: 0, total_issues: 0, total_ci_runs: 0 } },
    gcp: collectedData.gcp || { deployments: [], errors: [], summary: { total_deployments: 0, total_errors: 0, projects_monitored: 0 } },
    station: collectedData.station || { claude_code_sessions: [], cursor_active: false, squeegee_state: {} },
    checkpoints: collectedData.checkpoints || []
  };

  // Build prompt
  const prompt = formatPrompt(data);

  // Token estimation (rough heuristic: ~4 chars per token)
  const inputTokenEstimate = Math.ceil(prompt.length / 4);

  console.log(`Calling Gemini API (model: ${config.intelligence.gemini.model}, estimated input tokens: ${inputTokenEstimate})`);

  // Call Gemini with retry logic
  try {
    const result = await retryWithBackoff(async () => {
      const genAI = new GoogleGenerativeAI(apiKey);
      const model = genAI.getGenerativeModel({
        model: config.intelligence.gemini.model || 'gemini-2.5-flash'
      });

      const generationResult = await model.generateContent({
        contents: [{ role: 'user', parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: config.intelligence.gemini.temperature || 0.3,
          maxOutputTokens: config.intelligence.gemini.max_output_tokens || 4096
        }
      });

      const response = await generationResult.response;
      const text = response.text();

      if (!text || text.length === 0) {
        throw new GeminiAPIError('Gemini returned empty response', 500);
      }

      return { text, response };
    }, 3, 2000);

    // Parse response into structured sections
    const sections = parseBriefing(result.text);

    // Estimate output tokens
    const outputTokenEstimate = Math.ceil(result.text.length / 4);

    console.log(`Gemini briefing generated successfully (output tokens: ~${outputTokenEstimate})`);

    return {
      date: dateStr,
      ...sections,
      generated_at: new Date().toISOString(),
      model_used: config.intelligence.gemini.model || 'gemini-2.5-flash',
      token_count: {
        input: inputTokenEstimate,
        output: outputTokenEstimate
      },
      fallback_used: false,
      error: null
    };

  } catch (error) {
    console.error('Gemini synthesis failed, using fallback briefing:', error.message);

    // Generate fallback briefing
    const fallbackBriefing = generateFallbackBriefing(data);
    fallbackBriefing.error = error.message;

    return fallbackBriefing;
  }
}

module.exports = {
  synthesize,
  formatPrompt,
  // Export for testing
  formatGitHubActivity,
  formatGCPActivity,
  formatStationActivity,
  formatCheckpoints,
  parseBriefing,
  generateFallbackBriefing
};
