/**
 * Stage 17: CLAUDE.md Compliance Audit
 *
 * Weekly audit of CLAUDE.md files across all GBS repos.
 * Runs on Sundays or when explicitly triggered.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const claudeMdAuditor = require('../../../intelligence/claude-md-auditor');
const logWriter = require('../../../intelligence/log-writer');
const { log } = require('../utils');

/**
 * Run CLAUDE.md audit stage
 * @param {Object} config - Pipeline configuration
 * @param {Object} context - Pipeline context
 * @returns {Promise<Object>} - Stage result
 */
async function run(config, context = {}) {
  const { date = new Date() } = context;

  // Check if today is Sunday (day 0) or if explicitly forced
  const isSunday = date.getDay() === 0;
  const forceRun = context.forceClaudeMdAudit || false;

  if (!isSunday && !forceRun) {
    log('Stage 17: Skipping CLAUDE.md audit (not Sunday)', 'info');
    return {
      status: 'skipped',
      summary: 'Not scheduled for today (runs on Sundays)',
      next_run: getNextSunday(date)
    };
  }

  log('Stage 17: Auditing CLAUDE.md compliance...', 'info');

  try {
    // Run the audit
    const report = await claudeMdAuditor.audit(date, config);

    // Store in context
    context.claudeMdAudit = report;

    // Write audit report to logs
    await logWriter.write(report, 'claude-md-audit', date, config);

    const avgScore = report.summary?.average_score || 0;
    const needsWork = (report.summary?.needs_work || 0) + (report.summary?.critical || 0);

    log(
      `Audited ${report.repos_audited} repos, average score: ${avgScore.toFixed(1)}, ` +
      `${needsWork} repos need work`,
      avgScore >= 80 ? 'success' : 'warn'
    );

    return {
      status: 'success',
      summary: `Audited ${report.repos_audited} repos, average score: ${avgScore.toFixed(1)}`,
      repos_audited: report.repos_audited,
      average_score: avgScore,
      needs_work: needsWork,
      critical: report.summary?.critical || 0
    };
  } catch (error) {
    log(`CLAUDE.md audit failed: ${error.message}`, 'error');
    return {
      status: 'failed',
      error: error.message,
      summary: 'CLAUDE.md audit failed'
    };
  }
}

/**
 * Calculate next Sunday from given date
 * @param {Date} date - Current date
 * @returns {string} - ISO date string of next Sunday
 */
function getNextSunday(date) {
  const next = new Date(date);
  next.setDate(next.getDate() + (7 - next.getDay()));
  return next.toISOString().split('T')[0];
}

module.exports = { run };
