/**
 * CLAUDE.md Compliance Auditor
 *
 * Audits all repos for CLAUDE.md compliance against the 13-point rubric.
 * Generates audit reports and creates GitHub PRs for non-compliant repos.
 *
 * @file claude-md-auditor.js
 * @module intelligence/claude-md-auditor
 */

const { Octokit } = require('@octokit/rest');
const { retry } = require('@octokit/plugin-retry');
const { throttling } = require('@octokit/plugin-throttling');
const { GitHubAPIError, safeExecute } = require('./utils');

// Create Octokit with retry and throttling plugins
const MyOctokit = Octokit.plugin(retry, throttling);

// GitHub organization constant
const GH_ORG = 'Glass-Box-Solutions-Inc';

// 13-point compliance rubric
const COMPLIANCE_POINTS = [
  {
    id: 1,
    check: 'H1 heading with project name',
    test: (content) => /^#\s+.+/m.test(content)
  },
  {
    id: 2,
    check: 'Overview prose (≥3 lines)',
    test: (content) => {
      const firstH2 = content.indexOf('\n##');
      if (firstH2 === -1) return false;
      const prose = content.substring(0, firstH2).split('\n').filter(l => l.trim() && !l.startsWith('#')).length;
      return prose >= 3;
    }
  },
  {
    id: 3,
    check: 'Tech stack table',
    test: (content) => /\|\s*Layer\s*\|/i.test(content) || /\|\s*Technology\s*\|/i.test(content)
  },
  {
    id: 4,
    check: 'Commands section',
    test: (content) => /##\s*Commands/i.test(content)
  },
  {
    id: 5,
    check: 'Architecture section',
    test: (content) => /##\s*Architecture/i.test(content) || /##\s*Directory\s+Structure/i.test(content)
  },
  {
    id: 6,
    check: 'Environment variables table',
    test: (content) => /\|\s*Variable\s*\|/i.test(content) || /##\s*Environment/i.test(content)
  },
  {
    id: 7,
    check: 'API endpoints section',
    test: (content) => /##\s*API/i.test(content) || /##\s*Endpoints/i.test(content)
  },
  {
    id: 8,
    check: 'Deployment info',
    test: (content) => /Cloud Run|GCP|deployment|Production URL/i.test(content)
  },
  {
    id: 9,
    check: 'Documentation hub reference',
    test: (content) => /adjudica-documentation/i.test(content)
  },
  {
    id: 10,
    check: 'Glass Box attribution footer',
    test: (content) => /@Developed & Documented by Glass Box Solutions/i.test(content)
  },
  {
    id: 11,
    check: 'Centralized Documentation section',
    test: (content) => /##\s*Centralized Documentation/i.test(content)
  },
  {
    id: 12,
    check: 'Context Window & Checkpoint Protocol',
    test: (content) => /##\s*Context Window/i.test(content) || /Checkpoint/i.test(content)
  },
  {
    id: 13,
    check: 'No parent duplication',
    test: (content, repo) => {
      // Only check repos under ~/Desktop/ (inherit parent CLAUDE.md)
      // For now, we assume all GBS repos are under ~/Desktop/
      const hasDuplicateSections =
        /##\s*Related Projects/i.test(content) ||
        /##\s*GBS Engineering Standards/i.test(content);

      const hasConditionalLoad =
        /##\s*Conditional Context Load/i.test(content);

      // Pass if no duplicate sections, OR if conditional load instruction is present
      return !hasDuplicateSections || hasConditionalLoad;
    }
  }
];

/**
 * Create configured Octokit client
 * @param {string} token - GitHub PAT
 * @returns {Octokit} - Configured Octokit instance
 */
function createOctokit(token) {
  return new MyOctokit({
    auth: token,
    throttle: {
      onRateLimit: (retryAfter, options, octokit, retryCount) => {
        console.warn(`Rate limit hit for ${options.method} ${options.url}`);
        if (retryCount < 3) {
          return true;
        }
      },
      onSecondaryRateLimit: (retryAfter, options, octokit, retryCount) => {
        console.warn(`Secondary rate limit hit for ${options.method} ${options.url}`);
        return true;
      }
    },
    retry: {
      doNotRetry: [400, 401, 403, 404, 422]
    }
  });
}

/**
 * Extract markdown links from content
 * @param {string} markdown - Markdown content
 * @returns {Array<{text: string, path: string}>} - Array of links
 */
function extractMarkdownLinks(markdown) {
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  const links = [];
  let match;

  while ((match = linkRegex.exec(markdown)) !== null) {
    links.push({
      text: match[1],
      path: match[2]
    });
  }

  return links;
}

/**
 * Check if a file exists in the repository via GitHub API
 * @param {Octokit} octokit - GitHub API client
 * @param {string} repo - Repository name
 * @param {string} path - File path
 * @returns {Promise<boolean>} - True if file exists
 */
async function checkFileExists(octokit, repo, path) {
  try {
    await octokit.repos.getContent({
      owner: GH_ORG,
      repo,
      path
    });
    return true;
  } catch (error) {
    if (error.status === 404) {
      return false;
    }
    // Other errors (permissions, etc.) - assume file doesn't exist
    return false;
  }
}

/**
 * Validate internal markdown links
 * @param {string} markdown - Markdown content
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - GitHub API client
 * @returns {Promise<Array<string>>} - Array of broken link paths
 */
async function validateLinks(markdown, repo, octokit) {
  const links = extractMarkdownLinks(markdown);
  const broken = [];

  for (const link of links) {
    // Skip external links
    if (link.path.startsWith('http://') || link.path.startsWith('https://')) {
      continue;
    }

    // Skip anchors
    if (link.path.startsWith('#')) {
      continue;
    }

    // Skip mailto links
    if (link.path.startsWith('mailto:')) {
      continue;
    }

    // Clean up path (remove anchors)
    const cleanPath = link.path.split('#')[0];

    // Skip empty paths
    if (!cleanPath) {
      continue;
    }

    // Check if file exists
    const exists = await checkFileExists(octokit, repo, cleanPath);
    if (!exists) {
      broken.push(cleanPath);
    }
  }

  return broken;
}

/**
 * Get file last modified date via GitHub commits API
 * @param {Octokit} octokit - GitHub API client
 * @param {string} repo - Repository name
 * @param {string} path - File path
 * @returns {Promise<string|null>} - ISO 8601 date string or null
 */
async function getFileLastModified(octokit, repo, path) {
  try {
    const commits = await octokit.repos.listCommits({
      owner: GH_ORG,
      repo,
      path,
      per_page: 1
    });

    if (commits.data.length > 0) {
      return commits.data[0].commit.author.date;
    }

    return null;
  } catch (error) {
    console.warn(`Failed to get last modified date for ${repo}/${path}:`, error.message);
    return null;
  }
}

/**
 * Calculate freshness score based on last modified date
 * @param {string|null} lastModified - ISO 8601 date string
 * @returns {number} - Score 0-100
 */
function calculateFreshnessScore(lastModified) {
  if (!lastModified) {
    return 50; // Unknown - give neutral score
  }

  const now = new Date();
  const modified = new Date(lastModified);
  const daysSinceModified = (now - modified) / (1000 * 60 * 60 * 24);

  if (daysSinceModified < 30) {
    return 100;
  } else if (daysSinceModified < 90) {
    return 80;
  } else {
    return 50;
  }
}

/**
 * Calculate content quality score
 * @param {string} content - CLAUDE.md content
 * @returns {number} - Score 0-100
 */
function calculateContentScore(content) {
  let score = 0;

  // Line count (target: >100 lines)
  const lineCount = content.split('\n').length;
  if (lineCount > 100) {
    score += 40;
  } else if (lineCount > 50) {
    score += 20;
  } else {
    score += 10;
  }

  // Code blocks (expect at least 3)
  const codeBlocks = (content.match(/```/g) || []).length / 2;
  if (codeBlocks >= 3) {
    score += 30;
  } else if (codeBlocks >= 1) {
    score += 15;
  }

  // Tables (expect at least 2)
  const tables = (content.match(/\|/g) || []).length;
  if (tables >= 20) {
    score += 30; // Multiple tables
  } else if (tables >= 5) {
    score += 15; // At least one table
  }

  return score;
}

/**
 * Detect common issues in CLAUDE.md
 * @param {string} content - CLAUDE.md content
 * @returns {Array<string>} - Array of issue descriptions
 */
function detectIssues(content) {
  const issues = [];

  // Check for placeholder text
  if (/TODO|Coming soon|TBD/i.test(content)) {
    issues.push('Contains placeholder text (TODO, Coming soon, TBD)');
  }

  // Check for very short file
  const lineCount = content.split('\n').length;
  if (lineCount < 50) {
    issues.push(`File too short (${lineCount} lines, recommend >100)`);
  }

  // Check for missing code examples
  const codeBlocks = (content.match(/```/g) || []).length / 2;
  if (codeBlocks === 0) {
    issues.push('No code examples found');
  }

  return issues;
}

/**
 * Generate recommendations based on audit results
 * @param {Object} auditResult - Audit result for a repo
 * @returns {Array<string>} - Array of recommendations
 */
function generateRecommendations(auditResult) {
  const recommendations = [];

  // Missing sections
  if (auditResult.missing_points.includes(2)) {
    recommendations.push('Add overview prose (2-3 sentences) before first ## section');
  }
  if (auditResult.missing_points.includes(3)) {
    recommendations.push('Add tech stack table with Layer → Technology mapping');
  }
  if (auditResult.missing_points.includes(4)) {
    recommendations.push('Add Commands section with dev, build, test, deploy commands');
  }
  if (auditResult.missing_points.includes(11)) {
    recommendations.push('Add Centralized Documentation section with link to adjudica-documentation/projects/');
  }
  if (auditResult.missing_points.includes(12)) {
    recommendations.push('Add Context Window & Checkpoint Protocol section');
  }
  if (auditResult.missing_points.includes(13)) {
    recommendations.push('Move duplicate sections to GBS_CONTEXT_SUPPLEMENT.md and add conditional load instruction');
  }

  // Content quality
  if (auditResult.breakdown.content < 50) {
    recommendations.push('Add more code examples and tables to improve content quality');
  }

  // Freshness
  if (auditResult.breakdown.freshness < 80) {
    recommendations.push('Update documentation to reflect recent changes');
  }

  // Links
  if (auditResult.broken_links && auditResult.broken_links.length > 0) {
    recommendations.push(`Fix broken links: ${auditResult.broken_links.slice(0, 3).join(', ')}${auditResult.broken_links.length > 3 ? '...' : ''}`);
  }

  return recommendations;
}

/**
 * Audit a single repository for CLAUDE.md compliance
 * @param {string} repo - Repository name
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - Audit result
 */
async function auditRepo(repo, config) {
  const githubToken = process.env.GITHUB_TOKEN || config.github_token;
  const octokit = createOctokit(githubToken);

  console.log(`Auditing ${repo} CLAUDE.md...`);

  try {
    // Fetch CLAUDE.md via GitHub Contents API
    const { data } = await octokit.repos.getContent({
      owner: GH_ORG,
      repo,
      path: 'CLAUDE.md'
    });

    // Decode content
    const content = Buffer.from(data.content, 'base64').toString('utf-8');
    const lineCount = content.split('\n').length;

    // Get last modified date
    const lastModified = await getFileLastModified(octokit, repo, 'CLAUDE.md');

    // Run compliance checks
    const missingPoints = [];
    for (const point of COMPLIANCE_POINTS) {
      if (!point.test(content, repo)) {
        missingPoints.push(point.id);
      }
    }

    // Calculate scores
    const structureScore = Math.round(((13 - missingPoints.length) / 13) * 100);
    const contentScore = calculateContentScore(content);
    const freshnessScore = calculateFreshnessScore(lastModified);

    // Validate links (with error handling)
    const brokenLinks = await safeExecute(
      () => validateLinks(content, repo, octokit),
      [],
      `${repo}/link-validation`
    );
    const linkScore = brokenLinks.length === 0 ? 100 : Math.max(0, 100 - (brokenLinks.length * 20));

    // Calculate overall score (13-point scale)
    const overallScore = 13 - missingPoints.length;

    // Detect issues
    const issues = detectIssues(content);

    // Add broken links to issues
    if (brokenLinks.length > 0) {
      issues.push(`${brokenLinks.length} broken internal link(s)`);
    }

    // Generate result
    const result = {
      repo,
      has_claude_md: true,
      score: overallScore,
      breakdown: {
        structure: structureScore,
        content: contentScore,
        freshness: freshnessScore,
        links: linkScore
      },
      last_updated: lastModified,
      line_count: lineCount,
      missing_points: missingPoints,
      broken_links: brokenLinks,
      issues,
      recommendations: []
    };

    // Generate recommendations
    result.recommendations = generateRecommendations(result);

    return result;

  } catch (error) {
    if (error.status === 404) {
      // CLAUDE.md not found
      return {
        repo,
        has_claude_md: false,
        score: 0,
        breakdown: {
          structure: 0,
          content: 0,
          freshness: 0,
          links: 0
        },
        last_updated: null,
        line_count: 0,
        missing_points: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
        broken_links: [],
        issues: ['Missing CLAUDE.md'],
        recommendations: ['Create CLAUDE.md using template from engineering/templates/']
      };
    }

    throw new GitHubAPIError(
      `Failed to audit ${repo}: ${error.message}`,
      error.status || 500,
      `GET /repos/${GH_ORG}/${repo}/contents/CLAUDE.md`
    );
  }
}

/**
 * Audit all repositories for CLAUDE.md compliance
 * @param {Date} date - Date of the audit
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - ClaudeMdAuditReport
 */
async function audit(date, config) {
  const githubToken = process.env.GITHUB_TOKEN || config.github_token;

  if (!githubToken) {
    throw new Error('GitHub token not configured (GITHUB_TOKEN env var or config.github_token)');
  }

  console.log(`Starting CLAUDE.md audit for ${config.intelligence.repos.length} repos`);

  const startTime = Date.now();
  const details = [];
  const reposFailed = [];

  // Audit each repository
  for (const repo of config.intelligence.repos) {
    try {
      const result = await auditRepo(repo, config);
      details.push(result);
    } catch (error) {
      console.error(`Failed to audit ${repo}:`, error.message);
      reposFailed.push({ repo, error: error.message });
    }
  }

  // Calculate summary statistics
  const withClaudeMd = details.filter(d => d.has_claude_md).length;
  const missingClaudeMd = details.filter(d => !d.has_claude_md).length;

  const scores = details.filter(d => d.has_claude_md).map(d => d.score);
  const averageScore = scores.length > 0
    ? scores.reduce((a, b) => a + b, 0) / scores.length
    : 0;

  const excellent = details.filter(d => d.score >= 12).length;
  const good = details.filter(d => d.score >= 10 && d.score < 12).length;
  const needsWork = details.filter(d => d.score >= 7 && d.score < 10).length;
  const critical = details.filter(d => d.score < 7).length;

  const duration = Date.now() - startTime;
  console.log(`CLAUDE.md audit complete in ${duration}ms`, {
    repos_audited: details.length,
    with_claude_md: withClaudeMd,
    missing_claude_md: missingClaudeMd,
    average_score: averageScore.toFixed(1)
  });

  return {
    date,
    repos_audited: details.length + reposFailed.length,
    repos_failed: reposFailed,
    summary: {
      total_repos: details.length + reposFailed.length,
      with_claude_md: withClaudeMd,
      missing_claude_md: missingClaudeMd,
      average_score: Math.round(averageScore * 10) / 10,
      excellent,
      good,
      needs_work: needsWork,
      critical
    },
    details
  };
}

/**
 * Audit all repositories and return per-repo results with needs_pr flag
 * Convenience wrapper around audit() for API route usage
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Array>} - Array of per-repo audit results with needs_pr
 */
async function auditAll(config) {
  const date = new Date();
  const result = await audit(date, config);
  const threshold = config.intelligence?.claude_md_audit?.threshold || 10;

  return result.details.map(detail => ({
    ...detail,
    needs_pr: detail.score < threshold
  }));
}

module.exports = {
  audit,
  auditAll,
  auditRepo
};
