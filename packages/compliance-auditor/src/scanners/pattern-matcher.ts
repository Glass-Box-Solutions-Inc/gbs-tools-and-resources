// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Regex and TypeScript AST pattern matching utilities for compliance analyzers.
// Uses the TypeScript compiler API at runtime for AST-level code analysis,
// which enables detection of patterns that are difficult or impossible to
// catch with regex alone (e.g., nested function calls, string literal
// extraction across template expressions).

import ts from "typescript";

export interface RegexMatch {
  line: number;
  column: number;
  match: string;
  groups: Record<string, string | undefined>;
  context: string;
}

/**
 * Find all regex matches in a string, returning line numbers and context.
 */
export function findRegexMatches(
  content: string,
  pattern: RegExp,
  contextLines: number = 2,
): RegexMatch[] {
  const lines = content.split("\n");
  const results: RegexMatch[] = [];
  const flags = pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g";
  const globalPattern = new RegExp(pattern.source, flags);

  for (let i = 0; i < lines.length; i++) {
    globalPattern.lastIndex = 0;
    let lineMatch: RegExpExecArray | null;
    while ((lineMatch = globalPattern.exec(lines[i])) !== null) {
      const contextStart = Math.max(0, i - contextLines);
      const contextEnd = Math.min(lines.length, i + contextLines + 1);
      results.push({
        line: i + 1,
        column: lineMatch.index + 1,
        match: lineMatch[0],
        groups: lineMatch.groups ?? {},
        context: lines.slice(contextStart, contextEnd).join("\n"),
      });
      // Prevent infinite loops on zero-length matches
      if (lineMatch[0].length === 0) break;
    }
  }

  return results;
}

/**
 * Parse TypeScript/JavaScript source code into an AST using the TypeScript
 * compiler API. This does NOT require tsconfig or type-checking — it performs
 * syntactic parsing only, which is fast and sufficient for static analysis.
 */
export function parseTypeScriptAst(
  content: string,
  fileName: string = "analysis.ts",
): ts.SourceFile {
  return ts.createSourceFile(
    fileName,
    content,
    ts.ScriptTarget.Latest,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}

/**
 * Find all call expressions that invoke a specific function name.
 * Handles both direct calls (foo()) and method calls (obj.foo()).
 */
export function findFunctionCalls(
  sourceFile: ts.SourceFile,
  functionName: string,
): Array<{
  line: number;
  column: number;
  arguments: ts.NodeArray<ts.Expression>;
  fullText: string;
}> {
  const results: Array<{
    line: number;
    column: number;
    arguments: ts.NodeArray<ts.Expression>;
    fullText: string;
  }> = [];

  function visit(node: ts.Node): void {
    if (ts.isCallExpression(node)) {
      let name: string | null = null;

      // Direct call: functionName(...)
      if (ts.isIdentifier(node.expression)) {
        name = node.expression.text;
      }
      // Method call: obj.functionName(...)
      else if (ts.isPropertyAccessExpression(node.expression)) {
        name = node.expression.name.text;
      }

      if (name === functionName) {
        const { line, character } =
          sourceFile.getLineAndCharacterOfPosition(node.getStart());
        results.push({
          line: line + 1,
          column: character + 1,
          arguments: node.arguments,
          fullText: node.getText(sourceFile),
        });
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return results;
}

/**
 * Extract all string literals from the AST, including template literal
 * head/middle/tail portions. Useful for detecting SQL keywords, PHI data,
 * or other sensitive content embedded in string values.
 */
export function extractStringLiterals(
  sourceFile: ts.SourceFile,
): Array<{
  value: string;
  line: number;
  column: number;
  kind: "string" | "template" | "noSubstitutionTemplate";
}> {
  const results: Array<{
    value: string;
    line: number;
    column: number;
    kind: "string" | "template" | "noSubstitutionTemplate";
  }> = [];

  function visit(node: ts.Node): void {
    if (ts.isStringLiteral(node)) {
      const { line, character } =
        sourceFile.getLineAndCharacterOfPosition(node.getStart());
      results.push({
        value: node.text,
        line: line + 1,
        column: character + 1,
        kind: "string",
      });
    } else if (ts.isNoSubstitutionTemplateLiteral(node)) {
      const { line, character } =
        sourceFile.getLineAndCharacterOfPosition(node.getStart());
      results.push({
        value: node.text,
        line: line + 1,
        column: character + 1,
        kind: "noSubstitutionTemplate",
      });
    } else if (ts.isTemplateHead(node)) {
      const { line, character } =
        sourceFile.getLineAndCharacterOfPosition(node.getStart());
      results.push({
        value: node.text,
        line: line + 1,
        column: character + 1,
        kind: "template",
      });
    } else if (ts.isTemplateMiddle(node)) {
      const { line, character } =
        sourceFile.getLineAndCharacterOfPosition(node.getStart());
      results.push({
        value: node.text,
        line: line + 1,
        column: character + 1,
        kind: "template",
      });
    } else if (ts.isTemplateTail(node)) {
      const { line, character } =
        sourceFile.getLineAndCharacterOfPosition(node.getStart());
      results.push({
        value: node.text,
        line: line + 1,
        column: character + 1,
        kind: "template",
      });
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return results;
}

/**
 * Find property assignments matching a given property name within the AST.
 * Useful for detecting configuration patterns (e.g., ssl: false).
 */
export function findPropertyAssignments(
  sourceFile: ts.SourceFile,
  propertyName: string,
): Array<{
  line: number;
  column: number;
  valueText: string;
  fullText: string;
}> {
  const results: Array<{
    line: number;
    column: number;
    valueText: string;
    fullText: string;
  }> = [];

  function visit(node: ts.Node): void {
    if (ts.isPropertyAssignment(node)) {
      const name = node.name.getText(sourceFile);
      if (name === propertyName) {
        const { line, character } =
          sourceFile.getLineAndCharacterOfPosition(node.getStart());
        results.push({
          line: line + 1,
          column: character + 1,
          valueText: node.initializer.getText(sourceFile),
          fullText: node.getText(sourceFile),
        });
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return results;
}
