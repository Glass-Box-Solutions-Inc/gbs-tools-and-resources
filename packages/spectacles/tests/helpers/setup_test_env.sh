#!/bin/bash
###############################################################################
# Spectacles Test Environment Setup
#
# Loads necessary credentials from GCP Secret Manager for integration testing
#
# Usage:
#   source tests/helpers/setup_test_env.sh
#
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
###############################################################################

set -e

PROJECT_ID="glassbox-spectacles"

echo "================================================================"
echo "Setting up Spectacles Test Environment"
echo "================================================================"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI not found"
    echo "   Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "❌ Error: Not authenticated with gcloud"
    echo "   Run: gcloud auth login"
    exit 1
fi

echo ""
echo "Loading Slack credentials from GCP Secret Manager..."
echo ""

# Load Slack Bot Token
echo "🔐 Loading SLACK_BOT_TOKEN..."
export SLACK_BOT_TOKEN=$(gcloud secrets versions access latest \
    --secret="spectacles-slack-bot-token" \
    --project="$PROJECT_ID" 2>/dev/null || echo "")

if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "⚠️  Warning: SLACK_BOT_TOKEN not loaded (secret may not exist)"
else
    echo "✅ SLACK_BOT_TOKEN loaded (${SLACK_BOT_TOKEN:0:10}...)"
fi

# Load Slack App Token (Socket Mode)
echo "🔐 Loading SLACK_APP_TOKEN..."
export SLACK_APP_TOKEN=$(gcloud secrets versions access latest \
    --secret="spectacles-slack-app-token" \
    --project="$PROJECT_ID" 2>/dev/null || echo "")

if [ -z "$SLACK_APP_TOKEN" ]; then
    echo "⚠️  Warning: SLACK_APP_TOKEN not loaded (secret may not exist)"
else
    echo "✅ SLACK_APP_TOKEN loaded (${SLACK_APP_TOKEN:0:10}...)"
fi

# Load Gemini API Key (for AI Q&A testing)
echo "🔐 Loading GOOGLE_AI_API_KEY..."
export GOOGLE_AI_API_KEY=$(gcloud secrets versions access latest \
    --secret="gemini-api-key" \
    --project="$PROJECT_ID" 2>/dev/null || echo "")

if [ -z "$GOOGLE_AI_API_KEY" ]; then
    echo "⚠️  Warning: GOOGLE_AI_API_KEY not loaded (AI Q&A tests will be skipped)"
else
    echo "✅ GOOGLE_AI_API_KEY loaded"
fi

# Set approval channel
export SLACK_APPROVAL_CHANNEL="#spectacles-integration-testing"

# Set Spectacles service URL
export SPECTACLES_URL="https://spectacles-gc2qovgs7q-uc.a.run.app"

echo ""
echo "================================================================"
echo "Environment Setup Complete"
echo "================================================================"
echo ""
echo "Loaded Variables:"
echo "  SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN:+SET (${SLACK_BOT_TOKEN:0:10}...)}"
echo "  SLACK_APP_TOKEN: ${SLACK_APP_TOKEN:+SET (${SLACK_APP_TOKEN:0:10}...)}"
echo "  GOOGLE_AI_API_KEY: ${GOOGLE_AI_API_KEY:+SET}"
echo "  SLACK_APPROVAL_CHANNEL: $SLACK_APPROVAL_CHANNEL"
echo "  SPECTACLES_URL: $SPECTACLES_URL"
echo ""
echo "Next Steps:"
echo "  1. Create test channel in Slack: $SLACK_APPROVAL_CHANNEL"
echo "  2. Invite Spectacles bot to the channel"
echo "  3. Run test scripts:"
echo "     python3 tests/helpers/send_test_notification.py --type info --message 'Test'"
echo ""
