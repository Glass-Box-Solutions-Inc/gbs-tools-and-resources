/**
 * Unit tests for Portal Explanation Generator
 */

const { parseDualResponse } = require('../../src/portal/explanation-generator');

describe('Explanation Generator', () => {
  describe('parseDualResponse', () => {
    const projectData = {
      name: 'test-project',
      category: 'infrastructure',
      tech_stack: ['React', 'Node'],
    };

    test('parses standard TECHNICAL/NON-TECHNICAL format', () => {
      const text = `TECHNICAL:
This is the technical explanation. It covers architecture and design patterns.

NON-TECHNICAL:
This is the non-technical explanation. It explains business value.`;

      const result = parseDualResponse(text, projectData);
      expect(result.technical).toContain('technical explanation');
      expect(result.non_technical).toContain('non-technical explanation');
    });

    test('handles NON_TECHNICAL with underscore', () => {
      const text = `TECHNICAL:
Tech stuff here.

NON_TECHNICAL:
Plain English here.`;

      const result = parseDualResponse(text, projectData);
      expect(result.technical).toContain('Tech stuff');
      expect(result.non_technical).toContain('Plain English');
    });

    test('strips markdown bold markers', () => {
      const text = `TECHNICAL:
This is **bold** text with **emphasis**.

NON-TECHNICAL:
This is **also bold**.`;

      const result = parseDualResponse(text, projectData);
      expect(result.technical).not.toContain('**');
      expect(result.non_technical).not.toContain('**');
    });

    test('provides fallback for empty technical', () => {
      const text = `NON-TECHNICAL:
Some non-technical text.`;

      const result = parseDualResponse(text, projectData);
      // When no TECHNICAL: section exists, regex returns empty -> fallback used
      expect(result.technical).toBeTruthy();
      expect(result.non_technical).toContain('non-technical text');
    });

    test('provides fallback for empty non-technical', () => {
      const text = `TECHNICAL:
Some technical text.`;

      const result = parseDualResponse(text, projectData);
      expect(result.technical).toContain('technical text');
      expect(result.non_technical).toBeTruthy();
    });

    test('provides both fallbacks for unparseable text', () => {
      const result = parseDualResponse('Just random text with no headers', projectData);
      expect(result.technical).toContain('test-project');
      expect(result.non_technical).toBeTruthy();
    });
  });
});
