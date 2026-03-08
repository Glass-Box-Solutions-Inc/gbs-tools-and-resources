# Spectacles Slack Integration - Manual Test Procedures

**Date:** 2026-01-20
**Test User:** Alex (Alex@adjudica.AI)
**Environment:** Production Slack Workspace
**Service:** https://spectacles-378330630438.us-central1.run.app

---

## Prerequisites

### 1. Environment Setup

Load Slack credentials from GCP Secret Manager:

```bash
# Export Slack Bot Token
export SLACK_BOT_TOKEN=$(gcloud secrets versions access latest \
  --secret="spectacles-slack-bot-token" \
  --project="ousd-campaign")

# Export Slack App Token (Socket Mode)
export SLACK_APP_TOKEN=$(gcloud secrets versions access latest \
  --secret="spectacles-slack-app-token" \
  --project="ousd-campaign")

# Verify tokens loaded
echo "Bot token: ${SLACK_BOT_TOKEN:0:10}..."
echo "App token: ${SLACK_APP_TOKEN:0:10}..."
```

### 2. Test Channel Creation

Create dedicated test channel to isolate testing from production:

**Manual Steps:**
1. Open Slack workspace
2. Create new channel: `#spectacles-integration-testing`
3. Set channel description: "Integration testing for Spectacles - [TEST] messages only"
4. Invite the Spectacles bot to the channel
5. Post message: "[TEST ENVIRONMENT] All messages in this channel are for integration testing"

### 3. Test User Access

**Required:** 2-3 test users
- **Admin user**: Has admin privileges (can create channels)
- **Regular user**: Standard user (can query tasks, ask questions)
- **Observer**: Watches for notifications, approvals

**Admin User ID:** `U0A4CNFQVG8` (from channel_mappings.json)

---

## Test Scenarios

### Scenario 1: Webhook Notifications (One-Way)

**Objective:** Verify simple notification delivery

**Prerequisites:**
- Webhook URLs configured or accessible via GCP Secret Manager
- Test channel created

**Test Cases:**

#### 1.1: Info Notification
**Action:**
```python
python3 tests/helpers/send_test_notification.py \
  --type info \
  --message "[TEST] Info notification from integration test"
```

**Expected Result:**
- Message appears in test channel
- Formatted as info (no special emoji or color)
- Timestamp visible

**Verification:** ☐ Visual inspection in Slack

---

#### 1.2: Warning Notification with Context
**Action:**
```python
python3 tests/helpers/send_test_notification.py \
  --type warning \
  --message "[TEST] Warning notification" \
  --context "Test run: $(date)"
```

**Expected Result:**
- Message appears with warning emoji (⚠️)
- Block Kit formatting applied
- Context visible at bottom

**Verification:** ☐ Visual inspection in Slack

---

#### 1.3: Error Notification with Emoji
**Action:**
```python
python3 tests/helpers/send_test_notification.py \
  --type error \
  --message "[TEST] Error notification"
```

**Expected Result:**
- Message appears with error emoji (🚨 or ❌)
- Red color or visual indicator
- Clear error formatting

**Verification:** ☐ Visual inspection in Slack

---

#### 1.4: Success Notification
**Action:**
```python
python3 tests/helpers/send_test_notification.py \
  --type success \
  --message "[TEST] Success notification"
```

**Expected Result:**
- Message appears with success emoji (✅)
- Green color or positive indicator
- Clear success formatting

**Verification:** ☐ Visual inspection in Slack

---

#### 1.5: Multiple Webhook URLs
**Action:**
```bash
# Send to main webhook
python3 tests/helpers/send_test_notification.py \
  --webhook main \
  --message "[TEST] Message to main channel"

# Send to Alex's webhook (if configured)
python3 tests/helpers/send_test_notification.py \
  --webhook alex \
  --message "[TEST] Message to Alex"
```

**Expected Result:**
- Messages appear in different channels/DMs
- Each webhook receives correct message
- No cross-talk between webhooks

**Verification:** ☐ Check multiple channels

---

### Scenario 2: Approval Flow (Interactive Buttons)

**Objective:** Test HITL approval workflow with button interactions

**Prerequisites:**
- Spectacles service running with Socket Mode enabled
- Interactive buttons configured in Slack app
- Test task created

**CRITICAL:** This scenario requires bidirectional Slack integration (Slack Bolt, not just webhooks)

#### 2.1: Request Approval for Browser Action
**Action:**
1. Create test task via API:
   ```bash
   curl -X POST https://spectacles-378330630438.us-central1.run.app/api/tasks/ \
     -H "Content-Type: application/json" \
     -d '{
       "goal": "Navigate to example.com and click submit button",
       "start_url": "https://example.com",
       "require_approval": true
     }'
   ```
2. Wait for approval request in Slack

**Expected Result:**
- Approval message appears in designated channel
- Message contains:
  - Task description
  - Action requiring approval (e.g., "Click submit button")
  - Three buttons: "Approve", "Reject", "Take Control"
  - Screenshot of current page (if available)

**Verification:** ☐ Message received ☐ Buttons visible ☐ Screenshot attached

---

#### 2.2: Click "Approve" Button
**Action:**
1. Locate approval message from Test 2.1
2. Click "Approve" button

**Expected Result:**
- Button click acknowledged (message updates or new message sent)
- Message shows "Approved by @username"
- Task continues execution automatically
- Task status updates to RUNNING

**Verification:** ☐ Message updated ☐ Task resumed ☐ Status correct

---

#### 2.3: Click "Reject" Button
**Action:**
1. Create another test task (same as 2.1)
2. When approval message appears, click "Reject" button

**Expected Result:**
- Button click acknowledged
- Message shows "Rejected by @username"
- Task stops execution
- Task status updates to CANCELLED or FAILED

**Verification:** ☐ Message updated ☐ Task stopped ☐ Status correct

---

#### 2.4: Click "Take Control" Button
**Action:**
1. Create another test task (same as 2.1)
2. When approval message appears, click "Take Control" button

**Expected Result:**
- Tunnel URL provided in response
- URL format: `https://production-sfo.browserless.io/live/...`
- URL is clickable
- URL opens live browser session

**Verification:** ☐ URL received ☐ URL opens ☐ Browser control works

---

#### 2.5: Multiple Users Clicking Simultaneously
**Action:**
1. Create test task
2. Have 2 users click different buttons at the same time

**Expected Result:**
- First click wins (race condition handled)
- Other clicks either ignored or show "already handled"
- No duplicate actions taken
- No system errors

**Verification:** ☐ Race condition handled ☐ No errors

---

#### 2.6: Approval Timeout
**Action:**
1. Create test task with approval required
2. Do NOT click any button
3. Wait for timeout (default: 300 seconds / 5 minutes)

**Expected Result:**
- After timeout, task automatically cancelled or fails
- Timeout notification sent
- Status updated to TIMEOUT or CANCELLED

**Verification:** ☐ Timeout triggered ☐ Notification sent ☐ Status updated

---

### Scenario 3: Command Execution (DMs and Mentions)

**Objective:** Verify command parsing and execution

**Prerequisites:**
- Socket Mode enabled
- Bot responds to DMs and mentions

#### 3.1: `help` via DM
**Action:**
1. Open DM with Spectacles bot
2. Send message: `help`

**Expected Result:**
- Bot responds with list of available commands
- Commands include: `status`, `pause`, `resume`, `cancel`, `list`, `create channel`
- Examples provided for each command

**Verification:** ☐ Response received ☐ Commands listed ☐ Examples clear

---

#### 3.2: `status task-123`
**Action:**
1. Create a test task (note the task ID)
2. In DM, send: `status task-{ID}`

**Expected Result:**
- Bot responds with task status
- Includes: current state, goal, start time, progress
- Formatted clearly

**Verification:** ☐ Status returned ☐ Information accurate

---

#### 3.3: `pause task-456`
**Action:**
1. Create a running test task
2. Send: `pause task-{ID}`

**Expected Result:**
- Bot confirms pause action
- Task state changes to PAUSED
- Task execution halts

**Verification:** ☐ Confirmation received ☐ Task paused

---

#### 3.4: `resume task-456`
**Action:**
1. Resume the paused task from 3.3
2. Send: `resume task-{ID}`

**Expected Result:**
- Bot confirms resume action
- Task state changes to RUNNING
- Task execution continues

**Verification:** ☐ Confirmation received ☐ Task resumed

---

#### 3.5: `cancel task-789`
**Action:**
1. Create a running test task
2. Send: `cancel task-{ID}`

**Expected Result:**
- Bot confirms cancellation
- Task state changes to CANCELLED
- Task execution stops permanently

**Verification:** ☐ Confirmation received ☐ Task cancelled

---

#### 3.6: `list tasks`
**Action:**
1. Ensure 2-3 active tasks exist
2. Send: `list tasks`

**Expected Result:**
- Bot responds with list of active tasks
- Each task shows: ID, goal, state, start time
- List is formatted and readable

**Verification:** ☐ List returned ☐ All tasks shown ☐ Formatting clear

---

#### 3.7: @mention in Channel
**Action:**
1. In test channel, send: `@Spectacles what tasks are running?`

**Expected Result:**
- Bot responds in thread (or directly)
- Answers question with project context
- Lists tasks related to the project (if channel mapped)

**Verification:** ☐ Response received ☐ Context-aware ☐ In thread

---

#### 3.8: Invalid Command
**Action:**
1. Send: `invalid-command task-123`

**Expected Result:**
- Bot responds with helpful error message
- Suggests correct commands
- Offers `help` command

**Verification:** ☐ Error message helpful ☐ Suggestions provided

---

### Scenario 4: AI Q&A System

**Objective:** Test AI-powered question answering

**Prerequisites:**
- `GOOGLE_AI_API_KEY` configured (Gemini 2.0 Flash)
- Socket Mode enabled
- Project channels mapped

**IMPORTANT:** These tests require Gemini API access and may consume API quota.

#### 4.1: "What tasks are running?"
**Action:**
1. In DM or project channel, ask: `What tasks are running?`

**Expected Result:**
- Bot responds with AI-generated answer
- Lists active tasks
- Includes task IDs and goals
- Response is conversational

**Verification:** ☐ Response accurate ☐ Conversational tone ☐ Complete list

---

#### 4.2: "What is the status of project X?"
**Action:**
1. In project channel, ask: `What is the status of this project?`

**Expected Result:**
- Bot uses project context from channel mapping
- Responds with project-specific information
- Includes recent tasks, activity, status

**Verification:** ☐ Project-aware ☐ Accurate info ☐ Contextual

---

#### 4.3: Ambiguous Question
**Action:**
1. Ask: `What's happening?` (very vague)

**Expected Result:**
- Bot either:
  - Asks clarifying question, OR
  - Provides best-guess answer with disclaimer, OR
  - Escalates to human (if confidence < 60%)

**Verification:** ☐ Handled gracefully ☐ No error

---

#### 4.4: Low Confidence Question (Escalation)
**Action:**
1. Ask a billing question: `How much did I spend this month?`

**Expected Result:**
- Bot detects low confidence or billing keyword
- Escalates to human automatically
- User receives: "🆘 I've escalated your question to [person]"
- Human receives DM with:
  - Original question
  - Context (user, channel, recent messages)
  - AI attempted answer (if applicable)

**Verification:** ☐ Escalation triggered ☐ User notified ☐ Human received DM

---

#### 4.5: Thread-Based Follow-Up Questions
**Action:**
1. Ask initial question: `What tasks are running?`
2. In the reply thread, ask: `Which one started first?`

**Expected Result:**
- Bot maintains context from thread
- Answers follow-up correctly using previous context
- No need to repeat information

**Verification:** ☐ Context preserved ☐ Follow-up answered

---

#### 4.6: Project-Specific Questions in Project Channels
**Action:**
1. Create/use project channel (e.g., `#spectacles-test-project`)
2. Ask: `What's the latest activity?`

**Expected Result:**
- Bot filters to project-specific activity
- Does not include tasks from other projects
- Response is scoped to the channel's project

**Verification:** ☐ Project-scoped ☐ No cross-project data

---

### Scenario 5: Project Channel Management

**Objective:** Test project-to-channel mapping and context

**Prerequisites:**
- Admin user access
- `channels:manage` scope in Slack app

#### 5.1: Create Channel for New Project
**Action:**
1. As admin user, send DM: `create channel for test-integration-project`

**Expected Result:**
- Bot creates channel: `#spectacles-test-integration-project`
- Channel description set: "Spectacles automation for test-integration-project"
- Admin users invited to channel
- Mapping added to `config/channel_mappings.json`
- Confirmation message sent

**Verification:** ☐ Channel created ☐ Description correct ☐ Mapping added

---

#### 5.2: Map Existing Channel to Project
**Action:** (Currently requires manual edit of `channel_mappings.json`)
1. Manually add channel mapping:
   ```json
   {
     "channels": {
       "C1234567890": {
         "project_name": "existing-project",
         "owner": "alex",
         "description": "Existing project channel",
         "created_at": "2026-01-20T10:00:00"
       }
     }
   }
   ```
2. Restart service or reload config

**Expected Result:**
- Bot recognizes channel as project channel
- Provides project-specific context in that channel

**Verification:** ☐ Mapping recognized ☐ Context provided

---

#### 5.3: Bot Provides Project-Specific Info
**Action:**
1. In project channel, ask: `What tasks exist for this project?`

**Expected Result:**
- Bot filters tasks by project name
- Only shows tasks tagged with that project
- Does not show unrelated tasks

**Verification:** ☐ Project filtering works ☐ Accurate list

---

#### 5.4: Multiple Projects with Separate Channels
**Action:**
1. Create 2 project channels
2. Run tasks in each project
3. Ask status in each channel

**Expected Result:**
- Each channel shows only its project's tasks
- No cross-contamination between projects
- Context isolation maintained

**Verification:** ☐ Isolation correct ☐ No cross-talk

---

#### 5.5: Channel Naming Convention
**Action:**
1. Try creating channel with various names:
   - `create channel for Test Project` (spaces, capitals)
   - `create channel for project_name` (underscore)
   - `create channel for ab` (too short)

**Expected Result:**
- Valid names converted: `Test Project` → `#spectacles-test-project`
- Invalid names rejected with helpful error
- Naming rules enforced (lowercase, hyphens, 3-80 chars)

**Verification:** ☐ Valid names work ☐ Invalid names rejected ☐ Helpful errors

---

#### 5.6: Admin-Only Channel Creation Enforcement
**Action:**
1. As **non-admin** user, try: `create channel for unauthorized-project`

**Expected Result:**
- Bot rejects request
- Error message: "Only admins can create channels"
- No channel created

**Verification:** ☐ Access denied ☐ Error message clear ☐ No channel created

---

### Scenario 6: Message Routing

**Objective:** Verify correct routing of different message types

**Prerequisites:**
- Socket Mode enabled
- Project channels created

#### 6.1: DM to Bot
**Action:**
1. Send DM: `hello`

**Expected Result:**
- Routed to DM handler
- Bot responds appropriately
- Not treated as channel or mention

**Verification:** ☐ DM handler invoked ☐ Correct response

---

#### 6.2: @Mention in Channel
**Action:**
1. In channel, send: `@Spectacles help`

**Expected Result:**
- Routed to mention handler
- Bot responds in thread (or directly)
- Context includes channel info

**Verification:** ☐ Mention handler invoked ☐ Thread response

---

#### 6.3: Thread Reply
**Action:**
1. Bot sends message in channel (trigger a notification)
2. Reply in thread: `approved`

**Expected Result:**
- Routed to thread handler
- Thread context preserved (parent message)
- Approval processed correctly

**Verification:** ☐ Thread handler invoked ☐ Context correct

---

#### 6.4: Message in Project Channel (No Mention)
**Action:**
1. In project channel, send: `What's the status?` (no @mention)

**Expected Result:**
- Currently: Ignored (bot only responds to @mentions or DMs)
- OR (if configured): Bot responds to all messages in project channels

**Verification:** ☐ Behavior matches configuration

---

#### 6.5: Message in Non-Project Channel
**Action:**
1. In random channel (not project channel), send: `@Spectacles hello`

**Expected Result:**
- Bot responds but without project context
- General help or "this channel is not a project channel" message

**Verification:** ☐ No project context used ☐ Appropriate response

---

#### 6.6: Multiple Simultaneous Messages
**Action:**
1. Send 3 messages rapidly:
   - DM: `status task-123`
   - Channel @mention: `@Spectacles help`
   - Thread reply: `approved`

**Expected Result:**
- All messages processed
- No race conditions
- No dropped messages
- Responses sent to correct locations

**Verification:** ☐ All processed ☐ No errors ☐ Correct routing

---

### Scenario 7: Intent Classification

**Objective:** Test intent detection accuracy

**Note:** This scenario can be tested via automated script (see `test_slack_integration.py`)

**Expected Accuracy:** >90% for pattern-based classification

**Automated Test:** `python3 tests/integration/test_slack_integration.py --scenario 7`

---

### Scenario 8: Security & Error Handling

**Objective:** Verify security and robustness

#### 8.1: PII Filtering in Logs
**Action:**
1. Send message containing PII:
   - Email: `My email is test@example.com`
   - Phone: `Call me at 555-123-4567`
   - SSN: `My SSN is 123-45-6789`
2. Check server logs

**Expected Result:**
- PII replaced in logs:
  - Emails: `[EMAIL_REDACTED]`
  - Phones: `[PHONE_REDACTED]`
  - SSNs: `[SSN_REDACTED]`
- Original message may be sent to Gemini (needed for context)
- But never logged or stored with PII

**Verification:** ☐ Logs checked ☐ PII redacted

---

#### 8.2: Invalid Credentials Handling
**Action:**
1. Temporarily set invalid `SLACK_BOT_TOKEN`
2. Attempt to start service

**Expected Result:**
- Service fails to start with clear error
- Error message indicates auth failure
- No partial startup or zombie state

**Verification:** ☐ Clear error ☐ No startup

---

#### 8.3: Network Timeout Handling
**Action:**
1. Simulate network delay (if possible)
2. Send command that requires API call

**Expected Result:**
- Timeout handled gracefully (10s max)
- User receives timeout message
- No hanging or blocked state

**Verification:** ☐ Timeout handled ☐ User notified

---

#### 8.4: Malformed Slack Events
**Action:**
1. Send malformed event to webhook endpoint (if exposed)
2. OR monitor logs for handling of unexpected event formats

**Expected Result:**
- Malformed events rejected or ignored
- No server errors or crashes
- Error logged for debugging

**Verification:** ☐ Handled gracefully ☐ No crash

---

#### 8.5: Unauthorized Users
**Action:**
1. As non-admin, attempt admin action: `create channel for test`

**Expected Result:**
- Access denied
- Clear error message
- Action not performed

**Verification:** ☐ Access denied ☐ Error clear

---

#### 8.6: Rate Limiting Compliance
**Action:**
1. Send 100 messages rapidly (automated script)
2. Monitor Slack API responses

**Expected Result:**
- Rate limits respected (1 req/sec per method)
- No 429 errors from Slack
- Messages queued if needed

**Verification:** ☐ Rate limits respected ☐ No 429 errors

---

### Scenario 9: Tunnel Mode (Live Browser Takeover)

**Objective:** Test human browser control handoff

**Prerequisites:**
- Browserless.io account with tunnel support
- Task requiring approval

#### 9.1: Request Tunnel URL
**Action:**
1. Create task requiring approval
2. Click "Take Control" button in approval message

**Expected Result:**
- Tunnel URL provided
- Format: `https://production-sfo.browserless.io/live/{session-id}`
- URL is unique per session
- URL sent via DM or in approval thread

**Verification:** ☐ URL received ☐ Format correct ☐ Unique

---

#### 9.2: Open Tunnel URL
**Action:**
1. Click tunnel URL from 9.1

**Expected Result:**
- Opens in new browser tab
- Shows live browser session
- Page displays current browser state
- Controls available (mouse, keyboard)

**Verification:** ☐ Opens successfully ☐ Live session visible

---

#### 9.3: Control Browser via Tunnel
**Action:**
1. In tunnel session, navigate to different page
2. Click elements, type text
3. Take actions

**Expected Result:**
- Actions reflected in live browser
- Low latency (<500ms)
- Smooth experience
- No disconnections

**Verification:** ☐ Control works ☐ Low latency ☐ Stable

---

#### 9.4: Tunnel Timeout After Inactivity
**Action:**
1. Open tunnel
2. Do not interact for timeout period (e.g., 5 minutes)

**Expected Result:**
- Tunnel closes automatically
- User notified of timeout
- Browser session terminated

**Verification:** ☐ Timeout triggered ☐ Session terminated

---

#### 9.5: Tunnel Security (URL Not Guessable)
**Action:**
1. Get tunnel URL
2. Verify URL contains long random token
3. Try accessing with modified token

**Expected Result:**
- URL contains random session ID (>20 chars)
- Modified URLs return 404 or Access Denied
- No session enumeration possible

**Verification:** ☐ Random token ☐ No enumeration

---

### Scenario 10: Glassy Integration

**Objective:** Test Spectacles + Glassy alerting integration

**Prerequisites:**
- Glassy backend running
- Glassy configured to send alerts to Spectacles
- Spectacles webhook configured in Glassy

#### 10.1: Glassy → Spectacles Notification
**Action:**
1. Trigger test alert in Glassy backend:
   ```bash
   # Call Glassy endpoint to trigger security alert
   curl -X POST http://localhost:3000/api/test/trigger-alert \
     -H "Content-Type: application/json" \
     -d '{"type": "privilege_escalation", "severity": "high"}'
   ```

**Expected Result:**
- Alert sent from Glassy to Spectacles webhook
- Spectacles receives notification
- Message posted in Slack channel
- Alert formatted correctly (severity emoji, description)

**Verification:** ☐ Alert sent ☐ Spectacles received ☐ Slack message posted

---

#### 10.2: Alert Triggers Approval Flow
**Action:**
1. Configure Glassy alert to require approval
2. Trigger alert
3. Check Slack for approval request

**Expected Result:**
- Approval request appears in Slack
- Contains alert details
- Buttons available: Approve, Reject, Investigate
- User can respond to alert via Slack

**Verification:** ☐ Approval request received ☐ Buttons work

---

#### 10.3: Query Glassy Status via Slack
**Action:**
1. In Slack, ask: `@Spectacles what's the status of Glassy?`

**Expected Result:**
- Spectacles queries Glassy API (if integration exists)
- Returns Glassy health, recent alerts, status
- OR escalates to human if no integration

**Verification:** ☐ Query succeeds ☐ Status returned

---

#### 10.4: Cross-Project Notifications
**Action:**
1. Set up project channels for both Glassy and Spectacles
2. Trigger alerts in Glassy
3. Check if notifications appear in correct channels

**Expected Result:**
- Glassy alerts go to Glassy project channel
- Spectacles alerts go to Spectacles project channel
- No cross-project contamination

**Verification:** ☐ Correct routing ☐ No cross-talk

---

## Test Results Tracking

After each test, record results in `TEST_RESULTS.md`:

```markdown
| Test Case | Status | Notes | Timestamp |
|-----------|--------|-------|-----------|
| 1.1 | ✅ PASS | Message delivered | 2026-01-20 10:30 |
| 1.2 | ❌ FAIL | Block Kit not rendering | 2026-01-20 10:31 |
```

**Status Codes:**
- ✅ PASS - Test passed as expected
- ❌ FAIL - Test failed or unexpected behavior
- ⚠️ PARTIAL - Partially working, needs investigation
- ⏭️ SKIPPED - Test skipped (reason documented)
- ⏳ PENDING - Not yet executed

---

## Cleanup After Testing

1. **Delete test channels:**
   - `#spectacles-integration-testing`
   - Any other test project channels

2. **Remove test channel mappings:**
   ```bash
   # Restore backup
   cp config/channel_mappings.json.backup config/channel_mappings.json
   ```

3. **Clear test tasks:**
   ```bash
   # Cancel all test tasks via API
   curl -X DELETE https://spectacles-378330630438.us-central1.run.app/api/tasks/test/*
   ```

4. **Post completion summary:**
   - In test channel: "✅ Integration testing completed. All tests documented in TEST_RESULTS.md"
   - Delete test channel after 24 hours

---

## Troubleshooting

### Bot Not Responding
- Check Socket Mode enabled
- Verify `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` valid
- Check service logs: `kubectl logs spectacles-pod -f`

### Webhook Failures
- Verify webhook URLs correct
- Check GCP Secret Manager for `slack-webhook-*` secrets
- Test webhook with `curl`:
  ```bash
  curl -X POST $SLACK_WEBHOOK_MAIN \
    -H "Content-Type: application/json" \
    -d '{"text": "Test message"}'
  ```

### Permission Errors
- Check Slack app scopes match requirements
- Reinstall app to workspace if scopes changed
- Verify bot invited to relevant channels

---

**Next Steps:** Execute tests in order, document results, and compile final report.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
