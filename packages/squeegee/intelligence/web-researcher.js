/**
 * Web Research Module
 *
 * Performs best-practice research using Gemini with Google Search grounding.
 * Used for quarterly documentation standards research and on-demand topic exploration.
 *
 * Grounding enables real-time web search results to be incorporated into Gemini responses,
 * providing up-to-date information on evolving best practices.
 *
 * @file web-researcher.js
 * @module intelligence/web-researcher
 */

const { GoogleGenerativeAI } = require('@google/generative-ai');
const { GeminiAPIError, retryWithBackoff, formatDate } = require('./utils');

/**
 * Predefined research topics for quarterly automation
 */
const RESEARCH_TOPICS = {
  'documentation-standards': {
    query: 'software documentation best practices 2026',
    focus: 'CLAUDE.md standards, AI-assisted documentation, code intelligence'
  },
  'engineering-practices': {
    query: 'software engineering best practices 2026',
    focus: 'AI agents, autonomous development, testing automation'
  },
  'glass-box-stack': {
    query: 'Node.js TypeScript Python FastAPI best practices 2026',
    focus: 'GCP Cloud Run, PostgreSQL, modern web frameworks'
  },
  'compliance-standards': {
    query: 'HIPAA GDPR CCPA compliance software 2026',
    focus: 'Healthcare AI, data privacy, audit trails'
  },
  'ai-readable-docs': {
    query: 'AI-readable documentation patterns RAG optimization',
    focus: 'Context window optimization, semantic search, retrieval'
  },
  'technical-writing': {
    query: 'technical writing standards 2026 developer documentation',
    focus: 'Clarity, examples, progressive disclosure, scannability'
  }
};

/**
 * Build research prompt for Gemini
 * @param {string} topic - Research topic key or custom query
 * @param {Date} date - Date of the research
 * @returns {string} - Formatted prompt
 */
function buildResearchPrompt(topic, date) {
  const topicConfig = RESEARCH_TOPICS[topic];
  const query = topicConfig ? topicConfig.query : topic;
  const focus = topicConfig ? topicConfig.focus : 'General best practices and industry standards';

  return `You are a technology research analyst for Glass Box Solutions, Inc.

**Research Date:** ${formatDate(date)}
**Research Topic:** ${query}
**Focus Areas:** ${focus}

Using Google Search, research the following:
1. **Current Best Practices** — Industry standards and recommendations (2025-2026)
2. **Emerging Trends** — New technologies, methodologies, or patterns
3. **Common Pitfalls** — Anti-patterns, mistakes, and things to avoid
4. **Recommended Tools** — Frameworks, libraries, or services
5. **Compliance & Security** — Regulatory considerations and security best practices

Provide a comprehensive research report with:

## Executive Summary
3-5 key findings (bullet points)

## Detailed Findings
Organized by subtopic with evidence from your research. Include specific examples, statistics, and quotes where relevant.

## Recommendations for Glass Box Solutions
Actionable items our team should consider based on this research. Be specific and practical.

## Sources
List the key sources you referenced (title and URL)

**Format:** Markdown with clear sections and bullet points.
**Tone:** Professional, analytical, evidence-based.
**Length:** Aim for 800-1200 words.

Generate the research report now:`;
}

/**
 * Extract sources from Gemini response with grounding citations
 * @param {string} responseText - Gemini response text
 * @param {Object} groundingMetadata - Grounding metadata from response
 * @returns {Array<{title: string, url: string}>} - Extracted sources
 */
function extractSources(responseText, groundingMetadata) {
  const sources = [];

  // Parse grounding metadata for source URLs
  if (groundingMetadata?.groundingChunks) {
    for (const chunk of groundingMetadata.groundingChunks) {
      if (chunk.web) {
        sources.push({
          title: chunk.web.title || 'Untitled',
          url: chunk.web.uri
        });
      }
    }
  }

  // Fallback: extract URLs from markdown links in response
  const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g;
  let match;
  while ((match = linkRegex.exec(responseText)) !== null) {
    sources.push({
      title: match[1],
      url: match[2]
    });
  }

  // Deduplicate by URL
  const uniqueSources = [...new Map(sources.map(s => [s.url, s])).values()];

  return uniqueSources;
}

/**
 * Parse research report into structured sections
 * @param {string} responseText - Gemini response markdown
 * @returns {Object} - Parsed sections
 */
function parseResearchReport(responseText) {
  const sections = {
    executive_summary: [],
    findings: '',
    recommendations: [],
    sources_markdown: ''
  };

  const lines = responseText.split('\n');
  let currentSection = null;
  let buffer = [];

  for (const line of lines) {
    // Detect section headers
    if (line.match(/^##\s*Executive Summary/i)) {
      currentSection = 'executive_summary';
      buffer = [];
    } else if (line.match(/^##\s*Detailed Findings/i)) {
      if (currentSection === 'executive_summary') {
        // Extract bullet points
        sections.executive_summary = buffer
          .filter(l => l.trim().startsWith('-') || l.trim().startsWith('*'))
          .map(l => l.replace(/^[-*]\s*/, '').trim())
          .filter(l => l.length > 0);
      }
      currentSection = 'findings';
      buffer = [];
    } else if (line.match(/^##\s*Recommendations/i)) {
      if (currentSection === 'findings') {
        sections.findings = buffer.join('\n').trim();
      }
      currentSection = 'recommendations';
      buffer = [];
    } else if (line.match(/^##\s*Sources/i)) {
      if (currentSection === 'recommendations') {
        sections.recommendations = buffer
          .filter(l => l.trim().startsWith('-') || l.trim().startsWith('*'))
          .map(l => l.replace(/^[-*]\s*/, '').trim())
          .filter(l => l.length > 0);
      }
      currentSection = 'sources';
      buffer = [];
    } else {
      buffer.push(line);
    }
  }

  // Handle last section
  if (currentSection === 'sources') {
    sections.sources_markdown = buffer.join('\n').trim();
  }

  // Fallback: use entire text as findings if parsing failed
  if (!sections.findings && sections.executive_summary.length === 0) {
    sections.findings = responseText;
  }

  return sections;
}

/**
 * Research best practices using Gemini with Google Search grounding
 * @param {string} topic - Research topic (key from RESEARCH_TOPICS or custom query)
 * @param {Date} date - Date of the research
 * @param {Object} config - Intelligence configuration
 * @returns {Promise<Object>} - ResearchReport object
 */
async function research(topic, date, config) {
  console.log(`Starting web research: ${topic}`);

  // Check for API key
  const apiKey = config.intelligence?.gemini?.apiKey || process.env.GOOGLE_AI_API_KEY;
  if (!apiKey) {
    const error = new GeminiAPIError('Gemini API key not configured', 401);
    console.error('Research failed:', error.message);
    return {
      date: formatDate(date),
      topic,
      query: topic,
      executive_summary: [],
      findings: '',
      recommendations: [],
      sources: [],
      model_used: null,
      grounding_enabled: false,
      token_count: { input: 0, output: 0 },
      generated_at: new Date().toISOString(),
      fallback_used: false,
      error: error.message
    };
  }

  // Build prompt
  const prompt = buildResearchPrompt(topic, date);
  const inputTokenEstimate = Math.ceil(prompt.length / 4);

  console.log(`Calling Gemini API with grounding (estimated input tokens: ${inputTokenEstimate})`);

  // Try with grounding first
  try {
    const result = await retryWithBackoff(async () => {
      const genAI = new GoogleGenerativeAI(apiKey);

      // Configure model with Google Search grounding
      const model = genAI.getGenerativeModel({
        model: config.intelligence?.gemini?.model || 'gemini-2.0-flash-exp',
        generationConfig: {
          temperature: config.intelligence?.gemini?.temperature || 0.4, // Slightly more exploratory
          maxOutputTokens: config.intelligence?.gemini?.max_output_tokens || 8192
        },
        safetySettings: [
          {
            category: 'HARM_CATEGORY_HARASSMENT',
            threshold: 'BLOCK_MEDIUM_AND_ABOVE'
          },
          {
            category: 'HARM_CATEGORY_HATE_SPEECH',
            threshold: 'BLOCK_MEDIUM_AND_ABOVE'
          }
        ],
        tools: [{
          googleSearchRetrieval: {
            dynamicRetrievalConfig: {
              mode: 'MODE_DYNAMIC',
              dynamicThreshold: 0.7
            }
          }
        }]
      });

      const generationResult = await model.generateContent({
        contents: [{ role: 'user', parts: [{ text: prompt }] }]
      });

      const response = await generationResult.response;
      const text = response.text();

      if (!text || text.length === 0) {
        throw new GeminiAPIError('Gemini returned empty response', 500);
      }

      // Extract grounding metadata
      const groundingMetadata = response.candidates?.[0]?.groundingMetadata || null;

      return { text, groundingMetadata, response };
    }, 3, 2000);

    // Parse response
    const sections = parseResearchReport(result.text);
    const sources = extractSources(result.text, result.groundingMetadata);
    const outputTokenEstimate = Math.ceil(result.text.length / 4);

    console.log(`Research completed successfully with grounding (output tokens: ~${outputTokenEstimate}, sources: ${sources.length})`);

    return {
      date: formatDate(date),
      topic,
      query: RESEARCH_TOPICS[topic]?.query || topic,
      executive_summary: sections.executive_summary,
      findings: sections.findings,
      recommendations: sections.recommendations,
      sources,
      model_used: config.intelligence?.gemini?.model || 'gemini-2.0-flash-exp',
      grounding_enabled: true,
      token_count: {
        input: inputTokenEstimate,
        output: outputTokenEstimate
      },
      generated_at: new Date().toISOString(),
      fallback_used: false,
      error: null
    };

  } catch (error) {
    console.warn(`Research with grounding failed: ${error.message}`);

    // Check if error is grounding-related
    if (error.message.includes('grounding') || error.message.includes('search')) {
      console.warn('Attempting fallback to ungrounded Gemini...');

      // Retry without grounding
      try {
        const fallbackResult = await retryWithBackoff(async () => {
          const genAI = new GoogleGenerativeAI(apiKey);

          // Same model, no tools
          const model = genAI.getGenerativeModel({
            model: config.intelligence?.gemini?.model || 'gemini-2.0-flash-exp',
            generationConfig: {
              temperature: 0.4,
              maxOutputTokens: 8192
            }
          });

          const generationResult = await model.generateContent({
            contents: [{ role: 'user', parts: [{ text: prompt }] }]
          });

          const response = await generationResult.response;
          const text = response.text();

          if (!text || text.length === 0) {
            throw new GeminiAPIError('Gemini returned empty response', 500);
          }

          return { text, response };
        }, 3, 2000);

        // Parse response (no grounding metadata)
        const sections = parseResearchReport(fallbackResult.text);
        const sources = extractSources(fallbackResult.text, null);
        const outputTokenEstimate = Math.ceil(fallbackResult.text.length / 4);

        console.log(`Research completed with fallback (ungrounded, output tokens: ~${outputTokenEstimate})`);

        return {
          date: formatDate(date),
          topic,
          query: RESEARCH_TOPICS[topic]?.query || topic,
          executive_summary: sections.executive_summary,
          findings: sections.findings,
          recommendations: sections.recommendations,
          sources,
          model_used: config.intelligence?.gemini?.model || 'gemini-2.0-flash-exp',
          grounding_enabled: false,
          token_count: {
            input: inputTokenEstimate,
            output: outputTokenEstimate
          },
          generated_at: new Date().toISOString(),
          fallback_used: true,
          error: null
        };

      } catch (fallbackError) {
        console.error('Fallback research also failed:', fallbackError.message);

        // Return error result
        return {
          date: formatDate(date),
          topic,
          query: RESEARCH_TOPICS[topic]?.query || topic,
          executive_summary: [],
          findings: '',
          recommendations: [],
          sources: [],
          model_used: config.intelligence?.gemini?.model || 'gemini-2.0-flash-exp',
          grounding_enabled: false,
          token_count: { input: inputTokenEstimate, output: 0 },
          generated_at: new Date().toISOString(),
          fallback_used: true,
          error: fallbackError.message
        };
      }
    }

    // Non-grounding error, return error result
    console.error('Research failed:', error.message);
    return {
      date: formatDate(date),
      topic,
      query: RESEARCH_TOPICS[topic]?.query || topic,
      executive_summary: [],
      findings: '',
      recommendations: [],
      sources: [],
      model_used: config.intelligence?.gemini?.model || 'gemini-2.0-flash-exp',
      grounding_enabled: false,
      token_count: { input: inputTokenEstimate, output: 0 },
      generated_at: new Date().toISOString(),
      fallback_used: false,
      error: error.message
    };
  }
}

module.exports = {
  research,
  RESEARCH_TOPICS,
  // Export for testing
  buildResearchPrompt,
  extractSources,
  parseResearchReport
};
