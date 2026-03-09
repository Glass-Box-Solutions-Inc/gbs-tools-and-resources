/**
 * Unit tests for GCP Cloud Logging collector
 *
 * Tests cover:
 * - Happy path (multiple projects with deployments and errors)
 * - Partial failure (one project fails, others succeed)
 * - Empty results (no logs in timeframe)
 * - Pagination handling
 * - Filter accuracy
 * - Error handling and graceful degradation
 *
 * @file gcp-collector.test.js
 */

const { collect } = require('../../intelligence/gcp-collector');
const { Logging } = require('@google-cloud/logging');

// Mock @google-cloud/logging
jest.mock('@google-cloud/logging');

describe('GCP Collector', () => {
  let mockLogging;
  let mockGetEntries;

  beforeEach(() => {
    // Reset mocks before each test
    jest.clearAllMocks();

    // Create mock getEntries function
    mockGetEntries = jest.fn();

    // Mock Logging constructor
    mockLogging = {
      getEntries: mockGetEntries
    };

    Logging.mockImplementation(() => mockLogging);
  });

  describe('Happy Path - Multiple Projects', () => {
    it('should collect deployments and errors from multiple projects', async () => {
      const config = {
        gcp_projects: ['project-a', 'project-b']
      };

      // Mock deployment logs for project-a
      mockGetEntries
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: {
                labels: {
                  service_name: 'adjudica-ai-app',
                  revision_name: 'adjudica-ai-app-00042'
                }
              },
              timestamp: '2026-03-03T10:30:00Z'
            },
            data: {
              response: {
                status: {
                  conditions: [{ status: 'True' }]
                }
              }
            }
          }
        ]])
        // Mock error logs for project-a
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: {
                labels: {
                  service_name: 'adjudica-ai-app'
                }
              },
              severity: 'ERROR',
              timestamp: '2026-03-03T11:00:00Z'
            },
            data: {
              message: 'Database connection timeout'
            }
          }
        ]])
        // Mock deployment logs for project-b (empty)
        .mockResolvedValueOnce([[]])
        // Mock error logs for project-b
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: {
                labels: {
                  service_name: 'command-center'
                }
              },
              severity: 'CRITICAL',
              timestamp: '2026-03-03T12:00:00Z'
            },
            data: 'Authentication service unreachable'
          }
        ]]);

      const result = await collect('2026-03-03', config);

      expect(result).toEqual({
        deployments: [
          {
            project: 'project-a',
            service: 'adjudica-ai-app',
            revision: 'adjudica-ai-app-00042',
            status: 'success',
            timestamp: '2026-03-03T10:30:00Z'
          }
        ],
        errors: [
          {
            project: 'project-a',
            service: 'adjudica-ai-app',
            severity: 'ERROR',
            message: 'Database connection timeout',
            timestamp: '2026-03-03T11:00:00Z'
          },
          {
            project: 'project-b',
            service: 'command-center',
            severity: 'CRITICAL',
            message: 'Authentication service unreachable',
            timestamp: '2026-03-03T12:00:00Z'
          }
        ],
        summary: {
          total_deployments: 1,
          total_errors: 2,
          projects_monitored: 2
        }
      });

      // Verify Logging client was created for each project
      expect(Logging).toHaveBeenCalledTimes(2);
      expect(Logging).toHaveBeenCalledWith({ projectId: 'project-a' });
      expect(Logging).toHaveBeenCalledWith({ projectId: 'project-b' });

      // Verify getEntries was called with correct filters
      expect(mockGetEntries).toHaveBeenCalledTimes(4); // 2 projects × 2 query types
    });

    it('should accept Date object as input', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries
        .mockResolvedValueOnce([[]])
        .mockResolvedValueOnce([[]]);

      const date = new Date('2026-03-03');
      const result = await collect(date, config);

      expect(result.summary.projects_monitored).toBe(1);
    });
  });

  describe('Partial Failure - One Project Fails', () => {
    it('should continue processing other projects when one fails', async () => {
      const config = {
        gcp_projects: ['project-a', 'project-b', 'project-c']
      };

      // Override Logging constructor: project-b throws at construction time
      // so the error propagates out of collectProject to collect's catch block
      Logging.mockImplementation((options) => {
        if (options.projectId === 'project-b') {
          const err = new Error('Caller does not have required permission');
          err.code = 'PERMISSION_DENIED';
          throw err;
        }
        return { getEntries: mockGetEntries };
      });

      // project-a: deployment + empty errors
      mockGetEntries
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: { labels: { service_name: 'service-a' } },
              timestamp: '2026-03-03T10:00:00Z'
            },
            data: { response: { status: { conditions: [{ status: 'True' }] } } }
          }
        ]])
        .mockResolvedValueOnce([[]]);

      // project-c: empty deployments + error
      mockGetEntries
        .mockResolvedValueOnce([[]])
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: { labels: { service_name: 'service-c' } },
              severity: 'ERROR',
              timestamp: '2026-03-03T11:00:00Z'
            },
            data: { message: 'Test error' }
          }
        ]]);

      const result = await collect('2026-03-03', config);

      expect(result).toEqual({
        deployments: [
          {
            project: 'project-a',
            service: 'service-a',
            revision: 'unknown',
            status: 'success',
            timestamp: '2026-03-03T10:00:00Z'
          }
        ],
        errors: [
          {
            project: 'project-c',
            service: 'service-c',
            severity: 'ERROR',
            message: 'Test error',
            timestamp: '2026-03-03T11:00:00Z'
          }
        ],
        summary: {
          total_deployments: 1,
          total_errors: 1,
          projects_monitored: 2
        },
        projects_failed: [
          {
            project: 'project-b',
            error: 'PERMISSION_DENIED'
          }
        ]
      });
    });

    it('should handle quota exceeded errors gracefully', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      // Throw at Logging construction level so error reaches collect's catch
      Logging.mockImplementation(() => {
        const err = new Error('Quota exceeded for quota metric');
        err.code = 'QUOTA_EXCEEDED';
        throw err;
      });

      const result = await collect('2026-03-03', config);

      expect(result.projects_failed).toEqual([
        {
          project: 'project-a',
          error: 'QUOTA_EXCEEDED'
        }
      ]);
      expect(result.summary.projects_monitored).toBe(0);
    });
  });

  describe('Empty Results', () => {
    it('should return empty arrays when no logs in timeframe', async () => {
      const config = {
        gcp_projects: ['project-a', 'project-b']
      };

      // All queries return empty results
      mockGetEntries
        .mockResolvedValue([[]]); // Will be used for all calls

      const result = await collect('2026-03-03', config);

      expect(result).toEqual({
        deployments: [],
        errors: [],
        summary: {
          total_deployments: 0,
          total_errors: 0,
          projects_monitored: 2
        }
      });
    });
  });

  describe('Filter Accuracy', () => {
    it('should construct correct deployment filter', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries.mockResolvedValue([[]]);

      await collect('2026-03-03', config);

      // Check first call (deployments)
      const firstCall = mockGetEntries.mock.calls[0][0];
      expect(firstCall.filter).toContain('resource.type="cloud_run_revision"');
      expect(firstCall.filter).toContain('protoPayload.methodName');
      expect(firstCall.filter).toContain('CreateRevision');
      expect(firstCall.filter).toContain('timestamp>="2026-03-03T00:00:00.000Z"');
      expect(firstCall.filter).toContain('timestamp<"2026-03-03T23:59:59.000Z"');
    });

    it('should construct correct error filter', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries.mockResolvedValue([[]]);

      await collect('2026-03-03', config);

      // Check second call (errors)
      const secondCall = mockGetEntries.mock.calls[1][0];
      expect(secondCall.filter).toContain('resource.type="cloud_run_revision"');
      expect(secondCall.filter).toContain('severity>="ERROR"');
      expect(secondCall.filter).toContain('timestamp>="2026-03-03T00:00:00.000Z"');
      expect(secondCall.filter).toContain('timestamp<"2026-03-03T23:59:59.000Z"');
    });
  });

  describe('Pagination Handling', () => {
    it('should handle paginated results automatically', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      // Mock large result set (Cloud Logging SDK handles pagination internally)
      const manyDeployments = Array.from({ length: 150 }, (_, i) => ({
        metadata: {
          resource: {
            labels: {
              service_name: `service-${i}`,
              revision_name: `revision-${i}`
            }
          },
          timestamp: '2026-03-03T10:00:00Z'
        },
        data: { response: { status: { conditions: [{ status: 'True' }] } } }
      }));

      mockGetEntries
        .mockResolvedValueOnce([manyDeployments])
        .mockResolvedValueOnce([[]]);

      const result = await collect('2026-03-03', config);

      expect(result.deployments).toHaveLength(150);
      expect(result.summary.total_deployments).toBe(150);

      // Verify autoPaginate was enabled
      expect(mockGetEntries.mock.calls[0][0]).toMatchObject({
        pageSize: 1000,
        autoPaginate: true
      });
    });
  });

  describe('Edge Cases', () => {
    it('should handle missing metadata fields gracefully', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries
        .mockResolvedValueOnce([[
          {
            // Minimal metadata
            metadata: {},
            data: {}
          }
        ]])
        .mockResolvedValueOnce([[]]);

      const result = await collect('2026-03-03', config);

      expect(result.deployments).toHaveLength(1);
      expect(result.deployments[0]).toMatchObject({
        project: 'project-a',
        service: 'unknown',
        revision: 'unknown',
        status: 'failed'
      });
    });

    it('should handle error logs with string data', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries
        .mockResolvedValueOnce([[]])
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: { labels: { service_name: 'test-service' } },
              severity: 'ERROR',
              timestamp: '2026-03-03T10:00:00Z'
            },
            data: 'Plain string error message'
          }
        ]]);

      const result = await collect('2026-03-03', config);

      expect(result.errors).toEqual([
        {
          project: 'project-a',
          service: 'test-service',
          severity: 'ERROR',
          message: 'Plain string error message',
          timestamp: '2026-03-03T10:00:00Z'
        }
      ]);
    });

    it('should truncate very long error messages', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      const longMessage = 'x'.repeat(500);

      mockGetEntries
        .mockResolvedValueOnce([[]])
        .mockResolvedValueOnce([[
          {
            metadata: {
              resource: { labels: { service_name: 'test-service' } },
              severity: 'ERROR',
              timestamp: '2026-03-03T10:00:00Z'
            },
            data: { nested: { deep: { message: longMessage } } }
          }
        ]]);

      const result = await collect('2026-03-03', config);

      expect(result.errors[0].message.length).toBeLessThanOrEqual(200);
    });

    it('should handle deployment status variations', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries
        .mockResolvedValueOnce([[
          // Failed deployment (no success condition)
          {
            metadata: {
              resource: { labels: { service_name: 'failed-service' } },
              timestamp: '2026-03-03T10:00:00Z'
            },
            data: {
              status: { code: 13 } // INTERNAL error
            }
          },
          // Success via status code
          {
            metadata: {
              resource: { labels: { service_name: 'success-service' } },
              timestamp: '2026-03-03T11:00:00Z'
            },
            data: {
              status: { code: 0 } // OK
            }
          }
        ]])
        .mockResolvedValueOnce([[]]);

      const result = await collect('2026-03-03', config);

      expect(result.deployments).toHaveLength(2);
      expect(result.deployments[0].status).toBe('failed');
      expect(result.deployments[1].status).toBe('success');
    });
  });

  describe('Date Handling', () => {
    it('should correctly convert date strings to UTC timestamps', async () => {
      const config = {
        gcp_projects: ['project-a']
      };

      mockGetEntries.mockResolvedValue([[]]);

      await collect('2026-03-03', config);

      const deploymentFilter = mockGetEntries.mock.calls[0][0].filter;
      expect(deploymentFilter).toContain('timestamp>="2026-03-03T00:00:00.000Z"');
      expect(deploymentFilter).toContain('timestamp<"2026-03-03T23:59:59.000Z"');
    });
  });

  describe('Console Output', () => {
    let consoleLog;
    let consoleError;

    beforeEach(() => {
      consoleLog = jest.spyOn(console, 'log').mockImplementation();
      consoleError = jest.spyOn(console, 'error').mockImplementation();
    });

    afterEach(() => {
      consoleLog.mockRestore();
      consoleError.mockRestore();
    });

    it('should log collection start and completion', async () => {
      const config = {
        gcp_projects: ['project-a', 'project-b']
      };

      mockGetEntries.mockResolvedValue([[]]);

      await collect('2026-03-03', config);

      expect(consoleLog).toHaveBeenCalledWith(
        expect.stringContaining('Starting GCP collection for 2026-03-03 across 2 projects')
      );

      expect(consoleLog).toHaveBeenCalledWith(
        expect.stringContaining('GCP collection complete'),
        expect.objectContaining({
          projects_succeeded: 2,
          projects_failed: 0
        })
      );
    });

    it('should log errors for failed projects', async () => {
      const config = {
        gcp_projects: ['project-a', 'project-b']
      };

      // project-a works fine
      mockGetEntries
        .mockResolvedValueOnce([[]])
        .mockResolvedValueOnce([[]]);

      // project-b: throw at Logging construction so error reaches collect's catch
      Logging.mockImplementation((options) => {
        if (options.projectId === 'project-b') {
          const err = new Error('Access denied');
          err.code = 'PERMISSION_DENIED';
          throw err;
        }
        return { getEntries: mockGetEntries };
      });

      await collect('2026-03-03', config);

      expect(consoleError).toHaveBeenCalledWith(
        expect.stringContaining('Failed to collect logs for project project-b'),
        expect.any(String)
      );
    });
  });
});
