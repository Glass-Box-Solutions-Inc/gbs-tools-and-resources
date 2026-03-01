#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * KB Database MCP Server
 *
 * Provides read-only PostgreSQL access to the Knowledge Base database via
 * MCP tools. All queries run inside READ ONLY transactions with a 10-second
 * timeout and a 1000-row limit. Mutating SQL is rejected before execution.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import pg from 'pg';

const { Pool } = pg;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const DATABASE_URL = process.env.KB_DATABASE_URL;
if (!DATABASE_URL) {
  console.error('[kb-db-mcp] KB_DATABASE_URL environment variable is required');
  process.exit(1);
}

const pool = new Pool({
  connectionString: DATABASE_URL,
  max: 5,
  statement_timeout: 10_000, // 10 seconds
});

const MAX_ROWS = 1000;
const FULLTEXT_TRUNCATE_LENGTH = 500;

// SQL keywords that indicate a mutating statement
const MUTATING_KEYWORDS = /\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b/i;

// ---------------------------------------------------------------------------
// Safety checks
// ---------------------------------------------------------------------------

function assertReadOnly(sql: string): void {
  if (MUTATING_KEYWORDS.test(sql)) {
    throw new Error(
      'Only SELECT queries are allowed. Detected a mutating keyword (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, or COPY).',
    );
  }
}

/**
 * Truncate fullText / full_text columns to avoid overwhelming the response.
 * Operates on an array of row objects in-place.
 */
function truncateFullTextColumns(rows: Record<string, unknown>[]): void {
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      const lowerKey = key.toLowerCase();
      if (
        (lowerKey === 'fulltext' || lowerKey === 'full_text') &&
        typeof row[key] === 'string'
      ) {
        const val = row[key] as string;
        if (val.length > FULLTEXT_TRUNCATE_LENGTH) {
          row[key] = val.slice(0, FULLTEXT_TRUNCATE_LENGTH) + `... [truncated, ${val.length} chars total]`;
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Query execution helper
// ---------------------------------------------------------------------------

async function executeReadOnlyQuery(sql: string): Promise<Record<string, unknown>[]> {
  assertReadOnly(sql);

  const queryClient = await pool.connect();
  try {
    await queryClient.query('BEGIN');
    await queryClient.query('SET TRANSACTION READ ONLY');

    const result = await queryClient.query(sql);

    await queryClient.query('COMMIT');

    const rows = (result.rows || []).slice(0, MAX_ROWS) as Record<string, unknown>[];
    truncateFullTextColumns(rows);
    return rows;
  } catch (error) {
    await queryClient.query('ROLLBACK').catch(() => {
      // Ignore rollback errors
    });
    throw error;
  } finally {
    queryClient.release();
  }
}

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    name: 'db_query',
    description:
      'Execute a read-only SQL query against the Knowledge Base PostgreSQL database. Only SELECT statements are allowed. Results are limited to 1000 rows. The fullText/full_text columns are truncated to 500 characters.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        sql: {
          type: 'string',
          description: 'SQL SELECT query to execute',
        },
      },
      required: ['sql'],
    },
  },
  {
    name: 'db_schema',
    description:
      'Get the column schema for a specific table. Returns column names, data types, nullable status, defaults, and constraints.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        table: {
          type: 'string',
          description: 'Table name (e.g., "legal_cases", "case_briefs", "legal_principles", "citations_enhanced")',
        },
      },
      required: ['table'],
    },
  },
  {
    name: 'db_tables',
    description:
      'List all tables in the public schema of the Knowledge Base database. Returns table names and types.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'db_count',
    description:
      'Get a quick row count for a table, optionally filtered by a WHERE clause.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        table: {
          type: 'string',
          description: 'Table name',
        },
        where: {
          type: 'string',
          description: 'Optional WHERE clause without the WHERE keyword (e.g., "status = \'COMPLETED\'")',
        },
      },
      required: ['table'],
    },
  },
  {
    name: 'db_sample',
    description:
      'Get N sample rows from a table. Useful for understanding table structure and data patterns. Defaults to 5 rows.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        table: {
          type: 'string',
          description: 'Table name',
        },
        limit: {
          type: 'number',
          description: 'Number of sample rows to return (default: 5, max: 50)',
        },
      },
      required: ['table'],
    },
  },
  {
    name: 'db_case_lookup',
    description:
      'Find cases by name using a case-insensitive partial match (ILIKE). Returns key fields: id, case_name, status, verification_status, official_citation, composite_confidence, needs_human_review.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        name: {
          type: 'string',
          description: 'Partial case name to search for (e.g., "Brodie", "City of Fresno", "Milpitas")',
        },
      },
      required: ['name'],
    },
  },
  {
    name: 'db_status_report',
    description:
      'Generate a standard status report for the Knowledge Base. Shows counts by case status and verification_status, plus totals for cases needing human review and cases with briefs.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
];

// ---------------------------------------------------------------------------
// Tool execution
// ---------------------------------------------------------------------------

async function executeTool(
  name: string,
  args: Record<string, unknown>,
): Promise<{ content: Array<{ type: string; text: string }>; isError?: boolean }> {
  try {
    let rows: Record<string, unknown>[];

    switch (name) {
      case 'db_query':
        rows = await executeReadOnlyQuery(args.sql as string);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ rowCount: rows.length, rows }, null, 2),
            },
          ],
        };

      case 'db_schema': {
        const table = args.table as string;
        // Validate table name to prevent injection (only allow alphanumeric + underscore)
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(table)) {
          return {
            content: [{ type: 'text', text: 'Invalid table name. Only alphanumeric characters and underscores allowed.' }],
            isError: true,
          };
        }
        rows = await executeReadOnlyQuery(`
          SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = '${table}'
          ORDER BY ordinal_position
        `);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ table, columnCount: rows.length, columns: rows }, null, 2),
            },
          ],
        };
      }

      case 'db_tables':
        rows = await executeReadOnlyQuery(`
          SELECT table_name, table_type
          FROM information_schema.tables
          WHERE table_schema = 'public'
          ORDER BY table_name
        `);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ tableCount: rows.length, tables: rows }, null, 2),
            },
          ],
        };

      case 'db_count': {
        const countTable = args.table as string;
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(countTable)) {
          return {
            content: [{ type: 'text', text: 'Invalid table name.' }],
            isError: true,
          };
        }
        const whereClause = args.where ? ` WHERE ${args.where}` : '';
        // The WHERE clause comes from the user — assertReadOnly will catch any mutation attempt
        const countSql = `SELECT COUNT(*) as count FROM ${countTable}${whereClause}`;
        assertReadOnly(countSql);
        rows = await executeReadOnlyQuery(countSql);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ table: countTable, where: args.where || null, count: Number(rows[0]?.count ?? 0) }, null, 2),
            },
          ],
        };
      }

      case 'db_sample': {
        const sampleTable = args.table as string;
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(sampleTable)) {
          return {
            content: [{ type: 'text', text: 'Invalid table name.' }],
            isError: true,
          };
        }
        const sampleLimit = Math.min(Math.max((args.limit as number) || 5, 1), 50);
        rows = await executeReadOnlyQuery(
          `SELECT * FROM ${sampleTable} LIMIT ${sampleLimit}`,
        );
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ table: sampleTable, rowCount: rows.length, rows }, null, 2),
            },
          ],
        };
      }

      case 'db_case_lookup': {
        const searchName = (args.name as string).replace(/'/g, "''"); // Escape single quotes
        rows = await executeReadOnlyQuery(`
          SELECT
            id,
            case_name,
            status,
            verification_status,
            official_citation,
            composite_confidence,
            needs_human_review,
            year_decided,
            court_system,
            created_at
          FROM legal_cases
          WHERE case_name ILIKE '%${searchName}%'
          ORDER BY case_name
          LIMIT 50
        `);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ searchTerm: args.name, matchCount: rows.length, cases: rows }, null, 2),
            },
          ],
        };
      }

      case 'db_status_report': {
        const statusCounts = await executeReadOnlyQuery(`
          SELECT status, COUNT(*) as count
          FROM legal_cases
          GROUP BY status
          ORDER BY count DESC
        `);

        const verificationCounts = await executeReadOnlyQuery(`
          SELECT verification_status, COUNT(*) as count
          FROM legal_cases
          WHERE verification_status IS NOT NULL
          GROUP BY verification_status
          ORDER BY count DESC
        `);

        const reviewCount = await executeReadOnlyQuery(`
          SELECT COUNT(*) as count FROM legal_cases WHERE needs_human_review = true
        `);

        const briefCount = await executeReadOnlyQuery(`
          SELECT COUNT(*) as count FROM case_briefs
        `);

        const principleCount = await executeReadOnlyQuery(`
          SELECT COUNT(*) as count FROM legal_principles
        `);

        const totalCases = await executeReadOnlyQuery(`
          SELECT COUNT(*) as count FROM legal_cases
        `);

        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(
                {
                  totalCases: Number(totalCases[0]?.count ?? 0),
                  byStatus: statusCounts,
                  byVerificationStatus: verificationCounts,
                  needsHumanReview: Number(reviewCount[0]?.count ?? 0),
                  casesWithBriefs: Number(briefCount[0]?.count ?? 0),
                  legalPrinciples: Number(principleCount[0]?.count ?? 0),
                  generatedAt: new Date().toISOString(),
                },
                null,
                2,
              ),
            },
          ],
        };
      }

      default:
        return {
          content: [{ type: 'text', text: `Unknown tool: ${name}` }],
          isError: true,
        };
    }
  } catch (error: unknown) {
    const err = error as Error;
    return {
      content: [{ type: 'text', text: `Error in ${name}: ${err.message}` }],
      isError: true,
    };
  }
}

// ---------------------------------------------------------------------------
// Server bootstrap
// ---------------------------------------------------------------------------

const server = new Server(
  { name: 'kb-db-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  return executeTool(name, (args ?? {}) as Record<string, unknown>);
});

server.onerror = (error) => {
  console.error('[kb-db-mcp] Server error:', error);
};

process.on('SIGINT', async () => {
  await pool.end();
  await server.close();
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);

console.error('[kb-db-mcp] Connected — read-only database access ready');
