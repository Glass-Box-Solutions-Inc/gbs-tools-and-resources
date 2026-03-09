/**
 * Code analyzer — extract functions, classes, and exports from source files.
 *
 * Uses regex-based static analysis (no AST parser dependency).
 *
 * @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
 */

const path = require('path');
const { readFileSafe, findFiles } = require('../utils');

/**
 * Analyze code files in a project directory.
 * Returns counts of functions, classes, exports, and JSDoc coverage.
 */
async function analyzeCode(projectPath) {
  const jsFiles = await findFiles(projectPath, '.js');
  const tsFiles = await findFiles(projectPath, '.ts');
  const tsxFiles = await findFiles(projectPath, '.tsx');
  const pyFiles = await findFiles(projectPath, '.py');

  const allFiles = [...jsFiles, ...tsFiles, ...tsxFiles, ...pyFiles];

  const result = {
    files: [],
    totalFunctions: 0,
    totalDocumented: 0,
    totalExports: 0,
    totalClasses: 0,
  };

  for (const file of allFiles) {
    const content = await readFileSafe(file);
    if (!content) continue;

    const ext = path.extname(file);
    const analysis = ext === '.py'
      ? analyzePython(content)
      : analyzeJavaScript(content);

    result.files.push({
      path: file,
      relativePath: path.relative(projectPath, file),
      ...analysis,
    });

    result.totalFunctions += analysis.functionCount;
    result.totalDocumented += analysis.documentedFunctions;
    result.totalExports += analysis.exportCount;
    result.totalClasses += analysis.classCount;
  }

  return result;
}

function analyzeJavaScript(content) {
  const functions = content.match(/(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>))/g) || [];
  const classes = content.match(/class\s+\w+/g) || [];
  const exports = content.match(/(?:export\s+(?:default\s+)?(?:function|class|const|let|var|async)|module\.exports)/g) || [];
  const jsdoc = content.match(/\/\*\*[\s\S]*?\*\//g) || [];

  return {
    functionCount: functions.length,
    classCount: classes.length,
    exportCount: exports.length,
    documentedFunctions: jsdoc.length,
  };
}

function analyzePython(content) {
  const functions = content.match(/^\s*(?:async\s+)?def\s+\w+/gm) || [];
  const classes = content.match(/^\s*class\s+\w+/gm) || [];
  const docstrings = content.match(/"""[\s\S]*?"""|'''[\s\S]*?'''/g) || [];

  return {
    functionCount: functions.length,
    classCount: classes.length,
    exportCount: 0,
    documentedFunctions: docstrings.length,
  };
}

module.exports = { analyzeCode };
