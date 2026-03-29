/**
 * Stage 05: PLANS_APPROVED.md Curation
 *
 * Implements actual archiving (replaces the "Would archive" stub).
 * Reconstructs from git when no file exists.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { execSync } = require('child_process');
const { log, fileExists, ensureDir } = require('../utils');
const { resolveProjectPath } = require('../config');
const { timestamp } = require('../formatters/markdown');

async function run(config, _discovery, gitAnalysis) {
  log('Stage 5: Curating PLANS_APPROVED.md files...', 'info');

  const results = { created: [], updated: [], archived: [] };

  for (const project of config.projects) {
    const projectPath = resolveProjectPath(config, project.path);
    if (!(await fileExists(projectPath))) continue;

    const plansPath = path.join(projectPath, 'PLANS_APPROVED.md');

    if (await fileExists(plansPath)) {
      const result = await curateExisting(plansPath, config);
      if (result.archived > 0) results.archived.push({ project: project.name, count: result.archived });
      if (result.updated) results.updated.push(project.name);
    } else {
      const plans = reconstructFromGit(config.workspace, projectPath);
      await createPlansFile(plansPath, project.name, plans, config);
      results.created.push(project.name);
    }
  }

  log(`PLANS_APPROVED — created: ${results.created.length}, updated: ${results.updated.length}, archived: ${results.archived.length}`, 'success');
  return results;
}

/**
 * Actually archives old plans by rewriting the file.
 * The old monolith just logged "Would archive" — this does it for real.
 */
async function curateExisting(plansPath, config) {
  const result = { archived: 0, updated: false };

  try {
    const content = await fs.readFile(plansPath, 'utf-8');
    const lines = content.split('\n');

    // Parse plan entries
    const planRegex = /^###\s*\[PLAN-(\d{4}-\d{2}-\d{2})-\d+\]/;
    const plans = [];
    let currentPlan = null;

    for (const line of lines) {
      const match = line.match(planRegex);
      if (match) {
        if (currentPlan) plans.push(currentPlan);
        currentPlan = { date: match[1], lines: [line] };
      } else if (currentPlan) {
        currentPlan.lines.push(line);
        if (line.startsWith('---')) {
          plans.push(currentPlan);
          currentPlan = null;
        }
      }
    }
    if (currentPlan) plans.push(currentPlan);

    if (plans.length === 0) return result;

    // Split into recent vs archive-worthy
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - config.plans.archiveAfterDays);

    const recent = [];
    const archived = [];

    for (const plan of plans) {
      const planDate = new Date(plan.date);
      if (planDate < cutoffDate) {
        archived.push(plan);
      } else {
        recent.push(plan);
      }
    }

    // Trim to maxRecentPlans
    while (recent.length > config.plans.maxRecentPlans) {
      archived.push(recent.pop());
    }

    if (archived.length === 0) return result;

    // Rebuild the file with recent plans in "Recent Plans" and archived in "Archive"
    const date = timestamp();
    const projectName = path.basename(path.dirname(plansPath));

    let newContent = `# ${projectName} - Plans Approved

**Last Updated:** ${date}
**Curated by:** Squeegee

---

## Recent Plans

`;

    if (recent.length > 0) {
      for (const plan of recent) {
        newContent += plan.lines.join('\n') + '\n\n';
      }
    } else {
      newContent += '*No recent plans.*\n\n';
    }

    newContent += `---

## Archive

*Plans older than ${config.plans.archiveAfterDays} days are archived here.*

`;

    // Find existing archive section from original content
    const archiveIdx = content.indexOf('## Archive');
    let existingArchive = '';
    if (archiveIdx > -1) {
      // Get content after "## Archive" header, up to the Squeegee footer
      const afterArchive = content.slice(archiveIdx + '## Archive'.length);
      const footerIdx = afterArchive.lastIndexOf('*Managed by Squeegee');
      existingArchive = footerIdx > -1
        ? afterArchive.slice(0, footerIdx).trim()
        : afterArchive.trim();
      // Remove the first line if it's a description
      if (existingArchive.startsWith('\n')) existingArchive = existingArchive.slice(1);
      if (existingArchive.startsWith('*Plans older than')) {
        const nextNewline = existingArchive.indexOf('\n');
        existingArchive = nextNewline > -1 ? existingArchive.slice(nextNewline + 1).trim() : '';
      }
    }

    // Add newly archived plans
    for (const plan of archived) {
      newContent += plan.lines.join('\n') + '\n\n';
    }

    // Add previously archived content
    if (existingArchive) {
      newContent += existingArchive + '\n\n';
    }

    newContent += `---

*Managed by Squeegee Documentation System*
`;

    await fs.writeFile(plansPath, newContent, 'utf-8');
    result.archived = archived.length;
    result.updated = true;
    log(`Archived ${archived.length} plans in ${plansPath}`, 'info');

  } catch (e) {
    log(`Error curating ${plansPath}: ${e.message}`, 'warn');
  }

  return result;
}

function reconstructFromGit(workspace, projectPath) {
  const plans = [];

  try {
    const gitLog = execSync(
      `git log --format="%H %aI %s" --since="2025-01-01" --all -- .`,
      { cwd: projectPath, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024, stdio: ['pipe', 'pipe', 'ignore'] }
    ).trim();

    if (!gitLog) return plans;

    const commits = gitLog.split('\n').filter(Boolean);
    const commitsByDate = {};

    for (const commit of commits) {
      const [hash, isoDate, ...msgParts] = commit.split(' ');
      const msg = msgParts.join(' ');
      const dateStr = isoDate ? isoDate.split('T')[0] : null;

      if (!dateStr) continue;
      if (!commitsByDate[dateStr]) commitsByDate[dateStr] = [];
      commitsByDate[dateStr].push({ hash, msg });
    }

    let planNum = 1;
    const sortedDates = Object.keys(commitsByDate).sort().reverse();

    for (const date of sortedDates) {
      const dayCommits = commitsByDate[date];
      const significant = dayCommits.filter(c =>
        c.msg.match(/^(feat|fix|refactor|chore|docs)\(/i) ||
        c.msg.includes('implement') || c.msg.includes('add') || c.msg.includes('complete')
      );

      if (significant.length > 0) {
        const main = significant[0];
        const planId = `PLAN-${date}-${String(planNum).padStart(2, '0')}`;

        let title = main.msg;
        const ccMatch = title.match(/^(\w+)(?:\(([^)]+)\))?:\s*(.+)/i);
        if (ccMatch) title = ccMatch[3];

        plans.push({
          id: planId,
          date,
          title: title.charAt(0).toUpperCase() + title.slice(1),
          status: 'Completed',
          commits: significant.map(c => c.hash),
          summary: `Reconstructed from git: ${significant.length} commit(s)`,
          decisions: significant.map(c => `- ${c.msg}`).slice(0, 5),
        });
        planNum++;
      }
    }

    return plans.slice(0, 20);
  } catch (e) {
    log(`Git reconstruction failed for ${projectPath}: ${e.message}`, 'warn');
    return [];
  }
}

async function createPlansFile(plansPath, projectName, plans, config) {
  const date = timestamp();

  let content = `# ${projectName} - Plans Approved

**Last Updated:** ${date}
**Curated by:** Squeegee

---

## Recent Plans

`;

  if (plans.length === 0) {
    content += `*No plans recorded yet. Plans will be logged here when approved in Planning Mode.*

---

*Managed by Squeegee Documentation System*
`;
  } else {
    for (const plan of plans) {
      content += `### [${plan.id}] ${plan.title}
**Approved:** ${plan.date}
**Status:** ${plan.status}

#### Summary
${plan.summary}

#### Key Decisions
${plan.decisions.join('\n')}

#### Result
${plan.commits ? `Commits: ${plan.commits.join(', ')}` : 'Completed successfully.'}

---

`;
    }

    content += `
## Archive

*Plans older than ${config.plans.archiveAfterDays} days are archived automatically.*

---

*Managed by Squeegee Documentation System*
`;
  }

  await ensureDir(path.dirname(plansPath));
  await fs.writeFile(plansPath, content, 'utf-8');
  log(`Created PLANS_APPROVED.md for ${projectName}`, 'success');
}

module.exports = { run };
