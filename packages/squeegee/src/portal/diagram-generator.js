/**
 * Portal Diagram Generator
 *
 * Generates Mermaid diagrams (architecture, data flow, sequence) via
 * Gemini 3.1 Pro. Includes content-hash caching and fallback diagrams.
 * Ported from glass-box-hub/squeegee/diagram_generator.py (481 lines).
 *
 * @file src/portal/diagram-generator.js
 * @module portal/diagram-generator
 */

'use strict';

const crypto = require('crypto');
const { GoogleGenerativeAI } = require('@google/generative-ai');

/** Valid Mermaid diagram keyword prefixes */
const VALID_MERMAID_PREFIXES = [
  'graph', 'flowchart', 'sequenceDiagram', 'classDiagram',
  'stateDiagram', 'erDiagram', 'gantt', 'pie', 'gitgraph',
  'mindmap', 'timeline', 'C4Context', 'sankey',
];

let genAIInstance = null;

/**
 * Get or create Gemini client
 * @param {string} apiKey
 * @returns {GoogleGenerativeAI}
 */
function getGenAI(apiKey) {
  if (!genAIInstance) {
    genAIInstance = new GoogleGenerativeAI(apiKey);
  }
  return genAIInstance;
}

/**
 * Clean Mermaid output from model response
 * @param {string} text
 * @returns {string}
 */
function cleanMermaidOutput(text) {
  let cleaned = text.trim();
  // Strip markdown code fences
  cleaned = cleaned.replace(/^```mermaid\s*/i, '').replace(/^```\s*/m, '');
  cleaned = cleaned.replace(/\s*```$/m, '');
  return cleaned.trim();
}

/**
 * Validate that text is valid Mermaid
 * @param {string} diagram
 * @returns {boolean}
 */
function validateMermaid(diagram) {
  const firstLine = diagram.split('\n')[0].trim();
  return VALID_MERMAID_PREFIXES.some((prefix) => firstLine.startsWith(prefix));
}

/**
 * Compute content hash for delta detection
 * @param {Object} projectData
 * @returns {string} - 16-char hex hash
 */
function computeContentHash(projectData) {
  const hashInput = [
    projectData.name || '',
    projectData.description || '',
    (projectData.tech_stack || []).join(','),
    projectData.category || '',
  ].join('|');

  return crypto.createHash('sha256').update(hashInput).digest('hex').slice(0, 16);
}

/**
 * Generate architecture diagram via Gemini 3.1 Pro
 * @param {Object} projectData
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<string>} - Mermaid code
 */
async function generateArchitectureDiagram(projectData, readme, apiKey) {
  const genAI = getGenAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  const prompt = `Generate a Mermaid.js architecture diagram for this software project.

Project: ${projectData.name}
Description: ${projectData.description || 'N/A'}
Tech Stack: ${(projectData.tech_stack || []).join(', ')}
Category: ${projectData.category || 'N/A'}

README excerpt:
${(readme || '').slice(0, 3000)}

Requirements:
- Use "graph TD" (top-down) layout
- 15-30 nodes showing major components and their relationships
- Use subgraphs to group related components
- Include styling with dark-palette colors only (dark backgrounds, light text)
- Show data flow direction with labeled arrows
- Output ONLY the Mermaid code, no explanation
- Do NOT wrap in code fences`;

  try {
    const result = await model.generateContent(prompt);
    const text = result.response.text();
    const cleaned = cleanMermaidOutput(text);

    if (validateMermaid(cleaned)) return cleaned;
    console.warn(`Portal: Invalid Mermaid from Gemini for ${projectData.name} architecture, using fallback`);
    return fallbackArchitectureDiagram(projectData);
  } catch (err) {
    console.error(`Portal: Gemini diagram generation failed for ${projectData.name}: ${err.message}`);
    return fallbackArchitectureDiagram(projectData);
  }
}

/**
 * Generate data flow diagram via Gemini 3.1 Pro
 * @param {Object} projectData
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<string>}
 */
async function generateDataFlowDiagram(projectData, readme, apiKey) {
  const genAI = getGenAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  const prompt = `Generate a Mermaid.js data flow diagram for this software project.

Project: ${projectData.name}
Description: ${projectData.description || 'N/A'}
Tech Stack: ${(projectData.tech_stack || []).join(', ')}

README excerpt:
${(readme || '').slice(0, 3000)}

Requirements:
- Use "flowchart LR" (left-to-right) layout
- 10-20 nodes showing data sources, transformations, and destinations
- Label all arrows with data type or action
- Use dark-palette styling
- Output ONLY the Mermaid code, no explanation`;

  try {
    const result = await model.generateContent(prompt);
    const cleaned = cleanMermaidOutput(result.response.text());
    if (validateMermaid(cleaned)) return cleaned;
    return fallbackDataFlowDiagram(projectData);
  } catch {
    return fallbackDataFlowDiagram(projectData);
  }
}

/**
 * Generate sequence diagram via Gemini 3.1 Pro
 * @param {Object} projectData
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<string>}
 */
async function generateSequenceDiagram(projectData, readme, apiKey) {
  const genAI = getGenAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  const prompt = `Generate a Mermaid.js sequence diagram for this software project's main user flow.

Project: ${projectData.name}
Description: ${projectData.description || 'N/A'}
Tech Stack: ${(projectData.tech_stack || []).join(', ')}

README excerpt:
${(readme || '').slice(0, 3000)}

Requirements:
- Use "sequenceDiagram" type
- 3-6 participants (User, Frontend, API, Database, etc.)
- 8-15 messages showing the primary user interaction flow
- Include alt/opt blocks where appropriate
- Output ONLY the Mermaid code, no explanation`;

  try {
    const result = await model.generateContent(prompt);
    const cleaned = cleanMermaidOutput(result.response.text());
    if (validateMermaid(cleaned)) return cleaned;
    return fallbackSequenceDiagram(projectData);
  } catch {
    return fallbackSequenceDiagram(projectData);
  }
}

// ─── Fallback Diagrams ──────────────────────────────────────────────────────

function fallbackArchitectureDiagram(projectData) {
  const name = projectData.name || 'Project';
  const stack = projectData.tech_stack || [];

  let diagram = `graph TD\n`;
  diagram += `    User([User]) --> Frontend\n`;

  if (stack.some((s) => /react|vue|angular|next/i.test(s))) {
    diagram += `    subgraph Frontend\n`;
    diagram += `        UI[Web UI]\n`;
    diagram += `    end\n`;
  } else {
    diagram += `    subgraph Frontend\n`;
    diagram += `        UI[Client]\n`;
    diagram += `    end\n`;
  }

  diagram += `    Frontend --> API[API Server]\n`;

  if (stack.some((s) => /postgres|mysql|mongo|prisma/i.test(s))) {
    diagram += `    API --> DB[(Database)]\n`;
  }

  if (stack.some((s) => /redis/i.test(s))) {
    diagram += `    API --> Cache[(Redis Cache)]\n`;
  }

  if (stack.some((s) => /gemini|openai|claude|ai/i.test(s))) {
    diagram += `    API --> AI[AI Service]\n`;
  }

  return diagram;
}

function fallbackDataFlowDiagram(projectData) {
  const name = projectData.name || 'Project';
  return `flowchart LR
    Input[Input Data] --> Process[${name} Processing]
    Process --> Output[Output]
    Process --> Store[(Data Store)]
    Store --> Process`;
}

function fallbackSequenceDiagram(projectData) {
  return `sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant DB

    User->>Frontend: Request
    Frontend->>API: API Call
    API->>DB: Query
    DB-->>API: Results
    API-->>Frontend: Response
    Frontend-->>User: Display`;
}

/**
 * Generate all three diagram types for a project
 * @param {Object} projectData
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<Object>} - { architecture, data_flow, sequence }
 */
async function generateAllDiagrams(projectData, readme, apiKey) {
  const [architecture, data_flow, sequence] = await Promise.all([
    generateArchitectureDiagram(projectData, readme, apiKey),
    generateDataFlowDiagram(projectData, readme, apiKey),
    generateSequenceDiagram(projectData, readme, apiKey),
  ]);

  return { architecture, data_flow, sequence };
}

module.exports = {
  cleanMermaidOutput,
  validateMermaid,
  computeContentHash,
  generateArchitectureDiagram,
  generateDataFlowDiagram,
  generateSequenceDiagram,
  generateAllDiagrams,
  fallbackArchitectureDiagram,
  fallbackDataFlowDiagram,
  fallbackSequenceDiagram,
};
