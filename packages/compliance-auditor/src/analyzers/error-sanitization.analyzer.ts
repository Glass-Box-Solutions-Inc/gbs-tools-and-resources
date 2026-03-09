// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Verifies that error responses do not expose stack traces, internal error
// objects, or implementation details to API consumers. SOC2 CC6.1 requires
// information to be protected during transmission, and leaking stack traces
// or internal errors provides attackers with implementation details that
// facilitate further exploitation.

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

// reply.send(err) or res.json(error) — sending raw error objects
const SEND_RAW_ERROR_PATTERN =
  /(?:reply|res|response)\.(?:send|json)\s*\(\s*(?:err|error|e)\s*\)/;

// error.stack in response construction
const STACK_IN_RESPONSE_PATTERN =
  /(?:reply|res|response)\.(?:send|json|status)\s*\([^)]*(?:err|error|e)\.stack/;

// Catch block sending raw error to response
const CATCH_SEND_ERROR_PATTERN =
  /catch\s*\(\s*(?:err|error|e)\s*\)\s*\{[^}]*(?:reply|res|response)\.(?:status\s*\(\s*5\d{2}\s*\)\s*\.)?(?:send|json)\s*\(\s*(?:err|error|e)\s*\)/;

// error.message directly in response (can leak internals)
const ERROR_MESSAGE_IN_RESPONSE_PATTERN =
  /(?:reply|res|response)\.(?:send|json)\s*\(\s*\{[^}]*message\s*:\s*(?:err|error|e)\.message/;

// Stack trace property included in response objects
const STACK_PROPERTY_PATTERN =
  /(?:stack|stackTrace|stack_trace)\s*:\s*(?:err|error|e)\.stack/;

// Express/Fastify error handler that passes through raw error
const ERROR_HANDLER_PASSTHROUGH_PATTERN =
  /(?:setErrorHandler|use)\s*\(\s*(?:async\s*)?\(\s*(?:err|error),\s*(?:req|request),\s*(?:reply|res|response)\s*\)\s*=>\s*\{[^}]*(?:reply|res|response)\.send\s*\(\s*(?:err|error)\s*\)/;

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];

export class ErrorSanitizationAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "error-sanitization";
  readonly analyzerLabel = "Error Response Sanitization";
  readonly framework: Framework = "soc2";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    // Raw error object in response
    findings.push(
      ...this.findPattern(files, SEND_RAW_ERROR_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Raw error object sent in HTTP response",
        descriptionFn: (_match, file) =>
          `A raw error object is passed directly to reply.send() or res.json() in ${file.filePath}. This exposes stack traces, internal paths, and implementation details to API consumers.`,
        remediationFn: () =>
          "Return a sanitized error response with only a generic message and an error code. Map internal errors to user-safe messages: { error: 'Internal server error', code: 'ERR_INTERNAL' }.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // error.stack in response
    findings.push(
      ...this.findPattern(files, STACK_IN_RESPONSE_PATTERN, {
        severity: "CRITICAL",
        framework: "soc2",
        title: "Stack trace included in HTTP response",
        descriptionFn: (_match, file) =>
          `error.stack is included in an HTTP response in ${file.filePath}. Stack traces reveal file paths, line numbers, and dependency versions that attackers use for targeted exploits.`,
        remediationFn: () =>
          "Never include error.stack in API responses. Log the full error server-side with a correlation ID, and return only the correlation ID to the client for support reference.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // catch block sending raw error
    findings.push(
      ...this.findPattern(files, CATCH_SEND_ERROR_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Catch block sends raw error to client",
        descriptionFn: (_match, file) =>
          `A catch block in ${file.filePath} sends the caught error directly to the HTTP response. This pattern leaks internal error details including stack traces and dependency information.`,
        remediationFn: () =>
          "In catch blocks, log the full error server-side and return a generic error response: catch (err) { logger.error(err); reply.status(500).send({ error: 'Internal server error' }); }.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // error.message in response (weaker signal but still risky)
    findings.push(
      ...this.findPattern(files, ERROR_MESSAGE_IN_RESPONSE_PATTERN, {
        severity: "MEDIUM",
        framework: "soc2",
        title: "Internal error message exposed in response",
        descriptionFn: (_match, file) =>
          `error.message is included in an HTTP response object in ${file.filePath}. Internal error messages can reveal database table names, query syntax, and other implementation details.`,
        remediationFn: () =>
          "Map internal error messages to user-safe equivalents. Use an error mapping layer that translates known error types to generic messages while preserving the internal message in server logs.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // Stack property in response objects
    findings.push(
      ...this.findPattern(files, STACK_PROPERTY_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Stack trace property in response object",
        descriptionFn: (_match, file) =>
          `A stack trace property is being assigned from an error's stack in ${file.filePath}. This will include the full stack trace in the response payload.`,
        remediationFn: () =>
          "Remove the stack property from all response objects. Stack traces should only appear in server-side logs, never in client-facing responses.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // Error handler passthrough
    findings.push(
      ...this.findPattern(files, ERROR_HANDLER_PASSTHROUGH_PATTERN, {
        severity: "HIGH",
        framework: "soc2",
        title: "Error handler passes raw error to response",
        descriptionFn: (_match, file) =>
          `A Fastify/Express error handler in ${file.filePath} sends the raw error object to the client. Global error handlers must sanitize errors before responding.`,
        remediationFn: () =>
          "Implement a global error handler that maps errors to safe response types. Use distinct handling for validation errors (400), auth errors (401/403), and internal errors (500) with sanitized messages.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    return findings;
  }
}
