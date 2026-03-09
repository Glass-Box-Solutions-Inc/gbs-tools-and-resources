/**
 * Portal Explanation Generator
 *
 * Generates dual technical/non-technical explanations and user journeys
 * via Gemini 3.1 Flash. Ported from glass-box-hub/squeegee/explanation_generator.py.
 *
 * @file src/portal/explanation-generator.js
 * @module portal/explanation-generator
 */

'use strict';

const { GoogleGenerativeAI } = require('@google/generative-ai');

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
 * Parse dual response (TECHNICAL: / NON-TECHNICAL: sections)
 * @param {string} text
 * @param {Object} projectData
 * @returns {DualExplanation}
 */
function parseDualResponse(text, projectData) {
  const techMatch = text.match(/TECHNICAL:\s*([\s\S]*?)(?=NON[_-]?TECHNICAL:|$)/i);
  const nonTechMatch = text.match(/NON[_-]?TECHNICAL:\s*([\s\S]*?)$/i);

  let technical = techMatch ? techMatch[1].trim() : '';
  let nonTechnical = nonTechMatch ? nonTechMatch[1].trim() : '';

  // Strip markdown bold markers
  technical = technical.replace(/\*\*/g, '');
  nonTechnical = nonTechnical.replace(/\*\*/g, '');

  // Fallback if parsing failed
  if (!technical) {
    technical = `${projectData.name} is a ${projectData.category || 'software'} project built with ${(projectData.tech_stack || []).join(', ') || 'modern technologies'}.`;
  }
  if (!nonTechnical) {
    nonTechnical = `${projectData.name} ${projectData.description || 'helps streamline workflows and improve efficiency.'}`;
  }

  return { technical, non_technical: nonTechnical };
}

/**
 * Generate project explanation via Gemini 3.1 Flash
 * @param {Object} projectData
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<DualExplanation>}
 */
async function generateProjectExplanation(projectData, readme, apiKey) {
  const genAI = getGenAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  const prompt = `Write two explanations of this software project.

Project: ${projectData.name}
Description: ${projectData.description || 'N/A'}
Tech Stack: ${(projectData.tech_stack || []).join(', ')}
Category: ${projectData.category || 'N/A'}
Status: ${projectData.status || 'N/A'}

README excerpt:
${(readme || '').slice(0, 3000)}

Format your response EXACTLY like this:

TECHNICAL:
[2-3 paragraphs for developers — cover architecture, key technologies, design patterns, and integration points]

NON-TECHNICAL:
[1-2 paragraphs for non-technical stakeholders — explain what the project does, who it helps, and the business value in plain English]`;

  try {
    const result = await model.generateContent(prompt);
    return parseDualResponse(result.response.text(), projectData);
  } catch (err) {
    console.error(`Portal: Explanation generation failed for ${projectData.name}: ${err.message}`);
    return fallbackExplanation(projectData);
  }
}

/**
 * Generate diagram explanation via Gemini 3.1 Flash
 * @param {Object} projectData
 * @param {string} diagramCode - Mermaid code
 * @param {string} diagramType - "architecture" | "data_flow" | "sequence"
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<DualExplanation>}
 */
async function generateDiagramExplanation(projectData, diagramCode, diagramType, readme, apiKey) {
  const genAI = getGenAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  const typeNames = {
    architecture: 'architecture',
    data_flow: 'data flow',
    sequence: 'system interaction sequence',
  };

  const prompt = `Explain this ${typeNames[diagramType] || diagramType} diagram for the ${projectData.name} project.

Mermaid diagram:
${diagramCode}

Project context:
${projectData.description || ''}

Format:
TECHNICAL:
[1-2 paragraphs explaining the diagram for developers]

NON-TECHNICAL:
[1 paragraph explaining the diagram for non-technical stakeholders]`;

  try {
    const result = await model.generateContent(prompt);
    return parseDualResponse(result.response.text(), projectData);
  } catch {
    return {
      technical: `This ${typeNames[diagramType] || diagramType} diagram shows how ${projectData.name}'s components interact.`,
      non_technical: `This diagram illustrates how the different parts of ${projectData.name} work together.`,
    };
  }
}

/**
 * Generate user journey description via Gemini 3.1 Flash
 * @param {Object} projectData
 * @param {string} readme
 * @param {string} apiKey
 * @returns {Promise<string>} - HTML paragraphs
 */
async function generateUserJourney(projectData, readme, apiKey) {
  const genAI = getGenAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  const prompt = `Describe the main user journey for this software project in 5-8 numbered steps.

Project: ${projectData.name}
Description: ${projectData.description || 'N/A'}
Tech Stack: ${(projectData.tech_stack || []).join(', ')}

README excerpt:
${(readme || '').slice(0, 2000)}

Requirements:
- Write in plain English for non-technical readers
- Each step should be 1-2 sentences
- Focus on what the user experiences, not technical implementation
- Format as numbered list (1. First step... 2. Second step...)`;

  try {
    const result = await model.generateContent(prompt);
    const text = result.response.text().trim();
    // Convert numbered list to HTML paragraphs
    const steps = text
      .split(/\n/)
      .filter((line) => line.trim())
      .map((line) => `<p>${line.trim()}</p>`)
      .join('\n');
    return steps;
  } catch (err) {
    console.error(`Portal: User journey generation failed for ${projectData.name}: ${err.message}`);
    return fallbackUserJourney(projectData);
  }
}

// ─── Fallbacks ──────────────────────────────────────────────────────────────

function fallbackExplanation(projectData) {
  const stack = (projectData.tech_stack || []).join(', ') || 'modern technologies';
  return {
    technical: `${projectData.name} is a ${projectData.category || 'software'} project built with ${stack}. It follows modern development practices and is designed for reliability and maintainability.`,
    non_technical: `${projectData.name} ${projectData.description || 'is a tool that helps streamline workflows and improve team efficiency.'}`,
  };
}

function fallbackUserJourney(projectData) {
  return `<p>1. User accesses ${projectData.name} through their web browser or application.</p>
<p>2. The system authenticates the user and loads their workspace.</p>
<p>3. User interacts with the main features of the application.</p>
<p>4. Changes are saved automatically and synced across the platform.</p>`;
}

module.exports = {
  parseDualResponse,
  generateProjectExplanation,
  generateDiagramExplanation,
  generateUserJourney,
};
