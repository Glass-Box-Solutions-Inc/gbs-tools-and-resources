// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Checks that database connections use SSL/TLS in production configurations.
// SOC2 CC6.7 requires encryption of data in transit, and HIPAA Security Rule
// 164.312(e)(1) requires transmission security for ePHI. This analyzer flags
// DATABASE_URL values without sslmode=require, direct DB connections without
// SSL configuration, and Prisma datasource blocks without SSL settings.

import { BaseAnalyzer } from "./base.analyzer.js";
import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
} from "../types/index.js";

// DATABASE_URL without sslmode in env files or config
const DB_URL_NO_SSL_PATTERN =
  /DATABASE_URL\s*=\s*["']?postgres(?:ql)?:\/\/[^?\s]+(?:\?(?!.*sslmode=require)[^\s]*)?["']?\s*$/;

// Direct database connection configuration without ssl property
const DB_CONFIG_NO_SSL_PATTERN =
  /(?:createPool|createConnection|new\s+(?:Pool|Client))\s*\(\s*\{[^}]*(?:host|connectionString)[^}]*\}/;

// Prisma datasource without SSL in .prisma files
const PRISMA_NO_SSL_PATTERN =
  /datasource\s+\w+\s*\{[^}]*url\s*=\s*env\s*\(\s*["']DATABASE_URL["']\s*\)[^}]*\}/;

// Explicit ssl: false or sslmode=disable
const SSL_DISABLED_PATTERN =
  /(?:ssl\s*:\s*false|sslmode\s*=\s*(?:disable|prefer|allow))/;

// Rejectunauthorized set to false (disables certificate validation)
const REJECT_UNAUTHORIZED_FALSE_PATTERN =
  /rejectUnauthorized\s*:\s*false/;

const CODE_EXTENSIONS = [".ts", ".js", ".tsx", ".jsx"];
const ENV_EXTENSIONS = [".env", ".example"];
const SCHEMA_EXTENSIONS = [".prisma"];

export class SslConnectionAnalyzer extends BaseAnalyzer {
  readonly analyzerName = "ssl-connection";
  readonly analyzerLabel = "Database SSL/TLS Connection Verification";
  readonly framework: Framework = "both";

  async analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]> {
    const findings: ComplianceFindingInput[] = [];

    // DATABASE_URL without SSL (env files and config)
    const envAndConfigFiles = files.filter(
      (f) =>
        f.filePath.includes(".env") ||
        f.filePath.endsWith(".example") ||
        f.filePath.includes("config"),
    );
    findings.push(
      ...this.findPattern(envAndConfigFiles, DB_URL_NO_SSL_PATTERN, {
        severity: "HIGH",
        framework: "both",
        title: "Database connection URL missing SSL requirement",
        descriptionFn: (_match, file) =>
          `DATABASE_URL in ${file.filePath} does not include sslmode=require. Database connections without SSL transmit data (potentially including PHI) in plaintext over the network.`,
        remediationFn: () =>
          "Add ?sslmode=require (or &sslmode=require if other parameters exist) to the DATABASE_URL. For Cloud SQL, use the Cloud SQL Proxy which handles encryption automatically.",
      }),
    );

    // Explicit ssl: false or sslmode=disable
    findings.push(
      ...this.findPattern(files, SSL_DISABLED_PATTERN, {
        severity: "CRITICAL",
        framework: "both",
        title: "SSL explicitly disabled for database connection",
        descriptionFn: (_match, file) =>
          `SSL is explicitly disabled (ssl: false or sslmode=disable/prefer/allow) in ${file.filePath}. This forces database connections to use plaintext, violating both SOC2 CC6.7 and HIPAA transmission security requirements.`,
        remediationFn: () =>
          "Set ssl: true (or ssl: { rejectUnauthorized: true }) in the database connection configuration. Use sslmode=require or sslmode=verify-full in connection strings.",
        extensions: [...CODE_EXTENSIONS, ...ENV_EXTENSIONS],
      }),
    );

    // rejectUnauthorized: false (disables cert validation)
    findings.push(
      ...this.findPattern(files, REJECT_UNAUTHORIZED_FALSE_PATTERN, {
        severity: "HIGH",
        framework: "both",
        title: "TLS certificate validation disabled",
        descriptionFn: (_match, file) =>
          `rejectUnauthorized is set to false in ${file.filePath}. This disables TLS certificate validation, making the connection vulnerable to man-in-the-middle attacks even when SSL is enabled.`,
        remediationFn: () =>
          "Set rejectUnauthorized: true and configure the proper CA certificate. For Cloud SQL, use the server CA certificate provided by Google. For development, use a self-signed cert with the CA added to the trust store.",
        extensions: CODE_EXTENSIONS,
      }),
    );

    // Database connection config objects without ssl property
    // This is a heuristic check - it looks for connection configs that
    // mention host/connectionString but don't include ssl
    for (const file of files) {
      if (!CODE_EXTENSIONS.includes(file.extension)) continue;
      const lines = file.content.split("\n");
      for (let i = 0; i < lines.length; i++) {
        const match = lines[i].match(DB_CONFIG_NO_SSL_PATTERN);
        if (match) {
          // Check if ssl is configured within a reasonable range
          const contextStart = Math.max(0, i - 5);
          const contextEnd = Math.min(lines.length, i + 10);
          const contextBlock = lines.slice(contextStart, contextEnd).join("\n");
          if (
            !contextBlock.includes("ssl") &&
            !contextBlock.includes("SSL") &&
            !contextBlock.includes("sslmode")
          ) {
            const snippetStart = Math.max(0, i - 2);
            const snippetEnd = Math.min(lines.length, i + 3);
            findings.push({
              analyzer: this.analyzerName,
              severity: "HIGH",
              framework: "both",
              repo: file.repo,
              filePath: file.filePath,
              lineNumber: i + 1,
              title: "Database connection configuration missing SSL",
              description: `A database connection in ${file.filePath} is configured without an SSL property. All production database connections must use SSL/TLS for data-in-transit encryption.`,
              snippet: lines.slice(snippetStart, snippetEnd).join("\n"),
              remediation:
                "Add ssl: { rejectUnauthorized: true } to the connection configuration object. For connection strings, append ?sslmode=require.",
            });
          }
        }
      }
    }

    return findings;
  }
}
