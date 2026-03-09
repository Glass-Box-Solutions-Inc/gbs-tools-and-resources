// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Abstract base class for compliance analyzers. Each analyzer implements the
// `analyze()` method to scan source files for a specific compliance concern.
// Follows the BaseAuditor pattern from gbs-operations-audit.

import type {
  ScannedFile,
  ComplianceFindingInput,
  Framework,
  Severity,
} from "../types/index.js";

export abstract class BaseAnalyzer {
  abstract readonly analyzerName: string;
  abstract readonly analyzerLabel: string;
  abstract readonly framework: Framework;

  abstract analyze(files: ScannedFile[]): Promise<ComplianceFindingInput[]>;

  /**
   * Scan files for lines matching a regex pattern and produce findings for
   * each match. Handles line-number extraction and snippet generation.
   */
  protected findPattern(
    files: ScannedFile[],
    pattern: RegExp,
    opts: {
      severity: Severity;
      framework: Framework;
      title: string;
      descriptionFn: (match: RegExpMatchArray, file: ScannedFile) => string;
      remediationFn?: (match: RegExpMatchArray) => string;
      extensions?: string[];
    },
  ): ComplianceFindingInput[] {
    const findings: ComplianceFindingInput[] = [];
    for (const file of files) {
      if (opts.extensions && !opts.extensions.includes(file.extension))
        continue;
      const lines = file.content.split("\n");
      for (let i = 0; i < lines.length; i++) {
        const match = lines[i].match(pattern);
        if (match) {
          const snippetStart = Math.max(0, i - 2);
          const snippetEnd = Math.min(lines.length, i + 3);
          findings.push({
            analyzer: this.analyzerName,
            severity: opts.severity,
            framework: opts.framework,
            repo: file.repo,
            filePath: file.filePath,
            lineNumber: i + 1,
            title: opts.title,
            description: opts.descriptionFn(match, file),
            snippet: lines.slice(snippetStart, snippetEnd).join("\n"),
            remediation: opts.remediationFn?.(match),
          });
        }
      }
    }
    return findings;
  }
}
