/**
 * Section-aware read/write for markdown files.
 *
 * Uses SQUEEGEE:AUTO:START/END markers to identify regions that Squeegee owns.
 * Content outside markers is never modified. Content inside markers is regenerated.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const fs = require('fs').promises;
const { fileExists } = require('../utils');

/**
 * Read a file and extract auto-update regions.
 *
 * Returns { fullContent, sections } where sections is a Map of tag → content.
 */
async function readWithSections(filePath) {
  const content = await fs.readFile(filePath, 'utf-8').catch(() => '');
  const sections = new Map();

  const regex = /<!-- SQUEEGEE:AUTO:START (\S+) -->([\s\S]*?)<!-- SQUEEGEE:AUTO:END \1 -->/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    sections.set(match[1], match[2].trim());
  }

  return { fullContent: content, sections };
}

/**
 * Update specific auto-update sections in a file, preserving everything else.
 *
 * @param {string} filePath - File to update
 * @param {Map<string, string>|Object} updates - Map or object of tag → new content
 * @returns {boolean} Whether the file was modified
 */
async function updateSections(filePath, updates) {
  const exists = await fileExists(filePath);
  if (!exists) return false;

  let content = await fs.readFile(filePath, 'utf-8');
  let modified = false;

  const entries = updates instanceof Map ? updates.entries() : Object.entries(updates);

  for (const [tag, newContent] of entries) {
    const startMarker = `<!-- SQUEEGEE:AUTO:START ${tag} -->`;
    const endMarker = `<!-- SQUEEGEE:AUTO:END ${tag} -->`;

    const startIdx = content.indexOf(startMarker);
    const endIdx = content.indexOf(endMarker);

    if (startIdx === -1 || endIdx === -1) continue;

    const before = content.slice(0, startIdx + startMarker.length);
    const after = content.slice(endIdx);

    const updated = before + '\n' + newContent + '\n' + after;

    if (updated !== content) {
      content = updated;
      modified = true;
    }
  }

  if (modified) {
    await fs.writeFile(filePath, content, 'utf-8');
  }

  return modified;
}

/**
 * Inject section markers into a file if they don't exist.
 * Inserts them at the end of the file (before the last line if it's a Squeegee footer).
 */
async function ensureSectionMarkers(filePath, tags) {
  const exists = await fileExists(filePath);
  if (!exists) return false;

  let content = await fs.readFile(filePath, 'utf-8');
  let modified = false;

  for (const tag of tags) {
    const startMarker = `<!-- SQUEEGEE:AUTO:START ${tag} -->`;
    if (!content.includes(startMarker)) {
      const endMarker = `<!-- SQUEEGEE:AUTO:END ${tag} -->`;
      const block = `\n${startMarker}\n\n${endMarker}\n`;

      // Insert before the final Squeegee footer if present, otherwise append
      const footerIdx = content.lastIndexOf('*Managed by Squeegee');
      if (footerIdx > -1) {
        // Find the start of the line containing the footer
        const lineStart = content.lastIndexOf('\n', footerIdx);
        content = content.slice(0, lineStart) + block + content.slice(lineStart);
      } else {
        content += block;
      }
      modified = true;
    }
  }

  if (modified) {
    await fs.writeFile(filePath, content, 'utf-8');
  }

  return modified;
}

/**
 * Check if a file has a specific section marker.
 */
function hasSection(content, tag) {
  return content.includes(`<!-- SQUEEGEE:AUTO:START ${tag} -->`);
}

module.exports = {
  readWithSections,
  updateSections,
  ensureSectionMarkers,
  hasSection,
};
