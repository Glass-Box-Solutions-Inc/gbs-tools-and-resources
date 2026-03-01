# Access Control — merus-test-data-generator

Defines who can access what, and credential rotation procedures.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

---

## Access Matrix

| Resource | Who | How |
|----------|-----|-----|
| GCP VM (`dev-workstation`) | Engineering team | GCP IAM + SSH keys |
| GCP Secret Manager (`adjudica-production`) | Service accounts, authorized users | GCP IAM roles |
| GCP Secret Manager (`ousd-campaign`) | Service accounts, authorized users | GCP IAM roles |
| MerusCase API | Service (via OAuth client credentials) | `MERUSCASE_CLIENT_ID` + `MERUSCASE_CLIENT_SECRET` |
| MerusCase Web UI | Authenticated users (browser automation) | `MERUSCASE_EMAIL` + `MERUSCASE_PASSWORD` |
| Browserless Service | Service (API token) | `BROWSERLESS_API_TOKEN` |
| GitHub Repository | Engineering team | PAT via `~/.git-credentials` |

## Credential Inventory

| Credential | GCP Secret Name | GCP Project | Rotation Frequency |
|------------|-----------------|-------------|-------------------|
| MerusCase Client ID | `MERUSCASE_CLIENT_ID` | `adjudica-production` | On compromise |
| MerusCase Client Secret | `MERUSCASE_CLIENT_SECRET` | `adjudica-production` | 90 days |
| MerusCase Email | `meruscase-email` | `adjudica-production` | On change |
| MerusCase Password | `meruscase-password` | `adjudica-production` | 90 days |
| MerusCase Access Token | `qmeprep-meruscase-access-token` | `adjudica-production` | As needed (expires) |
| Browserless API Token | `spectacles-browserless-token` | `ousd-campaign` | 90 days |
| GitHub PAT | `github-pat-glassbox` | `ousd-campaign` | 90 days |

## Credential Rotation Procedure

### MerusCase Client Credentials

1. Generate new credentials in MerusCase admin panel
2. Update GCP Secret Manager:
   ```bash
   echo -n "NEW_CLIENT_SECRET" | gcloud secrets versions add MERUSCASE_CLIENT_SECRET \
     --data-file=- --project=adjudica-production
   ```
3. Verify: `python -c "from config import MERUSCASE_CLIENT_SECRET; print('OK')"`

### MerusCase Password

1. Change password in MerusCase web UI
2. Update GCP Secret Manager:
   ```bash
   echo -n "NEW_PASSWORD" | gcloud secrets versions add meruscase-password \
     --data-file=- --project=adjudica-production
   ```
3. Verify: `python -c "from config import MERUSCASE_PASSWORD; print(len(MERUSCASE_PASSWORD), 'chars')"`

### Browserless API Token

1. Rotate token in Browserless dashboard
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
- MerusCase API credentials are scoped to the test firm
- No production customer data is accessed — all data is generated (Faker)

## Access Reviews

| Review | Frequency | Owner |
|--------|-----------|-------|
| GCP IAM roles | Quarterly | Engineering Lead |
| Secret Manager access logs | Monthly | Security |
| MerusCase API scopes | On change | Engineering Lead |
| GitHub PAT scopes | On rotation | Engineering |
