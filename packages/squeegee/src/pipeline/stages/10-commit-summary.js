/**
 * Stage 10: Commit Summary / Bookkeeping
 *
 * Writes .squeegee-state.json to track the last pipeline run.
 * This state is used by Stage 02 (git-analyze) to know what's new since last run.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { log, writeJson, readJsonSafe } = require('../utils');

async function run(config, discovery, gitAnalysis) {
  log('Stage 10: Writing pipeline state...', 'info');

  const statePath = path.join(config.workspace, '.squeegee-state.json');
  const previousState = await readJsonSafe(statePath, { runs: [] });

  const now = new Date().toISOString();
  const headHash = gitAnalysis?.global?.headHash || null;

  // Project summaries
  const projectSummaries = {};
  if (gitAnalysis?.projects) {
    for (const [name, data] of Object.entries(gitAnalysis.projects)) {
      projectSummaries[name] = {
        commitCount: data.commitCount,
        filesChanged: data.filesChanged,
        hasActivity: data.hasActivity,
      };
    }
  }

  const newState = {
    lastRun: now,
    lastHash: headHash,
    version: config.version || '2.0.0',
    runs: [
      {
        timestamp: now,
        hash: headHash,
        projectsScanned: config.projects.length,
        projectsWithActivity: Object.values(projectSummaries).filter(p => p.hasActivity).length,
      },
      ...(previousState.runs || []).slice(0, 9), // Keep last 10 runs
    ],
    projects: projectSummaries,
  };

  await writeJson(statePath, newState);
  log(`Pipeline state saved (hash: ${headHash?.slice(0, 8) || 'none'})`, 'success');

  return newState;
}

module.exports = { run };
