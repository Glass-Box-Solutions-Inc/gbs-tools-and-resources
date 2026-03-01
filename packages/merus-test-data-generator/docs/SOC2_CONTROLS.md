# SOC2 Controls Mapping — merus-test-data-generator

Maps implemented security controls to SOC2 Trust Service Criteria.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

---

## CC6.1 — Logical Access Controls

| Control | Implementation |
|---------|----------------|
| Credential storage | GCP Secret Manager (primary), `.env` fallback for offline dev |
| VM access | GCP IAM, SSH key-based access to `dev-workstation` |
| No hardcoded secrets | `config.py` uses `_get_secret()` helper — no defaults for credentials |
| Git remote | HTTPS without embedded tokens; credentials via `~/.git-credentials` |

## CC6.6 — Encryption

| Control | Implementation |
|---------|----------------|
| In transit | All API calls use HTTPS (MerusCase API, GCP Secret Manager) |
| At rest | GCP Persistent Disk encryption (default), Secret Manager encryption |
| Credentials at rest | GCP Secret Manager (AES-256, Google-managed keys) |
| Local fallback | `.env` file with `600` permissions on dev VM |

## CC6.8 — Audit Logging

| Control | Implementation |
|---------|----------------|
| Audit logger | `orchestration/audit.py` — `PipelineAuditLogger` |
| Storage | SQLite with HMAC-SHA256 chain for tamper detection |
| Categories | `CREDENTIAL_ACCESS`, `PIPELINE_OPERATIONS`, `DOCUMENT_OPERATIONS`, `API_OPERATIONS` |
| Integrity | HMAC chain: each record's hash includes previous record's hash |
| Verification | `python main.py audit --verify-chain` validates full chain |
| Retention | 90-day default with `cleanup_expired()` |

## CC7.2 — Monitoring

| Control | Implementation |
|---------|----------------|
| Pipeline stats | `python main.py audit --stats` — event counts by category |
| Recent events | `python main.py audit --recent N` — last N events |
| Failure tracking | All case creation and document upload failures are audit-logged |
| Structured logging | `structlog` with sensitive field redaction |

## PI1.2 — Audit Trail (Processing Integrity)

| Control | Implementation |
|---------|----------------|
| Pipeline start/end | Logged with run ID, case count, results summary |
| Case creation | Each case creation logged with MerusCase ID, success/failure |
| Document uploads | Each upload logged with document ID, success/failure |
| Error capture | Errors logged with category, event type, message |

## C1.1 — Confidentiality

| Control | Implementation |
|---------|----------------|
| Log redaction | `structlog` processor redacts keys: `password`, `secret`, `token`, `api_key`, `credential`, `authorization`, `ssn` |
| No creds in code | All credentials loaded via GCP Secret Manager or env vars |
| `.gitignore` | Excludes `.env`, `.meruscase_token`, `*.token`, `.auth/`, `*.db` |
| Audit logger | Never stores secret values — only logs access events |

---

## Verification Commands

```bash
# Verify HMAC chain integrity
python main.py audit --verify-chain

# View audit statistics
python main.py audit --stats

# View recent audit events
python main.py audit --recent 20

# Check no secrets in source
grep -r "password\|secret\|token" --include="*.py" . | grep -v "REDACTED\|_SENSITIVE\|_get_secret\|env\|config\|audit\|\.pyc"
```

---

## Known Limitations

| Limitation | Risk | Mitigation |
|------------|------|------------|
| MerusCase token lacks auto-refresh | Token may expire during long runs | Manual token rotation; documented in ACCESS_CONTROL.md |
| Browserless token visible in WebSocket URL | Inherent to CDP protocol | Token masked in structured logs |
| `sys.path` manipulation for merus-expert imports | Not a security risk, but fragile | Document as tech debt; long-term fix: pip-installable merus-expert |
| Generated PDFs contain fake data (Faker) | No real PII exposure | Data is synthetic; no encryption needed |
