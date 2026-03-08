# Plan: Separate Spectacles into Standalone Repository & GCP Project

**Status:** Proposed
**Created:** 2026-02-08
**Author:** Claude Code

---

## Executive Summary

Spectacles is a fully self-contained browser automation platform currently living at `projects/spectacles/` in the GlassBoxSolutions/Sandbox monorepo. It has **zero code imports** from other Sandbox projects, making separation straightforward. This plan covers creating a standalone GitHub repo, a dedicated GCP project, and updating all cross-references.

---

## Current State

| Aspect | Current | Notes |
|--------|---------|-------|
| **GitHub** | `GlassBoxSolutions/Sandbox` → `projects/spectacles/` | Monorepo subdirectory |
| **GCP Project** | `ousd-campaign` (shared) | Shares with Legal Research, WC Paralegal |
| **Cloud Run** | `spectacles-378330630438.us-central1.run.app` | Lives in ousd-campaign |
| **Docker Registry** | `us-central1-docker.pkg.dev/ousd-campaign/...` | Shared registry |
| **Secrets** | `ousd-campaign` Secret Manager | 6+ spectacles-specific secrets |
| **Database** | SQLite (dev) / PostgreSQL (prod) | Self-contained |
| **Code Dependencies** | Zero imports from other Sandbox projects | Fully standalone |

---

## Phase 1: Create GitHub Repository

### 1.1 Create Repository

```bash
# Create new repo on GitHub
gh repo create GlassBoxSolutions/spectacles --private --description "AI-Powered Browser Automation Platform"

# Clone and set up
git clone https://github.com/GlassBoxSolutions/spectacles.git
cd spectacles
```

### 1.2 Extract Spectacles from Sandbox

Use `git filter-repo` to preserve full commit history:

```bash
# Option A: Filter-repo (preserves history)
cd /tmp
git clone https://github.com/GlassBoxSolutions/Sandbox.git spectacles-extract
cd spectacles-extract
git filter-repo --subdirectory-filter projects/spectacles

# Push to new repo
git remote add origin https://github.com/GlassBoxSolutions/spectacles.git
git push -u origin main
```

Alternatively, start fresh (simpler, loses history):

```bash
# Option B: Clean copy (fresh history)
cp -r /path/to/Sandbox/projects/spectacles/* /path/to/spectacles/
cd /path/to/spectacles
git init
git add .
git commit -m "feat: initial Spectacles standalone repo from Sandbox monorepo"
git remote add origin https://github.com/GlassBoxSolutions/spectacles.git
git push -u origin main
```

### 1.3 Update Package Structure

Current internal imports use relative paths (e.g., `from security.auth_capture import ...`). These work as-is since `spectacles/` becomes the repo root.

**No import changes needed** - the module structure is already self-contained.

### 1.4 Files to Update in New Repo

| File | Change |
|------|--------|
| `README.md` | Update repo references, remove dual-use Sandbox context |
| `CLAUDE.md` | Update paths (remove `projects/spectacles/` prefix) |
| `cloudbuild.yaml` | Update project ID, registry path |
| `Dockerfile` | No changes needed |
| `.env.example` | Update GCP_PROJECT_ID default |
| `tools/capture_auth.py` | Update AUTH_DIR default path |

### 1.5 CI/CD Setup

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Cloud Run
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_SA_EMAIL }}

      - uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: spectacles
          region: us-central1
          project_id: ${{ secrets.GCP_PROJECT_ID }}
          source: .
```

---

## Phase 2: Create GCP Project

### 2.1 Decision: New Project vs. Existing

**Option A: New dedicated GCP project** (Recommended)
- Clean separation of billing, IAM, and resources
- Independent scaling and cost tracking
- Suggested name: `spectacles-prod` or `glassbox-spectacles`

**Option B: Reuse `ousd-campaign`**
- No infrastructure work needed
- But continues sharing billing/IAM/resources
- Makes future separation harder

**Recommendation:** Option A (new project) for clean separation.

### 2.2 Create GCP Project

```bash
# Create project
gcloud projects create glassbox-spectacles \
  --name="Spectacles" \
  --organization=YOUR_ORG_ID

# Link billing account
gcloud billing projects link glassbox-spectacles \
  --billing-account=BILLING_ACCOUNT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  --project=glassbox-spectacles
```

### 2.3 Create Service Account

```bash
# Create service account for Cloud Run
gcloud iam service-accounts create spectacles-runner \
  --display-name="Spectacles Cloud Run" \
  --project=glassbox-spectacles

# Grant permissions
gcloud projects add-iam-policy-binding glassbox-spectacles \
  --member="serviceAccount:spectacles-runner@glassbox-spectacles.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding glassbox-spectacles \
  --member="serviceAccount:spectacles-runner@glassbox-spectacles.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

### 2.4 Migrate Secrets

Copy all spectacles-specific secrets from `ousd-campaign` to new project:

```bash
# List of secrets to migrate
SECRETS=(
  "spectacles-secret-key"
  "spectacles-browserless-token"
  "spectacles-slack-app-token"
  "spectacles-slack-bot-token"
  "spectacles-google-ai-api-key"
  "spectacles-slack-signing-secret"
)

# For each secret, read from old project and create in new
for secret in "${SECRETS[@]}"; do
  VALUE=$(gcloud secrets versions access latest \
    --secret="$secret" \
    --project=ousd-campaign)

  echo -n "$VALUE" | gcloud secrets create "$secret" \
    --data-file=- \
    --project=glassbox-spectacles
done
```

**Also migrate auth-related secrets** (storage states captured by auth capture):
```bash
# List auth storage state secrets
gcloud secrets list --project=ousd-campaign \
  --filter="name:storage-state" --format="value(name)"

# Migrate each one
```

### 2.5 Create Artifact Registry

```bash
gcloud artifacts repositories create spectacles \
  --repository-format=docker \
  --location=us-central1 \
  --project=glassbox-spectacles
```

### 2.6 Deploy to New Cloud Run

```bash
gcloud run deploy spectacles \
  --source . \
  --region us-central1 \
  --project glassbox-spectacles \
  --service-account spectacles-runner@glassbox-spectacles.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --set-secrets="SECRET_KEY=spectacles-secret-key:latest,BROWSERLESS_API_TOKEN=spectacles-browserless-token:latest,SLACK_APP_TOKEN=spectacles-slack-app-token:latest,SLACK_BOT_TOKEN=spectacles-slack-bot-token:latest,GOOGLE_AI_API_KEY=spectacles-google-ai-api-key:latest,SLACK_SIGNING_SECRET=spectacles-slack-signing-secret:latest" \
  --set-env-vars="GCP_PROJECT_ID=glassbox-spectacles,ENVIRONMENT=production"
```

**New URL:** `https://spectacles-XXXXXXXXXX.us-central1.run.app`

---

## Phase 3: Update Sandbox References

### 3.1 Files to Update in Sandbox

All references are documentation/configuration only (no code imports). Update the Spectacles production URL in:

| File | Change |
|------|--------|
| `SPECTACLES_INTEGRATION_GUIDE.md` | Update service URL |
| `SPECTACLES_AUTH_TESTING_QUICK_START.md` | Update API URLs |
| `SPECTACLES_AUTH_FLOW_TESTING.md` | Update API URLs |
| `.claude/instructions/testing-visual.md` | Update service URL |
| `.claude/instructions/core-principles.md` | Update service URL |
| `.claude/references/quick-commands.md` | Update API URLs |
| `projects/spectacles/CLAUDE.md` | Remove or replace with pointer to new repo |
| `.mcp.json` | Update MCP server path to new repo |

### 3.2 Keep Spectacles Stub in Sandbox

Replace `projects/spectacles/` with a pointer file:

```markdown
# Spectacles - Moved to Standalone Repository

Spectacles has been moved to its own repository:
- **GitHub:** https://github.com/GlassBoxSolutions/spectacles
- **Production:** https://spectacles-XXXXXXXXXX.us-central1.run.app
- **GCP Project:** glassbox-spectacles

See the new repository for all documentation and source code.
```

### 3.3 Update MCP Configuration

Update `.mcp.json` in Sandbox to point to new Spectacles installation:

```json
"spectacles": {
  "command": "python",
  "args": ["-m", "mcp.server"],
  "cwd": "/path/to/spectacles",
  "env": {
    "SPECTACLES_API_URL": "https://spectacles-XXXXXXXXXX.us-central1.run.app",
    "BROWSERLESS_API_TOKEN": "${BROWSERLESS_API_TOKEN}",
    "GOOGLE_AI_API_KEY": "${GOOGLE_AI_API_KEY}"
  }
}
```

Or use the REST API directly (no local MCP server needed):

```json
"spectacles": {
  "url": "https://spectacles-XXXXXXXXXX.us-central1.run.app/mcp"
}
```

---

## Phase 4: Verify & Decommission

### 4.1 Verification Checklist

- [ ] New repo builds and deploys successfully
- [ ] Health check returns OK: `curl https://NEW_URL/health`
- [ ] API docs accessible: `https://NEW_URL/docs`
- [ ] Auth capture CLI works: `python tools/capture_auth.py --service google`
- [ ] Auth capture API works: `POST /api/skills/auth-capture`
- [ ] Task submission works: `POST /api/tasks/`
- [ ] Slack notifications work (test webhook)
- [ ] MCP server accessible from Claude Code
- [ ] All tests pass: `pytest tests/`
- [ ] Observable tests pass: `python tests/observable/run_tests.py`

### 4.2 Decommission Old Service

After verification period (1-2 weeks with both running):

```bash
# Delete old Cloud Run service
gcloud run services delete spectacles \
  --region=us-central1 \
  --project=ousd-campaign

# Clean up old secrets (optional - keep for reference)
# Only delete if confirmed no other services use them
```

### 4.3 Remove from Sandbox

```bash
# Remove spectacles directory from Sandbox (keep stub)
rm -rf projects/spectacles/api projects/spectacles/core ...
# Keep projects/spectacles/README.md as pointer

git add -A
git commit -m "chore: remove Spectacles source (moved to GlassBoxSolutions/spectacles)"
```

---

## Shared Resources (Post-Separation)

These resources are shared and should NOT be duplicated:

| Resource | Location | Shared With | Action |
|----------|----------|-------------|--------|
| Browserless.io account | Paid subscription | Merus Expert, Legal Research | Share token (same Browserless account) |
| Slack workspace | Adjudica | All projects | Keep same webhooks |
| Google AI API key | Google Cloud | Other VLM users | Can share or create separate |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Broken references | Low | All refs are documentation/URLs, not code imports |
| Service downtime during migration | Medium | Run both services in parallel during transition |
| Secret migration missed | Medium | Script migration, verify each secret |
| Billing confusion | Low | New project has clean billing isolation |
| MCP server path change | Medium | Update `.mcp.json`, test before removing old |

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: GitHub repo | 1-2 hours | None |
| Phase 2: GCP project | 2-3 hours | GitHub repo ready |
| Phase 3: Update Sandbox | 1 hour | New URL known |
| Phase 4: Verify & decommission | 1-2 weeks | All phases complete |
| **Total Active Work** | **4-6 hours** | |

---

## Decision Points

Before starting, confirm:

1. **New GCP project name:** `glassbox-spectacles` or alternative?
2. **Git history:** Preserve with `filter-repo` or fresh start?
3. **Shared secrets:** Copy to new project or grant cross-project access?
4. **Decommission timeline:** How long to run both services in parallel?

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
