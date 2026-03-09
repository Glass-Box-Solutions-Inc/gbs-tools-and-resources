# GBS Integration Validator - Deployment Guide

GCP Cloud Run deployment guide for the GBS Integration Validator service.

## Prerequisites

- `gcloud` CLI installed and authenticated
- Access to the `adjudica-internal` GCP project
- Docker installed locally (for testing builds)

## 1. Service Account

Create a dedicated service account for the validator:

```bash
# Create service account
gcloud iam service-accounts create gbs-integration-validator \
  --display-name="GBS Integration Validator" \
  --project=adjudica-internal

# Grant Secret Manager access
gcloud projects add-iam-policy-binding adjudica-internal \
  --member="serviceAccount:gbs-integration-validator@adjudica-internal.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant Cloud Run invoker (for Cloud Scheduler to trigger runs)
gcloud projects add-iam-policy-binding adjudica-internal \
  --member="serviceAccount:gbs-integration-validator@adjudica-internal.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Grant Resource Manager read access (for GCP validator)
gcloud projects add-iam-policy-binding adjudica-internal \
  --member="serviceAccount:gbs-integration-validator@adjudica-internal.iam.gserviceaccount.com" \
  --role="roles/resourcemanager.projects.get"

# Grant IAM policy viewer (for GCP validator)
gcloud projects add-iam-policy-binding adjudica-internal \
  --member="serviceAccount:gbs-integration-validator@adjudica-internal.iam.gserviceaccount.com" \
  --role="roles/iam.securityReviewer"
```

## 2. Secret Manager

Store all API credentials in Secret Manager:

```bash
# GitHub PAT
echo -n "ghp_..." | gcloud secrets create github-token-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# Linear API Key
echo -n "lin_api_..." | gcloud secrets create linear-api-key-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# n8n API URL
echo -n "https://n8n.example.com" | gcloud secrets create n8n-api-url-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# n8n API Key
echo -n "n8n_..." | gcloud secrets create n8n-api-key-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# Stripe Secret Key (read-only)
echo -n "sk_live_..." | gcloud secrets create stripe-secret-key-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# Knowledge Base API URL
echo -n "https://kb.example.com" | gcloud secrets create kb-api-url-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# Knowledge Base API Key
echo -n "kb_..." | gcloud secrets create kb-api-key-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal

# Slack Bot Token
echo -n "xoxb-..." | gcloud secrets create slack-bot-token-integration-validator \
  --replication-policy="automatic" \
  --data-file=- \
  --project=adjudica-internal
```

## 3. Artifact Registry

Create a Docker repository (if not already existing):

```bash
gcloud artifacts repositories create cloud-run-images \
  --repository-format=docker \
  --location=us-west1 \
  --project=adjudica-internal \
  --description="Cloud Run container images"
```

Build and push the image:

```bash
# Configure Docker for Artifact Registry
gcloud auth configure-docker us-west1-docker.pkg.dev

# Build
docker build -t us-west1-docker.pkg.dev/adjudica-internal/cloud-run-images/gbs-integration-validator:latest .

# Push
docker push us-west1-docker.pkg.dev/adjudica-internal/cloud-run-images/gbs-integration-validator:latest
```

## 4. Cloud Run Deployment

```bash
gcloud run deploy gbs-integration-validator \
  --image=us-west1-docker.pkg.dev/adjudica-internal/cloud-run-images/gbs-integration-validator:latest \
  --region=us-west1 \
  --project=adjudica-internal \
  --service-account=gbs-integration-validator@adjudica-internal.iam.gserviceaccount.com \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=1 \
  --timeout=300 \
  --no-allow-unauthenticated \
  --set-env-vars="NODE_ENV=production,GCP_PROJECT_ID=adjudica-internal" \
  --set-secrets="\
GITHUB_TOKEN=github-token-integration-validator:latest,\
LINEAR_API_KEY=linear-api-key-integration-validator:latest,\
N8N_API_URL=n8n-api-url-integration-validator:latest,\
N8N_API_KEY=n8n-api-key-integration-validator:latest,\
STRIPE_SECRET_KEY=stripe-secret-key-integration-validator:latest,\
KB_API_URL=kb-api-url-integration-validator:latest,\
KB_API_KEY=kb-api-key-integration-validator:latest,\
SLACK_BOT_TOKEN=slack-bot-token-integration-validator:latest"
```

## 5. Cloud Scheduler

Set up a scheduled job to trigger validation every 6 hours:

```bash
# Get the Cloud Run service URL
SERVICE_URL=$(gcloud run services describe gbs-integration-validator \
  --region=us-west1 \
  --project=adjudica-internal \
  --format='value(status.url)')

# Create Cloud Scheduler job
gcloud scheduler jobs create http integration-validator-daily \
  --schedule="0 */6 * * *" \
  --uri="${SERVICE_URL}/api/run" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --message-body='{}' \
  --oidc-service-account-email=gbs-integration-validator@adjudica-internal.iam.gserviceaccount.com \
  --oidc-token-audience="${SERVICE_URL}" \
  --location=us-west1 \
  --project=adjudica-internal \
  --description="Trigger GBS integration validation every 6 hours" \
  --time-zone="America/Los_Angeles"
```

## 6. Cloud Build (CI/CD)

Deployed via Cloud Build trigger from the `gbs-tools-and-resources` monorepo:

- **Cloud Build trigger:** Points to `gbs-tools-and-resources` repo, `dir: packages/gbs-integration-validator/`
- **Build config:** `packages/gbs-integration-validator/cloudbuild.yaml`

```bash
gcloud builds triggers create github \
  --repo-name=gbs-tools-and-resources \
  --repo-owner=Glass-Box-Solutions-Inc \
  --branch-pattern="^main$" \
  --included-files="packages/gbs-integration-validator/**" \
  --build-config=packages/gbs-integration-validator/cloudbuild.yaml \
  --project=adjudica-internal \
  --name=integration-validator-deploy
```

## 7. Verification

After deployment, verify the service is running:

```bash
# Health check (no auth)
curl "$(gcloud run services describe gbs-integration-validator \
  --region=us-west1 --project=adjudica-internal \
  --format='value(status.url)')/health"

# Trigger a run (with OIDC)
curl -X POST "$(gcloud run services describe gbs-integration-validator \
  --region=us-west1 --project=adjudica-internal \
  --format='value(status.url)')/api/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{}'

# Check status
curl "$(gcloud run services describe gbs-integration-validator \
  --region=us-west1 --project=adjudica-internal \
  --format='value(status.url)')/api/status" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

## 8. Monitoring

View logs in Cloud Console or via CLI:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=gbs-integration-validator" \
  --project=adjudica-internal \
  --limit=50 \
  --format=json
```

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
