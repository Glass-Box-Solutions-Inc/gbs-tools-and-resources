# cli-anything-meruscase

Agent-native CLI for MerusCase — California Workers' Compensation case management.

## Prerequisites

- Python 3.10+
- `playwright install chromium` (for case creation only)
- MerusCase OAuth token in GCP Secret Manager or `~/.meruscase_token`

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Interactive REPL (default)
cli-anything-meruscase

# Subcommand mode
cli-anything-meruscase case list
cli-anything-meruscase case find "Smith"
cli-anything-meruscase case get 12345
cli-anything-meruscase case create "SMITH, JOHN"

cli-anything-meruscase billing bill-time --case 12345 --hours 0.5 --desc "Review medical records"
cli-anything-meruscase billing add-cost --case 12345 --amount 25.00 --desc "Filing fee"
cli-anything-meruscase billing summary --case 12345

cli-anything-meruscase activity list --case 12345
cli-anything-meruscase activity add-note --case 12345 --subject "Called client"

cli-anything-meruscase document upload --case 12345 --file /path/to/report.pdf
cli-anything-meruscase document list --case 12345

cli-anything-meruscase party list --case 12345

# JSON output (for agents)
cli-anything-meruscase --json case list

# Auth
cli-anything-meruscase auth login
cli-anything-meruscase auth status
```

## Credentials

Token is loaded automatically from:
1. GCP Secret Manager (`qmeprep-meruscase-access-token`, project `adjudica-internal`)
2. Env var `MERUSCASE_ACCESS_TOKEN`
3. File `~/.meruscase_token`
