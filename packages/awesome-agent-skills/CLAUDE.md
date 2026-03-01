# Awesome Agent Skills

Curated catalog of 180+ official Agent Skills from major development teams and the community.

## Overview

A documentation and reference repository featuring official skills published by leading development teams including Anthropic, Google Labs, Vercel, Stripe, Cloudflare, Hugging Face, Trail of Bits, Expo, Sentry, and more. Agent Skills are folders with instructions, scripts, and resources that teach AI coding assistants specific tasks. Compatible with Claude Code, Cursor, GitHub Copilot, Gemini CLI, Windsurf, and other AI coding assistants.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Type | Documentation/Reference Repository |
| Format | Markdown with YAML frontmatter |
| Compatible Tools | Claude Code, Codex, Antigravity, Gemini CLI, Cursor, GitHub Copilot, OpenCode, Windsurf |
| License | MIT License |
| Distribution | GitHub repository |

## Commands

```bash
# Clone repository
git clone https://github.com/VoltAgent/awesome-agent-skills.git
cd awesome-agent-skills

# Browse skills by category
# - Official Claude Skills (Document Creation, Creative/Design, Development, Branding)
# - Skills by Vercel, Cloudflare, Supabase, Google Labs, Hugging Face
# - Skills by Stripe, Trail of Bits, Expo, Sentry, Better Auth
# - Skills by Tinybird, Neon, fal.ai, Sanity, Remotion
# - Community Skills (Marketing, Productivity, Development, Security, Specialized Domains)

# Use skills with your AI coding assistant
# Copy desired skills to project or global path:
# - Project: .claude/skills/, .cursor/skills/, .gemini/skills/, etc.
# - Global: ~/.claude/skills/, ~/.cursor/skills/, ~/.gemini/skills/, etc.
```

## Architecture

### Skill Paths by AI Coding Assistant

| Tool | Project Path | Global Path |
|------|-------------|-------------|
| Antigravity | `.agent/skills/` | `~/.gemini/antigravity/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Codex | `.codex/skills/` | `~/.codex/skills/` |
| Cursor | `.cursor/skills/` | `~/.cursor/skills/` |
| Gemini CLI | `.gemini/skills/` | `~/.gemini/skills/` |
| GitHub Copilot | `.github/skills/` | `~/.copilot/skills/` |
| OpenCode | `.opencode/skills/` | `~/.config/opencode/skills/` |
| Windsurf | `.windsurf/skills/` | `~/.codeium/windsurf/skills/` |

### Skill Structure

```yaml
---
name: skill-name
description: Brief description of what this skill does
---

# Skill Name
Detailed description

## When to Use This Skill
Use cases and scenarios

## Instructions
Step-by-step guidance for the AI agent

## Additional Sections
Examples, response validation, best practices, etc.
```

### Categories

**Official Teams (100+ skills):**
- Anthropic (17 skills) - Document creation, design, development, branding
- Vercel (8 skills) - React, Next.js, web design, deployment
- Cloudflare (7 skills) - Workers, Durable Objects, MCP servers, web perf
- Hugging Face (8 skills) - ML workflows, datasets, training, evaluation
- Trail of Bits (23 skills) - Security auditing, smart contracts, static analysis
- Expo, Stripe, Sentry, Supabase, Google Labs, Better Auth, and more

**Community Skills (80+ skills):**
- Marketing (SEO, copywriting, ads, content research)
- Productivity (Notion, WhatsApp, Linear, NotebookLM)
- Development (Rails, Terraform, AWS, iOS, SwiftUI, Three.js)
- Testing (Playwright, property-based, fuzzing)
- Security (Firebase scanning, insecure defaults)
- Context Engineering (compression, optimization, memory systems)
- Specialized (scientific research, health assistance, AI research)

### Major Skill Publishers

| Publisher | Skills | Focus Area |
|-----------|--------|------------|
| Anthropic | 17 | Core AI assistant capabilities |
| Trail of Bits | 23 | Security auditing and analysis |
| Vercel | 8 | React/Next.js development |
| Hugging Face | 8 | Machine learning workflows |
| Cloudflare | 7 | Cloud edge computing |
| Community | 80+ | Diverse development needs |

## Environment Variables

No environment variables required. This is a reference repository - skills are copied to your AI assistant's skill directories for use.

Individual skills may require their own API keys or configuration when used with AI assistants (e.g., Vercel deployment requires Vercel API key, fal.ai skills require fal.ai API key).

## Note

For company-wide development standards, see the main CLAUDE.md at /home/vncuser/Desktop/CLAUDE.md.

---

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
