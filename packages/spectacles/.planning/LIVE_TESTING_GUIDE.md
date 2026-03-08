# Spectacles Slack Integration - Live Testing Guide

**Ready for live testing with you!**

---

## What We've Prepared

### ✅ Test Framework Created

1. **Manual Test Procedures** (`tests/integration/MANUAL_TEST_PROCEDURES.md`)
   - 68 detailed test cases across 10 scenarios
   - Step-by-step instructions
   - Expected results for each test
   - Verification checklists

2. **Helper Scripts**
   - `tests/helpers/setup_test_env.sh` - Load credentials from GCP
   - `tests/helpers/send_test_notification.py` - Send test notifications to Slack
   - `tests/helpers/create_test_task.py` - Create test tasks via API
   - `tests/integration/test_slack_integration.py` - Automated tests

3. **Result Tracking**
   - `TEST_RESULTS.md` - Pre-configured test results table
   - `TEST_PROGRESS.md` - Real-time progress tracking

---

## How We'll Test Together

### Phase 1: Environment Setup (Now)

**Your actions:**
1. Create Slack test channel: `#spectacles-integration-testing`
2. Invite the Spectacles bot to the channel
3. Let me know when ready

**My actions:**
- Load environment from GCP
- Verify service health
- Prepare first test

### Phase 2: Basic Webhook Tests (5-10 min)

**What we'll test:**
- Info, warning, error, success notifications
- Block Kit formatting
- Message delivery

**How:**
- I'll run: `python3 tests/helpers/send_test_notification.py --type info --message "[TEST] First notification"`
- You verify: Check Slack for message
- We document: Record result in TEST_RESULTS.md

### Phase 3: Command Execution (10-15 min)

**What we'll test:**
- `help` command
- `status task-ID` command
- `list tasks` command
- @mentions in channel

**How:**
- I'll create a test task
- You send commands in Slack (DM or @mention)
- We observe and document responses

### Phase 4: Approval Flows (15-20 min) **CRITICAL**

**What we'll test:**
- Approval request with buttons
- Click "Approve" button
- Click "Reject" button
- Click "Take Control" button (tunnel mode)

**How:**
- I'll create task requiring approval
- You click buttons in Slack
- We observe automation response
- Document each button interaction

### Phase 5: AI Q&A (10-15 min) **CRITICAL**

**What we'll test:**
- Ask questions about tasks
- Project-specific questions
- Low-confidence escalation
- Thread-based follow-ups

**How:**
- You ask questions in Slack
- We observe AI responses
- Check escalation behavior
- Measure response quality

### Phase 6: Glassy Integration (10 min) **CRITICAL**

**What we'll test:**
- Glassy sends alert → Spectacles → Slack
- Cross-project notifications

**How:**
- Trigger test alert in Glassy backend (if available)
- Or simulate via webhook
- Verify notification path

### Phase 7: Security & Edge Cases (10 min)

**What we'll test:**
- PII filtering
- Invalid commands
- Unauthorized actions
- Rate limiting (if time permits)

---

## Test Execution Flow

```
┌─────────────────────────────────────────────────────────┐
│ Step 1: You create test channel in Slack               │
│ Step 2: I load environment and run first test          │
│ Step 3: You verify result in Slack                     │
│ Step 4: I record result in TEST_RESULTS.md             │
│ Step 5: Repeat for next test                           │
└─────────────────────────────────────────────────────────┘
```

**After each test:**
1. I ask: "Did you see the expected result?"
2. You respond: "Yes" or "No, I saw [description]"
3. I update TEST_RESULTS.md with status
4. We proceed to next test

---

## Quick Reference: Test Commands

### Send Notification
```bash
cd projects/spectacles
python3 tests/helpers/send_test_notification.py \
  --type info \
  --message "[TEST] Your message here"
```

### Create Test Task
```bash
python3 tests/helpers/create_test_task.py \
  --goal "Navigate to example.com" \
  --url https://example.com \
  --require-approval
```

### Check Task Status
```bash
python3 tests/helpers/create_test_task.py \
  --check-status task-123
```

---

## What I Need From You

### Before Testing
- ✅ Create test channel: `#spectacles-integration-testing`
- ✅ Invite Spectacles bot to channel
- ✅ Confirm you can see the channel
- ✅ Ready to interact with bot (click buttons, send messages)

### During Testing
- **Visual verification**: Tell me what you see in Slack
- **Button clicks**: Click buttons when I create approval requests
- **Message sending**: Send commands/questions when prompted
- **Screenshots**: (Optional) Share screenshots of interesting results

### After Testing
- Review compiled TEST_RESULTS.md
- Confirm cleanup (delete test channel, etc.)

---

## Safety Measures

✅ **Isolated test channel** - All test messages prefixed with `[TEST]`
✅ **Production service** - But dedicated test channel
✅ **Backup config** - `channel_mappings.json.backup` created
✅ **Rollback plan** - Can restore original config if needed
✅ **Rate limiting** - Delays between tests to respect Slack API limits

---

## Estimated Timeline

| Phase | Duration | Priority |
|-------|----------|----------|
| Environment Setup | 5 min | - |
| Webhook Tests | 10 min | Medium |
| Command Tests | 15 min | Medium |
| Approval Flows | 20 min | **CRITICAL** |
| AI Q&A | 15 min | **CRITICAL** |
| Glassy Integration | 10 min | **CRITICAL** |
| Security | 10 min | High |
| **Total** | **~85 min** | **~1.5 hours** |

---

## Ready to Start?

**When you're ready:**
1. Confirm test channel created: `#spectacles-integration-testing`
2. Confirm Spectacles bot invited to channel
3. Say: "Ready to start testing"

**I will:**
1. Load environment from GCP
2. Run first test (webhook notification)
3. Ask you to verify in Slack

Let's begin! 🚀

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
