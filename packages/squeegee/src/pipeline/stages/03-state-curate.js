/**
 * Stage 03: STATE.md Curation
 *
 * Injects real git data into .planning/STATE.md files — not just date bumps.
 * Replaces StateCurator from the monolith.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists, ensureDir } = require('../utils');
const { resolveProjectPath } = require('../config');
const { updateSections, ensureSectionMarkers, hasSection } = require('../formatters/sections');
const { timestamp, bulletList } = require('../formatters/markdown');

async function run(config, discovery, gitAnalysis) {
  log('Stage 3: Curating STATE.md files...', 'info');

  const results = { created: [], updated: [], skipped: [] };

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    if (!(await fileExists(projectPath))) continue;

    const statePath = path.join(projectPath, '.planning', 'STATE.md');

    if (await fileExists(statePath)) {
      const updated = await updateState(statePath, project, config, gitAnalysis);
      if (updated) {
        results.updated.push(project.name);
      } else {
        results.skipped.push(project.name);
      }
    } else {
      await createState(statePath, project, config, gitAnalysis);
      results.created.push(project.name);
    }
  }

  log(`STATE.md — created: ${results.created.length}, updated: ${results.updated.length}, skipped: ${results.skipped.length}`, 'success');
  return results;
}

async function updateState(statePath, project, config, gitAnalysis) {
  let content = await fs.readFile(statePath, 'utf-8');
  const date = timestamp();
  let modified = false;

  // Update timestamp
  if (!content.includes(`**Last Updated:** ${date}`)) {
    content = content.replace(
      /\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}/,
      `**Last Updated:** ${date}`
    );
    modified = true;
  }

  // Update phase progress
  const phaseStatus = await getPhaseStatus(path.dirname(statePath));
  if (phaseStatus.currentPhase) {
    const oldPhaseMatch = content.match(/\*\*Current Phase:\*\*\s*(.*)/);
    if (oldPhaseMatch && oldPhaseMatch[1] !== phaseStatus.currentPhase) {
      content = content.replace(
        /\*\*Current Phase:\*\*\s*.*/,
        `**Current Phase:** ${phaseStatus.currentPhase}`
      );
      modified = true;
    }
  }

  // Inject recent activity from git (within markers if present)
  const gitData = gitAnalysis?.projects?.[project.name];
  if (gitData && gitData.commits.length > 0) {
    const recentCommits = gitData.commits.slice(0, 10);
    const activityContent = recentCommits.map(c => {
      const shortDate = c.date.split('T')[0];
      const typeTag = c.type ? `**${c.type}:** ` : '';
      return `- \`${shortDate}\` ${typeTag}${c.description}`;
    }).join('\n');

    if (hasSection(content, 'recent-activity')) {
      // Update within markers
      const updated = await updateSectionInMemory(content, 'recent-activity', activityContent);
      if (updated !== content) {
        content = updated;
        modified = true;
      }
    } else {
      // Try to find and replace the "Recent Activity" H2 section
      const activityHeader = '## Recent Activity';
      const idx = content.indexOf(activityHeader);
      if (idx > -1) {
        // Find the next H2 or end of file
        const nextH2 = content.indexOf('\n## ', idx + activityHeader.length);
        const endIdx = nextH2 > -1 ? nextH2 : content.length;
        const before = content.slice(0, idx);
        const after = content.slice(endIdx);

        content = before +
          `${activityHeader}\n\n` +
          `<!-- SQUEEGEE:AUTO:START recent-activity -->\n` +
          activityContent + '\n' +
          `<!-- SQUEEGEE:AUTO:END recent-activity -->\n` +
          after;
        modified = true;
      }
    }
  }

  if (modified) {
    await fs.writeFile(statePath, content, 'utf-8');
  }

  return modified;
}

/**
 * Replace content between section markers in a string (in-memory, no file I/O).
 */
function updateSectionInMemory(content, tag, newContent) {
  const startMarker = `<!-- SQUEEGEE:AUTO:START ${tag} -->`;
  const endMarker = `<!-- SQUEEGEE:AUTO:END ${tag} -->`;

  const startIdx = content.indexOf(startMarker);
  const endIdx = content.indexOf(endMarker);
  if (startIdx === -1 || endIdx === -1) return content;

  return content.slice(0, startIdx + startMarker.length) + '\n' + newContent + '\n' + content.slice(endIdx);
}

async function getPhaseStatus(planningDir) {
  const phasesDir = path.join(planningDir, 'phases');
  const status = { currentPhase: null, phases: [], completedCount: 0, totalCount: 0 };

  try {
    const entries = await fs.readdir(phasesDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const phasePath = path.join(phasesDir, entry.name);
      const hasPlan = await fileExists(path.join(phasePath, 'PLAN.md'));
      const hasSummary = await fileExists(path.join(phasePath, 'SUMMARY.md'));

      status.phases.push({ name: entry.name, hasPlan, hasSummary, completed: hasSummary });
      status.totalCount++;
      if (hasSummary) status.completedCount++;
      if (!status.currentPhase && hasPlan && !hasSummary) {
        status.currentPhase = entry.name;
      }
    }
  } catch {
    // No phases directory
  }

  return status;
}

async function createState(statePath, project, config, gitAnalysis) {
  const date = timestamp();
  const gitData = gitAnalysis?.projects?.[project.name];

  let recentActivity = '- GSD structure created by Squeegee';
  if (gitData && gitData.commits.length > 0) {
    recentActivity = gitData.commits.slice(0, 5).map(c => {
      const shortDate = c.date.split('T')[0];
      return `- \`${shortDate}\` ${c.description}`;
    }).join('\n');
  }

  const content = `# ${project.name} - Project State

**Last Updated:** ${date}
**Status:** Active Development
**Current Phase:** N/A (No phases defined yet)

---

## Current Focus

*No active task — awaiting instructions*

---

## Progress

### Completed
- GSD structure initialized

### In Progress
*None*

### Blocked
*None*

---

## Blockers

*No current blockers.*

---

## Key Decisions

*Key project decisions will be tracked here.*

---

## Recent Activity

<!-- SQUEEGEE:AUTO:START recent-activity -->
${recentActivity}
<!-- SQUEEGEE:AUTO:END recent-activity -->

---

## Quick Links

- [ROADMAP.md](ROADMAP.md) - Project roadmap
- [ISSUES.md](ISSUES.md) - Deferred work and issues
- [CLAUDE.md](../CLAUDE.md) - Project technical reference

---

*Managed by Squeegee Documentation System*
`;

  await ensureDir(path.dirname(statePath));
  await fs.writeFile(statePath, content, 'utf-8');
  log(`Created STATE.md for ${project.name}`, 'success');
}

module.exports = { run };
