# Spectacles MCP

**Source:** [Glass-Box-Solutions-Inc/Spectacles](https://github.com/Glass-Box-Solutions-Inc/Spectacles)

AI-powered browser automation platform — Playwright + Gemini vision + HITL.

## Architecture

The Spectacles MCP is a **thin HTTP client** that calls the deployed Spectacles
Cloud Run service via REST API. It does NOT import or instantiate any Spectacles
internals locally.

**Deployed Service URL:** `https://spectacles-gc2qovgs7q-uc.a.run.app`

## Setup

1. The Spectacles repo must be cloned at `/home/vncuser/Desktop/Spectacles`
2. Python `mcp` and `httpx` packages must be installed
3. Set `SPECTACLES_API_URL` environment variable (defaults to production URL)

## Config

```json
{
  "spectacles": {
    "command": "python3",
    "args": ["-m", "spectacles_mcp"],
    "cwd": "/home/vncuser/Desktop/Spectacles",
    "env": {
      "SPECTACLES_API_URL": "https://spectacles-gc2qovgs7q-uc.a.run.app"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `spectacles_health` | Check deployed service health |
| `spectacles_capabilities` | Get available automation modes |
| `spectacles_execute_task` | Submit browser automation task (Core API) |
| `spectacles_get_status` | Get task status |
| `spectacles_resume_task` | Resume paused task after HITL |
| `spectacles_cancel_task` | Cancel running task |
| `spectacles_get_actions` | Get task action history |
| `spectacles_screenshot` | Take screenshot of URL |
| `spectacles_browser_task` | Submit browser task (Skills API) |
| `spectacles_curator_status` | Get documentation curator status |
| `spectacles_curator_run` | Trigger documentation curation run |

## Optional Environment Variables

| Variable | Purpose |
|----------|---------|
| `SPECTACLES_API_URL` | Override deployed service URL |
| `CURATOR_BEARER_TOKEN` | Required for curator tools |

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
