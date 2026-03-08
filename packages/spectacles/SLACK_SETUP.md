# Spectacles Slack Setup Guide

This guide explains how to set up Spectacles' bidirectional Slack integration for human-in-the-loop browser automation.

---

## Overview

Spectacles integrates with Slack in two ways:

1. **Webhooks** (One-way, for notifications) - Already configured
2. **Socket Mode** (Bidirectional, for commands and Q&A) - This guide

With bidirectional Slack enabled, users can:
- Ask questions about tasks and projects in dedicated channels
- Control tasks via commands (`status`, `pause`, `cancel`, `list`)
- Create project-specific channels for organized automation
- Get AI-powered answers with automatic escalation to humans

---

## Prerequisites

### 1. Slack App Creation

Create a Slack app in your workspace:

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Name: `Spectacles` (or your preference)
4. Workspace: Select your workspace
5. Click **Create App**

### 2. Required OAuth Scopes

Add these **Bot Token Scopes** under **OAuth & Permissions**:

| Scope | Purpose |
|-------|---------|
| `channels:manage` | Create project channels |
| `channels:read` | List and access public channels |
| `channels:history` | Read message history for context |
| `chat:write` | Send messages and replies |
| `groups:write` | Create private channels (optional) |
| `im:history` | Read DM history |
| `im:write` | Send DMs |
| `users:read` | Look up user information |
| `app_mentions:read` | Respond to @mentions |

### 3. Enable Socket Mode

Socket Mode allows Spectacles to receive events without exposing a public webhook endpoint:

1. Go to **Socket Mode** in your app settings
2. Toggle **Enable Socket Mode** to ON
3. Copy the **App-Level Token** (starts with `xapp-`)
   - Store this as `SLACK_APP_TOKEN` environment variable

### 4. Subscribe to Events

Under **Event Subscriptions**:

1. Toggle **Enable Events** to ON
2. Add these **Bot Events**:
   - `message.channels` - Messages in channels
   - `message.im` - Direct messages
   - `app_mention` - When bot is @mentioned

3. Click **Save Changes**

### 5. Install App to Workspace

1. Go to **Install App** in sidebar
2. Click **Install to Workspace**
3. Authorize the app
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)
   - Store this as `SLACK_BOT_TOKEN` environment variable

---

## Configuration

### Step 1: Environment Variables

Add these to your `.env` file or environment:

```bash
# Socket Mode (for bidirectional communication)
SLACK_APP_TOKEN=xapp-XXXX-XXXX-XXXX
SLACK_BOT_TOKEN=xoxb-XXXX-XXXX-XXXX

# Webhooks (for notifications - existing)
SLACK_WEBHOOK_MAIN=https://hooks.slack.com/services/T.../B.../...
SLACK_WEBHOOK_ALEX=https://hooks.slack.com/services/T.../B.../...
SLACK_WEBHOOK_BRIAN=https://hooks.slack.com/services/T.../B.../...
```

### Step 2: Configure Admin Users

Admin users can create project channels. Add admin Slack user IDs to `config/channel_mappings.json`:

```json
{
  "channels": {},
  "admin_users": [
    "U01234ABCD",
    "U56789EFGH"
  ]
}
```

**Finding User IDs:**
1. In Slack, click on a user's profile
2. Click **More** → **Copy member ID**
3. Paste the ID into the `admin_users` array

### Step 3: Deploy or Restart Spectacles

If running locally:
```bash
uvicorn api.main:app --reload --port 8080
```

If running on Cloud Run, redeploy with new environment variables:
```bash
gcloud run deploy spectacles \
  --update-env-vars SLACK_APP_TOKEN=$SLACK_APP_TOKEN,SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN
```

---

## Creating Project Channels

Project channels allow dedicated communication per project with full context awareness.

### Command Syntax

As an admin user, send a DM to the Spectacles bot:

```
create channel for <project-name>
```

**Examples:**
- `create channel for glassy-v2`
- `create channel for ousd-campaign`
- `create channel for legal-research`

### Channel Naming Convention

Channels are automatically prefixed with `spectacles-`:

| Project Name | Channel Created |
|--------------|----------------|
| `glassy-v2` | `#spectacles-glassy-v2` |
| `ousd-campaign` | `#spectacles-ousd-campaign` |
| `my-project` | `#spectacles-my-project` |

### Project Name Requirements

Valid project names must:
- Be **lowercase** (uppercase will be converted automatically)
- Use **hyphens** for spaces (no underscores or special characters)
- Be **3-80 characters** long
- Start with a letter or number

**Valid:**
- `glassy-v2` ✅
- `ousd-campaign-platform` ✅
- `test-project-123` ✅

**Invalid:**
- `My Project` ❌ (spaces, uppercase)
- `project_name` ❌ (underscore)
- `ab` ❌ (too short)

### What Happens When You Create a Channel

1. Bot validates project name
2. Creates Slack channel with name `spectacles-<project-name>`
3. Sets channel description to "Spectacles automation for <project-name>"
4. Invites all admin users to the channel
5. Registers channel mapping in `config/channel_mappings.json`
6. Responds with success message and channel link

**Success Response:**
```
✅ Channel created: #spectacles-glassy-v2 for project `glassy-v2`
```

---

## Using Spectacles in Slack

### 1. Direct Messages (DMs)

Send commands or questions via DM to the Spectacles bot:

**Commands:**
- `help` - Show available commands
- `status task-123` - Get task status
- `pause task-456` - Pause a running task
- `resume task-456` - Resume a paused task
- `cancel task-789` - Cancel a task
- `list tasks` - List all active tasks

**Questions:**
Questions are answered with AI if no command pattern is detected:
- "What is task-123 doing?"
- "How many tasks are running?"

### 2. Project Channels

In project channels, the bot provides project-aware context:

**@mention the bot:**
```
@Spectacles what tasks are running for this project?
```

**AI answers with project context:**
- Active tasks for the project
- Recent task history
- Project-specific information

**Escalation:**
If AI confidence is low or question is complex, the bot escalates to the appropriate human via DM.

### 3. Thread Replies

When the bot sends a notification in a thread, you can reply in that thread:

```
Bot: Task task-123 requires approval to click "Submit Payment"
You: approved
```

The bot will detect your reply and resume the task.

---

## Command Reference

| Command | Description | Example |
|---------|-------------|---------|
| `help` | Show available commands | `help` |
| `status task-ID` | Get task status | `status task-123` |
| `pause task-ID` | Pause running task | `pause task-456` |
| `resume task-ID` | Resume paused task | `resume task-456` |
| `cancel task-ID` | Cancel task | `cancel task-789` |
| `list tasks` | List active tasks | `list tasks` |
| `create channel for PROJECT` | Create project channel (admin only) | `create channel for glassy-v2` |

**Flexible syntax:**
- `What's the status of task 123?` (natural language)
- `task-123 status` (shorthand)
- `Pause task 456` (imperative)

---

## AI Q&A Features

### Automatic Answers

The bot uses Gemini 2.0 Flash to answer questions about:
- Task status and progress
- Project context and history
- System capabilities
- Recent activity

### Context-Aware Responses

In project channels, the bot builds context from:
- Active tasks for the project
- Recent messages in the channel
- Task completion history
- Project metadata

### Escalation to Humans

Questions are escalated to humans when:
- AI confidence is below 60%
- Question is about billing, pricing, or account management
- User explicitly asks to "talk to a human" or "escalate"
- Response timeout (>10 seconds)

**Escalation Format:**
Human receives a DM with:
- Original question
- User and channel information
- AI attempted answer (if low confidence)
- Relevant context (active tasks, recent messages)

---

## Troubleshooting

### Bot Doesn't Respond to Commands

**Possible Causes:**
1. **Socket Mode not enabled** - Check app settings
2. **Event subscriptions missing** - Add `message.im`, `message.channels`, `app_mention`
3. **Bot token expired** - Regenerate and update `SLACK_BOT_TOKEN`
4. **Spectacles service not running** - Check service logs

**Solution:**
```bash
# Check Spectacles logs
docker logs spectacles-container

# Verify environment variables
echo $SLACK_APP_TOKEN
echo $SLACK_BOT_TOKEN

# Restart service
systemctl restart spectacles
```

---

### "Only admins can create channels" Error

**Cause:** User not in `admin_users` array in `config/channel_mappings.json`

**Solution:**
1. Get user's Slack ID (profile → More → Copy member ID)
2. Add to `admin_users` in `config/channel_mappings.json`:
   ```json
   {
     "admin_users": ["U01234ABCD", "U56789EFGH"]
   }
   ```
3. Restart Spectacles (changes are auto-loaded, but restart ensures it)

---

### "Invalid project name" Error

**Cause:** Project name doesn't meet requirements

**Solution:**
Use valid format:
- Lowercase letters and numbers
- Hyphens only (no spaces, underscores, special characters)
- 3-80 characters

**Examples:**
- `My Project` → `my-project` ✅
- `project_name` → `project-name` ✅
- `ab` → `abc` ✅ (at least 3 chars)

---

### Channel Already Exists

**Cause:** Channel with name `spectacles-<project>` already exists

**Solution:**
1. Use a different project name: `glassy-v2` → `glassy-v3`
2. Or delete the existing channel and retry
3. Or manually register the existing channel in `config/channel_mappings.json`

---

### Bot Doesn't Appear in Channel Members

**Cause:** Bot not invited to channel after creation

**Solution:**
Manually invite bot to channel:
1. In Slack, go to the channel
2. Click channel name → Integrations → Add apps
3. Select Spectacles bot

Or use Slack API to invite:
```bash
curl -X POST https://slack.com/api/conversations.invite \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -d "channel=C01234ABCD" \
  -d "users=U_BOT_ID"
```

---

### AI Answers Are Inaccurate

**Possible Causes:**
1. **Insufficient context** - Bot doesn't have recent message history
2. **Gemini API key missing** - Set `GOOGLE_AI_API_KEY` environment variable
3. **Low confidence threshold** - Question is ambiguous

**Solution:**
- Grant `channels:history` and `im:history` scopes
- Verify `GOOGLE_AI_API_KEY` is set
- Rephrase question more specifically
- Questions with <60% confidence escalate to human automatically

---

### Permission Denied Errors

**Cause:** Missing OAuth scopes

**Solution:**
1. Go to app settings → OAuth & Permissions
2. Add missing scopes (see Prerequisites section)
3. Reinstall app to workspace
4. Update `SLACK_BOT_TOKEN` if changed

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   SLACK WORKSPACE                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  User DM  →  @Spectacles  ← Project Channels        │
│      ↓            ↓              ↓                   │
│  ┌──────────────────────────────────────────────┐   │
│  │         Slack Events (Socket Mode)           │   │
│  └──────────────┬───────────────────────────────┘   │
└─────────────────┼──────────────────────────────────┘
                  ↓
       ┌──────────────────────┐
       │  SPECTICLES SERVICE  │
       ├──────────────────────┤
       │  MessageRouter       │
       │       ↓              │
       │  IntentClassifier    │
       │       ↓              │
       │  ┌─────────────────┐ │
       │  │ CommandParser   │ │
       │  │ AIQAHandler     │ │
       │  │ HumanRouter     │ │
       │  └─────────────────┘ │
       └──────────────────────┘
```

**Flow:**
1. User sends message in DM or channel
2. Slack Events API forwards to Spectacles (Socket Mode)
3. MessageRouter determines message type (DM, mention, channel, thread)
4. IntentClassifier identifies intent (command, question, help, etc.)
5. CommandParser executes commands or AIQAHandler answers questions
6. HumanRouter escalates complex questions to appropriate human

---

## Security Considerations

### Secrets Management

**Do NOT commit to version control:**
- `SLACK_APP_TOKEN`
- `SLACK_BOT_TOKEN`
- `SLACK_WEBHOOK_*` URLs

**Store in:**
- `.env` file (local development, add to `.gitignore`)
- GCP Secret Manager (production deployment)
- Environment variables (Cloud Run, Docker)

### PII Filtering

Questions and messages are filtered for PII before logging:
- Email addresses
- Phone numbers
- Credit card numbers
- SSNs

### Admin Authorization

Only users in `config/channel_mappings.json::admin_users` can:
- Create project channels
- Modify channel mappings

All users can:
- Query task status
- Control their own tasks
- Ask questions in project channels

---

## Next Steps

1. **Test Setup:** Use the manual test checklist in `tests/manual/CHANNEL_CREATION_TEST.md`
2. **Create First Channel:** `create channel for test-project`
3. **Try Commands:** `list tasks`, `help`
4. **Ask Questions:** Test AI Q&A in project channel
5. **Monitor Logs:** Check for errors or warnings

For more information, see:
- [README.md](README.md) - Full Spectacles documentation
- [BIDIRECTIONAL_SLACK.md](BIDIRECTIONAL_SLACK.md) - Technical implementation details (created in Phase 4)
- [Slack API Docs](https://api.slack.com/docs) - Official Slack documentation

---

**Questions or Issues?**
- Check logs: `docker logs spectacles-container`
- Review troubleshooting section above
- Contact admin team
