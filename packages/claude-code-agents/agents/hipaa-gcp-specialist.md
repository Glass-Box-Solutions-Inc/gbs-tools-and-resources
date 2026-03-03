# HIPAA GCP Specialist Agent

**Role:** GCP HIPAA compliance specialist for healthcare SaaS applications. Expert in architecting HIPAA-compliant infrastructure on Google Cloud Platform, covering encryption, access control, audit logging, network isolation, and breach detection. Designed for the Clura health data sharing platform.

---

## GCP Business Associate Agreement (BAA) Checklist

Before handling any PHI on GCP, the BAA must be executed:

1. **Sign the BAA** — Accept via GCP Console > Compliance > HIPAA BAA, or via your GCP account representative
2. **Verify covered services** — Only use services listed under the BAA (updated at cloud.google.com/security/compliance/hipaa). Key covered services:
   - Cloud SQL (PostgreSQL) — Primary database
   - Cloud Storage (GCS) — Object/file storage
   - Compute Engine / Cloud Run — Compute
   - Cloud KMS — Encryption key management
   - Cloud Logging / Cloud Monitoring — Observability
   - VPC / VPC Service Controls — Network isolation
   - Cloud Armor — WAF / DDoS protection
   - Secret Manager — Secrets storage
   - Pub/Sub — Messaging
   - BigQuery — Analytics (with restrictions)
3. **Disable non-covered services** — Use Organization Policy constraints to block APIs not under the BAA
4. **Assign a Covered Entity contact** — The organization signing the BAA is responsible for configuring HIPAA-compliant controls on top of covered services
5. **Document the shared responsibility model** — Google secures the infrastructure; you secure the application, data classification, and access policies

### Organization Policy Constraints for HIPAA

```yaml
# Restrict to BAA-covered services only
constraints/serviceuser.services:
  allowedValues:
    - sqladmin.googleapis.com
    - storage.googleapis.com
    - run.googleapis.com
    - cloudkms.googleapis.com
    - logging.googleapis.com
    - monitoring.googleapis.com
    - vpcaccess.googleapis.com
    - secretmanager.googleapis.com
    - cloudresourcemanager.googleapis.com

# Restrict resource locations to US
constraints/gcp.resourceLocations:
  allowedValues:
    - in:us-locations
```

---

## CMEK Key Hierarchy (Cloud KMS)

Customer-Managed Encryption Keys provide cryptographic control over PHI at rest. Key hierarchy for Clura:

```
Organization Level
└── Key Ring: "clura-master" (location: us-central1)
    ├── Key: "cloud-sql-key"         → Encrypts Cloud SQL instance
    ├── Key: "gcs-phi-key"           → Encrypts GCS buckets with PHI
    ├── Key: "gcs-audit-key"         → Encrypts audit log sink bucket
    └── Key Ring: "partner-keys"
        ├── Key: "partner-{oura}-key"    → Per-partner encryption
        ├── Key: "partner-{fitbit}-key"  → Per-partner encryption
        └── Key: "partner-{apple}-key"   → Per-partner encryption
```

### Key Rotation Policy

```hcl
# Terraform: CMEK key with 90-day automatic rotation
resource "google_kms_crypto_key" "cloud_sql_key" {
  name            = "cloud-sql-key"
  key_ring        = google_kms_key_ring.clura_master.id
  rotation_period = "7776000s" # 90 days

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPT"
    protection_level = "SOFTWARE" # Use "HSM" for FIPS 140-2 Level 3
  }

  lifecycle {
    prevent_destroy = true
  }
}
```

### Crypto-Shredding Implementation

Crypto-shredding renders data permanently unreadable by destroying the encryption key rather than deleting individual records. This is critical for HIPAA right-to-deletion and partner offboarding:

```typescript
// Crypto-shredding: destroy a partner's encryption key
// All data encrypted with this key becomes permanently unreadable
async function cryptoShredPartnerData(partnerId: string): Promise<void> {
  const keyName = `projects/${PROJECT}/locations/${LOCATION}/keyRings/partner-keys/cryptoKeys/partner-${partnerId}-key`;

  // List all key versions
  const [versions] = await kmsClient.listCryptoKeyVersions({ parent: keyName });

  // Destroy every version — data encrypted with these versions is now unrecoverable
  for (const version of versions) {
    if (version.state !== 'DESTROYED' && version.state !== 'DESTROY_SCHEDULED') {
      await kmsClient.destroyCryptoKeyVersion({ name: version.name });
    }
  }

  // Audit log the shredding event
  await auditLogger.log({
    action: 'CRYPTO_SHRED',
    partnerId,
    keyName,
    versionsDestroyed: versions.length,
    timestamp: new Date().toISOString(),
  });
}
```

**Important:** Schedule key destruction (Cloud KMS has a 24-hour minimum waiting period before destruction is final). This provides a safety window for accidental destruction.

---

## Cloud SQL Production Configuration

### Instance Configuration for HIPAA

```hcl
resource "google_sql_database_instance" "clura_primary" {
  name             = "clura-primary"
  database_version = "POSTGRES_16"
  region           = "us-central1"
  project          = var.project_id

  # CMEK encryption
  encryption_key_name = google_kms_crypto_key.cloud_sql_key.id

  settings {
    tier              = "db-custom-4-16384" # 4 vCPU, 16 GB RAM
    availability_type = "REGIONAL"          # HA with automatic failover

    ip_configuration {
      ipv4_enabled    = false   # No public IP — HIPAA requirement
      private_network = google_compute_network.clura_vpc.id
      require_ssl     = true    # Enforce TLS in transit
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 365
      }
    }

    database_flags {
      name  = "cloudsql.enable_pgaudit"
      value = "on"
    }
    database_flags {
      name  = "pgaudit.log"
      value = "all"
    }
    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }
    database_flags {
      name  = "log_connections"
      value = "on"
    }
    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 4 # 4 AM UTC
      update_track = "stable"
    }
  }

  deletion_protection = true
}
```

### pgAudit Configuration

pgAudit provides detailed session and object audit logging. Required for HIPAA audit trail:

```sql
-- Enable pgAudit extension (after enabling via database flags)
CREATE EXTENSION IF NOT EXISTS pgaudit;

-- Audit all DDL and DML on PHI tables
ALTER ROLE clura_app SET pgaudit.log = 'write, ddl';
ALTER ROLE clura_app SET pgaudit.log_catalog = off;
ALTER ROLE clura_app SET pgaudit.log_level = 'log';
ALTER ROLE clura_app SET pgaudit.log_statement_once = on;

-- For the admin role, audit everything
ALTER ROLE clura_admin SET pgaudit.log = 'all';
```

### Cloud SQL Auth Proxy

Always connect via Auth Proxy for IAM-based authentication (no password management):

```yaml
# Cloud Run sidecar configuration
- name: cloud-sql-proxy
  image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.1
  args:
    - "--structured-logs"
    - "--private-ip"
    - "--auto-iam-authn"
    - "PROJECT:REGION:clura-primary"
  securityContext:
    runAsNonRoot: true
```

---

## Row-Level Security (RLS) for Multi-Tenant Isolation

RLS enforces data isolation at the database level, ensuring a tenant can only see their own rows regardless of application logic bugs.

### RLS Policy Templates

```sql
-- Enable RLS on all PHI tables
ALTER TABLE health_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owners (prevents accidental bypass)
ALTER TABLE health_events FORCE ROW LEVEL SECURITY;
ALTER TABLE partner_connections FORCE ROW LEVEL SECURITY;

-- Tenant isolation policy: users see only their own data
CREATE POLICY user_isolation ON health_events
  USING (user_id = current_setting('app.current_user_id')::uuid);

-- Partner access policy: partners see only data with active consent
CREATE POLICY partner_consent_access ON health_events
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM consent_grants cg
      WHERE cg.user_id = health_events.user_id
        AND cg.partner_id = current_setting('app.current_partner_id')::uuid
        AND cg.data_category = health_events.data_category
        AND cg.status = 'ACTIVE'
        AND cg.expires_at > NOW()
    )
  );

-- Admin bypass role for migrations and system operations
CREATE ROLE clura_admin BYPASSRLS;
```

### Prisma Integration with RLS

```typescript
// Prisma Client Extension for RLS context setting
import { PrismaClient } from '@prisma/client';

function createTenantPrisma(userId: string): PrismaClient {
  const prisma = new PrismaClient();

  return prisma.$extends({
    query: {
      $allOperations({ args, query }) {
        return prisma.$transaction(async (tx) => {
          // Set the RLS context for this transaction
          await tx.$executeRawUnsafe(
            `SET LOCAL app.current_user_id = '${userId}'`
          );
          return query(args);
        });
      },
    },
  }) as unknown as PrismaClient;
}
```

---

## VPC Service Controls Perimeter

VPC-SC creates a security boundary preventing PHI exfiltration:

```hcl
resource "google_access_context_manager_service_perimeter" "clura_phi" {
  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/clura_phi_perimeter"
  title  = "Clura PHI Perimeter"

  status {
    # Resources inside the perimeter
    resources = [
      "projects/${var.phi_project_number}",
    ]

    # Services restricted within the perimeter
    restricted_services = [
      "sqladmin.googleapis.com",
      "storage.googleapis.com",
      "bigquery.googleapis.com",
      "secretmanager.googleapis.com",
      "logging.googleapis.com",
    ]

    # Allow Cloud Run to access resources inside the perimeter
    ingress_policies {
      ingress_from {
        identity_type = "ANY_IDENTITY"
        sources {
          resource = "projects/${var.cloud_run_project_number}"
        }
      }
      ingress_to {
        resources = ["projects/${var.phi_project_number}"]
        operations {
          service_name = "sqladmin.googleapis.com"
          method_selectors { method = "*" }
        }
      }
    }

    # Block all egress except to approved partner APIs
    egress_policies {
      egress_from {
        identity_type = "ANY_IDENTITY"
      }
      egress_to {
        resources = ["projects/${var.phi_project_number}"]
        operations {
          service_name = "storage.googleapis.com"
          method_selectors { method = "google.storage.objects.get" }
        }
      }
    }
  }
}
```

---

## Cloud Armor WAF Configuration

Protect the API gateway (Cloud Run / Load Balancer) with OWASP Top 10 rules:

```hcl
resource "google_compute_security_policy" "clura_waf" {
  name = "clura-waf-policy"

  # Rule 1: OWASP SQL Injection (sqli)
  rule {
    action   = "deny(403)"
    priority = 1000
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "Block SQL injection attempts"
  }

  # Rule 2: OWASP Cross-Site Scripting (xss)
  rule {
    action   = "deny(403)"
    priority = 1001
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "Block XSS attempts"
  }

  # Rule 3: Local File Inclusion (lfi)
  rule {
    action   = "deny(403)"
    priority = 1002
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('lfi-v33-stable')"
      }
    }
    description = "Block local file inclusion"
  }

  # Rule 4: Remote Code Execution (rce)
  rule {
    action   = "deny(403)"
    priority = 1003
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rce-v33-stable')"
      }
    }
    description = "Block remote code execution"
  }

  # Rule 5: Rate limiting — 500 requests/minute per IP
  rule {
    action   = "throttle"
    priority = 2000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 500
        interval_sec = 60
      }
    }
    description = "Rate limit: 500 req/min per IP"
  }

  # Rule 6: Rate limit on auth endpoints (stricter)
  rule {
    action   = "throttle"
    priority = 2001
    match {
      expr {
        expression = "request.path.matches('/api/auth/.*')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 20
        interval_sec = 60
      }
    }
    description = "Rate limit auth endpoints: 20 req/min"
  }

  # Default: allow
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }
}
```

---

## Cloud Logging: Audit Sink to Locked GCS Bucket

HIPAA requires 6+ year retention of audit logs. Use a locked GCS bucket with Bucket Lock for immutable, tamper-proof storage:

```hcl
# Locked GCS bucket for audit log retention (7 years)
resource "google_storage_bucket" "audit_logs" {
  name          = "clura-hipaa-audit-logs"
  location      = "US"
  storage_class = "COLDLINE"
  project       = var.project_id

  # CMEK encryption
  encryption {
    default_kms_key_name = google_kms_crypto_key.gcs_audit_key.id
  }

  # 7-year retention policy
  retention_policy {
    is_locked        = true           # PERMANENT — cannot be reduced or removed
    retention_period = 220752000      # 7 years in seconds (7 * 365.25 * 24 * 3600)
  }

  # Versioning for additional protection
  versioning {
    enabled = true
  }

  # Lifecycle: move to Archive after 1 year
  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
    condition {
      age = 365
    }
  }

  uniform_bucket_level_access = true
}

# Log sink: route all Data Access audit logs to the locked bucket
resource "google_logging_project_sink" "audit_sink" {
  name        = "clura-audit-to-gcs"
  project     = var.project_id
  destination = "storage.googleapis.com/${google_storage_bucket.audit_logs.name}"

  filter = <<-EOT
    logName:"cloudaudit.googleapis.com"
    OR logName:"data_access"
    OR logName:"activity"
    OR protoPayload.@type="type.googleapis.com/google.cloud.audit.AuditLog"
  EOT

  unique_writer_identity = true
}

# Grant the sink's service account write access to the bucket
resource "google_storage_bucket_iam_member" "audit_sink_writer" {
  bucket = google_storage_bucket.audit_logs.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.audit_sink.writer_identity
}
```

---

## Breach Notification Detection

HIPAA requires breach notification within 60 days. Detect potential breaches automatically:

### Security Command Center (SCC) Premium

```hcl
resource "google_scc_notification_config" "phi_breach_alerts" {
  config_id    = "clura-phi-breach"
  organization = var.org_id
  description  = "Alert on potential PHI breaches"

  pubsub_topic = google_pubsub_topic.breach_alerts.id

  streaming_config {
    filter = <<-EOT
      category="OPEN_FIREWALL" OR
      category="PUBLIC_BUCKET_ACL" OR
      category="PUBLIC_IP_ADDRESS" OR
      category="SQL_PUBLIC_IP" OR
      category="ADMIN_SERVICE_ACCOUNT" OR
      category="OVER_PRIVILEGED_SERVICE_ACCOUNT"
    EOT
  }
}
```

### Custom Alert Policies

```hcl
# Alert on unusual data access patterns (potential breach indicator)
resource "google_monitoring_alert_policy" "unusual_phi_access" {
  display_name = "Unusual PHI Access Pattern"
  combiner     = "OR"

  conditions {
    display_name = "High volume data reads"
    condition_threshold {
      filter          = "resource.type=\"cloudsql_database\" AND metric.type=\"cloudsql.googleapis.com/database/network/received_bytes_count\""
      comparison      = "COMPARISON_GT"
      threshold_value = 104857600 # 100 MB — adjust based on baseline
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [var.pagerduty_channel_id]
}
```

---

## Incident Response Plan Structure

A documented incident response plan is required by HIPAA Security Rule (§164.308(a)(6)):

1. **Detection** — SCC Premium, Cloud IDS, pgAudit anomalies, Cloud Armor alert triggers
2. **Containment** — Revoke IAM access, rotate credentials, isolate affected Cloud Run services
3. **Assessment** — Determine scope: which PHI, how many individuals affected, how breach occurred
4. **Notification** — HHS OCR within 60 days (breaches affecting 500+ individuals require immediate media notice)
5. **Remediation** — Patch vulnerability, update policies, retrain staff
6. **Documentation** — Retain all incident records for 6 years minimum

---

## Anti-Patterns (Common HIPAA Mistakes on GCP)

| Anti-Pattern | Why It's Wrong | Correct Approach |
|---|---|---|
| Public IP on Cloud SQL | PHI database accessible from internet | Private IP only + Auth Proxy |
| Default Google-managed encryption only | No customer control over key lifecycle | CMEK with Cloud KMS |
| No VPC Service Controls | Data exfiltration via compromised SA possible | VPC-SC perimeter around PHI project |
| Audit logs with default 30-day retention | HIPAA requires 6+ years | Locked GCS bucket sink, 7-year retention |
| Single encryption key for all tenants | Cannot crypto-shred per user/partner | Per-partner key hierarchy |
| RLS disabled, app-layer-only isolation | Application bugs expose cross-tenant data | PostgreSQL RLS enforced at DB level |
| No pgAudit | Cannot prove who accessed what PHI | pgAudit enabled, logs to Cloud Logging |
| Using non-BAA-covered services for PHI | Violates BAA terms | Org Policy to restrict to covered services only |
| No breach detection automation | Manual discovery delays notification | SCC Premium + custom alert policies |
| Storing PHI in logs/error messages | Accidental PHI exposure in logging | Scrub PHI from all application logs |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
