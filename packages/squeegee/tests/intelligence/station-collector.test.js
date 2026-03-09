/**
 * Station Collector Tests
 *
 * Tests for GCS-based station activity collection module.
 * Uses mocked @google-cloud/storage client.
 *
 * @file station-collector.test.js
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const {
  collect,
  listAvailableDates,
  collectBatch,
  sanitizeCommand,
  sanitizePath,
  processSessions,
  calculateSummary,
  downloadAndParse
} = require('../../intelligence/station-collector');
const { GCSStorageError } = require('../../intelligence/utils');

// Mock @google-cloud/storage
jest.mock('@google-cloud/storage', () => {
  const mockDownload = jest.fn();
  const mockExists = jest.fn();
  const mockGetFiles = jest.fn();

  const mockFile = jest.fn(() => ({
    download: mockDownload,
    exists: mockExists
  }));

  const mockBucket = jest.fn(() => ({
    file: mockFile,
    getFiles: mockGetFiles
  }));

  const mockStorage = jest.fn(() => ({
    bucket: mockBucket
  }));

  return {
    Storage: mockStorage,
    __mocks__: {
      mockDownload,
      mockExists,
      mockGetFiles,
      mockFile,
      mockBucket,
      mockStorage
    }
  };
});

// Get mocks for setup
const { __mocks__: mocks } = require('@google-cloud/storage');

describe('station-collector', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('sanitizeCommand()', () => {
    it('should redact --token arguments', () => {
      expect(sanitizeCommand('git push --token=abc123')).toBe('git push --token=***');
      expect(sanitizeCommand('git push --token abc123')).toBe('git push --token=***');
    });

    it('should redact Bearer tokens', () => {
      expect(sanitizeCommand('curl -H "Authorization: Bearer eyJhbGciOiJI..."'))
        .toBe('curl -H "Authorization: Bearer ***"');
    });

    it('should redact GitHub PATs', () => {
      expect(sanitizeCommand('GITHUB_TOKEN=ghp_abcdef123456'))
        .toBe('GITHUB_TOKEN=ghp_***');
    });

    it('should redact multiple sensitive values', () => {
      const input = 'cmd --token=secret1 --password=secret2 --api-key=key123';
      const result = sanitizeCommand(input);
      expect(result).toBe('cmd --token=*** --password=*** --api-key=***');
    });

    it('should handle null/empty input', () => {
      expect(sanitizeCommand(null)).toBe('');
      expect(sanitizeCommand('')).toBe('');
      expect(sanitizeCommand(undefined)).toBe('');
    });
  });

  describe('sanitizePath()', () => {
    it('should redact paths containing /secrets/', () => {
      expect(sanitizePath('/home/user/secrets/api-key.json')).toBe('[REDACTED]');
    });

    it('should redact paths containing .env', () => {
      expect(sanitizePath('/project/.env')).toBe('[REDACTED]');
      expect(sanitizePath('/project/.env.local')).toBe('[REDACTED]');
    });

    it('should redact paths containing /credentials/', () => {
      expect(sanitizePath('/etc/credentials/service-account.json')).toBe('[REDACTED]');
    });

    it('should pass through normal paths', () => {
      expect(sanitizePath('/home/user/project/src/main.js')).toBe('/home/user/project/src/main.js');
    });

    it('should handle null/empty input', () => {
      expect(sanitizePath(null)).toBe('');
      expect(sanitizePath('')).toBe('');
    });
  });

  describe('processSessions()', () => {
    it('should process valid session data', () => {
      const sessions = [
        {
          type: 'claude-code',
          project: '/home/user/my-project',
          start: '2026-03-03T09:00:00Z',
          end: '2026-03-03T10:30:00Z',
          commands: 45,
          files_edited: 12
        }
      ];

      const result = processSessions(sessions);

      expect(result).toHaveLength(1);
      expect(result[0].type).toBe('claude-code');
      expect(result[0].duration_minutes).toBe(90);
      expect(result[0].commands).toBe(45);
      expect(result[0].files_edited).toBe(12);
    });

    it('should sanitize project paths', () => {
      const sessions = [
        {
          type: 'vscode',
          project: '/home/user/secrets/internal',
          start: '2026-03-03T09:00:00Z',
          end: '2026-03-03T10:00:00Z'
        }
      ];

      const result = processSessions(sessions);
      expect(result[0].project).toBe('[REDACTED]');
    });

    it('should handle sessions without end time (ongoing)', () => {
      const sessions = [
        {
          type: 'cursor',
          project: '/home/user/project',
          start: new Date(Date.now() - 30 * 60 * 1000).toISOString(), // 30 min ago
          end: null
        }
      ];

      const result = processSessions(sessions);
      expect(result[0].end).toBeNull();
      expect(result[0].duration_minutes).toBeGreaterThanOrEqual(29);
      expect(result[0].duration_minutes).toBeLessThanOrEqual(31);
    });

    it('should include optional agent/model info', () => {
      const sessions = [
        {
          type: 'claude-code',
          project: '/project',
          start: '2026-03-03T09:00:00Z',
          end: '2026-03-03T10:00:00Z',
          agent: 'opus-4.5',
          model: 'claude-opus-4-5-20251101'
        }
      ];

      const result = processSessions(sessions);
      expect(result[0].agent).toBe('opus-4.5');
      expect(result[0].model).toBe('claude-opus-4-5-20251101');
    });

    it('should handle missing fields gracefully', () => {
      const sessions = [
        {
          start: '2026-03-03T09:00:00Z',
          end: '2026-03-03T10:00:00Z'
        }
      ];

      const result = processSessions(sessions);
      expect(result[0].type).toBe('unknown');
      expect(result[0].project).toBe('');
      expect(result[0].commands).toBe(0);
      expect(result[0].files_edited).toBe(0);
    });

    it('should handle non-array input', () => {
      expect(processSessions(null)).toEqual([]);
      expect(processSessions(undefined)).toEqual([]);
      expect(processSessions('invalid')).toEqual([]);
      expect(processSessions({})).toEqual([]);
    });

    it('should guard against negative durations', () => {
      const sessions = [
        {
          type: 'vscode',
          project: '/project',
          start: '2026-03-03T10:00:00Z',
          end: '2026-03-03T09:00:00Z' // End before start (data error)
        }
      ];

      const result = processSessions(sessions);
      expect(result[0].duration_minutes).toBe(0); // Should be 0, not negative
    });
  });

  describe('calculateSummary()', () => {
    it('should calculate correct totals', () => {
      const sessions = [
        { type: 'claude-code', project: '/project-a', duration_minutes: 60, commands: 30, files_edited: 10 },
        { type: 'cursor', project: '/project-b', duration_minutes: 90, commands: 20, files_edited: 5 },
        { type: 'claude-code', project: '/project-a', duration_minutes: 30, commands: 15, files_edited: 3 }
      ];

      const summary = calculateSummary(sessions);

      expect(summary.total_sessions).toBe(3);
      expect(summary.active_hours).toBe(3); // 180 min = 3h
      expect(summary.total_commands).toBe(65);
      expect(summary.total_files_edited).toBe(18);
    });

    it('should extract unique projects', () => {
      const sessions = [
        { type: 'claude-code', project: '/home/user/project-a', duration_minutes: 60 },
        { type: 'cursor', project: '/home/user/project-b', duration_minutes: 30 },
        { type: 'vscode', project: '/home/user/project-a', duration_minutes: 45 }
      ];

      const summary = calculateSummary(sessions);
      expect(summary.projects_touched).toEqual(['project-a', 'project-b']);
    });

    it('should count sessions by tool type', () => {
      const sessions = [
        { type: 'claude-code', project: '/p1', duration_minutes: 60 },
        { type: 'claude-code', project: '/p2', duration_minutes: 30 },
        { type: 'cursor', project: '/p1', duration_minutes: 45 },
        { type: 'vscode', project: '/p3', duration_minutes: 20 }
      ];

      const summary = calculateSummary(sessions);
      expect(summary.by_tool).toEqual({
        'claude-code': 2,
        'cursor': 1,
        'vscode': 1
      });
    });

    it('should exclude redacted projects from projects_touched', () => {
      const sessions = [
        { type: 'claude-code', project: '/project-a', duration_minutes: 60 },
        { type: 'cursor', project: '[REDACTED]', duration_minutes: 30 }
      ];

      const summary = calculateSummary(sessions);
      expect(summary.projects_touched).toEqual(['project-a']);
    });

    it('should handle empty sessions array', () => {
      const summary = calculateSummary([]);
      expect(summary.total_sessions).toBe(0);
      expect(summary.active_hours).toBe(0);
      expect(summary.projects_touched).toEqual([]);
      expect(summary.by_tool).toEqual({});
    });

    it('should round active_hours to 1 decimal', () => {
      const sessions = [
        { type: 'claude-code', project: '/p1', duration_minutes: 33 } // 0.55h
      ];

      const summary = calculateSummary(sessions);
      expect(summary.active_hours).toBe(0.6); // Rounded
    });
  });

  describe('collect()', () => {
    const config = {
      storage: {
        gcs_bucket: 'test-bucket',
        gcs_prefix: 'station/'
      }
    };

    const sampleLogData = {
      sessions: [
        {
          type: 'claude-code',
          project: '/home/user/my-project',
          start: '2026-03-03T09:00:00Z',
          end: '2026-03-03T10:30:00Z',
          commands: 45,
          files_edited: 12
        },
        {
          type: 'cursor',
          project: '/home/user/another-project',
          start: '2026-03-03T11:00:00Z',
          end: '2026-03-03T12:00:00Z',
          commands: 20,
          files_edited: 5
        }
      ]
    };

    it('should collect station activity from GCS', async () => {
      mocks.mockExists.mockResolvedValue([true]);
      mocks.mockDownload.mockResolvedValue([Buffer.from(JSON.stringify(sampleLogData))]);

      const result = await collect('2026-03-03', config);

      expect(result.date).toBe('2026-03-03');
      expect(result.sessions).toHaveLength(2);
      expect(result.summary.total_sessions).toBe(2);
      expect(result.summary.active_hours).toBe(2.5);
      expect(result.source.found).toBe(true);
      expect(result.source.bucket).toBe('test-bucket');
      expect(result.source.path).toBe('station/2026-03-03.json');
    });

    it('should accept Date object as input', async () => {
      mocks.mockExists.mockResolvedValue([true]);
      mocks.mockDownload.mockResolvedValue([Buffer.from(JSON.stringify(sampleLogData))]);

      const result = await collect(new Date('2026-03-03'), config);

      expect(result.date).toBe('2026-03-03');
      expect(result.sessions).toHaveLength(2);
    });

    it('should return empty structure when file not found', async () => {
      mocks.mockExists.mockResolvedValue([false]);

      const result = await collect('2026-03-03', config);

      expect(result.date).toBe('2026-03-03');
      expect(result.sessions).toEqual([]);
      expect(result.summary.total_sessions).toBe(0);
      expect(result.source.found).toBe(false);
    });

    it('should use default bucket/prefix when not configured', async () => {
      mocks.mockExists.mockResolvedValue([false]);

      await collect('2026-03-03', {});

      // Should use defaults
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('gs://glassbox-dev-activity/station/2026-03-03.json')
      );
    });

    it('should handle malformed JSON gracefully', async () => {
      mocks.mockExists.mockResolvedValue([true]);
      mocks.mockDownload.mockResolvedValue([Buffer.from('{ invalid json }')]);

      const result = await collect('2026-03-03', config);

      expect(result.sessions).toEqual([]);
      expect(result.source.found).toBe(false);
      expect(console.warn).toHaveBeenCalled();
    });

    it('should handle permission denied error', async () => {
      mocks.mockExists.mockResolvedValue([true]);
      const error = new Error('Permission denied');
      error.code = 403;
      mocks.mockDownload.mockRejectedValue(error);

      const result = await collect('2026-03-03', config);

      // Should return empty (graceful degradation via safeExecute)
      expect(result.sessions).toEqual([]);
      expect(result.source.found).toBe(false);
    });

    it('should handle empty sessions array in log file', async () => {
      mocks.mockExists.mockResolvedValue([true]);
      mocks.mockDownload.mockResolvedValue([Buffer.from(JSON.stringify({ sessions: [] }))]);

      const result = await collect('2026-03-03', config);

      expect(result.sessions).toEqual([]);
      expect(result.summary.total_sessions).toBe(0);
      expect(result.source.found).toBe(true);
    });

    it('should log progress messages', async () => {
      mocks.mockExists.mockResolvedValue([true]);
      mocks.mockDownload.mockResolvedValue([Buffer.from(JSON.stringify(sampleLogData))]);

      await collect('2026-03-03', config);

      expect(console.log).toHaveBeenCalledWith(expect.stringContaining('Collecting station activity'));
      expect(console.log).toHaveBeenCalledWith(expect.stringContaining('Station activity collected'));
    });
  });

  describe('listAvailableDates()', () => {
    const config = {
      storage: {
        gcs_bucket: 'test-bucket',
        gcs_prefix: 'station/'
      }
    };

    it('should list available dates from GCS', async () => {
      mocks.mockGetFiles.mockResolvedValue([
        [
          { name: 'station/2026-03-01.json' },
          { name: 'station/2026-03-02.json' },
          { name: 'station/2026-03-03.json' }
        ]
      ]);

      const dates = await listAvailableDates(config);

      expect(dates).toEqual(['2026-03-03', '2026-03-02', '2026-03-01']); // Most recent first
    });

    it('should filter by date range', async () => {
      mocks.mockGetFiles.mockResolvedValue([
        [
          { name: 'station/2026-02-28.json' },
          { name: 'station/2026-03-01.json' },
          { name: 'station/2026-03-02.json' },
          { name: 'station/2026-03-03.json' }
        ]
      ]);

      const dates = await listAvailableDates(config, {
        startDate: '2026-03-01',
        endDate: '2026-03-02'
      });

      expect(dates).toEqual(['2026-03-02', '2026-03-01']);
    });

    it('should ignore non-matching filenames', async () => {
      mocks.mockGetFiles.mockResolvedValue([
        [
          { name: 'station/2026-03-01.json' },
          { name: 'station/index.json' },
          { name: 'station/backup-2026-03-01.json' }
        ]
      ]);

      const dates = await listAvailableDates(config);

      expect(dates).toEqual(['2026-03-01']);
    });

    it('should return empty array on error', async () => {
      mocks.mockGetFiles.mockRejectedValue(new Error('Network error'));

      const dates = await listAvailableDates(config);

      expect(dates).toEqual([]);
      expect(console.error).toHaveBeenCalled();
    });
  });

  describe('collectBatch()', () => {
    const config = {
      storage: {
        gcs_bucket: 'test-bucket',
        gcs_prefix: 'station/'
      }
    };

    it('should collect multiple dates', async () => {
      const day1Data = {
        sessions: [
          { type: 'claude-code', project: '/p1', start: '2026-03-01T09:00:00Z', end: '2026-03-01T10:00:00Z' }
        ]
      };
      const day2Data = {
        sessions: [
          { type: 'cursor', project: '/p2', start: '2026-03-02T09:00:00Z', end: '2026-03-02T11:00:00Z' }
        ]
      };

      // First date: exists
      mocks.mockExists.mockResolvedValueOnce([true]);
      mocks.mockDownload.mockResolvedValueOnce([Buffer.from(JSON.stringify(day1Data))]);

      // Second date: exists
      mocks.mockExists.mockResolvedValueOnce([true]);
      mocks.mockDownload.mockResolvedValueOnce([Buffer.from(JSON.stringify(day2Data))]);

      const result = await collectBatch(['2026-03-01', '2026-03-02'], config);

      expect(result.dates_requested).toBe(2);
      expect(result.dates_found).toBe(2);
      expect(result.dates_missing).toEqual([]);
      expect(result.sessions).toHaveLength(2);
      expect(result.summary.total_sessions).toBe(2);
      expect(result.by_date['2026-03-01'].sessions).toBe(1);
      expect(result.by_date['2026-03-02'].sessions).toBe(1);
    });

    it('should track missing dates', async () => {
      const day1Data = {
        sessions: [
          { type: 'claude-code', project: '/p1', start: '2026-03-01T09:00:00Z', end: '2026-03-01T10:00:00Z' }
        ]
      };

      // First date: exists
      mocks.mockExists.mockResolvedValueOnce([true]);
      mocks.mockDownload.mockResolvedValueOnce([Buffer.from(JSON.stringify(day1Data))]);

      // Second date: not found
      mocks.mockExists.mockResolvedValueOnce([false]);

      const result = await collectBatch(['2026-03-01', '2026-03-02'], config);

      expect(result.dates_found).toBe(1);
      expect(result.dates_missing).toEqual(['2026-03-02']);
    });
  });

  describe('GCSStorageError', () => {
    it('should create error with correct properties', () => {
      const error = new GCSStorageError('Test error', 403, 'my-bucket');

      expect(error.name).toBe('GCSStorageError');
      expect(error.message).toBe('Test error');
      expect(error.code).toBe(403);
      expect(error.bucket).toBe('my-bucket');
    });

    it('should mark 5xx errors as recoverable', () => {
      const error500 = new GCSStorageError('Server error', 500, 'bucket');
      const error503 = new GCSStorageError('Unavailable', 503, 'bucket');

      expect(error500.recoverable).toBe(true);
      expect(error503.recoverable).toBe(true);
    });

    it('should mark 429 as recoverable', () => {
      const error = new GCSStorageError('Rate limited', 429, 'bucket');
      expect(error.recoverable).toBe(true);
    });

    it('should mark 403/404 as not recoverable', () => {
      const error403 = new GCSStorageError('Forbidden', 403, 'bucket');
      const error404 = new GCSStorageError('Not found', 404, 'bucket');

      expect(error403.recoverable).toBe(false);
      expect(error404.recoverable).toBe(false);
    });
  });
});
