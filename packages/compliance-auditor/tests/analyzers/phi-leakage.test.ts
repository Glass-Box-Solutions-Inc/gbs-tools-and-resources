// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { describe, it, expect } from "vitest";
import { PhiLeakageAnalyzer } from "../../src/analyzers/phi-leakage.analyzer.js";
import type { ScannedFile } from "../../src/types/index.js";

function makeFile(
  content: string,
  overrides?: Partial<ScannedFile>,
): ScannedFile {
  return {
    repo: "test-repo",
    filePath: "src/service.ts",
    content,
    extension: ".ts",
    ...overrides,
  };
}

describe("PhiLeakageAnalyzer", () => {
  const analyzer = new PhiLeakageAnalyzer();

  it("has the correct metadata", () => {
    expect(analyzer.analyzerName).toBe("phi-leakage");
    expect(analyzer.framework).toBe("hipaa");
  });

  // --- SSN Detection ---

  it("detects SSN patterns in source code", async () => {
    const file = makeFile(`
      const testSSN = "123-45-6789";
      processUser(testSSN);
    `);
    const findings = await analyzer.analyze([file]);
    const ssnFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("ssn"),
    );
    expect(ssnFindings.length).toBeGreaterThan(0);
    expect(ssnFindings[0].severity).toBe("CRITICAL");
    expect(ssnFindings[0].framework).toBe("hipaa");
  });

  it("does not flag non-SSN number patterns", async () => {
    const file = makeFile(`
      const phoneNumber = "555-1234";
      const zipCode = "90210";
      const version = "1.2.3";
    `);
    const findings = await analyzer.analyze([file]);
    const ssnFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("ssn"),
    );
    expect(ssnFindings.length).toBe(0);
  });

  // --- Date of Birth ---

  it("detects date of birth field assignments", async () => {
    const file = makeFile(`
      const patient = {
        name: "John",
        dateOfBirth: req.body.dob,
      };
    `);
    const findings = await analyzer.analyze([file]);
    const dobFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("date of birth"),
    );
    expect(dobFindings.length).toBeGreaterThan(0);
    expect(dobFindings[0].severity).toBe("HIGH");
  });

  it("detects snake_case date_of_birth fields", async () => {
    const file = makeFile(`
      const date_of_birth = formData.dob;
    `);
    const findings = await analyzer.analyze([file]);
    const dobFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("date of birth"),
    );
    expect(dobFindings.length).toBeGreaterThan(0);
  });

  // --- Medical Record Numbers ---

  it("detects medical record number fields", async () => {
    const file = makeFile(`
      const mrn = data.medicalRecordNumber;
    `);
    const findings = await analyzer.analyze([file]);
    const mrnFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("medical record"),
    );
    expect(mrnFindings.length).toBeGreaterThan(0);
  });

  // --- Patient Name in JSON ---

  it("detects patient name in JSON structures", async () => {
    const file = makeFile(
      `{
        "patientName": "Jane Doe",
        "visitDate": "2026-01-15"
      }`,
      { extension: ".json", filePath: "data/patients.json" },
    );
    const findings = await analyzer.analyze([file]);
    const nameFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("patient name"),
    );
    expect(nameFindings.length).toBeGreaterThan(0);
  });

  // --- PHI in Log Statements ---

  it("detects PHI fields in console.log statements", async () => {
    const file = makeFile(`
      console.log("Processing patient", patient.ssn);
    `);
    const findings = await analyzer.analyze([file]);
    const logFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("log"),
    );
    expect(logFindings.length).toBeGreaterThan(0);
    expect(logFindings[0].severity).toBe("CRITICAL");
  });

  it("detects PHI fields in logger calls", async () => {
    const file = makeFile(`
      logger.info("Patient record updated", { diagnosis: record.diagnosis });
    `);
    const findings = await analyzer.analyze([file]);
    const logFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("log"),
    );
    expect(logFindings.length).toBeGreaterThan(0);
  });

  // --- Clean Code (no findings) ---

  it("produces no findings for clean code", async () => {
    const file = makeFile(`
      import { PrismaClient } from "@prisma/client";
      const prisma = new PrismaClient();

      async function getUser(id: string) {
        return prisma.user.findUnique({ where: { id } });
      }

      export { getUser };
    `);
    const findings = await analyzer.analyze([file]);
    expect(findings.length).toBe(0);
  });

  it("produces no findings for encrypted PHI handling", async () => {
    const file = makeFile(`
      // This code properly handles PHI
      const encryptedData = encrypt(sensitiveInfo);
      await db.insert({ data: encryptedData });
      logger.info("Record created", { id: record.id });
    `);
    const findings = await analyzer.analyze([file]);
    // Should not flag generic log statements without PHI field names
    const logFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("log"),
    );
    expect(logFindings.length).toBe(0);
  });

  // --- Snippet and remediation ---

  it("includes code snippet and remediation in findings", async () => {
    const file = makeFile(`
      function processPatient(data) {
        console.log("Processing", data.ssn);
        return data;
      }
    `);
    const findings = await analyzer.analyze([file]);
    const relevantFinding = findings.find((f) =>
      f.title.toLowerCase().includes("log"),
    );
    expect(relevantFinding).toBeDefined();
    expect(relevantFinding!.snippet).toBeDefined();
    expect(relevantFinding!.snippet!.length).toBeGreaterThan(0);
    expect(relevantFinding!.remediation).toBeDefined();
    expect(relevantFinding!.remediation!.length).toBeGreaterThan(0);
  });

  // --- Multiple files ---

  it("scans multiple files and attributes findings correctly", async () => {
    const files: ScannedFile[] = [
      makeFile(`const ssn = "111-22-3333";`, {
        filePath: "src/a.ts",
        repo: "repo-a",
      }),
      makeFile(`const id = "abc-123";`, {
        filePath: "src/b.ts",
        repo: "repo-b",
      }),
      makeFile(`const mrn = data.medicalRecordNumber;`, {
        filePath: "src/c.ts",
        repo: "repo-c",
      }),
    ];
    const findings = await analyzer.analyze(files);
    const repoAFindings = findings.filter((f) => f.repo === "repo-a");
    const repoBFindings = findings.filter((f) => f.repo === "repo-b");
    const repoCFindings = findings.filter((f) => f.repo === "repo-c");

    expect(repoAFindings.length).toBeGreaterThan(0);
    expect(repoBFindings.length).toBe(0);
    expect(repoCFindings.length).toBeGreaterThan(0);
  });

  // --- Extension filtering ---

  it("skips non-applicable file extensions", async () => {
    const file = makeFile(`const mrn = data.medicalRecordNumber;`, {
      extension: ".md",
      filePath: "docs/readme.md",
    });
    const findings = await analyzer.analyze([file]);
    // MRN pattern only targets .ts, .js, .tsx, .jsx
    const mrnFindings = findings.filter((f) =>
      f.title.toLowerCase().includes("medical record"),
    );
    expect(mrnFindings.length).toBe(0);
  });
});
