/**
 * Stage 18: Documentation Quality Audit
 *
 * Monthly audit of documentation quality across all GBS repos.
 * Runs on the 1st of each month or when explicitly triggered.
 *
 * NOTE: This stage will be enabled once doc-quality-auditor.js is implemented.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const docQualityAuditor = require('../../../intelligence/doc-quality-auditor');
const { log } = require('../utils');

/**
 * Run documentation quality audit stage
 * @param {Object} config - Pipeline configuration
 * @param {Object} context - Pipeline context
 * @returns {Promise<Object>} - Stage result
 */
async function run(config, context = {}) {
  const { date = new Date() } = context;

  // Check if today is 1st of month or explicitly forced
  const isFirstOfMonth = date.getDate() === 1;
  const forceRun = context.forceDocQualityAudit || false;

  if (!isFirstOfMonth && !forceRun) {
    log('Stage 18: Skipping doc quality audit (not 1st of month)', 'info');
    return {
      status: 'skipped',
      summary: 'Not scheduled for today (runs on 1st of month)',
      next_run: getFirstOfNextMonth(date)
    };
  }

  log('Stage 18: Auditing documentation quality...', 'info');

  try {
    const logWriter = require('../../../intelligence/log-writer');

    const report = await docQualityAuditor.audit(date, config);
    context.docQualityAudit = report;

    await logWriter.write(report, 'doc-quality-audit', date, config);

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
      needs_work: needsWork
    };
  } catch (error) {
    log(`Documentation quality audit failed: ${error.message}`, 'error');
    return {
      status: 'failed',
      error: error.message,
      summary: 'Documentation quality audit failed'
    };
  }
}

/**
 * Calculate 1st of next month from given date
 * @param {Date} date - Current date
 * @returns {string} - ISO date string of next month's 1st
 */
function getFirstOfNextMonth(date) {
  const next = new Date(date);
  next.setMonth(next.getMonth() + 1);
  next.setDate(1);
  return next.toISOString().split('T')[0];
}

module.exports = { run };
