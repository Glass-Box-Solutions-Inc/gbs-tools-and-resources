/**
 * Stage 04: PROGRAMMING_PRACTICES.md Curation
 *
 * Re-analyzes tech stack on every run and updates auto sections.
 * Manual sections are preserved via markers.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const path = require('path');
const { log, fileExists, ensureDir } = require('../utils');
const { resolveProjectPath, resolveSourcePath } = require('../config');
const { detectStack } = require('../analyzers/stack-detector');
const { updateSections, hasSection } = require('../formatters/sections');
const { timestamp } = require('../formatters/markdown');

async function run(config, _discovery) {
  log('Stage 4: Curating PROGRAMMING_PRACTICES.md files...', 'info');

  const results = { created: [], updated: [], skipped: [] };

  for (const project of config.projects) {
    const outputPath = resolveProjectPath(config, project.path);
    const sourcePath = resolveSourcePath(config, project.path);
    if (!(await fileExists(outputPath))) {
      await ensureDir(outputPath);
    }

    const practicesPath = path.join(outputPath, 'PROGRAMMING_PRACTICES.md');
    // Detect stack from SOURCE repo (has package.json, code files),
    // not the docs output directory (only has markdown)
    const stack = await detectStack(sourcePath);

    if (await fileExists(practicesPath)) {
      const updated = await updatePractices(practicesPath, project, stack);
      if (updated) {
        results.updated.push(project.name);
      } else {
        results.skipped.push(project.name);
      }
    } else {
      await createPractices(practicesPath, project, stack);
      results.created.push(project.name);
    }
  }

  log(`PROGRAMMING_PRACTICES — created: ${results.created.length}, updated: ${results.updated.length}`, 'success');
  return results;
}

async function updatePractices(practicesPath, project, stack) {
  let content = await fs.readFile(practicesPath, 'utf-8');

  // Update timestamp
  const date = timestamp();
  content = content.replace(
    /\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}/,
    `**Last Updated:** ${date}`
  );

  // If the file has auto-update markers, update those sections
  if (hasSection(content, 'tech-stack')) {
    const techContent = formatTechStack(stack);
    const depsContent = formatDependencies(stack);
    const testContent = formatTesting(stack);

    const updates = { 'tech-stack': techContent };
    if (hasSection(content, 'dependencies')) updates['dependencies'] = depsContent;
    if (hasSection(content, 'testing')) updates['testing'] = testContent;

    return await updateSections(practicesPath, updates);
  }

  // Legacy file without markers — inject markers around auto sections
  const markerContent = injectMarkers(content, stack);
  if (markerContent !== content) {
    await fs.writeFile(practicesPath, markerContent, 'utf-8');
    return true;
  }

  return false;
}

/**
 * Inject SQUEEGEE markers into a legacy practices file.
 * Wraps the Tech Stack, Key Dependencies, and Testing sections.
 */
function injectMarkers(content, stack) {
  let result = content;

  // Wrap ## Tech Stack section
  result = wrapSection(result, 'Tech Stack', 'tech-stack', formatTechStack(stack));
  result = wrapSection(result, 'Key Dependencies', 'dependencies', formatDependencies(stack));
  result = wrapSection(result, 'Testing Approach', 'testing', formatTesting(stack));

  return result;
}

function wrapSection(content, heading, tag, newContent) {
  const headerRegex = new RegExp(`^## ${heading}\\s*$`, 'm');
  const match = content.match(headerRegex);
  if (!match) return content;

  const headerIdx = match.index;
  const afterHeader = headerIdx + match[0].length;

  // Find the next ## heading or ---
  const nextSection = content.slice(afterHeader).search(/^(?:## |---)/m);
  const endIdx = nextSection > -1 ? afterHeader + nextSection : content.length;

  const before = content.slice(0, afterHeader);
  const after = content.slice(endIdx);

  return before + '\n\n' +
    `<!-- SQUEEGEE:AUTO:START ${tag} -->\n` +
    newContent + '\n' +
    `<!-- SQUEEGEE:AUTO:END ${tag} -->\n\n` +
    after;
}

function formatTechStack(stack) {
  const items = [];
  if (stack.language) items.push(stack.language);
  items.push(...stack.frameworks);
  items.push(...stack.tools);
  items.push(...stack.conventions.filter(c =>
    ['TypeScript', 'ESLint', 'Prettier', 'Black', 'Ruff', 'MyPy'].includes(c)
  ));

  return items.length > 0
    ? items.map(s => `- ${s}`).join('\n')
    : '*Not detected — add manually*';
}

function formatDependencies(stack) {
  return stack.dependencies.length > 0
    ? '```\n' + stack.dependencies.join('\n') + '\n```'
    : '*See package.json or requirements.txt*';
}

function formatTesting(stack) {
  return stack.testing.length > 0
    ? stack.testing.map(t => `- ${t}`).join('\n')
    : '*Testing framework not detected*';
}

async function createPractices(practicesPath, project, stack) {
  const date = timestamp();

  const content = `# ${project.name} - Programming Practices

**Last Updated:** ${date}
**Curated by:** Squeegee

---

## Tech Stack

<!-- SQUEEGEE:AUTO:START tech-stack -->
${formatTechStack(stack)}
<!-- SQUEEGEE:AUTO:END tech-stack -->

---

## Architecture Patterns

${stack.conventions.length > 0
    ? stack.conventions
        .filter(c => !['TypeScript', 'ESLint', 'Prettier', 'Black', 'Ruff', 'MyPy'].includes(c))
        .map(p => `- ${p}`).join('\n') || '*No patterns detected*'
    : '*No patterns detected*'}

---

## Code Conventions

- Follow existing code style
- Use meaningful variable names
- Keep functions focused and small

---

## Key Dependencies

<!-- SQUEEGEE:AUTO:START dependencies -->
${formatDependencies(stack)}
<!-- SQUEEGEE:AUTO:END dependencies -->

---

## Testing Approach

<!-- SQUEEGEE:AUTO:START testing -->
${formatTesting(stack)}
<!-- SQUEEGEE:AUTO:END testing -->

---

## Project-Specific Notes

*Add project-specific programming practices here.*

---

*Managed by Squeegee Documentation System*
`;

  await ensureDir(path.dirname(practicesPath));
  await fs.writeFile(practicesPath, content, 'utf-8');
  log(`Created PROGRAMMING_PRACTICES.md for ${project.name}`, 'success');
}

module.exports = { run };
