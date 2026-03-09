/**
 * Markdown generation helpers.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

function heading(text, level = 2) {
  return '#'.repeat(level) + ' ' + text;
}

function table(headers, rows) {
  const headerLine = '| ' + headers.join(' | ') + ' |';
  const separator = '| ' + headers.map(() => '---').join(' | ') + ' |';
  const dataLines = rows.map(row => '| ' + row.join(' | ') + ' |');
  return [headerLine, separator, ...dataLines].join('\n');
}

function bulletList(items) {
  return items.map(item => `- ${item}`).join('\n');
}

function codeBlock(content, language = '') {
  return '```' + language + '\n' + content + '\n```';
}

function bold(text) {
  return `**${text}**`;
}

function link(text, url) {
  return `[${text}](${url})`;
}

function divider() {
  return '\n---\n';
}

function timestamp() {
  return new Date().toISOString().split('T')[0];
}

module.exports = {
  heading,
  table,
  bulletList,
  codeBlock,
  bold,
  link,
  divider,
  timestamp,
};
