#!/usr/bin/env node
// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

/**
 * WC Paralegal MCP Server
 *
 * Wraps the WC Paralegal Backend REST API as MCP tools, enabling Claude
 * (and other MCP clients) to check service health, manage cases,
 * process documents via Document AI + Gemini extraction, and interact
 * with the Gemini chat — all through the Model Context Protocol.
 *
 * The backend is a NestJS service running at WC_PARALEGAL_URL
 * (default: http://localhost:3002).
 *
 * NOTE: Most endpoints require authentication (BetterAuth session).
 * Tools that require auth will return 401 if no valid session is available.
 * The health check endpoints are public.
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

const BACKEND_URL = process.env.WC_PARALEGAL_URL || 'http://localhost:3002';
const REQUEST_TIMEOUT = 120_000; // 120 seconds — Document AI extraction can be slow

const client: AxiosInstance = axios.create({
  baseURL: BACKEND_URL,
  timeout: REQUEST_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

const TOOLS = [
  // -- Health Checks (Public) --
  {
    name: 'wc_health',
    description:
      'Check the health status of the WC Paralegal Backend. Returns database connectivity and overall health. This endpoint is public (no auth required).',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'wc_readiness',
    description:
      'Check if the WC Paralegal Backend is ready to accept traffic. Returns ready/not_ready status. This endpoint is public.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },
  {
    name: 'wc_liveness',
    description:
      'Simple liveness probe for the WC Paralegal Backend. Returns alive status. This endpoint is public.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },

  // -- Cases (Requires Auth) --
  {
    name: 'wc_list_cases',
    description:
      'List WC cases for the authenticated user. Optionally filter by status. Requires an active authenticated session.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        status: {
          type: 'string',
          description: 'Optional status filter (e.g., "ACTIVE", "CLOSED")',
        },
      },
      required: [] as string[],
    },
  },
  {
    name: 'wc_get_case',
    description:
      'Get details for a specific WC case by ID. Requires an active authenticated session.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        caseId: {
          type: 'string',
          description: 'Case UUID',
        },
      },
      required: ['caseId'],
    },
  },
  {
    name: 'wc_create_case',
    description:
      'Create a new WC case. Requires an active authenticated session.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        applicantName: {
          type: 'string',
          description: 'Name of the applicant/injured worker',
        },
        caseNumber: {
          type: 'string',
          description: 'ADJ or case number (e.g., "ADJ12345678")',
        },
        dateOfInjury: {
          type: 'string',
          description: 'Date of injury (YYYY-MM-DD format)',
        },
        employer: {
          type: 'string',
          description: 'Name of the employer',
        },
      },
      required: ['applicantName'],
    },
  },
  {
    name: 'wc_start_case_session',
    description:
      'Start a case session for document processing. Sets the active case context for subsequent operations. Requires auth.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        caseId: {
          type: 'string',
          description: 'Case UUID to start a session for',
        },
      },
      required: ['caseId'],
    },
  },
  {
    name: 'wc_get_active_session',
    description:
      'Get the currently active case session for the authenticated user. Returns null if no session is active.',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [] as string[],
    },
  },

  // -- Document Processing (Requires Auth + Case Session) --
  {
    name: 'wc_process_document',
    description:
      'Process a single document through Document AI OCR and WC field extraction (V1 rules-based). Requires auth and an active case session.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        fileId: {
          type: 'string',
          description: 'Google Drive file ID of the document to process',
        },
      },
      required: ['fileId'],
    },
  },
  {
    name: 'wc_process_document_v2',
    description:
      'Process a single document through Document AI OCR + Gemini LLM hybrid extraction (V2). Returns structured WC fields with confidence scores. Requires auth and an active case session.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        fileId: {
          type: 'string',
          description: 'Google Drive file ID of the document to process',
        },
      },
      required: ['fileId'],
    },
  },
  {
    name: 'wc_process_documents_with_summary',
    description:
      'Process multiple documents and generate a case summary. Requires auth and an active case session.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        caseId: {
          type: 'string',
          description: 'Case UUID',
        },
        fileIds: {
          type: 'array',
          items: { type: 'string' },
          description: 'Array of Google Drive file IDs to process',
        },
      },
      required: ['caseId', 'fileIds'],
    },
  },
  {
    name: 'wc_get_job_status',
    description:
      'Get the status of a document processing job. Returns progress, processed files count, and completion status.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        jobId: {
          type: 'string',
          description: 'Processing job ID',
        },
      },
      required: ['jobId'],
    },
  },
  {
    name: 'wc_get_processed_documents',
    description:
      'Get all processed documents for a specific case. Returns extracted WC fields and metadata.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        caseId: {
          type: 'string',
          description: 'Case UUID',
        },
      },
      required: ['caseId'],
    },
  },

  // -- Chat (Requires Auth) --
  {
    name: 'wc_chat_message',
    description:
      'Send a message to the Gemini chat assistant. The chat has context about the active WC case and processed documents. PHI is automatically redacted from prompts. Requires auth.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        message: {
          type: 'string',
          description: 'Message to send to the chat assistant',
        },
        sessionId: {
          type: 'string',
          description: 'Chat session ID (create one first with wc_create_chat_session)',
        },
      },
      required: ['message', 'sessionId'],
    },
  },
  {
    name: 'wc_create_chat_session',
    description:
      'Create a new Gemini chat session. Optionally associate with a case for contextual chat.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        caseId: {
          type: 'string',
          description: 'Optional case UUID to associate the chat session with',
        },
        title: {
          type: 'string',
          description: 'Optional title for the chat session',
        },
      },
      required: [] as string[],
    },
  },
  {
    name: 'wc_get_chat_history',
    description:
      'Get chat message history for a session. Returns messages in chronological order.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        sessionId: {
          type: 'string',
          description: 'Chat session ID',
        },
        limit: {
          type: 'number',
          description: 'Maximum number of messages to return (default: 50)',
        },
      },
      required: ['sessionId'],
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
      // -- Health Checks --
      case 'wc_health':
        response = await client.get('/health');
        break;

      case 'wc_readiness':
        response = await client.get('/health/ready');
        break;

      case 'wc_liveness':
        response = await client.get('/health/live');
        break;

      // -- Cases --
      case 'wc_list_cases': {
        const params: Record<string, string> = {};
        if (args.status) params.status = args.status as string;
        response = await client.get('/cases', { params });
        break;
      }

      case 'wc_get_case':
        response = await client.get(`/cases/${args.caseId}`);
        break;

      case 'wc_create_case':
        response = await client.post('/cases', {
          applicantName: args.applicantName,
          caseNumber: args.caseNumber,
          dateOfInjury: args.dateOfInjury,
          employer: args.employer,
        });
        break;

      case 'wc_start_case_session':
        response = await client.post(`/cases/${args.caseId}/start-session`);
        break;

      case 'wc_get_active_session':
        response = await client.get('/cases/active-session');
        break;

      // -- Document Processing --
      case 'wc_process_document':
        response = await client.post('/documents/process/single', {
          fileId: args.fileId,
        });
        break;

      case 'wc_process_document_v2':
        response = await client.post('/documents/process/v2/single', {
          fileId: args.fileId,
        });
        break;

      case 'wc_process_documents_with_summary':
        response = await client.post('/documents/process/with-summary', {
          caseId: args.caseId,
          fileIds: args.fileIds,
        });
        break;

      case 'wc_get_job_status':
        response = await client.get(`/documents/process/status/${args.jobId}`);
        break;

      case 'wc_get_processed_documents':
        response = await client.get(`/documents/processed-by-case/${args.caseId}`);
        break;

      // -- Chat --
      case 'wc_chat_message':
        response = await client.post('/chat/message', {
          message: args.message,
          sessionId: args.sessionId,
        });
        break;

      case 'wc_create_chat_session':
        response = await client.post('/chat/sessions', {
          caseId: args.caseId,
          title: args.title,
        });
        break;

      case 'wc_get_chat_history':
        response = await client.get(`/chat/sessions/${args.sessionId}/history`, {
          params: { limit: args.limit },
        });
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
  { name: 'wc-paralegal-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  return executeTool(name, (args ?? {}) as Record<string, unknown>);
});

server.onerror = (error) => {
  console.error('[wc-paralegal-mcp] Server error:', error);
};

process.on('SIGINT', async () => {
  await server.close();
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);

console.error(`[wc-paralegal-mcp] Connected to backend at ${BACKEND_URL}`);
