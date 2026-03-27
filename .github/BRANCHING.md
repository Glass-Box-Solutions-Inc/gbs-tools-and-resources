# Branch-Based Development

## Branch naming

```
<package>/<type>/<short-description>
```

| Segment | Values | Example |
|---------|--------|---------|
| package | Any directory name under `packages/` | `spectacles`, `phileas`, `squeegee` |
| type | `feat`, `fix`, `refactor`, `docs`, `chore`, `test` | |
| description | kebab-case, 2-5 words | `add-gemini-cache` |

**Examples:**
- `spectacles/feat/add-gemini-cache`
- `phileas/fix/null-entity-crash`
- `squeegee/refactor/pipeline-stages`
- `hindsight/docs/api-reference`
- `multi/chore/update-deps` (cross-package)

## Workflow

1. **Branch from `main`:** `git checkout -b <package>/<type>/<description>`
2. **Work in your package directory.** CI only runs tests for packages you touched.
3. **Open a PR against `main`.** CI Gate must pass. At least 1 review required.
4. **Squash-merge** to keep `main` linear and clean.

## What CI checks

Each package job runs independently, in its own language runtime, only when that package changed:

| Language | Steps |
|----------|-------|
| Node.js | `npm ci` > `npm run lint` > `npm test` |
| Python | `pip install` > `ruff check` / `make ci` > `pytest` |
| Java | `mvn package` (compile + test) |

The **CI Gate** job aggregates all 14 package results. If any affected package fails, the gate fails and the PR cannot merge.

## Rules

- No direct push to `main` — PRs only
- CI must pass before merge
- Stale approvals are dismissed on new commits
- One package per branch (cross-package changes use `multi/<description>`)
