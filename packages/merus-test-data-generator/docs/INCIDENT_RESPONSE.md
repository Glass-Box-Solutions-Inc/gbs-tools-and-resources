# Incident Response — merus-test-data-generator

Procedures for handling security incidents related to this tool.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

---

## Severity Levels

| Level | Description | Examples | Response Time |
|-------|-------------|----------|---------------|
| **P1 — Critical** | Credential exposure, production data breach | Secret committed to git, token leaked publicly | Immediate |
| **P2 — High** | Unauthorized access, audit chain tampering | Unknown access to VM, HMAC verification failure | < 4 hours |
| **P3 — Medium** | Service disruption, credential expiry | Pipeline failures, token expiration | < 24 hours |
| **P4 — Low** | Configuration drift, minor issues | Dependency version mismatch, stale secrets | Next sprint |

## Escalation Contacts

| Role | Contact | When |
|------|---------|------|
| Engineering Lead | Alex (Alex@adjudica.ai) | All P1, P2 incidents |
| Security | Internal security channel | All P1 incidents |

## Incident Response Procedures

### P1: Credential Exposure

**If a secret is committed to git or exposed publicly:**

1. **Contain** — Immediately rotate the compromised credential:
   ```bash
   # Rotate in GCP Secret Manager
   echo -n "NEW_VALUE" | gcloud secrets versions add SECRET_NAME \
     --data-file=- --project=PROJECT_ID
   ```
2. **Assess** — Determine scope of exposure:
   - Was it pushed to a public repository?
   - How long was it exposed?
   - Which services use this credential?
3. **Remediate** — Remove from git history if needed:
   ```bash
   # Use BFG Repo-Cleaner or git filter-branch
   bfg --replace-text passwords.txt repo.git
   ```
4. **Verify** — Confirm new credentials work:
   ```bash
   python -c "from config import MERUSCASE_CLIENT_ID; print('OK')"
   ```
5. **Document** — Log incident in audit trail and notify stakeholders

### P2: Audit Chain Tampering

**If `python main.py audit --verify-chain` reports INVALID:**

1. **Investigate** — Check which records are invalid
2. **Assess** — Determine if database was modified externally
3. **Preserve** — Back up current `audit.db` before any changes
4. **Remediate** — If legitimate corruption (not attack), rebuild from logs
5. **Monitor** — Run `--verify-chain` more frequently afterward

### P3: Pipeline Failure

**If the pipeline fails during case creation or upload:**

1. **Check** — `python main.py status` for current state
2. **Review** — `python main.py audit --recent 20` for recent events
3. **Diagnose** — Check if credentials are expired
4. **Resume** — Pipeline supports resumption via progress tracker

## Post-Incident Review

After any P1 or P2 incident:

1. **Timeline** — Document what happened and when
2. **Root cause** — Identify how the incident occurred
3. **Impact** — Assess what was affected
4. **Actions** — List remediation steps taken
5. **Prevention** — Identify improvements to prevent recurrence
6. **Update** — Revise this document if procedures were inadequate

## Preventive Measures

| Measure | Implementation |
|---------|----------------|
| No secrets in code | GCP Secret Manager integration |
| Git history scanning | `.gitignore` excludes sensitive files |
| Log redaction | Structlog processor redacts sensitive fields |
| Audit integrity | HMAC-chained audit records |
| Dependency pinning | Version ranges prevent supply chain drift |
| Access review | Quarterly IAM and credential review |
