# Deployment Guide -- Invoice Reconciliation Tester

GCP infrastructure setup for the invoice-reconciliation-tester Cloud Run service.

## Prerequisites

- `gcloud` CLI installed and authenticated
- Docker installed locally
- Access to the GBS GCP organization

## 1. Create GCP Project

```bash
gcloud projects create glassbox-irt \
  --name="Invoice Reconciliation Tester" \
  --organization=YOUR_ORG_ID

gcloud config set project glassbox-irt

gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com
```

## 2. Create Cloud SQL Instance

```bash
gcloud sql instances create irt-postgres \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-size=10GB \
  --storage-type=SSD \
  --availability-type=zonal

gcloud sql databases create irt_prod \
  --instance=irt-postgres

gcloud sql users set-password postgres \
  --instance=irt-postgres \
  --password=<generate-secure-password>
```

## 3. Create Service Account

```bash
gcloud iam service-accounts create irt-runner \
  --display-name="IRT Cloud Run Runner"

gcloud projects add-iam-policy-binding glassbox-irt \
  --member="serviceAccount:irt-runner@glassbox-irt.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding glassbox-irt \
  --member="serviceAccount:irt-runner@glassbox-irt.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## 4. Store Secrets

```bash
echo -n "postgresql://postgres:<password>@/<db>?host=/cloudsql/glassbox-irt:us-central1:irt-postgres" | \
  gcloud secrets create database-url --data-file=-

# Optional: GitHub and Linear tokens for live validation
echo -n "<your-github-pat>" | \
  gcloud secrets create github-token --data-file=-

echo -n "<your-linear-api-key>" | \
  gcloud secrets create linear-api-key --data-file=-
```

## 5. Build and Push Container

```bash
docker build -t gcr.io/glassbox-irt/invoice-reconciliation-tester:latest .

docker push gcr.io/glassbox-irt/invoice-reconciliation-tester:latest
```

## 6. Deploy to Cloud Run

```bash
gcloud run deploy invoice-reconciliation-tester \
  --image=gcr.io/glassbox-irt/invoice-reconciliation-tester:latest \
  --region=us-central1 \
  --platform=managed \
  --service-account=irt-runner@glassbox-irt.iam.gserviceaccount.com \
  --set-env-vars="PORT=5520,NODE_ENV=production" \
  --set-secrets="DATABASE_URL=database-url:latest" \
  --set-secrets="GITHUB_TOKEN=github-token:latest" \
  --set-secrets="LINEAR_API_KEY=linear-api-key:latest" \
  --add-cloudsql-instances=glassbox-irt:us-central1:irt-postgres \
  --memory=512Mi \
  --cpu=1 \
  --timeout=900 \
  --min-instances=0 \
  --max-instances=1 \
  --no-allow-unauthenticated
```

## 7. Set Up Cloud Scheduler (Optional)

```bash
gcloud scheduler jobs create http irt-weekly \
  --project=glassbox-irt \
  --location=us-central1 \
  --schedule="0 8 * * 1" \
  --uri="$(gcloud run services describe invoice-reconciliation-tester \
    --region=us-central1 --format='value(status.url)')/api/run" \
  --http-method=POST \
  --oidc-service-account-email=irt-runner@glassbox-irt.iam.gserviceaccount.com \
  --oidc-token-audience="$(gcloud run services describe invoice-reconciliation-tester \
    --region=us-central1 --format='value(status.url)')" \
  --headers="Content-Type=application/json" \
  --message-body='{}'
```

## 8. Verify Deployment

```bash
# Get service URL
URL=$(gcloud run services describe invoice-reconciliation-tester \
  --region=us-central1 --format='value(status.url)')

# Health check (no auth required)
curl -s "${URL}/health" | jq .

# Trigger a test run (requires OIDC token)
curl -X POST "${URL}/api/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{}'

# Check status
curl -s "${URL}/api/status" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" | jq .
```

## Infrastructure Summary

| Resource | Value |
|----------|-------|
| GCP Project | `glassbox-irt` |
| Region | `us-central1` |
| Cloud Run service | `invoice-reconciliation-tester` |
| Container image | `gcr.io/glassbox-irt/invoice-reconciliation-tester` |
| Service account | `irt-runner@glassbox-irt.iam.gserviceaccount.com` |
| Cloud SQL instance | `irt-postgres` (PostgreSQL 15, db-f1-micro) |
| Database | `irt_prod` |
| Scheduler | `irt-weekly` (Mondays 8am UTC, optional) |
| Memory | 512Mi |
| CPU | 1 |
| Timeout | 900s (15 min) |
| Min instances | 0 (scale to zero) |
| Max instances | 1 (no parallel runs) |

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
