/**
 * Jest test setup file
 * Runs before all tests
 */

// Suppress console output in tests (unless debugging)
if (!process.env.DEBUG_TESTS) {
  global.console = {
    ...console,
    log: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    debug: jest.fn()
  };
}

// Set test timeout
jest.setTimeout(10000);
