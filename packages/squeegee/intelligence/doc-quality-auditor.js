/**
 * Documentation Quality Auditor Module
 *
 * Audits overall documentation quality across repos, checking for completeness,
 * organization, and best practices beyond just CLAUDE.md.
 *
 * @file doc-quality-auditor.js
 * @module intelligence/doc-quality-auditor
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const { Octokit } = require('@octokit/rest');
const { retry } = require('@octokit/plugin-retry');
const { throttling } = require('@octokit/plugin-throttling');
const { GitHubAPIError, safeExecute, formatDate } = require('./utils');

// Create Octokit with retry and throttling plugins
const MyOctokit = Octokit.plugin(retry, throttling);

// GitHub organization constant
const GH_ORG = 'Glass-Box-Solutions-Inc';

/**
 * Create configured Octokit client
 * @param {string} token - GitHub PAT
 * @returns {Octokit} - Configured Octokit instance
 */
function createOctokit(token) {
  return new MyOctokit({
    auth: token,
    userAgent: 'Squeegee-Intelligence/1.0',
    throttle: {
      onRateLimit: (retryAfter, options, octokit, retryCount) => {
        console.warn(`Rate limit hit for ${options.method} ${options.url}`);
        if (retryCount < 3) {
          return true;
        }
        return false;
      },
      onSecondaryRateLimit: (retryAfter, options, octokit) => {
        console.warn(`Secondary rate limit hit for ${options.method} ${options.url}`);
        return true;
      }
    }
  });
}

/**
 * Audit documentation quality across all repos
 * @param {Date|string} date - Date of the audit
 * @param {Object} config - Configuration object
 * @returns {Promise<Object>} - Audit report
 */
async function audit(date, config) {
  const dateStr = date instanceof Date ? formatDate(date) : date;
  console.log(`[doc-quality-auditor] Starting documentation quality audit for ${dateStr}`);

  const token = config.github_token || process.env.GITHUB_TOKEN;
  if (!token) {
    throw new GitHubAPIError('GitHub token not configured', 401);
  }

  const octokit = createOctokit(token);
  const repos = config.repos || config.intelligence?.repos || [];

  const reposFailed = [];
  const details = [];

  // Audit each repository
  for (const repo of repos) {
    try {
      console.log(`[doc-quality-auditor] Auditing documentation quality for ${repo}...`);

      const repoDetails = await auditRepo(repo, config);
      details.push(repoDetails);

    } catch (error) {
      console.warn(`[doc-quality-auditor] Failed to audit ${repo}: ${error.message}`);
      reposFailed.push({
        repo,
        error: error.message
      });
    }
  }

  // Calculate summary statistics
  const totalRepos = repos.length;
  const averageScore = details.length > 0
    ? Math.round(details.reduce((sum, d) => sum + d.score, 0) / details.length * 10) / 10
    : 0;

  const excellent = details.filter(d => d.score >= 90).length;
  const good = details.filter(d => d.score >= 70 && d.score < 90).length;
  const needsWork = details.filter(d => d.score >= 50 && d.score < 70).length;
  const critical = details.filter(d => d.score < 50).length;

  console.log(`[doc-quality-auditor] Audit complete: ${details.length}/${totalRepos} repos audited`);

  return {
    date: dateStr,
    repos_audited: details.length,
    repos_failed: reposFailed,
    summary: {
      total_repos: totalRepos,
      average_score: averageScore,
      excellent,
      good,
      needs_work: needsWork,
      critical
    },
    details
  };
}

/**
 * Audit a single repository
 * @param {string} repo - Repository name
 * @param {Object} config - Configuration object
 * @returns {Promise<Object>} - Repository audit details
 */
async function auditRepo(repo, config) {
  const token = config.github_token || process.env.GITHUB_TOKEN;
  if (!token) {
    throw new GitHubAPIError('GitHub token not configured', 401);
  }

  const octokit = createOctokit(token);
  const owner = GH_ORG;

  // Get full file tree
  const tree = await getFileTree(owner, repo, octokit);

  // Extract markdown files
  const mdFiles = tree.filter(f => f.path.endsWith('.md'));

  // Identify key documentation files
  const docsFound = identifyKeyDocs(mdFiles);

  // Calculate scores for each dimension
  const coverageScore = calculateCoverageScore(docsFound, repo);
  const organizationScore = calculateOrganizationScore(mdFiles);
  const freshnessScore = await calculateFreshnessScore(docsFound, owner, repo, octokit);
  const qualityScore = await calculateQualityScore(docsFound, owner, repo, octokit);

  // Calculate weighted overall score
  const overallScore = Math.round(
    coverageScore * 0.40 +
    organizationScore * 0.25 +
    freshnessScore * 0.20 +
    qualityScore * 0.15
  );

  // Collect issues and recommendations
  const issues = [];
  const recommendations = [];

  if (!docsFound.readme) {
    issues.push('Missing README.md');
    recommendations.push('Add README.md with project overview');
  }

  if (!docsFound.claude_md) {
    issues.push('Missing CLAUDE.md');
    recommendations.push('Add CLAUDE.md following GBS 13-point compliance standard');
  }

  if (!docsFound.testing) {
    issues.push('Missing TESTING.md');
    recommendations.push('Add TESTING.md with test coverage and instructions');
  }

  if (!docsFound.deployment) {
    issues.push('Missing DEPLOYMENT.md');
    recommendations.push('Add DEPLOYMENT.md with deployment instructions');
  }

  if (!docsFound.architecture && isBackendRepo(repo)) {
    issues.push('Missing ARCHITECTURE.md for backend repo');
    recommendations.push('Add ARCHITECTURE.md documenting system design');
  }

  // Get last updated dates
  const lastUpdated = await getLastUpdatedDates(docsFound, owner, repo, octokit);

  return {
    repo,
    score: overallScore,
    breakdown: {
      coverage: coverageScore,
      organization: organizationScore,
      freshness: freshnessScore,
      quality: qualityScore
    },
    docs_found: docsFound,
    issues,
    recommendations,
    last_updated: lastUpdated
  };
}

/**
 * Get file tree for a repository
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<Array>}
 */
async function getFileTree(owner, repo, octokit) {
  try {
    // Get default branch
    const { data: repoData } = await octokit.repos.get({
      owner,
      repo
    });

    const defaultBranch = repoData.default_branch || 'main';

    // Get tree
    const { data } = await octokit.git.getTree({
      owner,
      repo,
      tree_sha: defaultBranch,
      recursive: 'true'
    });

    return data.tree || [];
  } catch (error) {
    if (error.status === 404) {
      throw new GitHubAPIError('Repository not found or not accessible', 404);
    }
    throw error;
  }
}

/**
 * Identify key documentation files
 * @param {Array} mdFiles - Array of markdown file objects
 * @returns {Object}
 */
function identifyKeyDocs(mdFiles) {
  const paths = mdFiles.map(f => f.path);

  return {
    readme: paths.some(p => /^README\.md$/i.test(p)),
    claude_md: paths.some(p => /^CLAUDE\.md$/i.test(p)),
    changelog: paths.some(p => /^CHANGELOG\.md$/i.test(p)),
    architecture: paths.some(p =>
      /^ARCHITECTURE\.md$/i.test(p) ||
      /^docs\/architecture\//i.test(p)
    ),
    testing: paths.some(p =>
      /^TESTING\.md$/i.test(p) ||
      /^docs\/testing\//i.test(p)
    ),
    deployment: paths.some(p =>
      /^DEPLOYMENT\.md$/i.test(p) ||
      /^docs\/deployment\//i.test(p)
    ),
    contributing: paths.some(p => /^CONTRIBUTING\.md$/i.test(p)),
    security: paths.some(p => /^SECURITY\.md$/i.test(p)),
    license: paths.some(p => /^LICENSE(\.md)?$/i.test(p)),
    code_of_conduct: paths.some(p => /^CODE_OF_CONDUCT\.md$/i.test(p))
  };
}

/**
 * Calculate coverage score (40% of total)
 * @param {Object} docsFound - Documentation files found
 * @param {string} repo - Repository name
 * @returns {number} - Score 0-100
 */
function calculateCoverageScore(docsFound, repo) {
  const isBackend = isBackendRepo(repo);

  // Define expected docs based on repo type
  const expectedDocs = {
    readme: true,         // Required for all
    claude_md: true,      // Required for all
    changelog: true,      // Required for all
    architecture: isBackend,  // Required for backend
    testing: true,        // Required for all
    deployment: isBackend     // Required for backend
  };

  let present = 0;
  let total = 0;

  for (const [doc, required] of Object.entries(expectedDocs)) {
    if (required) {
      total++;
      if (docsFound[doc]) {
        present++;
      }
    }
  }

  // Bonus points for optional docs
  if (docsFound.contributing) present += 0.5;
  if (docsFound.security) present += 0.5;
  if (docsFound.license) present += 0.5;
  if (docsFound.code_of_conduct) present += 0.5;

  return Math.min(100, Math.round((present / total) * 100));
}

/**
 * Calculate organization score (25% of total)
 * @param {Array} mdFiles - Markdown files in repo
 * @returns {number} - Score 0-100
 */
function calculateOrganizationScore(mdFiles) {
  const checks = [];

  // Check 1: Docs in standard locations (root or /docs)
  const standardLocations = mdFiles.filter(f =>
    /^[^/]+\.md$/.test(f.path) ||
    /^docs\//.test(f.path) ||
    /^documentation\//.test(f.path)
  );

  const orgScore = Math.round((standardLocations.length / Math.max(mdFiles.length, 1)) * 100);
  checks.push(orgScore);

  // Check 2: Consistent naming (kebab-case preferred)
  const kebabCaseFiles = mdFiles.filter(f => {
    const filename = f.path.split('/').pop();
    // README, CLAUDE, CHANGELOG are exceptions
    if (/^(README|CLAUDE|CHANGELOG|LICENSE|CONTRIBUTING|SECURITY)\.md$/i.test(filename)) {
      return true;
    }
    return /^[a-z0-9-]+\.md$/.test(filename);
  });

  const namingScore = Math.round((kebabCaseFiles.length / Math.max(mdFiles.length, 1)) * 100);
  checks.push(namingScore);

  // Check 3: Index file if many docs
  if (mdFiles.length > 5) {
    const hasIndex = mdFiles.some(f =>
      /^(INDEX|DOCUMENTATION)\.md$/i.test(f.path) ||
      /^docs\/(index|README)\.md$/i.test(f.path)
    );
    checks.push(hasIndex ? 100 : 0);
  } else {
    checks.push(100); // N/A for small doc sets
  }

  // Average of all checks
  return Math.round(checks.reduce((sum, s) => sum + s, 0) / checks.length);
}

/**
 * Calculate freshness score (20% of total)
 * @param {Object} docsFound - Documentation files found
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<number>} - Score 0-100
 */
async function calculateFreshnessScore(docsFound, owner, repo, octokit) {
  const scores = [];

  // Check README freshness (most important)
  if (docsFound.readme) {
    const readmeAge = await getFileAgeDays('README.md', owner, repo, octokit);
    if (readmeAge !== null) {
      // 100 if updated within 30 days, decreasing linearly to 0 at 365 days
      const score = Math.max(0, Math.min(100, 100 - (readmeAge - 30) * (100 / 335)));
      scores.push(score);
    }
  }

  // Check CHANGELOG freshness
  if (docsFound.changelog) {
    const changelogAge = await getFileAgeDays('CHANGELOG.md', owner, repo, octokit);
    if (changelogAge !== null) {
      const score = Math.max(0, Math.min(100, 100 - (changelogAge - 30) * (100 / 335)));
      scores.push(score);
    }
  }

  // Check CLAUDE.md freshness
  if (docsFound.claude_md) {
    const claudeAge = await getFileAgeDays('CLAUDE.md', owner, repo, octokit);
    if (claudeAge !== null) {
      const score = Math.max(0, Math.min(100, 100 - (claudeAge - 90) * (100 / 275)));
      scores.push(score);
    }
  }

  if (scores.length === 0) {
    return 0;
  }

  return Math.round(scores.reduce((sum, s) => sum + s, 0) / scores.length);
}

/**
 * Calculate quality score (15% of total)
 * @param {Object} docsFound - Documentation files found
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<number>} - Score 0-100
 */
async function calculateQualityScore(docsFound, owner, repo, octokit) {
  const checks = [];

  // Check README quality
  if (docsFound.readme) {
    const readmeContent = await getFileContent('README.md', owner, repo, octokit);
    if (readmeContent) {
      // Check for code examples (triple backticks)
      const hasCodeExamples = readmeContent.includes('```');
      checks.push(hasCodeExamples ? 100 : 0);

      // Check for proper headings (ATX style)
      const hasHeadings = /^#{1,6}\s+.+$/m.test(readmeContent);
      checks.push(hasHeadings ? 100 : 0);

      // Check for reasonable length (>200 chars, <50000 chars)
      const reasonableLength = readmeContent.length > 200 && readmeContent.length < 50000;
      checks.push(reasonableLength ? 100 : 0);

      // Check for links
      const hasLinks = /\[.+\]\(.+\)/.test(readmeContent);
      checks.push(hasLinks ? 100 : 0);
    }
  }

  if (checks.length === 0) {
    return 50; // Default score if can't assess
  }

  return Math.round(checks.reduce((sum, s) => sum + s, 0) / checks.length);
}

/**
 * Get file age in days
 * @param {string} path - File path
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<number|null>} - Age in days or null
 */
async function getFileAgeDays(path, owner, repo, octokit) {
  try {
    const { data: commits } = await octokit.repos.listCommits({
      owner,
      repo,
      path,
      per_page: 1
    });

    if (commits.length === 0) {
      return null;
    }

    const lastCommitDate = new Date(commits[0].commit.author.date);
    const now = new Date();
    const ageMs = now - lastCommitDate;
    const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24));

    return ageDays;
  } catch (error) {
    return null;
  }
}

/**
 * Get file content
 * @param {string} path - File path
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<string|null>}
 */
async function getFileContent(path, owner, repo, octokit) {
  try {
    const { data } = await octokit.repos.getContent({
      owner,
      repo,
      path
    });

    if (data.type !== 'file') {
      return null;
    }

    const content = Buffer.from(data.content, 'base64').toString('utf-8');
    return content;
  } catch (error) {
    return null;
  }
}

/**
 * Get last updated dates for key docs
 * @param {Object} docsFound - Documentation files found
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<Object>}
 */
async function getLastUpdatedDates(docsFound, owner, repo, octokit) {
  const dates = {};

  const files = {
    readme: 'README.md',
    claude_md: 'CLAUDE.md',
    changelog: 'CHANGELOG.md'
  };

  for (const [key, path] of Object.entries(files)) {
    if (docsFound[key]) {
      try {
        const { data: commits } = await octokit.repos.listCommits({
          owner,
          repo,
          path,
          per_page: 1
        });

        if (commits.length > 0) {
          dates[key] = commits[0].commit.author.date.split('T')[0];
        }
      } catch (error) {
        // Ignore errors
      }
    }
  }

  return dates;
}

/**
 * Determine if repo is a backend service
 * @param {string} repo - Repository name
 * @returns {boolean}
 */
function isBackendRepo(repo) {
  const backendKeywords = [
    'backend',
    'api',
    'server',
    'service',
    '-ai-',
    'knowledge-base',
    'file-review',
    'merus-expert',
    'hub',
    'command-center',
    'glassy',
    'paralegal'
  ];

  return backendKeywords.some(keyword => repo.toLowerCase().includes(keyword));
}

/**
 * Validate markdown links in content
 * @param {string} markdown - Markdown content
 * @param {string} repo - Repository name
 * @param {Octokit} octokit - Authenticated Octokit instance
 * @returns {Promise<Array<string>>} - Array of broken links
 */
async function validateLinks(markdown, repo, octokit) {
  const brokenLinks = [];
  const owner = GH_ORG;

  // Extract markdown links: [text](path)
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  const matches = [...markdown.matchAll(linkRegex)];

  for (const match of matches) {
    const url = match[2];

    // Skip external links and anchors
    if (url.startsWith('http') || url.startsWith('#')) {
      continue;
    }

    // Check if internal file exists
    try {
      await octokit.repos.getContent({
        owner,
        repo,
        path: url
      });
    } catch (error) {
      if (error.status === 404) {
        brokenLinks.push(url);
      }
    }
  }

  return brokenLinks;
}

// Export for module usage
module.exports = {
  audit,
  auditRepo,
  identifyKeyDocs,
  calculateCoverageScore,
  calculateOrganizationScore,
  calculateFreshnessScore,
  calculateQualityScore,
  isBackendRepo,
  validateLinks
};
