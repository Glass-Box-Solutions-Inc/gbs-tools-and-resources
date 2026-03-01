#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * KB API MCP Server
 *
 * Wraps the Knowledge Base backend REST API as MCP tools, enabling Claude
 * (and other MCP clients) to search cases, query legal principles, run
 * AI-powered legal Q&A, and inspect system health — all through the
 * Model Context Protocol.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import axios, { AxiosInstance, AxiosError } from 'axios';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BACKEND_URL = process.env.KB_BACKEND_URL || 'http://localhost:8080';
const REQUEST_TIMEOUT = 60_000; // 60 seconds — AI queries can be slow

const client: AxiosInstance = axios.create({
  baseURL: BACKEND_URL,
  timeout: REQUEST_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    name: 'kb_health',
    description:
      'Check the health status of the Knowledge Base backend service. Returns service name, version, and timestamp.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'kb_stats',
    description:
      'Get dashboard statistics for the Knowledge Base — total case counts broken down by status (PENDING, RESEARCHING, DOWNLOADING, PROCESSING, INCOMPLETE, COMPLETED, VERIFIED, ERROR, ABANDONED).',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'kb_search',
    description:
      'Hybrid vector + graph search across the legal knowledge base. Combines semantic similarity (vector embeddings) with citation-graph traversal to find relevant cases and legal principles.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        query: {
          type: 'string',
          description: 'Natural language search query about CA Workers\' Compensation law',
        },
        searchType: {
          type: 'string',
          description: 'Search mode: "hybrid" (default), "vector", or "graph"',
          enum: ['hybrid', 'vector', 'graph'],
        },
        limit: {
          type: 'number',
          description: 'Maximum number of results to return (default: 10)',
        },
        useVector: {
          type: 'boolean',
          description: 'Enable vector similarity search (default: true)',
        },
        useGraph: {
          type: 'boolean',
          description: 'Enable graph traversal search (default: true)',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'kb_case_graph',
    description:
      'Get the citation and principle graph for a specific case. Shows which cases it cites, which cases cite it, and which legal principles it relates to — including relationship types (follows, distinguishes, overrules, etc.).',
    inputSchema: {
      type: 'object' as const,
      properties: {
        id: {
          type: 'string',
          description: 'Case UUID',
        },
      },
      required: ['id'],
    },
  },
  {
    name: 'kb_ask',
    description:
      'AI-powered legal Q&A with intelligent model routing. Simple queries use fast models, complex queries use reasoning models, and high-stakes queries use multi-model consensus verification. Automatically searches the knowledge base for relevant context.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        query: {
          type: 'string',
          description: 'Legal question about California Workers\' Compensation law',
        },
        highStakes: {
          type: 'boolean',
          description: 'Force multi-model consensus verification for critical questions (default: false)',
        },
        includeSearchResults: {
          type: 'boolean',
          description: 'Whether to search the KB for context before answering (default: true)',
        },
        maxSearchResults: {
          type: 'number',
          description: 'Max search results to include as context (default: 5)',
        },
        context: {
          type: 'string',
          description: 'Additional context to provide to the AI model',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'kb_analyze_query',
    description:
      'Analyze query complexity without executing it. Returns complexity classification, suggested model tier, and routing rationale. Useful for understanding how the system would handle a query before running it.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        query: {
          type: 'string',
          description: 'Legal question to analyze',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'kb_principle',
    description:
      'Get detailed information about a specific legal principle, including its full statement, category, confidence score, and all related cases with their relationship types.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        id: {
          type: 'string',
          description: 'Legal principle UUID',
        },
      },
      required: ['id'],
    },
  },
  {
    name: 'kb_search_principles',
    description:
      'Search legal principles by name or keyword. Returns matching principles with names, full statements, categories, and confidence scores.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        query: {
          type: 'string',
          description: 'Search term for principle names (e.g., "apportionment", "permanent disability", "Labor Code 4660")',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'kb_case_detail',
    description:
      'Get full case details including brief (IRAC), summary, citations, enhanced citations, principle relations, status history, documents, and URLs. Returns everything known about a single case.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        id: {
          type: 'string',
          description: 'Case UUID',
        },
      },
      required: ['id'],
    },
  },
  {
    name: 'kb_update_case',
    description:
      'Update review flags on a case. Used to mark cases for human review or update verification status.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        id: {
          type: 'string',
          description: 'Case UUID',
        },
        needsHumanReview: {
          type: 'boolean',
          description: 'Flag the case for human review',
        },
        verificationStatus: {
          type: 'string',
          description: 'Verification status (e.g., "VERIFIED", "PROBABLE_MATCH", "UNVERIFIED")',
        },
      },
      required: ['id'],
    },
  },
  {
    name: 'kb_extraction_pending',
    description:
      'Get the count of cases that are ready for AI extraction (brief, citation, principle extraction). Useful for monitoring the extraction pipeline.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'kb_extraction_status',
    description:
      'Get the status of a specific extraction job including total cases, processed count, failed count, and errors.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        jobId: {
          type: 'string',
          description: 'Extraction job UUID',
        },
      },
      required: ['jobId'],
    },
  },
  {
    name: 'kb_queue_stats',
    description:
      'Get queue statistics including active, waiting, completed, and failed job counts for the background processing queue.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'kb_lock_status',
    description:
      'Get current lock status showing how many cases are locked for processing and which execution IDs hold them. Useful for diagnosing stuck processing.',
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
    let response;

    switch (name) {
      // -- Health & Stats --
      case 'kb_health':
        response = await client.get('/health');
        break;

      case 'kb_stats':
        response = await client.get('/webhook/legal-dashboard-stats-v2');
        break;

      // -- Knowledge Search & Q&A --
      case 'kb_search':
        response = await client.post('/api/knowledge/search', {
          query: args.query,
          searchType: args.searchType,
          limit: args.limit,
          useVector: args.useVector,
          useGraph: args.useGraph,
        });
        break;

      case 'kb_case_graph':
        response = await client.get(`/api/knowledge/case/${args.id}/graph`);
        break;

      case 'kb_ask':
        response = await client.post('/api/knowledge/query', {
          query: args.query,
          highStakes: args.highStakes,
          includeSearchResults: args.includeSearchResults,
          maxSearchResults: args.maxSearchResults,
          context: args.context,
        });
        break;

      case 'kb_analyze_query':
        response = await client.post('/api/knowledge/query/analyze', {
          query: args.query,
        });
        break;

      // -- Principles --
      case 'kb_principle':
        response = await client.get(`/api/knowledge/principle/${args.id}`);
        break;

      case 'kb_search_principles':
        response = await client.get('/api/knowledge/principles', {
          params: { q: args.query },
        });
        break;

      // -- Cases --
      case 'kb_case_detail':
        response = await client.get(`/api/cases/${args.id}`);
        break;

      case 'kb_update_case': {
        const updateBody: Record<string, unknown> = {};
        if (args.needsHumanReview !== undefined) updateBody.needsHumanReview = args.needsHumanReview;
        if (args.verificationStatus !== undefined) updateBody.verificationStatus = args.verificationStatus;
        response = await client.patch(`/api/cases/${args.id}`, updateBody);
        break;
      }

      // -- Extraction Pipeline --
      case 'kb_extraction_pending':
        response = await client.get('/webhook/extraction/pending-count');
        break;

      case 'kb_extraction_status':
        response = await client.get(`/webhook/extraction/job/${args.jobId}`);
        break;

      // -- Queue & Locks --
      case 'kb_queue_stats':
        response = await client.get('/api/queue/stats');
        break;

      case 'kb_lock_status':
        response = await client.get('/api/locks/status');
        break;

      default:
        return {
          content: [{ type: 'text', text: `Unknown tool: ${name}` }],
          isError: true,
        };
    }

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response.data, null, 2),
        },
      ],
    };
  } catch (error: unknown) {
    const axiosErr = error as AxiosError;
    const status = axiosErr.response?.status;
    const data = axiosErr.response?.data;
    const message = axiosErr.message || 'Unknown error';

    const errorDetail = data
      ? `HTTP ${status}: ${JSON.stringify(data, null, 2)}`
      : `${message}${status ? ` (HTTP ${status})` : ''}`;

    return {
      content: [{ type: 'text', text: `Error calling ${name}: ${errorDetail}` }],
      isError: true,
    };
  }
}

// ---------------------------------------------------------------------------
// Server bootstrap
// ---------------------------------------------------------------------------

const server = new Server(
  { name: 'kb-api-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  return executeTool(name, (args ?? {}) as Record<string, unknown>);
});

server.onerror = (error) => {
  console.error('[kb-api-mcp] Server error:', error);
};

process.on('SIGINT', async () => {
  await server.close();
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);

console.error(`[kb-api-mcp] Connected to backend at ${BACKEND_URL}`);
