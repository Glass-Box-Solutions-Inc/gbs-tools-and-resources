// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { describe, it, expect } from "vitest";
import {
  findRegexMatches,
  parseTypeScriptAst,
  findFunctionCalls,
  extractStringLiterals,
  findPropertyAssignments,
} from "../../src/scanners/pattern-matcher.js";

describe("findRegexMatches", () => {
  it("finds matches with correct line numbers", () => {
    const content = `line one
line two contains MATCH here
line three
another MATCH on line four`;

    const results = findRegexMatches(content, /MATCH/);
    expect(results).toHaveLength(2);
    expect(results[0].line).toBe(2);
    expect(results[0].match).toBe("MATCH");
    expect(results[1].line).toBe(4);
  });

  it("returns correct column positions", () => {
    const content = `prefix MATCH suffix`;
    const results = findRegexMatches(content, /MATCH/);
    expect(results).toHaveLength(1);
    expect(results[0].column).toBe(8);
  });

  it("provides surrounding context lines", () => {
    const content = `line 1
line 2
line 3 MATCH
line 4
line 5`;

    const results = findRegexMatches(content, /MATCH/, 1);
    expect(results).toHaveLength(1);
    // Context should include 1 line before and 1 line after
    expect(results[0].context).toContain("line 2");
    expect(results[0].context).toContain("line 3 MATCH");
    expect(results[0].context).toContain("line 4");
  });

  it("handles no matches gracefully", () => {
    const content = `nothing to see here`;
    const results = findRegexMatches(content, /MISSING/);
    expect(results).toHaveLength(0);
  });

  it("handles multiple matches on the same line", () => {
    const content = `foo bar foo baz foo`;
    const results = findRegexMatches(content, /foo/);
    expect(results).toHaveLength(3);
    expect(results[0].column).toBe(1);
    expect(results[1].column).toBe(9);
    expect(results[2].column).toBe(17);
  });

  it("supports capture groups", () => {
    const content = `const name = "hello"`;
    const results = findRegexMatches(content, /const (?<varName>\w+)/);
    expect(results).toHaveLength(1);
    expect(results[0].groups.varName).toBe("name");
  });

  it("handles context at file boundaries", () => {
    const content = `MATCH on first line
second line`;

    const results = findRegexMatches(content, /MATCH/, 5);
    expect(results).toHaveLength(1);
    // Should not crash when context extends beyond file start/end
    expect(results[0].context).toContain("MATCH");
    expect(results[0].context).toContain("second line");
  });
});

describe("parseTypeScriptAst", () => {
  it("parses valid TypeScript without errors", () => {
    const code = `
      interface User {
        id: string;
        name: string;
      }

      function greet(user: User): string {
        return \`Hello, \${user.name}\`;
      }
    `;
    const ast = parseTypeScriptAst(code);
    expect(ast).toBeDefined();
    expect(ast.statements.length).toBeGreaterThan(0);
  });

  it("parses TSX/JSX content", () => {
    const code = `
      function App() {
        return <div className="app">Hello</div>;
      }
    `;
    const ast = parseTypeScriptAst(code, "App.tsx");
    expect(ast).toBeDefined();
    expect(ast.statements.length).toBeGreaterThan(0);
  });

  it("handles syntax errors gracefully (returns partial AST)", () => {
    const code = `const x = {`;
    const ast = parseTypeScriptAst(code);
    // TypeScript parser is lenient — it produces a partial AST
    expect(ast).toBeDefined();
  });
});

describe("findFunctionCalls", () => {
  it("finds direct function calls", () => {
    const code = `
      const result = doSomething(arg1, arg2);
      const other = doSomethingElse();
    `;
    const ast = parseTypeScriptAst(code);
    const calls = findFunctionCalls(ast, "doSomething");
    expect(calls).toHaveLength(1);
    expect(calls[0].arguments).toHaveLength(2);
  });

  it("finds method calls", () => {
    const code = `
      const data = await prisma.user.findUnique({ where: { id } });
      const list = await prisma.user.findMany();
    `;
    const ast = parseTypeScriptAst(code);
    const calls = findFunctionCalls(ast, "findUnique");
    expect(calls).toHaveLength(1);
  });

  it("finds nested function calls", () => {
    const code = `
      function outer() {
        if (true) {
          doWork();
        }
      }
    `;
    const ast = parseTypeScriptAst(code);
    const calls = findFunctionCalls(ast, "doWork");
    expect(calls).toHaveLength(1);
  });

  it("returns correct line and column numbers", () => {
    const code = `const a = 1;
const b = 2;
const c = myFunc(a, b);`;
    const ast = parseTypeScriptAst(code);
    const calls = findFunctionCalls(ast, "myFunc");
    expect(calls).toHaveLength(1);
    expect(calls[0].line).toBe(3);
  });

  it("returns empty array when no calls match", () => {
    const code = `const x = 1 + 2;`;
    const ast = parseTypeScriptAst(code);
    const calls = findFunctionCalls(ast, "nonExistent");
    expect(calls).toHaveLength(0);
  });
});

describe("extractStringLiterals", () => {
  it("extracts regular string literals", () => {
    const code = `
      const greeting = "hello world";
      const name = 'TypeScript';
    `;
    const ast = parseTypeScriptAst(code);
    const literals = extractStringLiterals(ast);
    const values = literals.map((l) => l.value);
    expect(values).toContain("hello world");
    expect(values).toContain("TypeScript");
  });

  it("extracts template literals without substitutions", () => {
    const code = "const sql = `SELECT * FROM users`;";
    const ast = parseTypeScriptAst(code);
    const literals = extractStringLiterals(ast);
    const templateLiterals = literals.filter(
      (l) => l.kind === "noSubstitutionTemplate",
    );
    expect(templateLiterals).toHaveLength(1);
    expect(templateLiterals[0].value).toBe("SELECT * FROM users");
  });

  it("extracts template literal parts with substitutions", () => {
    const code = "const sql = `SELECT * FROM ${table} WHERE id = ${id}`;";
    const ast = parseTypeScriptAst(code);
    const literals = extractStringLiterals(ast);
    const templateParts = literals.filter((l) => l.kind === "template");
    // Should have head ("SELECT * FROM ") and middle (" WHERE id = ") and tail ("")
    expect(templateParts.length).toBeGreaterThanOrEqual(2);
  });

  it("includes correct line numbers", () => {
    const code = `const a = "first";
const b = "second";
const c = "third";`;
    const ast = parseTypeScriptAst(code);
    const literals = extractStringLiterals(ast);
    const second = literals.find((l) => l.value === "second");
    expect(second).toBeDefined();
    expect(second!.line).toBe(2);
  });

  it("handles empty strings", () => {
    const code = `const empty = "";`;
    const ast = parseTypeScriptAst(code);
    const literals = extractStringLiterals(ast);
    expect(literals.some((l) => l.value === "")).toBe(true);
  });
});

describe("findPropertyAssignments", () => {
  it("finds property assignments by name", () => {
    const code = `
      const config = {
        host: "localhost",
        port: 5432,
        ssl: false,
      };
    `;
    const ast = parseTypeScriptAst(code);
    const sslProps = findPropertyAssignments(ast, "ssl");
    expect(sslProps).toHaveLength(1);
    expect(sslProps[0].valueText).toBe("false");
  });

  it("finds nested property assignments", () => {
    const code = `
      const config = {
        database: {
          connection: {
            rejectUnauthorized: false,
          },
        },
      };
    `;
    const ast = parseTypeScriptAst(code);
    const props = findPropertyAssignments(ast, "rejectUnauthorized");
    expect(props).toHaveLength(1);
    expect(props[0].valueText).toBe("false");
  });

  it("returns empty array when property not found", () => {
    const code = `const x = { a: 1, b: 2 };`;
    const ast = parseTypeScriptAst(code);
    const props = findPropertyAssignments(ast, "missing");
    expect(props).toHaveLength(0);
  });

  it("finds multiple assignments of the same property name", () => {
    const code = `
      const a = { ssl: true };
      const b = { ssl: false };
    `;
    const ast = parseTypeScriptAst(code);
    const props = findPropertyAssignments(ast, "ssl");
    expect(props).toHaveLength(2);
  });
});
