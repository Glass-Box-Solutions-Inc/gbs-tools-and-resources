#!/bin/bash
# Generate .mcp.json from template + environment variables
# Usage: ./scripts/generate-mcp-config.sh [output-path]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVERS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$MCP_SERVERS_DIR/.mcp.json.template"
OUTPUT="${1:-.mcp.json}"

if [ ! -f "$TEMPLATE" ]; then
    echo "Error: Template not found at $TEMPLATE"
    exit 1
fi

# Replace ${VARIABLE} with env var values, leaving unset ones as-is
cp "$TEMPLATE" "$OUTPUT"

# Replace MCP_SERVERS_DIR first
sed -i "s|\${MCP_SERVERS_DIR}|$MCP_SERVERS_DIR|g" "$OUTPUT"

# Replace SPECTACLES_DIR (default to sibling Spectacles repo on Desktop)
SPECTACLES_DIR="${SPECTACLES_DIR:-$HOME/Desktop/Spectacles}"
sed -i "s|\${SPECTACLES_DIR}|$SPECTACLES_DIR|g" "$OUTPUT"

# Replace known env vars
for var in PENPOT_TOKEN N8N_API_KEY BROWSERLESS_API_TOKEN GOOGLE_AI_API_KEY \
           LINKEDIN_ACCESS_TOKEN TWITTER_BEARER_TOKEN MASTODON_ACCESS_TOKEN MASTODON_INSTANCE_URL \
           KB_DATABASE_URL OBSIDIAN_API_KEY; do
    value="${!var}"
    if [ -n "$value" ]; then
        sed -i "s|\${$var}|$value|g" "$OUTPUT"
    else
        echo "Warning: $var not set - leaving placeholder"
    fi
done

echo "Generated $OUTPUT from template"
