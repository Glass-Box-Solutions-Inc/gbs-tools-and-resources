// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type Framework = "soc2" | "hipaa" | "both";

export interface ScannedFile {
  repo: string;
  filePath: string;
  content: string;
  extension: string;
}

export interface ComplianceFindingInput {
  analyzer: string;
  severity: Severity;
  framework: Framework;
  repo: string;
  filePath: string;
  lineNumber?: number;
  title: string;
  description: string;
  snippet?: string;
  remediation?: string;
}

export interface AnalyzerResult {
  analyzerName: string;
  findings: ComplianceFindingInput[];
  filesScanned: number;
  durationMs: number;
}

export interface ScanSummary {
  scanId: string;
  status: string;
  framework: string;
  startedAt: string;
  completedAt: string | null;
  reposScanned: number;
  filesScanned: number;
  totalFindings: number;
  bySeverity: Record<Severity, number>;
  byAnalyzer: Record<string, number>;
  byRepo: Record<string, number>;
}

export interface RunRequest {
  repos?: string[];
  analyzers?: string[];
  framework?: Framework;
}
