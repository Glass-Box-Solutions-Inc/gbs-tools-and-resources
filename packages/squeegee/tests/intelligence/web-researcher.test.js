/**
 * Tests for web-researcher.js
 *
 * Tests web research functionality using Gemini with Google Search grounding.
 * Uses mocked Gemini SDK to avoid actual API calls in tests.
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

// Mock the Gemini SDK before requiring the module
jest.mock('@google/generative-ai', () => {
  return {
    GoogleGenerativeAI: jest.fn()
  };
});

// Mock utils
jest.mock('../../intelligence/utils', () => {
  return {
    GeminiAPIError: class GeminiAPIError extends Error {
      constructor(message, statusCode) {
        super(message);
        this.name = 'GeminiAPIError';
        this.statusCode = statusCode;
      }
    },
    retryWithBackoff: jest.fn(async (fn, maxRetries = 3) => {
      // Actually retry on failure up to maxRetries times
      let lastError;
      for (let i = 0; i < maxRetries; i++) {
        try {
          return await fn();
        } catch (error) {
          lastError = error;
        }
      }
      throw lastError;
    }),
    formatDate: jest.fn((date) => {
      if (date instanceof Date) {
        return date.toISOString().split('T')[0];
      }
      return date;
    })
  };
});

const { research, RESEARCH_TOPICS, buildResearchPrompt, extractSources, parseResearchReport } = require('../../intelligence/web-researcher');

describe('web-researcher', () => {
  let mockGenAI;
  let mockModel;
  let mockGenerateContent;
  let mockConfig;

  beforeEach(() => {
    jest.clearAllMocks();

    // Setup mock config
    mockConfig = {
      intelligence: {
        gemini: {
          apiKey: 'test-api-key',
          model: 'gemini-2.0-flash-exp',
          temperature: 0.4,
          max_output_tokens: 8192
        }
      }
    };

    // Setup mock Gemini SDK
    mockGenerateContent = jest.fn();
    mockModel = {
      generateContent: mockGenerateContent
    };
    mockGenAI = {
      getGenerativeModel: jest.fn(() => mockModel)
    };

    const { GoogleGenerativeAI } = require('@google/generative-ai');
    GoogleGenerativeAI.mockImplementation(() => mockGenAI);
  });

  describe('RESEARCH_TOPICS', () => {
    it('should contain predefined research topics', () => {
      expect(RESEARCH_TOPICS).toBeDefined();
      expect(Object.keys(RESEARCH_TOPICS).length).toBeGreaterThan(0);
    });

    it('should have query and focus fields for each topic', () => {
      for (const [key, config] of Object.entries(RESEARCH_TOPICS)) {
        expect(config.query).toBeDefined();
        expect(config.focus).toBeDefined();
        expect(typeof config.query).toBe('string');
        expect(typeof config.focus).toBe('string');
      }
    });

    it('should include key topics', () => {
      expect(RESEARCH_TOPICS['documentation-standards']).toBeDefined();
      expect(RESEARCH_TOPICS['engineering-practices']).toBeDefined();
      expect(RESEARCH_TOPICS['compliance-standards']).toBeDefined();
    });
  });

  describe('buildResearchPrompt', () => {
    it('should build prompt for predefined topic', () => {
      const date = new Date('2026-03-13');
      const prompt = buildResearchPrompt('documentation-standards', date);

      expect(prompt).toContain('Research Topic:');
      expect(prompt).toContain('software documentation best practices 2026');
      expect(prompt).toContain('CLAUDE.md standards');
      expect(prompt).toContain('Executive Summary');
      expect(prompt).toContain('Detailed Findings');
      expect(prompt).toContain('Recommendations');
      expect(prompt).toContain('Sources');
    });

    it('should build prompt for custom topic', () => {
      const date = new Date('2026-03-13');
      const prompt = buildResearchPrompt('Custom topic query', date);

      expect(prompt).toContain('**Research Topic:** Custom topic query');
      expect(prompt).toContain('General best practices');
    });

    it('should include research date', () => {
      const date = new Date('2026-03-13');
      const prompt = buildResearchPrompt('documentation-standards', date);

      expect(prompt).toContain('2026-03-13');
    });

    it('should structure prompt with clear sections', () => {
      const date = new Date('2026-03-13');
      const prompt = buildResearchPrompt('engineering-practices', date);

      expect(prompt).toContain('Current Best Practices');
      expect(prompt).toContain('Emerging Trends');
      expect(prompt).toContain('Common Pitfalls');
      expect(prompt).toContain('Recommended Tools');
      expect(prompt).toContain('Compliance & Security');
    });
  });

  describe('extractSources', () => {
    it('should extract sources from grounding metadata', () => {
      const groundingMetadata = {
        groundingChunks: [
          {
            web: {
              title: 'Best Practices Guide',
              uri: 'https://example.com/guide'
            }
          },
          {
            web: {
              title: 'Industry Standards',
              uri: 'https://example.com/standards'
            }
          }
        ]
      };

      const sources = extractSources('', groundingMetadata);

      expect(sources.length).toBe(2);
      expect(sources[0]).toEqual({
        title: 'Best Practices Guide',
        url: 'https://example.com/guide'
      });
      expect(sources[1]).toEqual({
        title: 'Industry Standards',
        url: 'https://example.com/standards'
      });
    });

    it('should handle missing title in grounding metadata', () => {
      const groundingMetadata = {
        groundingChunks: [
          {
            web: {
              uri: 'https://example.com/untitled'
            }
          }
        ]
      };

      const sources = extractSources('', groundingMetadata);

      expect(sources.length).toBe(1);
      expect(sources[0].title).toBe('Untitled');
      expect(sources[0].url).toBe('https://example.com/untitled');
    });

    it('should extract sources from markdown links as fallback', () => {
      const responseText = `
        Some content with links:
        - [Documentation Guide](https://example.com/docs)
        - [Best Practices](https://example.com/practices)
      `;

      const sources = extractSources(responseText, null);

      expect(sources.length).toBe(2);
      expect(sources[0]).toEqual({
        title: 'Documentation Guide',
        url: 'https://example.com/docs'
      });
    });

    it('should deduplicate sources by URL', () => {
      const groundingMetadata = {
        groundingChunks: [
          {
            web: {
              title: 'Guide v1',
              uri: 'https://example.com/guide'
            }
          }
        ]
      };

      const responseText = '[Guide v2](https://example.com/guide)';

      const sources = extractSources(responseText, groundingMetadata);

      expect(sources.length).toBe(1);
      // Implementation uses last occurrence for deduplication
      expect(sources[0].title).toBe('Guide v2');
    });

    it('should return empty array when no sources found', () => {
      const sources = extractSources('No links here', null);
      expect(sources.length).toBe(0);
    });
  });

  describe('parseResearchReport', () => {
    it('should parse complete research report', () => {
      const responseText = `
## Executive Summary
- Finding 1
- Finding 2
- Finding 3

## Detailed Findings
### Subtopic 1
Content about subtopic 1

### Subtopic 2
Content about subtopic 2

## Recommendations for Glass Box Solutions
- Recommendation 1
- Recommendation 2

## Sources
- [Source 1](https://example.com/1)
- [Source 2](https://example.com/2)
      `;

      const sections = parseResearchReport(responseText);

      expect(sections.executive_summary.length).toBe(3);
      expect(sections.executive_summary[0]).toBe('Finding 1');
      expect(sections.findings).toContain('Subtopic 1');
      expect(sections.findings).toContain('Subtopic 2');
      expect(sections.recommendations.length).toBe(2);
      expect(sections.sources_markdown).toContain('Source 1');
    });

    it('should handle missing executive summary', () => {
      const responseText = `
## Detailed Findings
Some findings here

## Recommendations
- Recommendation 1
      `;

      const sections = parseResearchReport(responseText);

      expect(sections.executive_summary.length).toBe(0);
      expect(sections.findings).toContain('Some findings');
    });

    it('should use entire text as findings if parsing fails', () => {
      const responseText = 'Just plain text without sections';

      const sections = parseResearchReport(responseText);

      expect(sections.findings).toBe(responseText);
    });

    it('should handle recommendations without bullet points', () => {
      const responseText = `
## Recommendations for Glass Box Solutions
Narrative recommendation text
without bullet points
      `;

      const sections = parseResearchReport(responseText);

      expect(sections.recommendations.length).toBe(0);
    });
  });

  describe('research (happy path)', () => {
    it('should complete research with grounding successfully', async () => {
      const mockResponse = {
        text: () => `
## Executive Summary
- Key finding 1
- Key finding 2

## Detailed Findings
Comprehensive analysis here

## Recommendations for Glass Box Solutions
- Adopt practice X
- Implement tool Y

## Sources
- [Source](https://example.com)
        `,
        candidates: [{
          groundingMetadata: {
            groundingChunks: [{
              web: {
                title: 'Example Source',
                uri: 'https://example.com'
              }
            }]
          }
        }]
      };

      mockGenerateContent.mockResolvedValue({
        response: mockResponse
      });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.date).toBe('2026-03-13');
      expect(result.topic).toBe('documentation-standards');
      expect(result.executive_summary.length).toBeGreaterThan(0);
      expect(result.findings).toContain('Comprehensive analysis');
      expect(result.recommendations.length).toBeGreaterThan(0);
      expect(result.sources.length).toBeGreaterThan(0);
      expect(result.grounding_enabled).toBe(true);
      expect(result.fallback_used).toBe(false);
      expect(result.error).toBeNull();
      expect(result.model_used).toBe('gemini-2.0-flash-exp');
    });

    it('should include token count estimates', async () => {
      const mockResponse = {
        text: () => 'Short response',
        candidates: [{ groundingMetadata: null }]
      };

      mockGenerateContent.mockResolvedValue({
        response: mockResponse
      });

      const date = new Date('2026-03-13');
      const result = await research('engineering-practices', date, mockConfig);

      expect(result.token_count).toBeDefined();
      expect(result.token_count.input).toBeGreaterThan(0);
      expect(result.token_count.output).toBeGreaterThan(0);
    });

    it('should call Gemini with grounding configuration', async () => {
      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => 'Response',
          candidates: []
        }
      });

      const date = new Date('2026-03-13');
      await research('documentation-standards', date, mockConfig);

      expect(mockGenAI.getGenerativeModel).toHaveBeenCalledWith(
        expect.objectContaining({
          model: 'gemini-2.0-flash-exp',
          generationConfig: expect.objectContaining({
            temperature: 0.4,
            maxOutputTokens: 8192
          }),
          tools: expect.arrayContaining([
            expect.objectContaining({
              googleSearchRetrieval: expect.any(Object)
            })
          ])
        })
      );
    });
  });

  describe('research (fallback scenarios)', () => {
    it('should fallback to ungrounded when grounding fails', async () => {
      // All grounded calls fail (retries exhausted), then fallback succeeds
      mockGenerateContent
        .mockRejectedValueOnce(new Error('grounding unavailable'))
        .mockRejectedValueOnce(new Error('grounding unavailable'))
        .mockRejectedValueOnce(new Error('grounding unavailable'))
        // Fallback call succeeds
        .mockResolvedValueOnce({
          response: {
            text: () => `
## Executive Summary
- Finding 1

## Detailed Findings
Analysis without grounding

## Recommendations for Glass Box Solutions
- Recommendation 1
          `,
            candidates: []
          }
        });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.error).toBeNull();
      expect(result.grounding_enabled).toBe(false);
      expect(result.fallback_used).toBe(true);
      expect(result.findings).toContain('Analysis without grounding');
    });

    it('should return error result when API key is missing', async () => {
      const configWithoutKey = {
        intelligence: {
          gemini: {
            model: 'gemini-2.0-flash-exp'
            // No apiKey
          }
        }
      };

      // Clear environment variable
      delete process.env.GOOGLE_AI_API_KEY;

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, configWithoutKey);

      expect(result.error).toBe('Gemini API key not configured');
      expect(result.executive_summary.length).toBe(0);
      expect(result.sources.length).toBe(0);
    });

    it('should return error result when both grounding and fallback fail', async () => {
      // Both calls fail
      mockGenerateContent.mockRejectedValue(
        new Error('API quota exceeded')
      );

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.error).toContain('API quota exceeded');
      expect(result.executive_summary.length).toBe(0);
      expect(result.fallback_used).toBe(false);
    });

    it('should handle empty Gemini response', async () => {
      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => '',
          candidates: []
        }
      });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.error).toContain('empty response');
    });
  });

  describe('research (custom topics)', () => {
    it('should research custom topic query', async () => {
      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => `
## Executive Summary
- Custom finding

## Detailed Findings
Custom analysis

## Recommendations for Glass Box Solutions
- Custom recommendation
          `,
          candidates: []
        }
      });

      const date = new Date('2026-03-13');
      const result = await research('Custom topic not in RESEARCH_TOPICS', date, mockConfig);

      expect(result.topic).toBe('Custom topic not in RESEARCH_TOPICS');
      expect(result.query).toBe('Custom topic not in RESEARCH_TOPICS');
      expect(result.executive_summary.length).toBeGreaterThan(0);
    });

    it('should use predefined config for known topics', async () => {
      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => 'Response',
          candidates: []
        }
      });

      const date = new Date('2026-03-13');
      const result = await research('compliance-standards', date, mockConfig);

      expect(result.query).toBe(RESEARCH_TOPICS['compliance-standards'].query);
      expect(result.query).toContain('HIPAA');
    });
  });

  describe('research (source extraction)', () => {
    it('should extract sources from both grounding and markdown', async () => {
      const mockResponse = {
        text: () => `
## Executive Summary
- Finding

## Detailed Findings
Content with [Inline Link](https://inline.example.com)

## Sources
- [Manual Source](https://manual.example.com)
        `,
        candidates: [{
          groundingMetadata: {
            groundingChunks: [{
              web: {
                title: 'Grounded Source',
                uri: 'https://grounded.example.com'
              }
            }]
          }
        }]
      };

      mockGenerateContent.mockResolvedValue({
        response: mockResponse
      });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.sources.length).toBeGreaterThan(0);

      // Should contain grounded source
      const groundedSource = result.sources.find(s => s.url === 'https://grounded.example.com');
      expect(groundedSource).toBeDefined();
      expect(groundedSource.title).toBe('Grounded Source');
    });

    it('should deduplicate sources from multiple extraction methods', async () => {
      const mockResponse = {
        text: () => `
[Same Source](https://same.example.com)
[Same Source Again](https://same.example.com)
        `,
        candidates: [{
          groundingMetadata: {
            groundingChunks: [{
              web: {
                title: 'Same Source From Grounding',
                uri: 'https://same.example.com'
              }
            }]
          }
        }]
      };

      mockGenerateContent.mockResolvedValue({
        response: mockResponse
      });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      // Should only have one entry for the URL
      const sameSources = result.sources.filter(s => s.url === 'https://same.example.com');
      expect(sameSources.length).toBe(1);
    });
  });

  describe('research (error handling)', () => {
    it('should retry on transient Gemini errors', async () => {
      // First call fails, second succeeds
      mockGenerateContent
        .mockRejectedValueOnce(new Error('Transient error'))
        .mockResolvedValueOnce({
          response: {
            text: () => 'Response after retry',
            candidates: []
          }
        });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.error).toBeNull();
      expect(result.findings).toContain('Response after retry');
    });

    it('should handle missing grounding metadata gracefully', async () => {
      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => `
## Executive Summary
- Finding

## Detailed Findings
Analysis
          `,
          candidates: [] // No grounding metadata
        }
      });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, mockConfig);

      expect(result.error).toBeNull();
      expect(result.sources.length).toBe(0); // No sources without metadata
    });
  });

  describe('research (configuration overrides)', () => {
    it('should use config temperature', async () => {
      const customConfig = {
        intelligence: {
          gemini: {
            apiKey: 'test-key',
            model: 'gemini-2.0-flash-exp',
            temperature: 0.7, // Custom temperature
            max_output_tokens: 8192
          }
        }
      };

      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => 'Response',
          candidates: []
        }
      });

      const date = new Date('2026-03-13');
      await research('documentation-standards', date, customConfig);

      expect(mockGenAI.getGenerativeModel).toHaveBeenCalledWith(
        expect.objectContaining({
          generationConfig: expect.objectContaining({
            temperature: 0.7
          })
        })
      );
    });

    it('should use config model', async () => {
      const customConfig = {
        intelligence: {
          gemini: {
            apiKey: 'test-key',
            model: 'gemini-1.5-pro', // Different model
            temperature: 0.4,
            max_output_tokens: 8192
          }
        }
      };

      mockGenerateContent.mockResolvedValue({
        response: {
          text: () => 'Response',
          candidates: []
        }
      });

      const date = new Date('2026-03-13');
      const result = await research('documentation-standards', date, customConfig);

      expect(mockGenAI.getGenerativeModel).toHaveBeenCalledWith(
        expect.objectContaining({
          model: 'gemini-1.5-pro'
        })
      );
      expect(result.model_used).toBe('gemini-1.5-pro');
    });
  });
});
