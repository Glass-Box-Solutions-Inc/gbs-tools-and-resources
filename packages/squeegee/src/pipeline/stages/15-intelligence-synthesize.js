/**
 * Stage 15: Intelligence Synthesis
 *
 * Generates daily intelligence briefing using Gemini 2.0 Flash.
 * Falls back to template-based briefing if Gemini is unavailable.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const geminiSynthesizer = require('../../../intelligence/gemini-synthesizer');
const { log } = require('../utils');

/**
 * Run intelligence synthesis stage
 * @param {Object} config - Pipeline configuration
 * @param {Object} context - Pipeline context (contains intelligence data)
 * @returns {Promise<Object>} - Stage result
 */
async function run(config, context = {}) {
  log('Stage 15: Synthesizing intelligence briefing...', 'info');

  const { date = new Date(), intelligence } = context;

  if (!intelligence) {
    log('No intelligence data available - run collection stage first', 'error');
    return {
      status: 'failed',
      error: 'Missing intelligence data',
      summary: 'Cannot synthesize without collection data'
    };
  }

  try {
    // Generate briefing using Gemini or fallback
    const briefing = await geminiSynthesizer.synthesize(date, intelligence, config);

    // Store in context for next stages
    context.briefing = briefing;

    const statusMsg = briefing.fallback_used
      ? 'Generated fallback briefing (Gemini unavailable)'
      : `Generated briefing using ${briefing.model_used}`;

    log(statusMsg, briefing.fallback_used ? 'warn' : 'success');

    return {
      status: briefing.fallback_used ? 'partial' : 'success',
      summary: statusMsg,
      fallback_used: briefing.fallback_used,
      model: briefing.model_used,
      token_count: briefing.token_count || 0
    };
  } catch (error) {
    log(`Synthesis failed: ${error.message}`, 'error');
    return {
      status: 'failed',
      error: error.message,
      summary: 'Intelligence synthesis failed'
    };
  }
}

module.exports = { run };
