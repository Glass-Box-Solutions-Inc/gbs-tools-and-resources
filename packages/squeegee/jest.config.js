/**
 * Jest configuration for Squeegee
 */

module.exports = {
  // Test environment
  testEnvironment: 'node',

  // Test file patterns
  testMatch: [
    '**/tests/**/*.test.js'
  ],

  // Coverage configuration
  collectCoverageFrom: [
    'intelligence/**/*.js',
    'src/pipeline/**/*.js',
    'src/github/**/*.js',
    'src/api/**/*.js',
    'src/portal/**/*.js',
    '!intelligence/types.js',
    '!**/node_modules/**'
  ],

  // Setup files
  setupFilesAfterEnv: ['<rootDir>/tests/setup.js'],

  // Coverage directory
  coverageDirectory: 'coverage',

  // Coverage thresholds — fail CI if coverage drops below these
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 60,
      lines: 60,
      statements: 60
    }
  },

  // E2E tests need more time (git operations, file I/O)
  testTimeout: 30000,

  // Verbose output
  verbose: true
};
