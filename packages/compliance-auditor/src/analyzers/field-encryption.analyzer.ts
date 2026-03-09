// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Verifies that PHI fields use encryption at rest. HIPAA Security Rule
// (45 CFR 164.312(a)(2)(iv)) requires encryption of ePHI. This analyzer
// checks for PHI field names stored without encryption indicators, Prisma
// schema fields using @db.Text on PHI columns (should use encrypted types),
// and missing @encrypted decorators on sensitive model fields.

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

// PHI field names stored without encryption wrapper
const PHI_FIELD_ASSIGNMENT_PATTERN =
  /(?:ssn|socialSecurity|social_security|dateOfBirth|date_of_birth|dob|medicalRecord|medical_record|mrn|diagnosis|prescription|patientName|patient_name)\s*[:=]\s*(?:(?:req|request|body|data|input|form|payload)\.|["'`])/i;

// Prisma schema: PHI fields with @db.Text (plaintext storage)
const PRISMA_PHI_TEXT_PATTERN =
  /(?:ssn|socialSecurity|dateOfBirth|dob|medicalRecord|mrn|diagnosis|prescription|patientName)\s+String\s+.*@db\.Text/i;

// Prisma schema: PHI fields without any encryption indicator
const PRISMA_PHI_PLAIN_STRING_PATTERN =
  /(?:ssn|socialSecurity|dateOfBirth|dob|medicalRecord|mrn|diagnosis|prescription|patientName)\s+String(?!\s*.*(?:@encrypted|@map\("encrypted_|encrypt))/i;

// Direct database column with PHI name and no encryption
const DB_PHI_COLUMN_PATTERN =
  /(?:ADD\s+COLUMN|ALTER\s+COLUMN|CREATE\s+TABLE[^;]*)\s+(?:ssn|date_of_birth|medical_record|diagnosis|prescription|patient_name)\s+(?:VARCHAR|TEXT|CHAR)/i;

// PHI fields passed to plaintext operations (JSON.stringify, toString)
const PHI_PLAINTEXT_OP_PATTERN =
  /(?:JSON\.stringify|\.toString)\s*\(\s*(?:.*\.)?(?:ssn|dateOfBirth|date_of_birth|medicalRecord|medical_record|diagnosis|prescription|patientName|patient_name)/i;

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];
const SCHEMA_EXTENSIONS = [".prisma"];
const SQL_EXTENSIONS = [".sql"];

export class FieldEncryptionAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "field-encryption";
  readonly analyzerLabel = "PHI Field Encryption Verification";
  readonly framework: Framework = "hipaa";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    // PHI field assignments without encryption wrapper
    findings.push(
      ...this.findPattern(files, PHI_FIELD_ASSIGNMENT_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "PHI field stored without encryption",
        descriptionFn: (_match, file) =>
          `A PHI field (SSN, DOB, MRN, diagnosis, prescription, or patient name) is assigned from user input without an encryption wrapper in ${file.filePath}. HIPAA requires encryption of ePHI at rest.`,
        remediationFn: () =>
          "Wrap PHI field values with an encryption function before storage. Use field-level encryption (e.g., AES-256-GCM) and store the encrypted value. Decrypt only when needed for authorized display.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // Prisma schema: PHI fields with @db.Text
    findings.push(
      ...this.findPattern(files, PRISMA_PHI_TEXT_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "PHI field uses plaintext database type in Prisma schema",
        descriptionFn: (_match, file) =>
          `A Prisma model in ${file.filePath} defines a PHI field with @db.Text, which stores data as plaintext in the database. PHI fields must use encrypted storage.`,
        remediationFn: () =>
          "Use application-level encryption before storing PHI in the database. Consider using Prisma middleware or a custom encryption extension to transparently encrypt/decrypt PHI fields.",
        extensions: SCHEMA_EXTENSIONS,
      }),
    );

    // Prisma schema: PHI fields as plain String without encryption markers
    findings.push(
      ...this.findPattern(files, PRISMA_PHI_PLAIN_STRING_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "PHI field in Prisma schema lacks encryption indicator",
        descriptionFn: (_match, file) =>
          `A PHI field in the Prisma schema at ${file.filePath} is defined as a plain String without any encryption annotation. This suggests the field may be stored unencrypted.`,
        remediationFn: () =>
          "Add an @encrypted annotation or implement Prisma middleware that encrypts PHI fields before database writes and decrypts after reads. Document the encryption approach in the model comments.",
        extensions: SCHEMA_EXTENSIONS,
      }),
    );

    // Raw SQL with PHI columns as plaintext types
    findings.push(
      ...this.findPattern(files, DB_PHI_COLUMN_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "Database migration defines PHI column without encryption",
        descriptionFn: (_match, file) =>
          `A SQL migration in ${file.filePath} defines a PHI column (SSN, DOB, MRN, etc.) as a plaintext type (VARCHAR/TEXT/CHAR). PHI columns must store encrypted values.`,
        remediationFn: () =>
          "Store encrypted values in BYTEA columns or use application-level encryption with a TEXT column that holds base64-encoded ciphertext. Add a comment documenting the encryption scheme.",
        extensions: SQL_EXTENSIONS,
      }),
    );

    // PHI passed to plaintext serialization
    findings.push(
      ...this.findPattern(files, PHI_PLAINTEXT_OP_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "PHI field passed to plaintext serialization",
        descriptionFn: (_match, file) =>
          `A PHI field is passed to JSON.stringify or toString in ${file.filePath}. Serializing PHI to plaintext strings can result in unencrypted data in logs, caches, or network payloads.`,
        remediationFn: () =>
          "Use a custom serializer that redacts or encrypts PHI fields before serialization. Implement a toSafeJSON() method on PHI-containing objects that masks sensitive values.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    return findings;
  }
}
