// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Verifies that DEBUG-level and raw console logging is not present in
// production source paths. Excessive or uncontrolled logging can leak
// sensitive data, violating SOC2 CC6.1 (logical access controls) and
// CC7.2 (system monitoring). This analyzer flags console.log in non-test
// files, console.debug anywhere, logger.debug with sensitive data patterns,
// and JSON.stringify(req.body) in log calls.

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

// console.log in production code (non-test files)
const CONSOLE_LOG_PATTERN = /\bconsole\.log\s*\(/;

// console.debug anywhere
const CONSOLE_DEBUG_PATTERN = /\bconsole\.debug\s*\(/;

// logger.debug with sensitive data patterns
const LOGGER_DEBUG_SENSITIVE_PATTERN =
  /\blogger\.debug\s*\([^)]*(?:password|token|secret|credential|apiKey|api_key|authorization|cookie|session)/i;

// JSON.stringify(req.body) or JSON.stringify(request.body) in log calls
const STRINGIFY_BODY_IN_LOG_PATTERN =
  /(?:console\.(?:log|info|warn|error|debug)|logger\.(?:info|warn|error|debug))\s*\([^)]*JSON\.stringify\s*\(\s*(?:req|request)\.body/;

// General JSON.stringify of request/response objects in logs
const STRINGIFY_REQ_IN_LOG_PATTERN =
  /(?:console\.(?:log|info|warn|error|debug)|logger\.(?:info|warn|error|debug))\s*\([^)]*JSON\.stringify\s*\(\s*(?:req|request|res|response)\s*\)/;

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];

export class DebugLoggingAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "debug-logging";
  readonly analyzerLabel = "Debug Logging in Production Paths";
  readonly framework: Framework = "soc2";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    // Filter to only src/ files, skip test directories
    const productionFiles = files.filter(
      (f) =>
        (f.filePath.includes("/src/") || f.filePath.startsWith("src/")) &&
        !f.filePath.includes("/test") &&
        !f.filePath.includes("/tests/") &&
        !f.filePath.includes("/__tests__/") &&
        !f.filePath.includes(".test.") &&
        !f.filePath.includes(".spec."),
    );

    // console.log in production code
    findings.push(
      ...this.findPattern(productionFiles, CONSOLE_LOG_PATTERN, {
        severity: "MEDIUM",
        framework: "soc2",
        title: "console.log statement in production code",
        descriptionFn: (_match, file) =>
          `console.log found in ${file.filePath}. Unstructured console output in production can leak sensitive data and bypasses log management controls required by SOC2 CC7.2.`,
        remediationFn: () =>
          "Replace console.log with a structured logger (e.g., Pino) that supports log levels, redaction, and centralized collection. Set production log level to 'info' or higher.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // console.debug anywhere (including test files since it may leak to production)
    findings.push(
      ...this.findPattern(files, CONSOLE_DEBUG_PATTERN, {
        severity: "MEDIUM",
        framework: "soc2",
        title: "console.debug statement detected",
        descriptionFn: (_match, file) =>
          `console.debug found in ${file.filePath}. Debug-level console output should be replaced with a structured logger that can be disabled in production.`,
        remediationFn: () =>
          "Use a structured logger with configurable log levels. Debug output should be controlled by the LOG_LEVEL environment variable, not by code changes.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // logger.debug with sensitive data patterns
    findings.push(
      ...this.findPattern(productionFiles, LOGGER_DEBUG_SENSITIVE_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Debug log contains sensitive data reference",
        descriptionFn: (_match, file) =>
          `A logger.debug call in ${file.filePath} references potentially sensitive data (password, token, secret, credential, API key, etc.). Even at debug level, sensitive data in logs violates SOC2 CC6.1 requirements.`,
        remediationFn: () =>
          "Remove sensitive field references from all log statements. Use Pino's redact option to automatically mask sensitive fields: redact: ['password', 'token', 'secret', 'authorization'].",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // JSON.stringify(req.body) in log calls
    findings.push(
      ...this.findPattern(productionFiles, STRINGIFY_BODY_IN_LOG_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Request body stringified in log statement",
        descriptionFn: (_match, file) =>
          `JSON.stringify(req.body) found in a log statement in ${file.filePath}. Logging entire request bodies can expose passwords, tokens, PII, and other sensitive data submitted by users.`,
        remediationFn: () =>
          "Log only specific, non-sensitive fields from the request body. Use a serializer or redaction layer to strip sensitive fields before logging.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // JSON.stringify of entire request/response objects
    findings.push(
      ...this.findPattern(productionFiles, STRINGIFY_REQ_IN_LOG_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Entire request/response object stringified in log",
        descriptionFn: (_match, file) =>
          `JSON.stringify of a full request or response object found in a log call in ${file.filePath}. This can expose headers (including Authorization), cookies, and body content.`,
        remediationFn: () =>
          "Log only the fields needed for debugging (method, URL, status code). Use Fastify/Express request serializers that automatically exclude sensitive headers and body content.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    return findings;
  }
}
