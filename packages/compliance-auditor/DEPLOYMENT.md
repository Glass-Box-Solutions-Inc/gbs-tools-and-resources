# Compliance Auditor -- GCP Deployment Guide

This document covers the GCP infrastructure setup for deploying the compliance-auditor service to Cloud Run.

## Prerequisites

- `gcloud` CLI installed and authenticated
- Access to the GBS GCP organization
- A GitHub Personal Access Token with `repo` scope for the Glass-Box-Solutions-Inc org

## GCP Project Setup

### 1. Create the GCP Project

```bash
gcloud projects create glassbox-compliance-auditor \
  --name="Compliance Auditor" \
  --organization=<GBS_ORG_ID>

gcloud config set project glassbox-compliance-auditor
```

### 2. Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  containerregistry.googleapis.com
```

### 3. Create Cloud SQL Instance

```bash
gcloud sql instances create compliance-auditor-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-size=10GB \
  --storage-auto-increase

gcloud sql databases create ca_production \
  --instance=compliance-auditor-db

gcloud sql users create ca_app \
  --instance=compliance-auditor-db \
  --password="<generate-strong-password>"
```

### 4. Store Secrets

```bash
# Database connection string
echo -n "postgresql://ca_app:<password>@/ca_production?host=/cloudsql/glassbox-compliance-auditor:us-central1:compliance-auditor-db&sslmode=require" | \
  gcloud secrets create database-url --data-file=-

# GitHub PAT
echo -n "<github-pat>" | \
  gcloud secrets create github-pat --data-file=-
```

### 5. Create Service Account

```bash
gcloud iam service-accounts create compliance-auditor-runner \
  --display-name="Compliance Auditor Runner"

# Grant Cloud SQL Client access
gcloud projects add-iam-policy-binding glassbox-compliance-auditor \
  --member="serviceAccount:compliance-auditor-runner@glassbox-compliance-auditor.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# Grant Secret Manager access
gcloud secrets add-iam-policy-binding database-url \
  --member="serviceAccount:compliance-auditor-runner@glassbox-compliance-auditor.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding github-pat \
  --member="serviceAccount:compliance-auditor-runner@glassbox-compliance-auditor.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Build and Deploy

Deployed via Cloud Build trigger from the `gbs-tools-and-resources` monorepo:

- **Cloud Build trigger:** Points to `gbs-tools-and-resources` repo, `dir: packages/compliance-auditor/`
- **Build config:** `packages/compliance-auditor/cloudbuild.yaml`

### 1. Build Container Image

```bash
gcloud builds submit --tag gcr.io/glassbox-compliance-auditor/compliance-auditor
```

### 2. Deploy to Cloud Run

```bash
gcloud run deploy compliance-auditor \
  --image=gcr.io/glassbox-compliance-auditor/compliance-auditor \
  --region=us-central1 \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=compliance-auditor-runner@glassbox-compliance-auditor.iam.gserviceaccount.com \
  --set-secrets="DATABASE_URL=database-url:latest,GITHUB_TOKEN=github-pat:latest" \
  --set-env-vars="GITHUB_ORG=Glass-Box-Solutions-Inc,NODE_ENV=production" \
  --add-cloudsql-instances=glassbox-compliance-auditor:us-central1:compliance-auditor-db \
  --memory=1Gi \
  --cpu=1 \
  --timeout=900 \
  --min-instances=0 \
  --max-instances=1 \
  --port=5530
```

### 3. Run Initial Database Migration

```bash
SERVICE_URL=$(gcloud run services describe compliance-auditor \
  --project=glassbox-compliance-auditor \
  --region=us-central1 \
  --format='value(status.url)')

# The CMD in Dockerfile runs prisma migrate deploy before starting the server,
# so the first deployment automatically applies migrations.
echo "Service deployed at: ${SERVICE_URL}"
```

## Cloud Scheduler (Optional)

Set up a daily compliance scan:

```bash
gcloud scheduler jobs create http compliance-scan-daily \
  --schedule="0 6 * * *" \
  --uri="${SERVICE_URL}/api/run" \
  --http-method=POST \
  --body='{"framework":"both"}' \
  --headers="Content-Type=application/json" \
  --oidc-service-account-email=compliance-auditor-runner@glassbox-compliance-auditor.iam.gserviceaccount.com \
  --location=us-central1
```

## Infrastructure Summary

| Resource | Value |
|----------|-------|
| **GCP Project** | `glassbox-compliance-auditor` |
| **Region** | `us-central1` |
| **Cloud Run Service** | `compliance-auditor` |
| **Container Image** | `gcr.io/glassbox-compliance-auditor/compliance-auditor` |
| **Service Account** | `compliance-auditor-runner@glassbox-compliance-auditor.iam.gserviceaccount.com` |
| **Cloud SQL Instance** | `compliance-auditor-db` (PostgreSQL 15) |
| **Secrets** | `database-url`, `github-pat` |
| **Memory** | 1Gi |
| **CPU** | 1 |
| **Timeout** | 900s (15 min) |
| **Min Instances** | 0 (scale to zero) |
| **Max Instances** | 1 (no parallel scans) |
| **Port** | 5530 |

## Triggering a Scan

### Manual trigger via gcloud

```bash
SERVICE_URL=$(gcloud run services describe compliance-auditor \
  --project=glassbox-compliance-auditor \
  --region=us-central1 \
  --format='value(status.url)')

# Full org scan
curl -X POST "${SERVICE_URL}/api/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"framework": "both"}'

# Single repo scan
curl -X POST "${SERVICE_URL}/api/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"repos": ["adjudica-ai-app"], "framework": "hipaa"}'

# Check status
curl "${SERVICE_URL}/api/status" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"

# Get Markdown report
curl "${SERVICE_URL}/api/reports/<scan-id>/markdown" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

## Monitoring

- Cloud Run logs are available in Cloud Logging (Pino JSON format)
- Set up alerting on `severity>=ERROR` log entries
- Monitor Cloud SQL connection counts and storage usage
- Set up uptime checks on the `/health` endpoint (if using external monitoring)

## Cost Optimization

- Cloud Run scales to zero when idle (no cost when not scanning)
- Cloud SQL uses `db-f1-micro` tier (suitable for periodic scan workloads)
- `--max-instances=1` prevents concurrent scans that could exceed GitHub API limits
- Shallow clones (`--depth=1`) minimize disk usage and clone time

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
