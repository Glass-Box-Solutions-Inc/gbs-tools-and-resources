/**
 * Unit tests for Portal Linear Client
 */

const { collectSprintData } = require('../../src/portal/linear-client');

describe('Portal Linear Client', () => {
  describe('collectSprintData', () => {
    test('returns empty object when no API key provided', async () => {
      const result = await collectSprintData(null);
      expect(result).toEqual({});
    });

    test('returns empty object when empty API key provided', async () => {
      const result = await collectSprintData('');
      expect(result).toEqual({});
    });
  });
});
