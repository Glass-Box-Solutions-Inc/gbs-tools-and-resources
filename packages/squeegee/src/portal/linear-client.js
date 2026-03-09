/**
 * Portal Linear Client
 *
 * Fetches sprint/cycle data from Linear's GraphQL API for the portal.
 * Ported from glass-box-hub/squeegee/linear_client.py (239 lines).
 *
 * @file src/portal/linear-client.js
 * @module portal/linear-client
 */

'use strict';

const https = require('https');

const LINEAR_API_URL = 'https://api.linear.app/graphql';

/**
 * Execute a Linear GraphQL query
 * @param {string} apiKey - Linear API key
 * @param {string} query - GraphQL query
 * @param {Object} [variables={}] - Query variables
 * @returns {Promise<Object>} - Response data
 */
function graphqlQuery(apiKey, query, variables = {}) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ query, variables });
    const url = new URL(LINEAR_API_URL);

    const req = https.request(
      {
        hostname: url.hostname,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: apiKey,
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            if (parsed.errors) {
              reject(new Error(`Linear GraphQL error: ${JSON.stringify(parsed.errors)}`));
            } else {
              resolve(parsed.data);
            }
          } catch (err) {
            reject(new Error(`Failed to parse Linear response: ${err.message}`));
          }
        });
      }
    );

    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

/**
 * Get active cycles from Linear
 * @param {string} apiKey
 * @returns {Promise<Array>}
 */
async function getActiveCycles(apiKey) {
  const query = `
    query {
      cycles(filter: { isActive: { eq: true } }) {
        nodes {
          id
          name
          number
          startsAt
          endsAt
          team {
            id
            name
            key
          }
          progress
          scopeHistory
          completedScopeHistory
          issues {
            nodes {
              id
              title
              state {
                name
                type
              }
              priority
              assignee {
                name
              }
            }
          }
        }
      }
    }
  `;

  const data = await graphqlQuery(apiKey, query);
  return data?.cycles?.nodes || [];
}

/**
 * Get project status from Linear
 * @param {string} apiKey
 * @param {string} projectName
 * @returns {Promise<Object|null>}
 */
async function getProjectStatus(apiKey, projectName) {
  const query = `
    query($name: String!) {
      projects(filter: { name: { eq: $name } }) {
        nodes {
          id
          name
          state
          progress
          startDate
          targetDate
          issues {
            nodes {
              id
              state {
                type
              }
            }
          }
        }
      }
    }
  `;

  const data = await graphqlQuery(apiKey, query, { name: projectName });
  const nodes = data?.projects?.nodes || [];
  return nodes.length > 0 ? nodes[0] : null;
}

/**
 * Collect sprint data from all active cycles
 * @param {string} apiKey
 * @returns {Promise<Object<string, Sprint>>} - team_name -> Sprint
 */
async function collectSprintData(apiKey) {
  if (!apiKey) {
    console.warn('Portal: Linear API key not configured, skipping sprint data');
    return {};
  }

  try {
    const cycles = await getActiveCycles(apiKey);
    const sprints = {};

    for (const cycle of cycles) {
      const teamName = cycle.team?.name || 'Unknown';

      // Compute burndown from scope history
      const burndown = [];
      const scopeHistory = cycle.scopeHistory || [];
      const completedHistory = cycle.completedScopeHistory || [];
      const maxLen = Math.max(scopeHistory.length, completedHistory.length);

      for (let i = 0; i < maxLen; i++) {
        const scope = scopeHistory[i] ?? scopeHistory[scopeHistory.length - 1] ?? 0;
        const completed = completedHistory[i] ?? 0;
        burndown.push({ day: i, scope, completed, remaining: scope - completed });
      }

      sprints[teamName] = {
        id: cycle.id,
        name: cycle.name || `Sprint ${cycle.number}`,
        start_date: cycle.startsAt,
        end_date: cycle.endsAt,
        velocity: completedHistory[completedHistory.length - 1] || 0,
        progress: Math.round((cycle.progress || 0) * 100),
        burndown_data: burndown,
      };
    }

    console.log(`Portal: Collected sprint data for ${Object.keys(sprints).length} teams`);
    return sprints;
  } catch (err) {
    console.error(`Portal: Failed to collect Linear sprint data: ${err.message}`);
    return {};
  }
}

module.exports = {
  graphqlQuery,
  getActiveCycles,
  getProjectStatus,
  collectSprintData,
};
