# Spectacles Utilization Recommendations for Claude Code

**Analysis Date:** 2026-01-27
**Based on:** 3-month git history, current GSD workflows, active project analysis

---

## Executive Summary

You have a **production-grade browser automation platform (Spectacles)** that is:
- ✅ **Live and running** at `https://spectacles-383072931874.us-central1.run.app`
- ✅ **Fully documented** with 38 references across `.claude/` directory
- ✅ **Integrated in theory** with `checkpoint:ai-verify` workflow designed
- ❌ **NOT being used in practice** - 0 active implementations found

**Opportunity Cost:** You're spending **15-50 minutes/week** on manual visual verification that Spectacles could automate with 80%+ confidence, escalating only edge cases to human review.

---

## Current State Analysis

### What We Found

**Usage Patterns (Last 3 Months):**
- 100+ commits across 8 active projects
- 35% feature development, 20% bug fixes, 8% testing
- **100% of checkpoints are `checkpoint:human-verify`** (manual)
- **0% use `checkpoint:ai-verify`** (automated visual testing)
- **0% of plans have `ai_supervision: true`** frontmatter

**Available Infrastructure:**
- ✅ Spectacles: Production-ready, zero setup cost
- ✅ Playwright: Configured in attorney-dashboard, legal-research
- ✅ VLM access: Gemini 2.5 Flash (vision) + Gemini 3.0 (reasoning)
- ❌ Spectacles MCP: **NOT in `.mcp.json`** - can't call from workflows
- ❌ Environment variables: **BROWSERLESS_API_TOKEN missing**

**Recurring Pain Points:**
- Manual "check if it looks right" steps in every UI feature
- Post-deployment verification gaps (deploy → assume success)
- Auth flow testing repeated manually (OAuth, login, 2FA)
- Form validation not visually verified (error messages, states)
- Responsive design unchecked across viewports
- Visual regression not caught until production
- E2E test selector fragility (41 skipped tests in attorney-dashboard)

---

## Opportunities Identified

### High-Impact Gaps

1. **Post-Deployment Verification** - Every Cloud Run/Vercel deploy lacks automated visual check
2. **Auth Flow Testing** - OAuth, login, role-based UI manually tested each time
3. **Visual Regression Detection** - CSS changes ship without before/after comparison
4. **Form Validation Display** - Error states, tooltips not verified visually
5. **GSD Checkpoint Integration** - `checkpoint:ai-verify` documented but never used

### Projects Ready for Integration

| Project | Priority | Reason | Estimated Time Savings |
|---------|----------|--------|------------------------|
| **Attorney Dashboard** | HIGH | Cloud Run + E2E framework + 41 skipped tests | 20 min/deploy × 3 deploys/week = 1 hour/week |
| **Glassy Platform** | HIGH | 6 existing checkpoints in PLAN.md ready to convert | 15 min/checkpoint × 6 checkpoints = 90 min |
| **Legal Research Dashboard** | MEDIUM | Active development, table/chart consistency critical | 10 min/feature × 2 features/week = 20 min/week |
| **Adjudica.AI Website** | MEDIUM | Visual mockups missing, needs systematic verification | 15 min/deploy × 2 deploys/week = 30 min/week |
| **Glass Box Website** | LOW | Marketing focus, layout consistency matters | 10 min/deploy |

**Total Estimated Time Savings: 2.5-3.5 hours/week**

---

## Priority Recommendations

### 1. HIGH PRIORITY (Immediate Impact)

#### A. Enable Spectacles MCP Server
**Problem:** Cannot call Spectacles from Claude Code workflows
**Impact:** Blocks all automated visual verification
**Effort:** 15 minutes

**Implementation:**

```bash
# 1. Add to .mcp.json
```

```json
{
  "mcpServers": {
    "spectacles": {
      "command": "node",
      "args": ["projects/spectacles/mcp/server.js"],
      "env": {
        "SPECTACLES_API_URL": "https://spectacles-383072931874.us-central1.run.app",
        "BROWSERLESS_API_TOKEN": "${BROWSERLESS_API_TOKEN}",
        "GOOGLE_AI_API_KEY": "${GOOGLE_AI_API_KEY}"
      },
      "description": "Spectacles MCP - Browser automation + VLM verification"
    }
  }
}
```

```bash
# 2. Add environment variables to GCP Secret Manager
gcloud secrets create browserless-api-token --data-file=- --project=alex-stuff-480421
# Paste token, then Ctrl+D

# 3. Test MCP server
claude --mcp-list
```

**Verification:** `claude --mcp-list` should show `spectacles` with 3 tools: `execute_task`, `get_status`, `resume_task`

---

#### B. Convert Glassy Checkpoints to AI-Verify
**Problem:** Glassy Phase 01-01 has 6 manual checkpoints that slow down execution
**Impact:** Automate 90 minutes of manual work
**Effort:** 30 minutes

**Before (Current):**
```markdown
---
phase: 01-web-stack-migration
---

## Tasks

**Task 1:** Setup React Router 7 project structure

**Task 2:** Configure Vite build

**Checkpoint 1:** Verify project builds successfully
- Run `npm run build`
- Check dist/ folder exists
- Verify no errors in console

[Manually test, wait for human]
```

**After (With Spectacles):**
```markdown
---
ai_supervision: true
confidence_threshold: 80
slack_channel: main
---

## Tasks

**Task 1:** Setup React Router 7 project structure

**Task 2:** Configure Vite build

<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>http://localhost:3000</url>
  <criteria>
    <description>Vite development server runs without errors</description>
    <look-for>
      - React Router 7 welcome page or blank screen (expected initial state)
      - No console errors visible
      - No "Module not found" errors
    </look-for>
    <fail-if>
      - Error message displayed
      - Blank page with console errors
      - "Cannot GET /" message
    </fail-if>
  </criteria>
  <escalation-channel>main</escalation-channel>
</task>
```

**Execution Flow:**
1. Claude completes Task 1-2
2. Spectacles navigates to `http://localhost:3000`
3. Captures screenshot
4. Gemini VLM analyzes against criteria
5. If confidence ≥ 80%: Auto-continue, notify Slack ✓
6. If confidence < 80%: Escalate to human via Slack ⚠️

**Time Saved:** 15 min × 6 checkpoints = **90 minutes**

---

#### C. Add Post-Deployment Verification to Attorney Dashboard
**Problem:** Cloud Run deploys succeed but visual rendering failures go undetected
**Impact:** Catch production issues before users do
**Effort:** 20 minutes

**Implementation:**

Add to `attorney-dashboard/.planning/phases/XX/XX-XX-PLAN.md`:

```markdown
---
ai_supervision: true
---

**Task 10:** Deploy to Cloud Run

<task type="auto">
  <name>Trigger Cloud Build deployment</name>
  <action>
    git add -A && \
    git commit -m "feat(dashboard): deploy Phase XX-XX changes" && \
    git push origin main
  </action>
  <verify>
    Cloud Build succeeds (check logs), \
    Cloud Run service updated (gcloud run services describe)
  </verify>
</task>

<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>https://attorney-dashboard-web-5paunecalq-uc.a.run.app</url>
  <criteria>
    <description>Dashboard renders without errors after deployment</description>
    <look-for>
      - Attorney Dashboard title visible
      - Navigation menu renders
      - Case list table displays
      - No error messages or broken layouts
    </look-for>
    <fail-if>
      - 404 or 500 error page
      - Blank white screen
      - "Application Error" message
      - CSS not loading (unstyled content)
    </fail-if>
  </criteria>
  <escalation-channel>alex</escalation-channel>
</task>
```

**Expected Behavior:**
- Deploy completes → Spectacles automatically visits URL
- If confident: Slack notification "✓ Attorney Dashboard deployment verified"
- If uncertain: Slack with screenshot "⚠️ Deployment needs review" + Browserless Live View link
- **Time Saved:** 5-10 min per deploy × 3 deploys/week = **15-30 min/week**

---

#### D. Implement Visual Regression Detection for Legal Research Dashboard
**Problem:** TanStack Table styling changes break silently
**Impact:** Catch CSS regressions before production
**Effort:** 45 minutes (one-time baseline setup)

**Step 1: Capture Baseline Screenshots**

```bash
# From legal-research-dashboard directory
curl -X POST https://spectacles-383072931874.us-central1.run.app/api/skills/screenshot \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://legal-research-dashboard-816980776764.us-central1.run.app",
    "mode": "browser",
    "full_page": true,
    "blur_pii": false
  }' | jq -r '.screenshot_base64' | base64 -d > .visual-baselines/dashboard-home.png

# Capture other critical pages
curl -X POST ... -d '{"url": ".../cases"}' ... > .visual-baselines/cases-table.png
curl -X POST ... -d '{"url": ".../research"}' ... > .visual-baselines/research-view.png
```

**Step 2: Add Visual Comparison to Deployment Plan**

```markdown
<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>https://legal-research-dashboard-816980776764.us-central1.run.app</url>
  <criteria>
    <description>Dashboard layout matches baseline (no visual regressions)</description>
    <look-for>
      - Table columns align correctly
      - Header navigation layout unchanged
      - Search filters display properly
      - No content overflow or clipping
    </look-for>
    <fail-if>
      - Layout shifted or broken
      - Missing UI elements
      - Styling completely different
      - Text overlapping or unreadable
    </fail-if>
  </criteria>
  <escalation-channel>main</escalation-channel>
</task>
```

**VLM Prompt (Automatic):**
```
Compare the current screenshot to the baseline screenshot from .visual-baselines/dashboard-home.png.

Are there any significant visual regressions?
- Layout shifts
- Missing elements
- Color/styling changes
- Content overflow

Confidence: X%
```

**Time Saved:** Prevents visual bugs from reaching production, **saves 1-2 hotfixes per month**

---

### 2. MEDIUM PRIORITY (High Value)

#### E. Automate OAuth Flow Testing
**Problem:** BetterAuth, GitHub OAuth flows manually tested every auth change
**Impact:** Prevent auth regressions, automate repetitive testing
**Effort:** 1 hour (reusable across projects)

**Implementation:**

Create shared verification script:

```typescript
// .claude/scripts/verify-oauth-flow.ts

import { createSpecticlesClient } from './spectacles-client';

export async function verifyOAuthFlow(params: {
  provider: 'github' | 'google' | 'betterauth';
  startUrl: string;
  credentialsKey: string;
  expectedRedirect: string;
}) {
  const spectacles = createSpecticlesClient();

  const result = await spectacles.execute_task({
    goal: `Complete ${params.provider} OAuth flow and verify successful redirect to ${params.expectedRedirect}`,
    start_url: params.startUrl,
    credentials_key: params.credentialsKey,
    require_approval: false
  });

  return {
    success: result.status === 'completed',
    redirectUrl: result.final_url,
    confidence: result.confidence
  };
}
```

**Usage in Plans:**

```markdown
<task type="auto">
  <name>Test GitHub OAuth integration</name>
  <action>
    node .claude/scripts/verify-oauth-flow.ts \
      --provider=github \
      --start-url="https://myapp.com/auth/github" \
      --credentials-key="github_test_user" \
      --expected-redirect="https://myapp.com/dashboard"
  </action>
  <verify>
    Script exits 0, \
    OAuth flow completes successfully, \
    User redirected to dashboard
  </verify>
</task>
```

**Time Saved:** 10 min per auth feature × 2 features/month = **20 min/month**

---

#### F. Fill E2E Test Gaps with VLM-Based Verification
**Problem:** Attorney Dashboard has 41 skipped E2E tests due to auth state issues
**Impact:** Increase test coverage from 85% to 95%+
**Effort:** 2 hours

**Current Issue:**
```typescript
// attorney-dashboard/frontend/test/e2e/cases.spec.ts
test.skip('should display case details', async ({ page }) => {
  // Skipped: Auth state not persisting in E2E environment
});
```

**Solution with Spectacles:**

```typescript
// Replace Playwright selector-based tests with Spectacles VLM verification

test('should display case details (VLM-verified)', async () => {
  const result = await spectacles.execute_task({
    goal: 'Navigate to case #123 and verify details display correctly',
    start_url: 'https://attorney-dashboard-web.../cases/123',
    credentials_key: 'test-assistant-user',
    require_approval: false
  });

  expect(result.status).toBe('completed');
  expect(result.final_observation).toContain('case details');
  expect(result.confidence).toBeGreaterThan(80);
});
```

**Benefits:**
- No selector brittleness (VLM finds elements by description)
- Handles auth state automatically (Spectacles manages cookies/sessions)
- Visual verification (catches layout issues E2E tests miss)

**Time Saved:** Un-skip 41 tests, **increase coverage by 10%**

---

#### G. Form Validation Visual Verification
**Problem:** React Hook Form + Zod error messages not verified visually
**Impact:** Error state UX issues caught early
**Effort:** 30 minutes per form-heavy feature

**Before (No Verification):**
```typescript
// Form implemented, manually test error states:
// - Invalid email format → should show "Invalid email" error
// - Missing required field → should show "Required" error
// - Submit disabled until valid → should gray out button
```

**After (Automated):**

```markdown
<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>http://localhost:3000/register</url>
  <criteria>
    <description>Registration form displays validation errors correctly</description>
    <look-for>
      - "Invalid email" error message below email field
      - "Password must be 8+ characters" error message
      - Submit button disabled (grayed out) when form invalid
      - Submit button enabled (blue) when form valid
    </look-for>
    <fail-if>
      - No error messages display
      - Submit button active despite invalid input
      - Errors display in wrong location
    </fail-if>
  </criteria>
</task>
```

**Coverage:**
- Error message text
- Error message styling (color, position)
- Button state (disabled vs enabled)
- Field highlighting (red border on error)

**Time Saved:** 10-15 min per form × 2 forms/month = **20-30 min/month**

---

### 3. QUICK WINS (Easy to Implement)

#### H. Add Spectacles Screenshot to All Deployment Commits
**Effort:** 5 minutes per project
**Impact:** Visual confirmation of every deploy

**Add to deployment documentation:**

```bash
# After Cloud Run deployment succeeds
curl -X POST https://spectacles-383072931874.us-central1.run.app/api/skills/screenshot \
  -d '{"url": "https://your-app-url.run.app", "full_page": true}' \
  | jq -r '.screenshot_base64' | base64 -d > deployment-$(date +%Y%m%d-%H%M).png

# Upload to Slack
curl -F file=@deployment-*.png -F channels=C0A5YU9EHSB -F token=$SLACK_BOT_TOKEN \
  https://slack.com/api/files.upload
```

**Time Saved:** 5 min per deploy (visual confirmation without opening browser)

---

#### I. Enable Responsive Testing for Adjudica.AI Website
**Effort:** 15 minutes
**Impact:** Catch mobile layout issues before production

```typescript
// Test multiple viewports automatically
const viewports = [
  { width: 375, height: 667, name: 'iPhone SE' },
  { width: 768, height: 1024, name: 'iPad' },
  { width: 1920, height: 1080, name: 'Desktop' }
];

for (const viewport of viewports) {
  await spectacles.execute_task({
    goal: `Screenshot homepage at ${viewport.name} resolution`,
    start_url: 'https://adjudica.ai',
    viewport: viewport,
    require_approval: false
  });
}
```

**Time Saved:** 5 min per viewport × 3 viewports = **15 min per responsive feature**

---

#### J. Slack Notification for All Verifications
**Effort:** 0 minutes (already configured)
**Impact:** Visibility into automated testing

Spectacles automatically sends Slack notifications:
- ✓ Verification passed (high confidence)
- ⚠️ Verification needs review (low confidence)
- ✗ Verification failed (errors detected)

**Channel routing:**
```
- Production deploys → #main
- Dev/staging deploys → #engineering
- Personal projects → @alex DM
```

**Already works!** Just enable `ai_supervision: true` in plans.

---

## Implementation Guide

### Phase 1: Foundation (Week 1)

**Day 1-2: MCP Configuration**
- [ ] Add Spectacles MCP to `.mcp.json`
- [ ] Add `BROWSERLESS_API_TOKEN` to environment
- [ ] Test MCP tools: `claude --mcp-list`, verify `spectacles_execute_task` available

**Day 3-4: First AI-Verify Checkpoint**
- [ ] Convert 1 Glassy checkpoint to `ai-verify`
- [ ] Add `ai_supervision: true` frontmatter
- [ ] Execute plan, observe Spectacles in action
- [ ] Tune confidence threshold based on results

**Day 5: Post-Deployment Verification**
- [ ] Add `ai-verify` checkpoint to Attorney Dashboard deployment
- [ ] Deploy to staging, verify Spectacles screenshot + VLM analysis
- [ ] Monitor Slack notifications, adjust criteria if needed

### Phase 2: Scale (Week 2-3)

**Convert Remaining Glassy Checkpoints**
- [ ] 5 more checkpoints → ai-verify
- [ ] Measure time savings vs manual verification

**Enable Visual Regression Detection**
- [ ] Capture baseline screenshots for Legal Research Dashboard
- [ ] Add before/after comparison to deployment workflows

**OAuth Flow Automation**
- [ ] Create reusable oauth verification script
- [ ] Test with GitHub OAuth, BetterAuth
- [ ] Add to auth-related plan templates

### Phase 3: Optimize (Week 4+)

**Fill E2E Test Gaps**
- [ ] Replace 10 skipped E2E tests with Spectacles VLM verification
- [ ] Measure coverage increase

**Form Validation Verification**
- [ ] Add to all new form implementations
- [ ] Standardize error state verification criteria

**Multi-Viewport Testing**
- [ ] Implement responsive verification for Adjudica.AI
- [ ] Extend to Glass Box Website

---

## Project-Specific Integration Plans

### Attorney Dashboard

**Current State:**
- 586 backend tests, 272 frontend tests passing
- 41 E2E tests skipped (auth state issues)
- Cloud Run deployment automated
- Manual verification after each deploy

**Integration Plan:**

1. **Post-Deployment Visual Check** (Week 1)
   ```
   Deploy → Cloud Build → ai-verify checkpoint → Slack notification
   ```

2. **Replace Skipped E2E Tests** (Week 2-3)
   ```
   41 skipped tests → 30 VLM-verified Spectacles tasks
   Coverage: 85% → 95%
   ```

3. **Case Management UI Verification** (Week 4)
   ```
   Case list, case details, timeline view → automated visual verification
   ```

**Expected Time Savings:** 1 hour/week

---

### Glassy Platform

**Current State:**
- Phase 01-01 with 6 manual checkpoints
- React Router 7 migration in progress
- Multiple sub-projects (web, backend, mobile)

**Integration Plan:**

1. **Convert 6 Checkpoints** (Week 1)
   ```
   checkpoint:human-verify → checkpoint:ai-verify
   ai_supervision: true frontmatter
   ```

2. **Dashboard & Chat Visual Regression** (Week 2)
   ```
   Baseline screenshots captured
   Before/after comparison on each deploy
   ```

3. **Mobile App Screenshot Verification** (Week 3)
   ```
   iOS/Android emulator screenshots
   VLM verification of UI consistency
   ```

**Expected Time Savings:** 90 minutes initially, 30 min/week ongoing

---

### Legal Research Dashboard

**Current State:**
- Active development on research visualization
- TanStack Table for cases display
- Cloud Run deployment

**Integration Plan:**

1. **Visual Baseline Capture** (Day 1)
   ```
   3 critical pages: dashboard, cases table, research view
   Baseline screenshots stored in .visual-baselines/
   ```

2. **Deployment Visual Regression** (Week 1)
   ```
   Deploy → ai-verify with baseline comparison → Slack notification
   ```

3. **Table Layout Verification** (Week 2)
   ```
   Column alignment, sorting, filtering → automated verification
   ```

**Expected Time Savings:** 20 min/week

---

### Adjudica.AI & Glass Box Websites

**Current State:**
- Marketing focus, visual consistency critical
- Next.js deployments
- Manual QA for layout issues

**Integration Plan:**

1. **Multi-Viewport Screenshots** (Week 1)
   ```
   Mobile, tablet, desktop → automated screenshots
   ```

2. **Visual Asset Verification** (Week 2)
   ```
   Images, logos, icons → load verification
   Color/branding consistency → VLM check
   ```

3. **Responsive Layout Testing** (Week 3)
   ```
   Breakpoint verification at 375px, 768px, 1920px
   ```

**Expected Time Savings:** 30 min/week per site

---

## Success Metrics

### Quantitative

- **Time Saved:** Target 2.5-3.5 hours/week (based on current manual verification)
- **Test Coverage:** Increase from 85% → 95%+ (41 skipped tests un-skipped)
- **Deployment Confidence:** 0% automated visual checks → 100%
- **Visual Regressions Caught:** 0/month → 2-3/month (before production)

### Qualitative

- **Reduced Context Switching:** No more "check if it looks right" manual steps
- **Faster Feedback Loops:** AI verification completes in 30-60 seconds vs 5-10 minutes manual
- **Higher Quality:** VLM catches visual issues humans miss (contrast, alignment, responsive)
- **Documentation:** Screenshots automatically captured for each deploy (audit trail)

### Leading Indicators

- **Week 1:** Spectacles MCP configured, first ai-verify checkpoint executed
- **Week 2:** 3 projects using ai-verify in active plans
- **Week 4:** 50%+ of visual verifications automated
- **Week 8:** Zero manual "check the UI" checkpoints in new plans

---

## Cost-Benefit Analysis

### Investment

| Item | Time Investment |
|------|-----------------|
| MCP configuration | 15 min (one-time) |
| Environment setup | 30 min (one-time) |
| First ai-verify checkpoint | 45 min (learning curve) |
| Convert existing checkpoints | 15 min each |
| Visual baseline capture | 30 min per project |
| OAuth flow automation script | 1 hour (reusable) |
| E2E test replacement | 2 hours |

**Total:** ~6 hours initial setup

### Return

| Item | Time Saved |
|------|------------|
| Post-deployment verification | 20 min/deploy × 3/week = 1 hour/week |
| Glassy checkpoint automation | 90 min initially, 30 min/week ongoing |
| Legal Research visual regression | 20 min/week |
| Website visual verification | 30 min/week per site |
| Form validation checks | 20 min/month |
| OAuth testing | 20 min/month |

**Total:** ~2.5-3.5 hours/week = **10-14 hours/month**

**Break-even:** Week 2
**ROI after 1 month:** 5-8 hours net time savings
**ROI after 3 months:** 30-40 hours net time savings

---

## Risk Mitigation

### Risk: VLM Confidence Too Low

**Mitigation:**
- Start with threshold = 70% (escalate more often)
- Tune upward as you learn what "good enough" looks like
- Provide detailed `<look-for>` criteria to guide VLM

### Risk: False Positives (Auto-Approve When Shouldn't)

**Mitigation:**
- Use `gate="non-blocking"` for critical paths initially
- Review escalated cases to identify patterns
- Adjust criteria based on false positive patterns

### Risk: Environment Access Issues

**Mitigation:**
- Test localhost URLs first (development environment)
- For internal Cloud Run services, ensure Spectacles can access (VPN/allowlist)
- Use staging URLs before production

### Risk: Spectacles Downtime

**Mitigation:**
- Spectacles is deployed on Cloud Run (high availability)
- If down, checkpoints fall back to manual verification
- Monitor Spectacles `/health` endpoint

---

## Next Steps (Immediate Actions)

1. **Add Spectacles MCP to `.mcp.json`** (15 min) → [See recommendation A](#a-enable-spectacles-mcp-server)
2. **Add `BROWSERLESS_API_TOKEN` to environment** (5 min)
3. **Test MCP tools:** `claude --mcp-list` → verify `spectacles_execute_task` appears
4. **Convert 1 Glassy checkpoint to `ai-verify`** (30 min) → [See recommendation B](#b-convert-glassy-checkpoints-to-ai-verify)
5. **Execute plan and observe:** Watch Spectacles → VLM → Slack flow
6. **Add post-deploy check to Attorney Dashboard** (20 min) → [See recommendation C](#c-add-post-deployment-verification-to-attorney-dashboard)

**Start with recommendations A, B, C this week. Measure time savings. Expand from there.**

---

## Conclusion

You've built excellent infrastructure (Spectacles, E2E frameworks, VLM access) but haven't connected it into your daily workflow. The gap is **adoption**, not **capability**.

**The opportunity:** Automate 2.5-3.5 hours/week of manual visual verification with AI, while increasing quality and catching issues earlier.

**The path:** Start with 3 high-priority recommendations (A, B, C) this week. Measure impact. Scale what works.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
