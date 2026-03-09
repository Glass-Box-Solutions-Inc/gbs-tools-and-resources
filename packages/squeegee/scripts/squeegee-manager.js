#!/usr/bin/env node
/**
 * Squeegee Documentation Manager — Backward-Compatible Shim
 *
 * Delegates to the modular pipeline (scripts/squeegee/index.js) for all commands.
 * Legacy commands that haven't been migrated yet fall back to the old monolith.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { runPipeline } = require('../src/pipeline/index');

// Commands handled by the new modular pipeline
const NEW_PIPELINE_COMMANDS = new Set([
  'scan',
  'analyze',
  'variable',
  'practices',
  'plans',
  'changelog',
  'patterns',
  'report',
  'health',
  'projects',
  'projects-index',
  'state',
  'commit-summary',
  'generate',
  'validate',
  'claudemd',
  'full',
  'help',
]);

// Commands that still use the legacy monolith
// Deprecated commands removed: clean-legacy, migrate-gsd (one-time migrations, already done)
const LEGACY_COMMANDS = new Set([
  'history',
  'learnings',
  'triggers',
  'root',
  'install-hook',
  'gsd-analyze',
  'gsd-issues',
]);

const command = process.argv[2] || 'help';
const workspace = process.env.WORKSPACE || process.cwd();

if (NEW_PIPELINE_COMMANDS.has(command)) {
  // Route to new modular pipeline
  runPipeline(command, workspace).catch(err => {
    console.error(`\n✗ Pipeline error: ${err.message}`);
    process.exit(1);
  });
} else if (LEGACY_COMMANDS.has(command)) {
  // Fall back to legacy monolith
  console.log('⚠️  Using legacy pipeline for command:', command);
  console.log('   This command will be migrated in a future update.\n');
  require('./squeegee-manager-legacy.js');
} else {
  // Unknown command — show help from new pipeline
  runPipeline('help', workspace).catch(console.error);
}
