/**
 * Unit tests for Station Activity Monitor
 *
 * @file station-monitor.test.js
 */

const assert = require('assert');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const {
  collect,
  sanitizeCommand,
  sanitizePath,
  processSessions,
  calculateSummary
} = require('../../intelligence/station-monitor');

// Test utilities
async function createTestLogDir() {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'station-test-'));
  return tmpDir;
}

async function writeTestLogFile(dir, date, data) {
  const dateStr = typeof date === 'string' ? date : date.toISOString().split('T')[0];
  const filePath = path.join(dir, `${dateStr}.json`);
  await fs.writeFile(filePath, JSON.stringify(data, null, 2));
  return filePath;
}

async function cleanupTestLogDir(dir) {
  try {
    await fs.rm(dir, { recursive: true, force: true });
  } catch (error) {
    // Ignore cleanup errors
  }
}

describe('Station Monitor', () => {
  describe('sanitizeCommand', () => {
    it('should remove token arguments', () => {
      const input = 'curl --token abc123 https://api.example.com';
      const output = sanitizeCommand(input);
      assert.ok(!output.includes('abc123'));
      assert.ok(output.includes('--token=***'));
    });

    it('should remove password arguments', () => {
      const input = 'mysql --password=secret123 -u user';
      const output = sanitizeCommand(input);
      assert.ok(!output.includes('secret123'));
      assert.ok(output.includes('--password=***'));
    });

    it('should remove Bearer tokens', () => {
      const input = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9';
      const output = sanitizeCommand(input);
      assert.ok(!output.includes('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'));
      assert.ok(output.includes('Bearer ***'));
    });

    it('should handle empty or null input', () => {
      assert.strictEqual(sanitizeCommand(''), '');
      assert.strictEqual(sanitizeCommand(null), '');
      assert.strictEqual(sanitizeCommand(undefined), '');
    });

    it('should preserve safe commands', () => {
      const input = 'npm install @octokit/rest';
      const output = sanitizeCommand(input);
      assert.strictEqual(output, input);
    });
  });

  describe('sanitizePath', () => {
    it('should redact paths containing /secrets/', () => {
      const input = '/var/run/secrets/github-token';
      const output = sanitizePath(input);
      assert.strictEqual(output, '[REDACTED]');
    });

    it('should redact paths containing .env', () => {
      const input = '/home/user/project/.env';
      const output = sanitizePath(input);
      assert.strictEqual(output, '[REDACTED]');
    });

    it('should preserve safe paths', () => {
      const input = '/home/vncuser/Desktop/adjudica-ai-app';
      const output = sanitizePath(input);
      assert.strictEqual(output, input);
    });

    it('should handle empty or null input', () => {
      assert.strictEqual(sanitizePath(''), '');
      assert.strictEqual(sanitizePath(null), '');
      assert.strictEqual(sanitizePath(undefined), '');
    });
  });

  describe('processSessions', () => {
    it('should calculate duration in minutes', () => {
      const sessions = [
        {
          type: 'claude-code',
          project: '/home/user/project',
          start: '2026-03-03T10:00:00Z',
          end: '2026-03-03T12:30:00Z',
          commands: 45,
          files_edited: 12
        }
      ];

      const processed = processSessions(sessions);
      assert.strictEqual(processed.length, 1);
      assert.strictEqual(processed[0].duration_minutes, 150); // 2.5 hours = 150 minutes
    });

    it('should handle ongoing sessions (no end time)', () => {
      const sessions = [
        {
          type: 'cursor',
          project: '/home/user/project',
          start: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
          commands: 10,
          files_edited: 5
        }
      ];

      const processed = processSessions(sessions);
      assert.strictEqual(processed.length, 1);
      assert.ok(processed[0].duration_minutes >= 59); // At least ~60 minutes
      assert.strictEqual(processed[0].end, null);
    });

    it('should sanitize project paths', () => {
      const sessions = [
        {
          type: 'vscode',
          project: '/var/run/secrets/project',
          start: '2026-03-03T10:00:00Z',
          end: '2026-03-03T10:30:00Z'
        }
      ];

      const processed = processSessions(sessions);
      assert.strictEqual(processed[0].project, '[REDACTED]');
    });

    it('should handle empty or invalid input', () => {
      assert.deepStrictEqual(processSessions([]), []);
      assert.deepStrictEqual(processSessions(null), []);
      assert.deepStrictEqual(processSessions(undefined), []);
      assert.deepStrictEqual(processSessions('invalid'), []);
    });

    it('should handle sessions with missing fields', () => {
      const sessions = [
        {
          start: '2026-03-03T10:00:00Z',
          end: '2026-03-03T11:00:00Z'
        }
      ];

      const processed = processSessions(sessions);
      assert.strictEqual(processed.length, 1);
      assert.strictEqual(processed[0].type, 'unknown');
      assert.strictEqual(processed[0].project, '');
      assert.strictEqual(processed[0].commands, 0);
      assert.strictEqual(processed[0].files_edited, 0);
    });
  });

  describe('calculateSummary', () => {
    it('should calculate total sessions and active hours', () => {
      const sessions = [
        {
          type: 'claude-code',
          project: '/home/user/project1',
          start: '2026-03-03T10:00:00Z',
          end: '2026-03-03T11:30:00Z',
          duration_minutes: 90,
          commands: 30,
          files_edited: 8
        },
        {
          type: 'cursor',
          project: '/home/user/project2',
          start: '2026-03-03T14:00:00Z',
          end: '2026-03-03T16:00:00Z',
          duration_minutes: 120,
          commands: 50,
          files_edited: 15
        }
      ];

      const summary = calculateSummary(sessions);
      assert.strictEqual(summary.total_sessions, 2);
      assert.strictEqual(summary.active_hours, 3.5); // 90 + 120 = 210 min = 3.5 hours
    });

    it('should extract unique project names', () => {
      const sessions = [
        {
          type: 'claude-code',
          project: '/home/user/Desktop/adjudica-ai-app',
          duration_minutes: 60
        },
        {
          type: 'cursor',
          project: '/home/user/Desktop/glassy-personal-ai',
          duration_minutes: 30
        },
        {
          type: 'vscode',
          project: '/home/user/Desktop/adjudica-ai-app', // Duplicate
          duration_minutes: 45
        }
      ];

      const summary = calculateSummary(sessions);
      assert.strictEqual(summary.projects_touched.length, 2);
      assert.ok(summary.projects_touched.includes('adjudica-ai-app'));
      assert.ok(summary.projects_touched.includes('glassy-personal-ai'));
    });

    it('should count sessions by tool type', () => {
      const sessions = [
        { type: 'claude-code', project: '/home/user/project', duration_minutes: 60 },
        { type: 'claude-code', project: '/home/user/project', duration_minutes: 30 },
        { type: 'cursor', project: '/home/user/project', duration_minutes: 45 },
        { type: 'vscode', project: '/home/user/project', duration_minutes: 20 }
      ];

      const summary = calculateSummary(sessions);
      assert.strictEqual(summary.by_tool['claude-code'], 2);
      assert.strictEqual(summary.by_tool['cursor'], 1);
      assert.strictEqual(summary.by_tool['vscode'], 1);
    });

    it('should exclude redacted paths from projects_touched', () => {
      const sessions = [
        {
          type: 'claude-code',
          project: '/home/user/project',
          duration_minutes: 60
        },
        {
          type: 'cursor',
          project: '[REDACTED]',
          duration_minutes: 30
        }
      ];

      const summary = calculateSummary(sessions);
      assert.strictEqual(summary.projects_touched.length, 1);
      assert.ok(summary.projects_touched.includes('project'));
      assert.ok(!summary.projects_touched.includes('[REDACTED]'));
    });

    it('should handle empty sessions array', () => {
      const summary = calculateSummary([]);
      assert.strictEqual(summary.total_sessions, 0);
      assert.strictEqual(summary.active_hours, 0);
      assert.strictEqual(summary.projects_touched.length, 0);
      assert.deepStrictEqual(summary.by_tool, {});
    });
  });

  describe('collect', () => {
    let testLogDir;

    beforeEach(async () => {
      testLogDir = await createTestLogDir();
    });

    afterEach(async () => {
      await cleanupTestLogDir(testLogDir);
    });

    it('should collect activity from valid log file', async () => {
      const testDate = new Date('2026-03-11');
      const logData = {
        date: '2026-03-11',
        sessions: [
          {
            type: 'claude-code',
            project: '/home/vncuser/Desktop/adjudica-ai-app',
            start: '2026-03-11T08:15:00Z',
            end: '2026-03-11T10:30:00Z',
            commands: 45,
            files_edited: 12
          },
          {
            type: 'cursor',
            project: '/home/vncuser/Desktop/glassy-personal-ai',
            start: '2026-03-11T14:00:00Z',
            end: '2026-03-11T16:30:00Z',
            commands: 30,
            files_edited: 8
          }
        ]
      };

      await writeTestLogFile(testLogDir, testDate, logData);

      const config = { station: { log_dir: testLogDir } };
      const result = await collect(testDate, config);

      assert.strictEqual(result.date, '2026-03-11');
      assert.strictEqual(result.log_file_missing, false);
      assert.strictEqual(result.sessions.length, 2);
      assert.strictEqual(result.summary.total_sessions, 2);
      assert.strictEqual(result.summary.projects_touched.length, 2);
      assert.ok(result.summary.projects_touched.includes('adjudica-ai-app'));
      assert.ok(result.summary.projects_touched.includes('glassy-personal-ai'));
    });

    it('should return empty data when log file is missing', async () => {
      const testDate = new Date('2026-03-11');
      const config = { station: { log_dir: testLogDir } };

      const result = await collect(testDate, config);

      assert.strictEqual(result.date, '2026-03-11');
      assert.strictEqual(result.log_file_missing, true);
      assert.strictEqual(result.sessions.length, 0);
      assert.strictEqual(result.summary.total_sessions, 0);
      assert.strictEqual(result.summary.active_hours, 0);
    });

    it('should handle malformed JSON gracefully', async () => {
      const testDate = new Date('2026-03-11');
      const filePath = path.join(testLogDir, '2026-03-11.json');
      await fs.writeFile(filePath, 'invalid json {{{');

      const config = { station: { log_dir: testLogDir } };
      const result = await collect(testDate, config);

      // Should return empty data instead of throwing
      assert.strictEqual(result.log_file_missing, true);
      assert.strictEqual(result.sessions.length, 0);
    });

    it('should handle empty log file', async () => {
      const testDate = new Date('2026-03-11');
      const logData = { date: '2026-03-11', sessions: [] };

      await writeTestLogFile(testLogDir, testDate, logData);

      const config = { station: { log_dir: testLogDir } };
      const result = await collect(testDate, config);

      assert.strictEqual(result.log_file_missing, false);
      assert.strictEqual(result.sessions.length, 0);
      assert.strictEqual(result.summary.total_sessions, 0);
    });

    it('should handle missing log directory gracefully', async () => {
      const testDate = new Date('2026-03-11');
      const nonExistentDir = '/nonexistent/directory/path';

      const config = { station: { log_dir: nonExistentDir } };
      const result = await collect(testDate, config);

      // Should return empty data instead of throwing
      assert.strictEqual(result.log_file_missing, true);
      assert.strictEqual(result.sessions.length, 0);
    });

    it('should use default log directory when not configured', async () => {
      const testDate = new Date('2026-03-11');
      const config = {}; // No station.log_dir configured

      // Should not throw - gracefully handles missing directory
      const result = await collect(testDate, config);
      assert.ok(result);
      assert.strictEqual(result.log_file_missing, true);
    });

    it('should aggregate statistics for multiple sessions', async () => {
      const testDate = new Date('2026-03-11');
      const logData = {
        date: '2026-03-11',
        sessions: [
          {
            type: 'claude-code',
            project: '/home/vncuser/Desktop/project1',
            start: '2026-03-11T08:00:00Z',
            end: '2026-03-11T09:00:00Z',
            commands: 20,
            files_edited: 5
          },
          {
            type: 'claude-code',
            project: '/home/vncuser/Desktop/project2',
            start: '2026-03-11T10:00:00Z',
            end: '2026-03-11T11:30:00Z',
            commands: 35,
            files_edited: 10
          },
          {
            type: 'cursor',
            project: '/home/vncuser/Desktop/project1',
            start: '2026-03-11T14:00:00Z',
            end: '2026-03-11T15:00:00Z',
            commands: 15,
            files_edited: 3
          }
        ]
      };

      await writeTestLogFile(testLogDir, testDate, logData);

      const config = { station: { log_dir: testLogDir } };
      const result = await collect(testDate, config);

      assert.strictEqual(result.summary.total_sessions, 3);
      assert.strictEqual(result.summary.active_hours, 3.5); // 60 + 90 + 60 = 210 min = 3.5 hours
      assert.strictEqual(result.summary.by_tool['claude-code'], 2);
      assert.strictEqual(result.summary.by_tool['cursor'], 1);
      assert.strictEqual(result.summary.projects_touched.length, 2);
    });

    it('should sanitize sensitive data in sessions', async () => {
      const testDate = new Date('2026-03-11');
      const logData = {
        date: '2026-03-11',
        sessions: [
          {
            type: 'claude-code',
            project: '/var/run/secrets/sensitive-project',
            start: '2026-03-11T08:00:00Z',
            end: '2026-03-11T09:00:00Z',
            commands: 10,
            files_edited: 2
          }
        ]
      };

      await writeTestLogFile(testLogDir, testDate, logData);

      const config = { station: { log_dir: testLogDir } };
      const result = await collect(testDate, config);

      assert.strictEqual(result.sessions[0].project, '[REDACTED]');
      assert.strictEqual(result.summary.projects_touched.length, 0); // Redacted paths excluded
    });
  });

  describe('Integration', () => {
    let testLogDir;

    beforeEach(async () => {
      testLogDir = await createTestLogDir();
    });

    afterEach(async () => {
      await cleanupTestLogDir(testLogDir);
    });

    it('should handle full workflow from log file to summary', async () => {
      const testDate = new Date('2026-03-11');
      const logData = {
        date: '2026-03-11',
        sessions: [
          {
            type: 'claude-code',
            project: '/home/vncuser/Desktop/adjudica-ai-app',
            start: '2026-03-11T08:00:00Z',
            end: '2026-03-11T12:00:00Z',
            commands: 120,
            files_edited: 35
          }
        ]
      };

      await writeTestLogFile(testLogDir, testDate, logData);

      const config = { station: { log_dir: testLogDir } };
      const result = await collect(testDate, config);

      // Verify complete data structure
      assert.ok(result.date);
      assert.ok(Array.isArray(result.sessions));
      assert.ok(result.summary);
      assert.ok(typeof result.log_file_missing === 'boolean');

      // Verify session data
      assert.strictEqual(result.sessions[0].type, 'claude-code');
      assert.strictEqual(result.sessions[0].duration_minutes, 240);
      assert.strictEqual(result.sessions[0].commands, 120);
      assert.strictEqual(result.sessions[0].files_edited, 35);

      // Verify summary
      assert.strictEqual(result.summary.total_sessions, 1);
      assert.strictEqual(result.summary.active_hours, 4.0);
      assert.strictEqual(result.summary.by_tool['claude-code'], 1);
      assert.strictEqual(result.summary.projects_touched.length, 1);
    });
  });
});

