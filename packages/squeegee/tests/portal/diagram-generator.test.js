/**
 * Unit tests for Portal Diagram Generator
 */

const {
  cleanMermaidOutput,
  validateMermaid,
  computeContentHash,
  fallbackArchitectureDiagram,
  fallbackDataFlowDiagram,
  fallbackSequenceDiagram,
} = require('../../src/portal/diagram-generator');

describe('Diagram Generator', () => {
  describe('cleanMermaidOutput', () => {
    test('strips mermaid code fences', () => {
      const input = '```mermaid\ngraph TD\n    A --> B\n```';
      expect(cleanMermaidOutput(input)).toBe('graph TD\n    A --> B');
    });

    test('strips generic code fences', () => {
      const input = '```\ngraph TD\n    A --> B\n```';
      expect(cleanMermaidOutput(input)).toBe('graph TD\n    A --> B');
    });

    test('handles already clean input', () => {
      const input = 'graph TD\n    A --> B';
      expect(cleanMermaidOutput(input)).toBe('graph TD\n    A --> B');
    });

    test('trims whitespace', () => {
      const input = '  \n  graph TD\n    A --> B  \n  ';
      expect(cleanMermaidOutput(input)).toBe('graph TD\n    A --> B');
    });
  });

  describe('validateMermaid', () => {
    test('accepts graph TD', () => {
      expect(validateMermaid('graph TD\n    A --> B')).toBe(true);
    });

    test('accepts flowchart LR', () => {
      expect(validateMermaid('flowchart LR\n    A --> B')).toBe(true);
    });

    test('accepts sequenceDiagram', () => {
      expect(validateMermaid('sequenceDiagram\n    A->>B: hello')).toBe(true);
    });

    test('accepts classDiagram', () => {
      expect(validateMermaid('classDiagram\n    class A')).toBe(true);
    });

    test('rejects invalid content', () => {
      expect(validateMermaid('This is not mermaid')).toBe(false);
    });

    test('rejects empty string', () => {
      expect(validateMermaid('')).toBe(false);
    });
  });

  describe('computeContentHash', () => {
    test('returns 16-char hex string', () => {
      const hash = computeContentHash({
        name: 'test-project',
        description: 'A test project',
        tech_stack: ['React', 'Node'],
        category: 'infrastructure',
      });
      expect(hash).toMatch(/^[a-f0-9]{16}$/);
    });

    test('returns same hash for same input', () => {
      const data = { name: 'test', description: 'desc', tech_stack: ['React'], category: 'infra' };
      expect(computeContentHash(data)).toBe(computeContentHash(data));
    });

    test('returns different hash for different input', () => {
      const a = { name: 'project-a', description: '', tech_stack: [], category: '' };
      const b = { name: 'project-b', description: '', tech_stack: [], category: '' };
      expect(computeContentHash(a)).not.toBe(computeContentHash(b));
    });

    test('handles missing fields gracefully', () => {
      const hash = computeContentHash({});
      expect(hash).toMatch(/^[a-f0-9]{16}$/);
    });
  });

  describe('fallback diagrams', () => {
    const project = {
      name: 'test-project',
      tech_stack: ['React', 'PostgreSQL', 'Redis'],
    };

    test('fallbackArchitectureDiagram generates valid mermaid', () => {
      const diagram = fallbackArchitectureDiagram(project);
      expect(validateMermaid(diagram)).toBe(true);
      expect(diagram).toContain('graph TD');
      expect(diagram).toContain('Database');
      expect(diagram).toContain('Redis Cache');
    });

    test('fallbackDataFlowDiagram generates valid mermaid', () => {
      const diagram = fallbackDataFlowDiagram(project);
      expect(validateMermaid(diagram)).toBe(true);
      expect(diagram).toContain('flowchart LR');
    });

    test('fallbackSequenceDiagram generates valid mermaid', () => {
      const diagram = fallbackSequenceDiagram(project);
      expect(validateMermaid(diagram)).toBe(true);
      expect(diagram).toContain('sequenceDiagram');
    });

    test('fallback handles AI tech stack', () => {
      const aiProject = { name: 'ai-app', tech_stack: ['Gemini', 'FastAPI'] };
      const diagram = fallbackArchitectureDiagram(aiProject);
      expect(diagram).toContain('AI Service');
    });
  });
});
