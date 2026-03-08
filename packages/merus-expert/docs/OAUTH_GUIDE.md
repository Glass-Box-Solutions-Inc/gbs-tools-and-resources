# MerusCase OAuth Token Guide

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

---

## Overview

The merus-expert service communicates with the MerusCase REST API (`api.meruscase.com`) using an **OAuth 2.0 access token**. This token is required for all API-based operations — case search, billing, activities, document upload, and the AI agent chat. Browser automation (matter creation) uses separate login credentials and does not require an OAuth token.

**Token flow:** Your OAuth app credentials (client ID + secret) are used once to acquire an access token via an authorization code flow. The token is saved to disk and reused by the service until it expires or is rejected.

---

## Prerequisites

Before acquiring a token, you need four values in your `.env`:

| Variable | Where to Get It |
|----------|----------------|
| `MERUSCASE_EMAIL` | Your MerusCase login email |
| `MERUSCASE_PASSWORD` | Your MerusCase login password |
| `MERUSCASE_API_CLIENT_ID` | MerusCase 3rd Party Apps → App Publisher (see below) |
| `MERUSCASE_API_CLIENT_SECRET` | Same location as client ID |

---

## Getting OAuth App Credentials

If you already have an OAuth app registered in MerusCase, skip to **Retrieving Existing Credentials**.

### Registering a New App

1. Log into MerusCase at `https://meruscase.com`
2. Navigate to **Settings → 3rd Party Apps → App Publisher**
3. Click **Create New App**
4. Fill in app name (e.g., "merus-expert") and callback URL
5. Save — you'll receive a **Client ID** and **Client Secret**
6. Add both to your `.env` file

### Retrieving Existing Credentials

If an app is already registered, use these scripts to extract the credentials:

| Script | What It Does |
|--------|-------------|
| `get_oauth_creds.py` | Navigates to 3rd Party Apps → App Publisher to display credentials |
| `extract_oauth_creds.py` | Clicks on an existing app entry to extract client ID and secret |

```bash
# View credentials for an existing app
python get_oauth_creds.py

# Or extract from a specific app entry
python extract_oauth_creds.py
```

Both scripts use Playwright browser automation to log into MerusCase and navigate to the credentials page. They require `MERUSCASE_EMAIL` and `MERUSCASE_PASSWORD` in your `.env`.

---

## Acquiring a Token

Four scripts are available. Choose based on your situation:

| Script | Method | When to Use |
|--------|--------|------------|
| `oauth_browser_flow.py` | Fully automated browser flow | **Recommended.** Works when no reCAPTCHA is present. |
| `complete_oauth.py` | Automated with checkbox/button handling | When MerusCase shows a "Yep" confirmation button and consent checkbox. |
| `oauth_via_main.py` | Login via main site, then OAuth | When `api.meruscase.com` login has reCAPTCHA blocking. Bypasses by authenticating through `meruscase.com` first. |
| `manual_oauth.py` | Human-in-the-loop (120s window) | **Fallback.** Opens browser — you log in and authorize manually while the script captures the token. |

### Recommended Flow

```bash
# 1. Try the fully automated flow first
python oauth_browser_flow.py

# 2. If reCAPTCHA blocks the API login page, bypass via main site
python oauth_via_main.py

# 3. If consent page has special UI (checkbox + "Yep" button)
python complete_oauth.py

# 4. Last resort — do it manually while the script watches
python manual_oauth.py
```

All scripts:
- Read credentials from `.env` (via `python-dotenv`)
- Save screenshots to `screenshots/oauth_*/` for debugging
- Print the access token to the console on success
- Save the token to `.meruscase_token`

---

## Token Storage

### Where the Token Lives

The token is saved to **`.meruscase_token`** in the project root. This file is gitignored.

### How the Service Reads It

The service loads the token at startup via two mechanisms (checked in order):

1. **`MERUSCASE_ACCESS_TOKEN` env var** — if set, used directly
2. **`MERUSCASE_TOKEN_FILE`** — path to the token file (defaults to `.meruscase_token`)

For local development, the token file approach is simplest — just run an OAuth script and the service picks it up automatically.

For production, set `MERUSCASE_ACCESS_TOKEN` directly as an environment variable (see **Production Token Management** below).

---

## Token Lifecycle

| Aspect | Detail |
|--------|--------|
| **Format** | Bearer token string |
| **Expiry** | No documented expiry from MerusCase. Tokens appear to be long-lived. |
| **Renewal signal** | API returns **HTTP 401 Unauthorized** |
| **Renewal action** | Re-run any acquisition script above |
| **Rotation** | No automatic refresh token flow — manual re-acquisition required |

### When to Re-Acquire

- The service logs `401` errors from MerusCase API calls
- You see `"error": "Unauthorized"` in API responses
- After a MerusCase password change
- After revoking the app in MerusCase settings

---

## Production Token Management

In production (Cloud Run, GCP), store the token in **GCP Secret Manager** instead of a file:

```bash
# Store the token (after acquiring it locally)
gcloud secrets create meruscase-oauth-token \
  --project=YOUR_GCP_PROJECT \
  --data-file=.meruscase_token

# Or from a variable (never echo tokens in shared terminals)
printf '%s' "$TOKEN" | gcloud secrets versions add meruscase-oauth-token \
  --project=YOUR_GCP_PROJECT \
  --data-file=-
```

In your Cloud Run service configuration, map the secret to the environment variable:

```yaml
env:
  - name: MERUSCASE_ACCESS_TOKEN
    valueFrom:
      secretKeyRef:
        name: meruscase-oauth-token
        version: latest
```

To rotate in production:
1. Run an OAuth acquisition script locally
2. Update the secret version in GCP Secret Manager
3. Redeploy or restart the Cloud Run service

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| reCAPTCHA blocks login | API login page (`api.meruscase.com`) has bot detection | Use `oauth_via_main.py` to log in through `meruscase.com` first |
| Consent page not loading | OAuth authorize URL redirects unexpectedly | Check `MERUSCASE_API_CLIENT_ID` is correct. Verify app is still active in MerusCase settings. |
| Token rejected (401) | Token expired or revoked | Re-run any acquisition script to get a fresh token |
| "No code in redirect URL" | Authorization wasn't completed | Use `manual_oauth.py` — click through the consent page manually |
| Script hangs at login | Page layout changed or element selectors stale | Check `screenshots/oauth_*/` for what the script saw. Update selectors if needed. |
| `.meruscase_token` empty | Script failed silently | Check script console output. Re-run with `LOG_LEVEL=DEBUG`. |
| Service ignores new token | Token file not reloaded | Restart the service (`uvicorn` or Docker container) — token is read at startup |

---

## Related Documentation

- [Developer Quick Start](DEVELOPER_QUICKSTART.md) — full local setup guide
- [Agent Documentation](AGENT_DOCUMENTATION.md) — AI agent tools and capabilities
- [MerusCase API Guide](MERUSCASE_API_DEVELOPER_GUIDE.md) — raw API reference
