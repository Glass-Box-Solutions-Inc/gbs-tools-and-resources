/**
 * Unit tests for Portal Models
 */

const {
  ProjectStatus,
  ProjectCategory,
  ExpertiseLevel,
  getExpertiseLevel,
  getColorIntensity,
  STATUS_MAP,
  CATEGORY_MAP,
} = require('../../src/portal/models');

describe('Portal Models', () => {
  describe('getExpertiseLevel', () => {
    test('returns NONE for 0 commits', () => {
      expect(getExpertiseLevel(0)).toBe(ExpertiseLevel.NONE);
    });

    test('returns FAMILIAR for 1-50 commits', () => {
      expect(getExpertiseLevel(1)).toBe(ExpertiseLevel.FAMILIAR);
      expect(getExpertiseLevel(50)).toBe(ExpertiseLevel.FAMILIAR);
    });

    test('returns PROFICIENT for 51-200 commits', () => {
      expect(getExpertiseLevel(51)).toBe(ExpertiseLevel.PROFICIENT);
      expect(getExpertiseLevel(200)).toBe(ExpertiseLevel.PROFICIENT);
    });

    test('returns EXPERT for 201-500 commits', () => {
      expect(getExpertiseLevel(201)).toBe(ExpertiseLevel.EXPERT);
      expect(getExpertiseLevel(500)).toBe(ExpertiseLevel.EXPERT);
    });

    test('returns MASTER for 500+ commits', () => {
      expect(getExpertiseLevel(501)).toBe(ExpertiseLevel.MASTER);
      expect(getExpertiseLevel(1000)).toBe(ExpertiseLevel.MASTER);
    });

    test('returns NONE for negative values', () => {
      expect(getExpertiseLevel(-1)).toBe(ExpertiseLevel.NONE);
    });
  });

  describe('getColorIntensity', () => {
    test('returns 0 for 0 commits', () => {
      expect(getColorIntensity(0)).toBe(0);
    });

    test('returns 1 for 1-5 commits', () => {
      expect(getColorIntensity(1)).toBe(1);
      expect(getColorIntensity(5)).toBe(1);
    });

    test('returns 2 for 6-15 commits', () => {
      expect(getColorIntensity(6)).toBe(2);
      expect(getColorIntensity(15)).toBe(2);
    });

    test('returns 3 for 16-50 commits', () => {
      expect(getColorIntensity(16)).toBe(3);
      expect(getColorIntensity(50)).toBe(3);
    });

    test('returns 4 for 50+ commits', () => {
      expect(getColorIntensity(51)).toBe(4);
      expect(getColorIntensity(1000)).toBe(4);
    });
  });

  describe('STATUS_MAP', () => {
    test('maps all valid statuses', () => {
      expect(STATUS_MAP.active).toBe(ProjectStatus.ACTIVE);
      expect(STATUS_MAP.deployed).toBe(ProjectStatus.DEPLOYED);
      expect(STATUS_MAP.planning).toBe(ProjectStatus.PLANNING);
      expect(STATUS_MAP.archived).toBe(ProjectStatus.ARCHIVED);
    });
  });

  describe('CATEGORY_MAP', () => {
    test('maps all valid categories', () => {
      expect(CATEGORY_MAP['adjudica-platform']).toBe(ProjectCategory.ADJUDICA_PLATFORM);
      expect(CATEGORY_MAP['infrastructure']).toBe(ProjectCategory.INFRASTRUCTURE);
      expect(CATEGORY_MAP['internal-tools']).toBe(ProjectCategory.INTERNAL_TOOLS);
    });
  });
});
