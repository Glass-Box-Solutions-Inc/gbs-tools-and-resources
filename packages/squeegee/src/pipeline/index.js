#!/usr/bin/env node
/**
 * Squeegee Documentation Pipeline v2
 *
 * Modular pipeline replacing the 4,738-line monolith.
 * Each stage is a focused module that does one thing well.
 *
 * Usage:
 *   node scripts/squeegee/index.js full          # Run complete pipeline
 *   node scripts/squeegee/index.js scan          # Stage 1: Discover
 *   node scripts/squeegee/index.js analyze       # Stage 2: Git analysis
 *   node scripts/squeegee/index.js variable      # Stage 3: STATE.md curation
 *   node scripts/squeegee/index.js practices     # Stage 4: PROGRAMMING_PRACTICES.md
 *   node scripts/squeegee/index.js plans         # Stage 5: PLANS_APPROVED.md
 *   node scripts/squeegee/index.js changelog     # Stage 6: Per-project changelogs
 *   node scripts/squeegee/index.js patterns      # Stage 7: Pattern library
 *   node scripts/squeegee/index.js report        # Stage 8: Health report
 *   node scripts/squeegee/index.js projects      # Stage 9: Projects index
 *   node scripts/squeegee/index.js state         # Stage 10: Pipeline state
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { log } = require('./utils');
const { loadConfig } = require('./config');

// Stage imports
const discover = require('./stages/01-discover');
const gitAnalyze = require('./stages/02-git-analyze');
const stateCurate = require('./stages/03-state-curate');
const practices = require('./stages/04-practices');
const plans = require('./stages/05-plans');
const changelog = require('./stages/06-changelog');
const patterns = require('./stages/07-patterns');
const health = require('./stages/08-health');
const projectsIndex = require('./stages/09-projects-index');
const commitSummary = require('./stages/10-commit-summary');
const generate = require('./stages/11-generate');
const validate = require('./stages/12-validate');
const claudemd = require('./stages/13-claudemd');

// Portal stages (21-23)
const portalCollect = require('./stages/21-portal-collect');
const portalAI = require('./stages/22-portal-ai');
const portalRender = require('./stages/23-portal-render');

async function runPipeline(command, workspace, prebuiltConfig = null) {
  console.log('\n🧽 Squeegee Documentation Pipeline v2\n');

  // Allow callers (e.g. org-discovery.js) to pass a pre-built config so we skip reading from disk
  const config = prebuiltConfig || await loadConfig(workspace);

  switch (command) {
    case 'scan':
      return await discover.run(config);

    case 'analyze':
      return await gitAnalyze.run(config);

    case 'variable':
    case 'state-curate': {
      const disc = await discover.run(config);
      const git = await gitAnalyze.run(config);
      return await stateCurate.run(config, disc, git);
    }

    case 'practices': {
      const disc = await discover.run(config);
      return await practices.run(config, disc);
    }

    case 'plans': {
      const disc = await discover.run(config);
      const git = await gitAnalyze.run(config);
      return await plans.run(config, disc, git);
    }

    case 'changelog': {
      const disc = await discover.run(config);
      const git = await gitAnalyze.run(config);
      return await changelog.run(config, disc, git);
    }

    case 'patterns': {
      const disc = await discover.run(config);
      return await patterns.run(config, disc);
    }

    case 'report':
    case 'health': {
      const disc = await discover.run(config);
      return await health.run(config, disc);
    }

    case 'projects':
    case 'projects-index': {
      const disc = await discover.run(config);
      return await projectsIndex.run(config, disc);
    }

    case 'state':
    case 'commit-summary': {
      const git = await gitAnalyze.run(config);
      return await commitSummary.run(config, null, git);
    }

    case 'generate': {
      const disc = await discover.run(config);
      return await generate.run(config, disc);
    }

    case 'validate': {
      const disc = await discover.run(config);
      return await validate.run(config, disc);
    }

    case 'claudemd': {
      const disc = await discover.run(config);
      return await claudemd.run(config, disc);
    }

    // Portal stages (21-23)
    case 'portal-collect':
      return await portalCollect.run(config);

    case 'portal-ai': {
      const collectData = await portalCollect.run(config);
      return await portalAI.run(config, collectData);
    }

    case 'portal-render': {
      const collectData = await portalCollect.run(config);
      const aiContent = await portalAI.run(config, collectData);
      return await portalRender.run(config, collectData, aiContent);
    }

    case 'portal':
      return await runPortal(config);

    case 'full':
      return await runFull(config);

    default:
      showHelp();
      return null;
  }
}

async function runFull(config) {
  const totalStages = 10;
  const startTime = Date.now();

  const stageNames = [
    'Discover projects',
    'Git analysis',
    'STATE.md curation',
    'PROGRAMMING_PRACTICES.md',
    'PLANS_APPROVED.md',
    'Changelogs',
    'Pattern library',
    'Health report',
    'Projects index',
    'Pipeline state',
  ];

  // Track results: 'pass', 'fail', or error message
  const results = new Array(totalStages).fill(null);
  let disc = null;
  let git = null;

  // Stage 1: Discover
  log(`Stage 1/${totalStages}: Discovering projects...`, 'info');
  try {
    disc = await discover.run(config);
    results[0] = 'pass';
  } catch (err) {
    log(`Stage 1 failed: ${err.message}`, 'error');
    results[0] = err.message;
  }

  // Stage 2: Git analysis
  log(`Stage 2/${totalStages}: Analyzing git history...`, 'info');
  try {
    git = await gitAnalyze.run(config);
    results[1] = 'pass';
  } catch (err) {
    log(`Stage 2 failed: ${err.message}`, 'error');
    results[1] = err.message;
  }

  // Stage 3: STATE.md curation
  log(`Stage 3/${totalStages}: Curating STATE.md files...`, 'info');
  try {
    await stateCurate.run(config, disc, git);
    results[2] = 'pass';
  } catch (err) {
    log(`Stage 3 failed: ${err.message}`, 'error');
    results[2] = err.message;
  }

  // Stage 4: PROGRAMMING_PRACTICES.md
  log(`Stage 4/${totalStages}: Curating PROGRAMMING_PRACTICES.md...`, 'info');
  try {
    await practices.run(config, disc);
    results[3] = 'pass';
  } catch (err) {
    log(`Stage 4 failed: ${err.message}`, 'error');
    results[3] = err.message;
  }

  // Stage 5: PLANS_APPROVED.md
  log(`Stage 5/${totalStages}: Curating PLANS_APPROVED.md...`, 'info');
  try {
    await plans.run(config, disc, git);
    results[4] = 'pass';
  } catch (err) {
    log(`Stage 5 failed: ${err.message}`, 'error');
    results[4] = err.message;
  }

  // Stage 6: Changelogs
  log(`Stage 6/${totalStages}: Generating changelogs...`, 'info');
  try {
    await changelog.run(config, disc, git);
    results[5] = 'pass';
  } catch (err) {
    log(`Stage 6 failed: ${err.message}`, 'error');
    results[5] = err.message;
  }

  // Stage 7: Pattern library
  log(`Stage 7/${totalStages}: Generating pattern library...`, 'info');
  try {
    await patterns.run(config, disc);
    results[6] = 'pass';
  } catch (err) {
    log(`Stage 7 failed: ${err.message}`, 'error');
    results[6] = err.message;
  }

  // Stage 8: Health report
  log(`Stage 8/${totalStages}: Calculating health scores...`, 'info');
  try {
    await health.run(config, disc);
    results[7] = 'pass';
  } catch (err) {
    log(`Stage 8 failed: ${err.message}`, 'error');
    results[7] = err.message;
  }

  // Stage 9: Projects index
  log(`Stage 9/${totalStages}: Updating projects index...`, 'info');
  try {
    await projectsIndex.run(config, disc);
    results[8] = 'pass';
  } catch (err) {
    log(`Stage 9 failed: ${err.message}`, 'error');
    results[8] = err.message;
  }

  // Stage 10: Pipeline state
  log(`Stage 10/${totalStages}: Saving pipeline state...`, 'info');
  try {
    await commitSummary.run(config, disc, git);
    results[9] = 'pass';
  } catch (err) {
    log(`Stage 10 failed: ${err.message}`, 'error');
    results[9] = err.message;
  }

  // --- Run Summary ---
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const passed = results.filter(r => r === 'pass').length;
  const failed = results.filter(r => r !== 'pass').length;

  console.log('\n' + '='.repeat(60));
  console.log('  SQUEEGEE PIPELINE SUMMARY');
  console.log('='.repeat(60));
  console.log(`  Total: ${totalStages}  |  Passed: ${passed}  |  Failed: ${failed}  |  Time: ${elapsed}s`);
  console.log('-'.repeat(60));

  for (let i = 0; i < totalStages; i++) {
    const status = results[i] === 'pass' ? 'PASS' : 'FAIL';
    const marker = results[i] === 'pass' ? '[+]' : '[X]';
    const detail = results[i] !== 'pass' ? ` -- ${results[i]}` : '';
    console.log(`  ${marker} Stage ${String(i + 1).padStart(2)}. ${stageNames[i].padEnd(28)} ${status}${detail}`);
  }

  console.log('='.repeat(60) + '\n');

  if (failed > 0) {
    log(`Pipeline finished with ${failed} failed stage(s)`, 'error');
    process.exit(1);
  } else {
    log('Pipeline complete!', 'success');
  }
}

async function runPortal(config) {
  const startTime = Date.now();
  const stageNames = ['Portal collect', 'Portal AI content', 'Portal render'];
  const results = new Array(3).fill(null);
  let collectData = null;
  let aiContent = null;

  // Stage 21: Collect
  log('Stage 21/23: Portal data collection...', 'info');
  try {
    collectData = await portalCollect.run(config);
    results[0] = 'pass';
  } catch (err) {
    log(`Stage 21 failed: ${err.message}`, 'error');
    results[0] = err.message;
  }

  // Stage 22: AI content
  log('Stage 22/23: Portal AI content generation...', 'info');
  try {
    aiContent = await portalAI.run(config, collectData);
    results[1] = 'pass';
  } catch (err) {
    log(`Stage 22 failed: ${err.message}`, 'error');
    results[1] = err.message;
  }

  // Stage 23: Render
  log('Stage 23/23: Portal render and upload...', 'info');
  try {
    await portalRender.run(config, collectData, aiContent);
    results[2] = 'pass';
  } catch (err) {
    log(`Stage 23 failed: ${err.message}`, 'error');
    results[2] = err.message;
  }

  // Summary
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const passed = results.filter(r => r === 'pass').length;
  const failed = results.filter(r => r !== 'pass').length;

  console.log('\n' + '='.repeat(60));
  console.log('  PORTAL PIPELINE SUMMARY');
  console.log('='.repeat(60));
  console.log(`  Total: 3  |  Passed: ${passed}  |  Failed: ${failed}  |  Time: ${elapsed}s`);
  console.log('-'.repeat(60));

  for (let i = 0; i < 3; i++) {
    const status = results[i] === 'pass' ? 'PASS' : 'FAIL';
    const marker = results[i] === 'pass' ? '[+]' : '[X]';
    const detail = results[i] !== 'pass' ? ` -- ${results[i]}` : '';
    console.log(`  ${marker} Stage ${i + 21}. ${stageNames[i].padEnd(28)} ${status}${detail}`);
  }

  console.log('='.repeat(60) + '\n');

  if (failed > 0) {
    log(`Portal pipeline finished with ${failed} failed stage(s)`, 'error');
  } else {
    log('Portal pipeline complete!', 'success');
  }
}

function showHelp() {
  console.log('Usage: node scripts/squeegee-manager.js <command>');
  console.log('');
  console.log('Commands:');
  console.log('  full          Run complete pipeline (all 10 stages)');
  console.log('  scan          Stage 1: Discover projects and documentation');
  console.log('  analyze       Stage 2: Analyze git history');
  console.log('  variable      Stage 3: Curate STATE.md files');
  console.log('  practices     Stage 4: Curate PROGRAMMING_PRACTICES.md');
  console.log('  plans         Stage 5: Curate PLANS_APPROVED.md');
  console.log('  changelog     Stage 6: Generate per-project changelogs');
  console.log('  patterns      Stage 7: Generate pattern library');
  console.log('  report        Stage 8: Generate health report');
  console.log('  projects      Stage 9: Update projects index');
  console.log('  state         Stage 10: Save pipeline state');
  console.log('  generate      Stage 11: Generate missing documentation');
  console.log('  validate      Stage 12: Validate documentation quality');
  console.log('  claudemd      Stage 13: Curate CLAUDE.md files');
  console.log('  portal        Run portal pipeline (stages 21-23)');
  console.log('  portal-collect  Stage 21: Collect GitHub/Linear data for portal');
  console.log('  portal-ai       Stage 22: Generate diagrams + explanations via Gemini');
  console.log('  portal-render   Stage 23: Render HTML + upload to GCS');
  console.log('');
}

// CLI entry point
if (require.main === module) {
  const command = process.argv[2] || 'help';
  const workspace = process.env.WORKSPACE || process.cwd();
  runPipeline(command, workspace).catch(err => {
    console.error(`\n✗ Pipeline error: ${err.message}`);
    process.exit(1);
  });
}

module.exports = { runPipeline };
