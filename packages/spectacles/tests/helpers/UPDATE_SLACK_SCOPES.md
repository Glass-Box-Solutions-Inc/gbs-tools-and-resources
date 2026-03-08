# Update Slack App Scopes for Channel Creation

**Issue Found:** Bot token missing `channels:manage` scope
**Current Scopes:** `chat:write`, `channels:read`, `users:read`, etc.
**Needed:** `channels:manage` (or `channels:write` + `groups:write`)

---

## Step-by-Step Guide

### Step 1: Open Slack App Settings

1. Go to: https://api.slack.com/apps
2. Find and click on the **Spectacles** app (or whatever it's named)
3. You should see the app dashboard

### Step 2: Add Required Scopes

1. In the left sidebar, click **OAuth & Permissions**
2. Scroll down to **Scopes** section
3. Under **Bot Token Scopes**, click **Add an OAuth Scope**

**Add these scopes:**

| Scope | Purpose | Priority |
|-------|---------|----------|
| `channels:manage` | Create and manage public channels | **REQUIRED** |
| `channels:write` | (Alternative to channels:manage) | REQUIRED |
| `groups:write` | Create private channels | Optional |

**Note:** `channels:manage` includes `channels:write`, so you only need to add `channels:manage`.

### Step 3: Reinstall App to Workspace

**⚠️ IMPORTANT:** After adding new scopes, the app MUST be reinstalled.

1. Scroll to the top of the **OAuth & Permissions** page
2. You should see a banner: "Please reinstall your app for these changes to take effect"
3. Click **Reinstall to Workspace** button
4. Review the new permissions
5. Click **Allow**

### Step 4: Copy New Bot Token

1. After reinstalling, you'll see **Bot User OAuth Token** at the top
2. Click **Copy** button
3. The token starts with `xoxb-`

**Example:** `xoxb-XXXX-XXXX-XXXX` (placeholder — replace with real token)

### Step 5: Update GCP Secret Manager

**I'll do this part - just paste the new token when ready.**

Once you have the new token, I'll run:
```bash
echo -n "YOUR_NEW_TOKEN" | gcloud secrets versions add spectacles-slack-bot-token \
  --data-file=- \
  --project=ousd-campaign
```

---

## Verification Checklist

After reinstalling, verify these scopes are present:

### Previously Had ✅
- ✅ `chat:write` - Send messages
- ✅ `channels:read` - List and access channels
- ✅ `users:read` - Look up user info
- ✅ `chat:write.public` - Send messages to channels without joining

### Newly Added ✨
- ✨ `channels:manage` - Create and manage channels
- ✨ `channels:write` - (Alternative/subset of channels:manage)

---

## After Update

Once the new token is in GCP Secret Manager, I'll:

1. Reload environment with new token
2. Retry channel creation
3. Verify Spectacles bot can create `#spectacles-integration-testing`
4. Record this as **Test Case 5.1: Create Channel** - **PASS** ✅

---

## Quick Reference: Current Status

**Current Token Scopes:**
```
incoming-webhook
chat:write
chat:write.public
channels:read
team:read
users:read
assistant:write
```

**Missing (Needed for Channel Creation):**
```
channels:manage (or channels:write + groups:write)
```

---

## Ready?

When you've completed Steps 1-4, let me know and provide the new bot token.

I'll update GCP Secret Manager and retry the channel creation.
