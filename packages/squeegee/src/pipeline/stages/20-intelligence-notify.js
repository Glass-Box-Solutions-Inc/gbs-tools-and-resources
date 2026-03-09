/**
 * Stage 20: Intelligence Notification
 *
 * Sends daily briefing to Slack channel.
 * Only runs if Slack notifications are enabled in config.
 *
 * NOTE: This stage will be enabled once slack-notifier.js is implemented.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { log } = require('../utils');
const slackNotifier = require('../../../intelligence/slack-notifier');

/**
 * Run intelligence notification stage
 * @param {Object} config - Pipeline configuration
 * @param {Object} context - Pipeline context (contains briefing)
 * @returns {Promise<Object>} - Stage result
 */
async function run(config, context = {}) {
  const { date = new Date(), briefing } = context;

  // Check if Slack notifications are enabled
  const slackEnabled = config.notifications?.slack?.enabled || false;

  if (!slackEnabled) {
    log('Stage 20: Slack notifications disabled in config', 'info');
    return {
      status: 'skipped',
      summary: 'Slack notifications disabled in config',
      note: 'Enable in intelligence.config.json: notifications.slack.enabled = true'
    };
  }

  if (!briefing) {
    log('Stage 20: No briefing available - run synthesis stage first', 'error');
    return {
      status: 'failed',
      error: 'Missing briefing data',
      summary: 'Cannot send notification without briefing'
    };
  }

  log('Stage 20: Sending Slack notification...', 'info');

  try {
    const result = await slackNotifier.notify(briefing, date, config);

    if (result.skipped) {
      log('Stage 20: Slack notification skipped (disabled or no webhook)', 'info');
      return {
        status: 'skipped',
        summary: result.error || 'Slack notification skipped',
        channel: result.channel
      };
    }

    if (result.success) {
      log(`Sent briefing to ${result.channel}`, 'success');
      return {
        status: 'success',
        summary: `Sent briefing to ${result.channel}`,
        channel: result.channel,
        message_ts: result.message_ts
      };
    } else {
      log(`Failed to send notification: ${result.error}`, 'error');
      return {
        status: 'failed',
        error: result.error,
        summary: `Failed to send notification: ${result.error}`
      };
    }
  } catch (error) {
    log(`Notification failed: ${error.message}`, 'error');
    return {
      status: 'failed',
      error: error.message,
      summary: 'Slack notification failed'
    };
  }
}

module.exports = { run };
