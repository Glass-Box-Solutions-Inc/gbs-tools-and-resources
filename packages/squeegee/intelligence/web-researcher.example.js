/**
 * Web Researcher Usage Examples
 *
 * This file demonstrates how to use the web-researcher module for
 * quarterly best-practice research and on-demand topic exploration.
 *
 * Run examples:
 *   node intelligence/web-researcher.example.js
 */

const { research, RESEARCH_TOPICS } = require('./web-researcher');
const { loadConfig } = require('../config/loader');

/**
 * Example 1: Research a predefined quarterly topic
 */
async function exampleQuarterlyResearch() {
  console.log('===== Example 1: Quarterly Research =====\n');

  const config = loadConfig();
  const date = new Date();
  const topic = 'documentation-standards';

  console.log(`Researching: ${topic}`);
  console.log(`Query: ${RESEARCH_TOPICS[topic].query}`);
  console.log(`Focus: ${RESEARCH_TOPICS[topic].focus}\n`);

  const result = await research(topic, date, config);

  console.log(`Status: ${result.error ? 'Failed' : 'Success'}`);
  console.log(`Grounding Enabled: ${result.grounding_enabled}`);
  console.log(`Fallback Used: ${result.fallback_used}`);
  console.log(`Model: ${result.model_used}`);
  console.log(`Tokens: ${result.token_count.input} input / ${result.token_count.output} output`);
  console.log(`\nExecutive Summary (${result.executive_summary.length} points):`);
  result.executive_summary.forEach((point, i) => {
    console.log(`  ${i + 1}. ${point}`);
  });
  console.log(`\nRecommendations (${result.recommendations.length} items):`);
  result.recommendations.forEach((rec, i) => {
    console.log(`  ${i + 1}. ${rec}`);
  });
  console.log(`\nSources (${result.sources.length} found):`);
  result.sources.slice(0, 5).forEach((source, i) => {
    console.log(`  ${i + 1}. ${source.title} - ${source.url}`);
  });

  return result;
}

/**
 * Example 2: Research a custom topic
 */
async function exampleCustomResearch() {
  console.log('\n===== Example 2: Custom Topic Research =====\n');

  const config = loadConfig();
  const date = new Date();
  const customTopic = 'Claude Code best practices for enterprise development';

  console.log(`Researching custom topic: ${customTopic}\n`);

  const result = await research(customTopic, date, config);

  console.log(`Status: ${result.error ? 'Failed' : 'Success'}`);
  console.log(`Executive Summary:`);
  result.executive_summary.forEach((point, i) => {
    console.log(`  ${i + 1}. ${point}`);
  });

  return result;
}

/**
 * Example 3: Iterate through all quarterly topics
 */
async function exampleBatchResearch() {
  console.log('\n===== Example 3: Batch Quarterly Research =====\n');

  const config = loadConfig();
  const date = new Date();

  const results = [];

  for (const topic of Object.keys(RESEARCH_TOPICS)) {
    console.log(`\nResearching: ${topic}...`);

    const result = await research(topic, date, config);

    console.log(`  Status: ${result.error ? 'Failed' : 'Success'}`);
    console.log(`  Summary Points: ${result.executive_summary.length}`);
    console.log(`  Recommendations: ${result.recommendations.length}`);
    console.log(`  Sources: ${result.sources.length}`);

    results.push({
      topic,
      success: !result.error,
      summaryPoints: result.executive_summary.length,
      recommendations: result.recommendations.length,
      sources: result.sources.length
    });

    // Brief pause between requests to respect rate limits
    await new Promise(resolve => setTimeout(resolve, 2000));
  }

  console.log('\n=== Batch Research Summary ===');
  console.log(`Total topics: ${results.length}`);
  console.log(`Successful: ${results.filter(r => r.success).length}`);
  console.log(`Failed: ${results.filter(r => !r.success).length}`);

  return results;
}

/**
 * Example 4: Handle errors gracefully
 */
async function exampleErrorHandling() {
  console.log('\n===== Example 4: Error Handling =====\n');

  // Simulate missing API key
  const configWithoutKey = {
    intelligence: {
      gemini: {
        model: 'gemini-2.0-flash-exp',
        temperature: 0.4
        // No apiKey
      }
    }
  };

  const date = new Date();
  const result = await research('documentation-standards', date, configWithoutKey);

  console.log('Result with missing API key:');
  console.log(`  Error: ${result.error}`);
  console.log(`  Executive Summary: ${result.executive_summary.length} points`);
  console.log(`  Findings: ${result.findings.length} chars`);
  console.log('  (Should return error result, not throw)');

  return result;
}

/**
 * Example 5: Format research report for markdown output
 */
function exampleFormatReport(researchResult) {
  console.log('\n===== Example 5: Format Report =====\n');

  const markdown = `# Research Report: ${researchResult.topic}

**Date:** ${researchResult.date}
**Model:** ${researchResult.model_used}
**Grounding Enabled:** ${researchResult.grounding_enabled ? 'Yes' : 'No'}
**Generated:** ${researchResult.generated_at}

---

## Executive Summary

${researchResult.executive_summary.map(point => `- ${point}`).join('\n')}

---

## Detailed Findings

${researchResult.findings}

---

## Recommendations for Glass Box Solutions

${researchResult.recommendations.map(rec => `- ${rec}`).join('\n')}

---

## Sources

${researchResult.sources.map(s => `- [${s.title}](${s.url})`).join('\n')}

---

**Token Usage:** ${researchResult.token_count.input} input / ${researchResult.token_count.output} output
**Fallback Used:** ${researchResult.fallback_used ? 'Yes' : 'No'}
${researchResult.error ? `\n**Error:** ${researchResult.error}` : ''}
`;

  console.log(markdown);
  return markdown;
}

/**
 * Run all examples
 */
async function runAllExamples() {
  try {
    // Example 1: Standard quarterly research
    const quarterlyResult = await exampleQuarterlyResearch();

    // Example 2: Custom topic
    await exampleCustomResearch();

    // Example 3: Batch research (commented out to avoid rate limits)
    // await exampleBatchResearch();

    // Example 4: Error handling
    await exampleErrorHandling();

    // Example 5: Format report
    exampleFormatReport(quarterlyResult);

    console.log('\n✅ All examples completed successfully');

  } catch (error) {
    console.error('\n❌ Example failed:', error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  runAllExamples()
    .then(() => process.exit(0))
    .catch((error) => {
      console.error('Fatal error:', error);
      process.exit(1);
    });
}

module.exports = {
  exampleQuarterlyResearch,
  exampleCustomResearch,
  exampleBatchResearch,
  exampleErrorHandling,
  exampleFormatReport
};
