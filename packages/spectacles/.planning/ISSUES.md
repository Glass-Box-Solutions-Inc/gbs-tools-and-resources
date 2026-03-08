# spectacles - Issues & Deferred Work

**Last Updated:** 2026-01-20
**Test Session:** Slack Integration Testing

---

## Critical Issues Found During Integration Testing

### ISSUE-001: Slack App Missing Required Scope ✅ RESOLVED
**Severity:** High
**Test:** 5.1 - Channel Creation
**Status:** Fixed

**Description:** Slack app initially missing `channels:manage` scope.

**Resolution:**
- Added `channels:manage` scope to Slack app
- Reinstalled app to workspace
- Updated bot token in GCP Secret Manager (version 2)
- Channel creation now functional

---

## Medium Issues

### ISSUE-002: Intent Classifier - Question Recognition 🔧 NEEDS FIX
**Severity:** Medium
**Test:** 7.3 - Question Intent
**Accuracy:** 67% (threshold: 90%)

**Problem:** Generic questions misclassified as STATUS_QUERY

**Examples:**
- ❌ "what is happening with project X?" → STATUS_QUERY (should be QUESTION)

**Fix Needed:** Add more flexible question patterns in `intent_classifier.py`

---

### ISSUE-003: Intent Classifier - Help Recognition 🔧 NEEDS FIX
**Severity:** Medium
**Test:** 7.5 - Help Intent
**Accuracy:** 25% (threshold: 90%)

**Problem:** Only exact "help" keyword recognized

**Examples:**
- ❌ "show me the commands" → QUESTION
- ❌ "what can you do?" → QUESTION
- ❌ "help me" → ESCALATE

**Fix Needed:** Add patterns for help variations

---

## Deferred Items

### DEFER-001: Webhook URLs Not in GCP
**Priority:** Low
**Workaround:** Using bot token API instead

**Issue:** `slack-webhook-main` etc. not found in GCP Secret Manager

---

## Future Enhancements

### ENH-001: AI Q&A Testing
**Status:** Blocked - No Gemini API key in GCP
**Test:** 4.1-4.6 skipped

### ENH-002: Approval Flow Verification
**Status:** Awaiting user feedback
**Test:** 2.1 in progress

---

## Test Results Summary

**Completed:** 8 tests
**Passed:** 6 tests
**Failed:** 2 tests (intent classification)
**In Progress:** 2 tests (approval flow, commands)

---

*Updated during integration testing session - 2026-01-20*
