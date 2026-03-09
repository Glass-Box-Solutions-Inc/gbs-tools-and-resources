/**
 * Slack Notifier Module
 *
 * Sends daily intelligence briefings to Slack #main channel via webhook.
 * Uses native Node.js https module (zero external dependencies).
 *
 * @file slack-notifier.js
 * @module intelligence/slack-notifier
 */

const https = require('https');
const { formatDate } = require('./utils');

/**
 * Truncate text to fit Slack block limits
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Max length (default 3000)
 * @returns {string} - Truncated text
 */
function truncateText(text, maxLength = 3000) {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength - 3) + '...';
}

/**
 * Extract key metrics from briefing
 * @param {Object} briefing - Gemini briefing object
 * @returns {Object} - Metrics summary
 */
function extractMetrics(briefing) {
  // Parse metrics from briefing content (best effort)
  const metrics = {
    commits: 0,
    prs: 0,
    deployments: 0,
    sessions: 0
  };

  // Try to extract from executive summary or observations
  const content = JSON.stringify(briefing).toLowerCase();

  // Simple regex-based extraction (can be improved)
  const commitMatch = content.match(/(\d+)\s+commit/i);
  if (commitMatch) metrics.commits = parseInt(commitMatch[1], 10);

  const prMatch = content.match(/(\d+)\s+(?:pr|pull request)/i);
  if (prMatch) metrics.prs = parseInt(prMatch[1], 10);

  const deployMatch = content.match(/(\d+)\s+deployment/i);
  if (deployMatch) metrics.deployments = parseInt(deployMatch[1], 10);

  const sessionMatch = content.match(/(\d+)\s+(?:session|active hour)/i);
  if (sessionMatch) metrics.sessions = parseInt(sessionMatch[1], 10);

  return metrics;
}

/**
 * Convert markdown briefing to Slack Block Kit
 * @param {Object} briefing - Gemini briefing object
 * @param {string} date - Date of briefing (YYYY-MM-DD)
 * @returns {Object} - Slack Block Kit payload
 */
function formatSlackMessage(briefing, date) {
  const blocks = [];

  // Header
  blocks.push({
    type: 'header',
    text: {
      type: 'plain_text',
      text: `📊 Daily Intelligence Briefing - ${date}`,
      emoji: true
    }
  });

  // Executive Summary
  if (briefing.executive_summary && briefing.executive_summary.length > 0) {
    const summaryText = briefing.executive_summary
      .map(s => `• ${s}`)
      .join('\n');

    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Executive Summary*\n${truncateText(summaryText, 2800)}`
      }
    });

    blocks.push({ type: 'divider' });
  }

  // Development Highlights (if present in briefing)
  if (briefing.development_highlights) {
    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Development Highlights*\n${truncateText(briefing.development_highlights, 2800)}`
      }
    });
  }

  // Repository Activity
  if (briefing.repository_activity) {
    const repoText = typeof briefing.repository_activity === 'string'
      ? briefing.repository_activity
      : JSON.stringify(briefing.repository_activity);

    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Repository Activity*\n${truncateText(repoText, 2800)}`
      }
    });
  }

  // Pull Request Activity (if present)
  if (briefing.pull_request_activity) {
    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Pull Request Activity*\n${truncateText(briefing.pull_request_activity, 2800)}`
      }
    });
  }

  // Deployment Events
  if (briefing.deployment_events) {
    const deployText = typeof briefing.deployment_events === 'string'
      ? briefing.deployment_events
      : JSON.stringify(briefing.deployment_events);

    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Infrastructure & Operations*\n${truncateText(deployText, 2800)}`
      }
    });
  }

  // Development Activity (Claude Code, Cursor, etc.)
  if (briefing.development_activity) {
    const devText = typeof briefing.development_activity === 'string'
      ? briefing.development_activity
      : JSON.stringify(briefing.development_activity);

    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Team Activity*\n${truncateText(devText, 2800)}`
      }
    });
  }

  // Recommendations (Observations section)
  if (briefing.observations) {
    blocks.push({ type: 'divider' });

    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Recommendations*\n${truncateText(briefing.observations, 2800)}`
      }
    });
  }

  // Metrics footer
  const metrics = extractMetrics(briefing);
  const metricsText = [
    `Commits: ${metrics.commits}`,
    `PRs: ${metrics.prs}`,
    `Deployments: ${metrics.deployments}`,
    `Active Hours: ${metrics.sessions}`
  ].join(' | ');

  blocks.push({ type: 'divider' });

  blocks.push({
    type: 'context',
    elements: [
      {
        type: 'mrkdwn',
        text: metricsText
      }
    ]
  });

  // Link to full briefing
  const year = date.substring(0, 4);
  const month = date.substring(5, 7);
  const briefingUrl = `https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/logs/analysis/${year}/${month}/${date}.md`;

  blocks.push({
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: `<${briefingUrl}|View full briefing on GitHub>`
    }
  });

  // Footer context
  const modelUsed = briefing.model_used || 'gemini-2.0-flash-exp';
  blocks.push({
    type: 'context',
    elements: [
      {
        type: 'mrkdwn',
        text: `Generated by Squeegee Intelligence System | Model: ${modelUsed}`
      }
    ]
  });

  return { blocks };
}

/**
 * Send POST request to Slack webhook
 * @param {string} webhookUrl - Slack webhook URL
 * @param {Object} payload - Slack Block Kit payload
 * @returns {Promise<Object>} - Response from Slack
 */
function sendSlackWebhook(webhookUrl, payload) {
  return new Promise((resolve, reject) => {
    const url = new URL(webhookUrl);
    const postData = JSON.stringify(payload);

    const options = {
      hostname: url.hostname,
      path: url.pathname + url.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData)
      },
      timeout: 10000 // 10 second timeout
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode === 200) {
          resolve({ statusCode: res.statusCode, body: data });
        } else {
          reject(new Error(`Slack webhook returned ${res.statusCode}: ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(new Error(`Slack webhook request failed: ${error.message}`));
    });

    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Slack webhook timeout'));
    });

    req.write(postData);
    req.end();
  });
}

/**
 * Retry Slack webhook with exponential backoff
 * @param {string} webhookUrl - Slack webhook URL
 * @param {Object} payload - Slack Block Kit payload
 * @param {number} maxRetries - Max retry attempts (default: 3)
 * @returns {Promise<Object>} - Response from Slack
 */
async function sendWithRetry(webhookUrl, payload, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await sendSlackWebhook(webhookUrl, payload);
    } catch (error) {
      const isLastAttempt = attempt === maxRetries - 1;

      // Check status code if available
      const statusMatch = error.message.match(/returned (\d+)/);
      const statusCode = statusMatch ? parseInt(statusMatch[1], 10) : null;

      // Don't retry on 4xx errors (bad request, invalid webhook)
      if (statusCode && statusCode >= 400 && statusCode < 500) {
        throw error;
      }

      // Retry on 5xx errors (server issues)
      if (isLastAttempt) {
        throw error;
      }

      // Exponential backoff: 2s, 4s, 8s
      const delay = 2000 * Math.pow(2, attempt);
      console.warn(`Slack webhook retry attempt ${attempt + 1}/${maxRetries} after ${delay}ms`, {
        error: error.message
      });
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

/**
 * Send intelligence briefing to Slack
 * @param {Object} briefing - Gemini briefing object (from gemini-synthesizer)
 * @param {Date|string} date - Date of the briefing
 * @param {Object} config - Configuration object
 * @returns {Promise<Object>} - SlackNotificationResult
 */
async function notify(briefing, date, config) {
  // Normalize date
  const dateStr = typeof date === 'string' ? date : formatDate(date);

  // Check if Slack notifications enabled
  if (!config.notifications?.slack?.enabled) {
    console.log('Slack notifications disabled');
    return {
      success: true,
      skipped: true,
      channel: config.notifications?.slack?.channel || '#main',
      timestamp: new Date().toISOString(),
      message_ts: null,
      error: null
    };
  }

  // Check webhook URL
  const webhookUrl = config.notifications.slack.webhook_url;
  if (!webhookUrl) {
    console.warn('Slack webhook URL not configured');
    return {
      success: false,
      channel: config.notifications.slack.channel || '#main',
      timestamp: new Date().toISOString(),
      message_ts: null,
      error: 'Webhook URL not configured'
    };
  }

  try {
    console.log(`Sending intelligence briefing to Slack for ${dateStr}`);

    // Format message
    const payload = formatSlackMessage(briefing, dateStr);

    // Send to Slack with retry
    const response = await sendWithRetry(webhookUrl, payload);

    console.log('Successfully sent Slack notification', {
      date: dateStr,
      statusCode: response.statusCode
    });

    return {
      success: true,
      channel: config.notifications.slack.channel || '#main',
      timestamp: new Date().toISOString(),
      message_ts: response.body || null, // Slack may return message timestamp
      error: null
    };

  } catch (error) {
    // Log error but don't throw - intelligence should succeed even if notification fails
    console.error('Failed to send Slack notification', {
      error: error.message,
      date: dateStr
    });

    return {
      success: false,
      channel: config.notifications.slack.channel || '#main',
      timestamp: new Date().toISOString(),
      message_ts: null,
      error: error.message
    };
  }
}

module.exports = { notify };
