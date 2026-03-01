# Social Media MCP

**Source:** Custom Node.js server in `servers/social-media-mcp/`

Post to LinkedIn, Twitter/X, and Mastodon with AI-powered content generation.

## Setup

1. Build the server:
   ```bash
   cd servers/social-media-mcp
   npm install
   npm run build
   ```

2. Set environment variables:
   - `LINKEDIN_ACCESS_TOKEN` - LinkedIn OAuth token
   - `TWITTER_BEARER_TOKEN` - Twitter/X API bearer token
   - `MASTODON_ACCESS_TOKEN` - Mastodon access token
   - `MASTODON_INSTANCE_URL` - Mastodon instance URL

## Config

```json
{
  "social-media-mcp": {
    "command": "node",
    "args": ["${MCP_SERVERS_DIR}/servers/social-media-mcp/build/index.js"],
    "env": {
      "LINKEDIN_ACCESS_TOKEN": "${LINKEDIN_ACCESS_TOKEN}",
      "TWITTER_BEARER_TOKEN": "${TWITTER_BEARER_TOKEN}",
      "MASTODON_ACCESS_TOKEN": "${MASTODON_ACCESS_TOKEN}",
      "MASTODON_INSTANCE_URL": "${MASTODON_INSTANCE_URL}"
    }
  }
}
```
