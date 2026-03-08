# Channel Creation Manual Test Checklist

**Purpose:** Verify the Slack channel creation command works correctly and handles all edge cases.

**Prerequisites:**
- Spectacles service running
- Slack app installed with OAuth token
- At least one admin user configured in `config/channel_mappings.json`
- Slack app has `channels:manage`, `channels:read`, `groups:write` scopes

---

## Test Scenarios

### Scenario 1: Valid Channel Creation (Happy Path)

**Test Steps:**
1. As admin user, send DM to Spectacles bot: `create channel for test-project-alpha`
2. Verify bot response indicates success
3. Check Slack workspace for new channel `#spectacles-test-project-alpha`
4. Verify channel description is set to "Spectacles automation for test-project-alpha"
5. Verify admin users are invited to the channel
6. Check `config/channel_mappings.json` for new entry

**Expected Result:**
```
✅ Channel created: #spectacles-test-project-alpha for project `test-project-alpha`
```

**Channel Mapping Entry:**
```json
{
  "channels": {
    "C01234ABCD": {
      "project_name": "test-project-alpha",
      "owner": "U01234",
      "description": "Spectacles automation for test-project-alpha",
      "created_at": "2026-01-18T..."
    }
  }
}
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 2: Non-Admin User Attempts Creation

**Test Steps:**
1. As non-admin user, send DM to Spectacles bot: `create channel for unauthorized-project`
2. Verify bot denies permission

**Expected Result:**
```
🚫 Only admins can create channels.
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 3: Invalid Project Name - Special Characters

**Test Steps:**
1. As admin user, send: `create channel for My Project!`
2. Verify validation error

**Expected Result:**
```
Invalid project name: `My Project!`. Must be lowercase, hyphens only, 3-80 chars.
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 4: Invalid Project Name - Too Short

**Test Steps:**
1. As admin user, send: `create channel for ab`
2. Verify validation error

**Expected Result:**
```
Invalid project name: `ab`. Must be lowercase, hyphens only, 3-80 chars.
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 5: Invalid Project Name - Too Long

**Test Steps:**
1. As admin user, send: `create channel for this-is-a-very-long-project-name-that-exceeds-the-maximum-allowed-length-of-eighty-characters`
2. Verify validation error

**Expected Result:**
```
Invalid project name: `this-is-a-very-long-...`. Must be lowercase, hyphens only, 3-80 chars.
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 6: Missing Project Name

**Test Steps:**
1. As admin user, send: `create channel`
2. Verify helpful error message

**Expected Result:**
```
Please specify a project name. Example: `create channel for glassy-v2`
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 7: Duplicate Channel Name

**Test Steps:**
1. Create channel for `test-project-beta` (should succeed)
2. Attempt to create channel for `test-project-beta` again
3. Verify Slack API error is caught and user-friendly message shown

**Expected Result:**
```
Failed to create channel: name_taken
```
or
```
A channel with this name already exists.
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 8: Slack Client Not Available

**Test Steps:**
1. Stop Spectacles service or disable Slack client
2. Attempt channel creation
3. Verify graceful error handling

**Expected Result:**
```
Slack client not available for channel creation.
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 9: Channel Creation with Uppercase Input

**Test Steps:**
1. As admin user, send: `Create Channel For TEST-PROJECT-GAMMA`
2. Verify project name is normalized to lowercase
3. Verify channel created as `#spectacles-test-project-gamma`

**Expected Result:**
```
✅ Channel created: #spectacles-test-project-gamma for project `test-project-gamma`
```

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Scenario 10: Multiple Admin Invites

**Test Steps:**
1. Configure 3 admin users in `config/channel_mappings.json`
2. Create new channel
3. Verify all 3 admins are invited to the channel

**Expected Result:**
- All admin users appear in channel member list
- No errors in logs for admin invites

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

## Edge Cases

### Edge Case 1: Slack Rate Limiting
**Description:** Create 20+ channels rapidly
**Expected:** Graceful handling of rate limit errors with retry or user message

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Edge Case 2: Network Timeout
**Description:** Simulate network timeout during Slack API call
**Expected:** Timeout error caught, user-friendly message shown

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

### Edge Case 3: Invalid Admin User ID
**Description:** Admin user ID in config doesn't exist in workspace
**Expected:** Channel creation succeeds, admin invite fails gracefully (logged as warning)

**Status:** [ ] Pass [ ] Fail [ ] N/A

---

## Summary

**Total Scenarios:** 13
**Passed:** ___
**Failed:** ___
**N/A:** ___

**Tester:** _______________
**Date:** _______________
**Environment:** _______________

**Notes:**
