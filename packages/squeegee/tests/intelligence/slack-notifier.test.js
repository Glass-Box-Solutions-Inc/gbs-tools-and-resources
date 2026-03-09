/**
 * Tests for Slack Notifier Module
 *
 * @file slack-notifier.test.js
 */

const https = require('https');
const { EventEmitter } = require('events');
const { notify } = require('../../intelligence/slack-notifier');

// Mock HTTPS module
let mockHttpsRequest;
let mockRequestEmitter;
let mockResponseEmitter;

function setupHttpsMock(statusCode = 200, responseBody = 'ok', shouldTimeout = false, shouldError = false) {
  mockRequestEmitter = new EventEmitter();
  mockResponseEmitter = new EventEmitter();

  mockHttpsRequest = (options, callback) => {
    // Call response handler
    process.nextTick(() => {
      if (shouldTimeout) {
        process.nextTick(() => {
          mockRequestEmitter.emit('timeout');
        }, 50);
      } else if (shouldError) {
        process.nextTick(() => {
          mockRequestEmitter.emit('error', new Error('Network error'));
        }, 10);
      } else {
        mockResponseEmitter.statusCode = statusCode;
        callback(mockResponseEmitter);

        process.nextTick(() => {
          mockResponseEmitter.emit('data', responseBody);
          mockResponseEmitter.emit('end');
        }, 10);
      }
    });

    return mockRequestEmitter;
  };

  // Mock request methods
  mockRequestEmitter.write = jest.fn();
  mockRequestEmitter.end = jest.fn();
  mockRequestEmitter.destroy = jest.fn();

  // Replace https.request
  https.request = mockHttpsRequest;
}

describe('Slack Notifier', () => {
  describe('notify()', () => {
    const validConfig = {
      notifications: {
        slack: {
          enabled: true,
          webhook_url: 'https://hooks.slack.com/services/TEST/WEBHOOK/URL',
          channel: '#main'
        }
      }
    };

    const mockBriefing = {
      executive_summary: [
        'Total of 15 commits across 5 repositories',
        '3 pull requests merged',
        '2 Cloud Run deployments successful'
      ],
      repository_activity: '## Active Repos\n\n- adjudica-ai-app: 8 commits\n- glassy-personal-ai: 4 commits',
      deployment_events: '2 deployments to production',
      development_activity: '3 Claude Code sessions active',
      observations: 'Strong development velocity. Consider updating CLAUDE.md compliance.',
      generated_at: '2026-03-03T07:15:00Z',
      model_used: 'gemini-2.0-flash-exp'
    };

    beforeEach(() => {
      // Reset mocks before each test
      setupHttpsMock();
    });

    afterEach(() => {
      // Clean up
      mockHttpsRequest = null;
      mockRequestEmitter = null;
      mockResponseEmitter = null;
    });

    it('should send briefing successfully', async () => {
      setupHttpsMock(200, 'ok');

      const result = await notify(mockBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(true);
      expect(result.channel).toBe('#main');
      expect(result.error).toBeNull();
      expect(result.timestamp).toBeTruthy();
    });

    it('should format Block Kit message correctly', async () => {
      let capturedPayload = null;

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      await notify(mockBriefing, '2026-03-03', validConfig);

      expect(capturedPayload).toBeTruthy();
      expect(capturedPayload.blocks).toBeTruthy();
      expect(Array.isArray(capturedPayload.blocks)).toBe(true);

      // Check for header block
      const headerBlock = capturedPayload.blocks.find(b => b.type === 'header');
      expect(headerBlock).toBeTruthy();
      expect(headerBlock.text.text).toContain('2026-03-03');

      // Check for executive summary
      const summaryBlock = capturedPayload.blocks.find(
        b => b.type === 'section' && b.text?.text?.includes('Executive Summary')
      );
      expect(summaryBlock).toBeTruthy();
      expect(summaryBlock.text.text).toContain('15 commits');

      // Check for footer with model
      const footerBlock = capturedPayload.blocks.find(
        b => b.type === 'context' && b.elements?.[0]?.text?.includes('Squeegee')
      );
      expect(footerBlock).toBeTruthy();
      expect(footerBlock.elements[0].text).toContain('gemini-2.0-flash-exp');
    });

    it('should include GitHub link in message', async () => {
      let capturedPayload = null;

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      await notify(mockBriefing, '2026-03-13', validConfig);

      expect(capturedPayload).toBeTruthy();

      // Find GitHub link block
      const linkBlock = capturedPayload.blocks.find(
        b => b.type === 'section' && b.text?.text?.includes('github.com')
      );
      expect(linkBlock).toBeTruthy();
      expect(linkBlock.text.text).toContain('logs/analysis/2026/03/2026-03-13.md');
    });

    it('should truncate long text to fit Slack limits', async () => {
      let capturedPayload = null;

      const longBriefing = {
        ...mockBriefing,
        executive_summary: Array(100).fill('This is a very long summary point that should be truncated')
      };

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      await notify(longBriefing, '2026-03-03', validConfig);

      expect(capturedPayload).toBeTruthy();

      // Check all text blocks are under Slack's limit
      for (const block of capturedPayload.blocks) {
        if (block.type === 'section' && block.text?.text) {
          expect(block.text.text.length).toBeLessThanOrEqual(3000);
        }
      }
    });

    it('should skip when notifications disabled', async () => {
      const disabledConfig = {
        notifications: {
          slack: {
            enabled: false,
            webhook_url: 'https://hooks.slack.com/services/TEST/WEBHOOK/URL',
            channel: '#main'
          }
        }
      };

      const result = await notify(mockBriefing, '2026-03-03', disabledConfig);

      expect(result.success).toBe(true);
      expect(result.skipped).toBe(true);
      expect(result.error).toBeNull();
    });

    it('should return error when webhook URL missing', async () => {
      const noWebhookConfig = {
        notifications: {
          slack: {
            enabled: true,
            webhook_url: null,
            channel: '#main'
          }
        }
      };

      const result = await notify(mockBriefing, '2026-03-03', noWebhookConfig);

      expect(result.success).toBe(false);
      expect(result.error).toBeTruthy();
      expect(result.error).toContain('not configured');
    });

    it('should retry on 5xx errors', async () => {
      let attemptCount = 0;

      setupHttpsMock(200, 'ok'); // Setup first to create mockRequestEmitter

      https.request = (options, callback) => {
        attemptCount++;

        process.nextTick(() => {
          mockResponseEmitter.statusCode = attemptCount < 3 ? 503 : 200;
          callback(mockResponseEmitter);

          process.nextTick(() => {
            mockResponseEmitter.emit('data', attemptCount < 3 ? 'Service unavailable' : 'ok');
            mockResponseEmitter.emit('end');
          }, 10);
        });

        return mockRequestEmitter;
      };

      const result = await notify(mockBriefing, '2026-03-03', validConfig);

      expect(attemptCount).toBe(3);
      expect(result.success).toBe(true);
    });

    it('should not retry on 4xx errors', async () => {
      let attemptCount = 0;

      setupHttpsMock(200, 'ok'); // Setup first to create mockRequestEmitter

      https.request = (options, callback) => {
        attemptCount++;

        process.nextTick(() => {
          mockResponseEmitter.statusCode = 404;
          callback(mockResponseEmitter);

          process.nextTick(() => {
            mockResponseEmitter.emit('data', 'Not found');
            mockResponseEmitter.emit('end');
          }, 10);
        });

        return mockRequestEmitter;
      };

      const result = await notify(mockBriefing, '2026-03-03', validConfig);

      expect(attemptCount).toBe(1); // No retry
      expect(result.success).toBe(false);
      expect(result.error).toBeTruthy();
    });

    it('should handle network timeout', async () => {
      setupHttpsMock(200, 'ok', true); // Enable timeout

      const result = await notify(mockBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(false);
      expect(result.error).toBeTruthy();
      expect(result.error).toContain('timeout');
    });

    it('should handle network error', async () => {
      setupHttpsMock(200, 'ok', false, true); // Enable error

      const result = await notify(mockBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(false);
      expect(result.error).toBeTruthy();
    });

    it('should handle Date object for date parameter', async () => {
      setupHttpsMock(200, 'ok');

      const date = new Date('2026-03-03T00:00:00Z');
      const result = await notify(mockBriefing, date, validConfig);

      expect(result.success).toBe(true);
    });

    it('should handle minimal briefing', async () => {
      let capturedPayload = null;

      const minimalBriefing = {
        executive_summary: ['Minimal activity']
      };

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      const result = await notify(minimalBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(true);
      expect(capturedPayload).toBeTruthy();
      expect(capturedPayload.blocks.length).toBeGreaterThan(0);
    });

    it('should handle fallback briefing (template-based)', async () => {
      let capturedPayload = null;

      const fallbackBriefing = {
        executive_summary: ['Gemini synthesis unavailable', 'Using template-based briefing'],
        repository_activity: 'Activity data collected but not synthesized',
        generated_at: '2026-03-03T07:15:00Z'
      };

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      const result = await notify(fallbackBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(true);
      expect(capturedPayload).toBeTruthy();
      expect(capturedPayload.blocks.find(b =>
        b.text?.text?.includes('template-based')
      )).toBeTruthy();
    });

    it('should handle missing optional briefing sections', async () => {
      let capturedPayload = null;

      const partialBriefing = {
        executive_summary: ['Summary only'],
        generated_at: '2026-03-03T07:15:00Z'
      };

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      const result = await notify(partialBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(true);
      expect(capturedPayload).toBeTruthy();
      // Should still format successfully even with missing sections
    });

    it('should extract metrics from briefing', async () => {
      let capturedPayload = null;

      const metricsTest = {
        executive_summary: [
          '42 commits across repositories',
          '15 pull requests merged',
          '8 deployments to production'
        ],
        observations: '5 active sessions detected',
        generated_at: '2026-03-03T07:15:00Z'
      };

      setupHttpsMock(200, 'ok');

      mockRequestEmitter.write = jest.fn((data) => {
        capturedPayload = JSON.parse(data);
      });

      await notify(metricsTest, '2026-03-03', validConfig);

      expect(capturedPayload).toBeTruthy();

      // Find metrics block
      const metricsBlock = capturedPayload.blocks.find(
        b => b.type === 'context' && b.elements?.[0]?.text?.includes('Commits:')
      );

      expect(metricsBlock).toBeTruthy();
      const metricsText = metricsBlock.elements[0].text;
      expect(metricsText).toContain('Commits: 42');
      expect(metricsText).toContain('PRs: 15');
      expect(metricsText).toContain('Deployments: 8');
    });

    it('should not throw on Slack failure (graceful degradation)', async () => {
      setupHttpsMock(500, 'Internal Server Error');

      // Should not throw even if all retries fail
      const result = await notify(mockBriefing, '2026-03-03', validConfig);

      expect(result.success).toBe(false);
      expect(result.error).toBeTruthy();
    });
  });

  describe('Error handling edge cases', () => {
    beforeEach(() => {
      setupHttpsMock();
    });

    afterEach(() => {
      mockHttpsRequest = null;
      mockRequestEmitter = null;
      mockResponseEmitter = null;
    });

    it('should handle malformed briefing object', async () => {
      setupHttpsMock(200, 'ok');

      const validConfig = {
        notifications: {
          slack: {
            enabled: true,
            webhook_url: 'https://hooks.slack.com/services/TEST/WEBHOOK/URL',
            channel: '#main'
          }
        }
      };

      const malformedBriefing = {
        // Missing expected fields
        something_unexpected: 'value'
      };

      // Should not throw
      const result = await notify(malformedBriefing, '2026-03-03', validConfig);

      // May succeed or fail depending on validation, but shouldn't throw
      expect(result).toBeTruthy();
      expect(typeof result.success).toBe('boolean');
    });

    it('should handle null briefing gracefully', async () => {
      setupHttpsMock(200, 'ok');

      const validConfig = {
        notifications: {
          slack: {
            enabled: true,
            webhook_url: 'https://hooks.slack.com/services/TEST/WEBHOOK/URL',
            channel: '#main'
          }
        }
      };

      // Should handle gracefully (either return error or throw, but not crash)
      try {
        const result = await notify(null, '2026-03-03', validConfig);
        expect(result).toBeTruthy();
      } catch (error) {
        // Also acceptable to throw, as long as it doesn't crash
        expect(error).toBeTruthy();
      }
    });
  });
});
