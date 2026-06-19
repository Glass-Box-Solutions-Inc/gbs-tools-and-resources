# CLI-Anything: Adjudica Staging

An agent-native CLI harness for driving browser automation and tests on Adjudica staging environments (`staging.app.adjudica.ai` and `staging.file-review.adjudica.ai`) using Playwright.

## Installation
Install in editable mode:
```bash
pip install -e .
```

## Config
Configure staging site variables:
```bash
cli-anything-adjudica-staging auth setup --url https://staging.app.adjudica.ai --email lawyer@adjudica.ai --password password123 --firm-slug smith-associates
```

## Usage
Login to establish storageState:
```bash
cli-anything-adjudica-staging auth login
```

Verify connection status:
```bash
cli-anything-adjudica-staging auth status
```

Upload a document to a specific matter:
```bash
cli-anything-adjudica-staging document upload --file test.pdf --matter-id 123
```

Execute staging Playwright E2E tests:
```bash
cli-anything-adjudica-staging test run --suite staging
```
