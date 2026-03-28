# Access Control — merus-test-data-generator

Defines who can access what, and credential rotation procedures.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

---

## Access Matrix

| Resource | Who | How |
|----------|-----|-----|
| GCP VM (`dev-workstation`) | Engineering team | GCP IAM + SSH keys |
| GCP Secret Manager (`adjudica-internal`) | Service accounts, authorized users | GCP IAM roles |
| GCP Secret Manager (`ousd-campaign`) | Service accounts, authorized users | GCP IAM roles |
| MerusCase API | Service (via OAuth client credentials) | `MERUSCASE_CLIENT_ID` + `MERUSCASE_CLIENT_SECRET` |
| MerusCase Web UI | Authenticated users (browser automation) | `MERUSCASE_EMAIL` + `MERUSCASE_PASSWORD` |
| Browserless Service | Service (API token) | `BROWSERLESS_API_TOKEN` |
| GitHub Repository | Engineering team | PAT via `~/.git-credentials` |

## Credential Inventory

### Environment Labels

All MerusCase secrets in GCP Secret Manager carry an `environment` label of either `staging` or `production`. This label determines which firm the credential authorizes access to.

- **`environment=staging`** — Test firm used during development and QA. Safe to use for generating and uploading test cases.
- **`environment=production`** — Slater & Associates on Adjudica. **Not yet stored. Off-limits until staging is fully vetted.**

| Credential | GCP Secret Name | GCP Project | Environment Label | Rotation Frequency |
|------------|-----------------|-------------|-------------------|-------------------|
| MerusCase Client ID | `MERUSCASE_CLIENT_ID` | `adjudica-internal` | `staging` | On compromise |
| MerusCase Client Secret | `MERUSCASE_CLIENT_SECRET` | `adjudica-internal` | `staging` | 90 days |
| MerusCase Email | `meruscase-email` | `adjudica-internal` | `staging` | On change |
| MerusCase Password | `meruscase-password` | `adjudica-internal` | `staging` | 90 days |
| MerusCase Access Token | `merus-expert-access-token` | `ousd-campaign` | — | As needed (expires) |
| Browserless API Token | `spectacles-browserless-token` | `ousd-campaign` | — | 90 days |
| GitHub PAT | `github-pat-glassbox` | `adjudica-internal` | — | 90 days |

> **Production credentials do not exist yet.** When production is authorized, a separate secret version with `environment=production` will be created. Until then, any code path that would touch production MerusCase credentials must be considered out of scope.

## Credential Rotation Procedure

### MerusCase Client Credentials

These are staging credentials (`environment=staging` label). Do not rotate production credentials until production has been formally authorized.

1. Generate new credentials in MerusCase admin panel (staging firm)
2. Update GCP Secret Manager:
   ```bash
   echo -n "NEW_CLIENT_SECRET" | gcloud secrets versions add MERUSCASE_CLIENT_SECRET \
     --data-file=- --project=adjudica-internal
   ```
3. Verify: `python -c "from config import MERUSCASE_CLIENT_SECRET; print('OK')"`

### MerusCase Password

1. Change password in MerusCase web UI (staging firm)
2. Update GCP Secret Manager:
   ```bash
   echo -n "NEW_PASSWORD" | gcloud secrets versions add meruscase-password \
     --data-file=- --project=adjudica-internal
   ```
3. Verify: `python -c "from config import MERUSCASE_PASSWORD; print(len(MERUSCASE_PASSWORD), 'chars')"`

### MerusCase Access Token

The access token (`merus-expert-access-token`) is short-lived and refreshed automatically by the merus-expert service. Manual rotation is only needed on compromise.

```bash
echo -n "NEW_TOKEN" | gcloud secrets versions add merus-expert-access-token \
  --data-file=- --project=ousd-campaign
```

### Browserless API Token

Case creation uses Browserless cloud (not a local browser). The token is stored in `ousd-campaign`.

1. Rotate token in the Browserless dashboard
2. Update GCP Secret Manager:
   ```bash
   echo -n "NEW_TOKEN" | gcloud secrets versions add spectacles-browserless-token \
     --data-file=- --project=ousd-campaign
   ```

### GitHub PAT

See `CLAUDE.md` → `.claude/instructions/git-authentication.md` for full procedure.

## Principle of Least Privilege

- The tool runs as a single-user process on a dev VM
- GCP IAM limits Secret Manager access to authorized service accounts
- All active MerusCase credentials are labeled `environment=staging` and scoped to the test firm only
- Production credentials (Slater & Associates) are not stored and must not be created until staging is vetted
- Case creation uses Browserless cloud — no local browser or local network exposure
- No production customer data is accessed — all data is generated (Faker)

## Access Reviews

| Review | Frequency | Owner |
|--------|-----------|-------|
| GCP IAM roles | Quarterly | Engineering Lead |
| Secret Manager access logs | Monthly | Security |
| MerusCase API scopes | On change | Engineering Lead |
| GitHub PAT scopes | On rotation | Engineering |
