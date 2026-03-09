// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Scans for Protected Health Information (PHI) patterns that may appear in
// source code, metadata, or log statements. PHI leakage in code or logs
// violates HIPAA's Privacy and Security Rules (45 CFR 164.312). This analyzer
// catches hardcoded SSNs, date-of-birth fields in plaintext, medical record
// numbers, patient name patterns in JSON, and PHI field names in log calls.

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

// SSN pattern: 123-45-6789
const SSN_PATTERN = /\b\d{3}-\d{2}-\d{4}\b/;

// Date of birth fields stored/logged in plain text
const DOB_FIELD_PATTERN =
  /(?:dateOfBirth|date_of_birth|dob|birthDate|birth_date)\s*[=:]/i;

// Medical record number patterns
const MRN_PATTERN =
  /(?:medicalRecordNumber|medical_record_number|mrn|patientId|patient_id)\s*[=:]/i;

// Patient name in JSON-like structures
const PATIENT_NAME_JSON_PATTERN =
  /["'](?:patientName|patient_name|patientFirstName|patientLastName|patient_first_name|patient_last_name)["']\s*:/i;

// console.log / logger calls containing PHI field names
const LOG_PHI_PATTERN =
  /(?:console\.(?:log|info|warn|error|debug)|logger\.(?:info|warn|error|debug))\s*\([^)]*(?:ssn|dateOfBirth|date_of_birth|dob|medicalRecord|medical_record|mrn|patientName|patient_name|diagnosis|prescription)/i;

// Hardcoded PHI-like data in string literals (SSN format in quotes)
const HARDCODED_SSN_STRING =
  /["']\d{3}-\d{2}-\d{4}["']/;

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];
const ALL_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx", ".json"];

export class PhiLeakageAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "phi-leakage";
  readonly analyzerLabel = "PHI Leakage Detection";
  readonly framework: Framework = "hipaa";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    // SSN patterns in any scanned file
    findings.push(
      ...this.findPattern(files, SSN_PATTERN, {
        severity: "CRITICAL",
        framework: "hipaa",
        title: "Social Security Number pattern detected",
        descriptionFn: (_match, file) =>
          `A string matching SSN format (XXX-XX-XXXX) was found in ${file.filePath}. Hardcoded or logged SSNs violate HIPAA Privacy Rule requirements for PHI protection.`,
        remediationFn: () =>
          "Remove hardcoded SSN values. Use tokenization or encryption for SSN storage. Never log SSN values - use masked representations (***-**-1234) if display is required.",
        extensions: ALL_EXTENSIONS,
      }),
    );

    // Hardcoded SSN in string literals (higher confidence)
    findings.push(
      ...this.findPattern(files, HARDCODED_SSN_STRING, {
        severity: "CRITICAL",
        framework: "hipaa",
        title: "Hardcoded SSN value in string literal",
        descriptionFn: (_match, file) =>
          `A quoted string matching SSN format was found in ${file.filePath}. This is likely a hardcoded PHI value that must be removed immediately.`,
        remediationFn: () =>
          "Remove all hardcoded SSN values from source code. Use environment variables or encrypted storage for test fixtures. Replace with synthetic data in test files.",
        extensions: ALL_EXTENSIONS,
      }),
    );

    // Date of birth fields in plain text
    findings.push(
      ...this.findPattern(files, DOB_FIELD_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "Date of birth field stored or assigned in plaintext",
        descriptionFn: (_match, file) =>
          `A date-of-birth field assignment was found in ${file.filePath}. Date of birth is PHI under HIPAA and must be encrypted at rest and in transit.`,
        remediationFn: () =>
          "Encrypt date-of-birth values at rest using field-level encryption. Ensure the field is not included in log output or error messages.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // Medical record numbers
    findings.push(
      ...this.findPattern(files, MRN_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "Medical record number field detected",
        descriptionFn: (_match, file) =>
          `A medical record number field was found in ${file.filePath}. MRNs are direct patient identifiers and qualify as PHI under HIPAA.`,
        remediationFn: () =>
          "Encrypt medical record numbers at rest. Use tokenized references in application code and logs. Restrict access to MRN fields to authorized roles only.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // Patient name in JSON metadata
    findings.push(
      ...this.findPattern(files, PATIENT_NAME_JSON_PATTERN, {
        severity: "HIGH",
        framework: "hipaa",
        title: "Patient name field in JSON structure",
        descriptionFn: (_match, file) =>
          `A patient name field was found in a JSON-like structure in ${file.filePath}. Patient names are PHI and must be encrypted and access-controlled.`,
        remediationFn: () =>
          "Encrypt patient name fields at rest. Do not include patient names in API response metadata or log payloads. Use patient IDs or tokens for cross-service references.",
        extensions: ALL_EXTENSIONS,
      }),
    );

    // PHI field names in log/console calls
    findings.push(
      ...this.findPattern(files, LOG_PHI_PATTERN, {
        severity: "CRITICAL",
        framework: "hipaa",
        title: "PHI field referenced in log statement",
        descriptionFn: (_match, file) =>
          `A log statement in ${file.filePath} references a PHI field name (SSN, DOB, MRN, patient name, diagnosis, or prescription). Logging PHI violates HIPAA audit controls and the minimum necessary standard.`,
        remediationFn: () =>
          "Remove PHI fields from all log statements. Use structured logging with field redaction. Implement a PHI-safe logger wrapper that automatically strips sensitive fields before output.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    return findings;
  }
}
