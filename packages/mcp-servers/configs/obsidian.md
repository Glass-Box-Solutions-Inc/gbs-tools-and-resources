# Obsidian MCP Server Configuration

## Prerequisites

1. **Obsidian** installed on the dev VM (`dpkg -l | grep obsidian`)
2. **Local REST API** community plugin enabled in Obsidian
3. **API key** copied from Local REST API plugin settings

## Setup

### 1. Install Local REST API Plugin

1. Open Obsidian
2. Settings → Community Plugins → Browse
3. Search "Local REST API" → Install → Enable
4. Settings → Local REST API → copy the API key

### 2. Set Environment Variable

```bash
# Add to ~/.bashrc or ~/.profile
export OBSIDIAN_API_KEY="your-api-key-here"
```

### 3. Regenerate MCP Config

```bash
cd ~/Desktop/gbs-tools-and-resources/packages/mcp-servers
./scripts/generate-mcp-config.sh ~/.claude/mcp-servers.json
```

### 4. Restart Claude Code

The MCP server will be available on next Claude Code session start.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_API_KEY` | Yes | — | Bearer token from Local REST API plugin |
| `OBSIDIAN_HOST` | No | `127.0.0.1` | Obsidian REST API host |
| `OBSIDIAN_PORT` | No | `27124` | Obsidian REST API port |

## Available Tools

| Tool | Description |
|------|-------------|
| `obsidian_list_files` | List files/directories in vault or subdirectory |
| `obsidian_read_note` | Read note content by path |
| `obsidian_search` | Full-text search across vault |
| `obsidian_create_note` | Create new note with content |
| `obsidian_update_note` | Append/prepend/overwrite note content |
| `obsidian_delete_note` | Delete a note |
| `obsidian_get_frontmatter` | Read YAML frontmatter properties |
| `obsidian_set_frontmatter` | Update YAML frontmatter properties |

## Vault Location

The GBS knowledge vault is `adjudica-documentation/` at `~/Desktop/adjudica-documentation/`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Cannot connect to Obsidian" | Obsidian not running or plugin disabled | Open Obsidian, enable Local REST API plugin |
| 401 Unauthorized | Wrong or missing API key | Copy key from Obsidian → Settings → Local REST API |
| Tools not appearing in Claude Code | MCP config not regenerated | Run `generate-mcp-config.sh` and restart Claude Code |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
