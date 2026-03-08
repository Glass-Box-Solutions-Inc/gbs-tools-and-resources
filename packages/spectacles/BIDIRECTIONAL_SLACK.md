# Bidirectional Slack Communication System

**Technical implementation documentation for Spectacles' Slack integration.**

---

## Overview

Spectacles' bidirectional Slack system enables two-way communication between users and the browser automation service via Slack. Users can ask questions, control tasks, and receive AI-powered answers with automatic human escalation.

### Key Features

- **Bidirectional Communication**: Users send commands/questions, bot responds
- **AI-Powered Q&A**: Gemini 2.0 Flash answers questions with project context
- **Smart Escalation**: Low-confidence or complex questions route to humans
- **Project Channels**: Dedicated channels per project with context awareness
- **Command Control**: Pause, resume, cancel, and query tasks via Slack
- **Thread Support**: Reply in threads for task approvals
- **PII Protection**: Automatic PII filtering before logging

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SLACK WORKSPACE                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  User DM  →  @Spectacles Mention  ←  Project Channels   │
│      │              │                        │           │
│      └──────────────┼────────────────────────┘           │
│                     │                                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Slack Events (Socket Mode)               │   │
│  └──────────────┬───────────────────────────────────┘   │
└─────────────────┼────────────────────────────────────────┘
                  ↓
       ┌──────────────────────┐
       │  SPECTICLES SERVICE  │
       ├──────────────────────┤
       │  SlackClient         │
       │       ↓              │
       │  MessageRouter       │
       │       ↓              │
       │  IntentClassifier    │
       │       ↓              │
       │  ┌─────────────────┐ │
       │  │ CommandParser   │ │
       │  ├─────────────────┤ │
       │  │ AIQAHandler     │ │
       │  ├─────────────────┤ │
       │  │ HumanRouter     │ │
       │  └─────────────────┘ │
       └──────────────────────┘
                  ↓
       ┌──────────────────────┐
       │  ChannelContext      │
       │  Manager             │
       ├──────────────────────┤
       │  TaskStore           │
       └──────────────────────┘
```

---

## Component Architecture

### 1. SlackClient (`hitl/slack_client.py`)

**Purpose:** Socket Mode connection to Slack, event handling

**Responsibilities:**
- Maintain WebSocket connection to Slack
- Listen for message events (`message.im`, `message.channels`, `app_mention`)
- Forward events to MessageRouter
- Provide `say` function for replying

**Key Methods:**
```python
async def start():  # Start Socket Mode listener
async def message_handler(event, say):  # Handle message events
async def send_message(channel, text):  # Send message to channel
```

---

### 2. MessageRouter (`hitl/message_router.py`)

**Purpose:** Routes incoming messages to appropriate handlers

**Routing Logic:**

```
Incoming Message
    │
    ├── In Thread? → ThreadHandler
    ├── DM? → DM Handler
    ├── @Mention? → Mention Handler
    ├── Project Channel? → Channel Handler
    └── Else → Ignore
```

**Key Methods:**
```python
async def route_message(event, say_fn, client) -> Optional[str]
async def _handle_dm(event, text, user_id, say_fn) -> str
async def _handle_mention(event, text, user_id, channel_id, say_fn) -> str
async def _handle_channel_message(event, text, user_id, channel_id, project_name, say_fn) -> Optional[str]
async def _handle_thread_reply(event, text, user_id, thread_ts, say_fn) -> Optional[str]
```

**Thread Detection:**
```python
if thread_ts and thread_ts != message_ts:
    # Message is a reply in a thread
    handle_thread_reply()
```

---

### 3. IntentClassifier (`hitl/intent_classifier.py`)

**Purpose:** Determine user intent from message text

**Intent Types:**
- `STATUS_QUERY`: Check task status
- `COMMAND`: Execute task command (pause, cancel, resume, list)
- `QUESTION`: General question about project/system
- `CHANNEL_CREATE`: Request to create project channel
- `ESCALATE`: Complex/ambiguous query needing human review
- `HELP`: Show available commands

**Classification Method:**
1. **Pattern Matching (Fast):** Regex patterns for common intents (90% accurate)
2. **AI Fallback (Optional):** Gemini for ambiguous cases

**Key Methods:**
```python
def classify(message: str, context: Optional[Dict]) -> ClassificationResult
def _classify_with_patterns(message: str, context: Optional[Dict]) -> ClassificationResult
def _extract_command(message: str) -> Optional[str]
def _extract_project_name(message: str) -> Optional[str]
```

**Example Patterns:**
```python
PATTERNS = {
    Intent.STATUS_QUERY: [
        r'status\s+(of\s+)?task[\s-]?\d+',
        r'how.*doing',
        r'progress\s+(of|on)'
    ],
    Intent.COMMAND: [
        r'^(pause|cancel|resume|stop|kill)\s+task',
        r'^list\s+(tasks|active)'
    ]
}
```

---

### 4. CommandParser (`hitl/command_parser.py`)

**Purpose:** Parse and execute task commands

**Supported Commands:**
- `status task-123` - Get task status
- `pause task-456` - Pause running task
- `resume task-789` - Resume paused task
- `cancel task-101` - Cancel task
- `list tasks` - List active tasks
- `create channel for PROJECT` - Create project channel (admin only)
- `help` - Show available commands

**Authorization:**
- Admin check for channel creation (via ChannelContextManager)
- Task owner check for task control (future: per-task permissions)

**Key Methods:**
```python
async def parse_and_execute(message, user_id, channel_id) -> CommandResult
async def _handle_status(message, user_id) -> CommandResult
async def _handle_pause(message, user_id) -> CommandResult
async def _handle_cancel(message, user_id) -> CommandResult
async def _handle_create_channel(message, user_id, channel_id) -> CommandResult
```

---

### 5. AIQAHandler (`hitl/ai_qa_handler.py`)

**Purpose:** Answer questions using Gemini 2.0 Flash with project context

**Features:**
- **Context Building:** Project info, active tasks, recent messages
- **Confidence Scoring:** Heuristic-based (0.0-1.0)
- **Auto-Escalation:** Billing, pricing, account questions
- **PII Filtering:** Remove emails, phones, SSNs from logs
- **Timeout Protection:** 10s max response time

**Context Window:**
```python
{
  'project_name': 'glassy',
  'project_description': 'Glassy platform development',
  'active_tasks': [
    {'task_id': 'task-123', 'goal': '...', 'state': 'RUNNING'}
  ],
  'recent_messages': [
    {'user': 'U123', 'text': 'Last message...'}
  ]
}
```

**Confidence Extraction:**
```python
# ESCALATE marker → 0.1
# "I don't know" → 0.3
# Contains task IDs/numbers → 0.9
# Default → 0.7
```

**Escalation Rules:**
- Confidence < 0.6 (configurable threshold)
- Billing/pricing/account keywords
- User says "talk to human" or "escalate"
- Timeout (>10s)

**Key Methods:**
```python
async def answer_question(question, user_id, channel_id, project_name) -> str
def _build_context(channel_id, project_name) -> Dict
async def _generate_response(question, context) -> tuple[str, float]
def _should_escalate(response, confidence) -> bool
def _filter_pii(text) -> str
```

---

### 6. HumanRouter (`hitl/human_router.py`)

**Purpose:** Route escalated questions to appropriate humans via DM

**Routing Logic:**
1. **Topic-Based:** Billing → Alex, Usage → Brian
2. **Project Owner:** Check channel mapping for project owner
3. **Fallback:** Default recipient (usually Alex)

**Escalation Message Format:**
```markdown
🆘 Escalation Needed

From: @U123 in #channel-name
Project: project-name

Question:
> User's original question

AI Response (confidence: 40%):
> AI attempted answer

Active Tasks:
• task-123: Goal... (RUNNING)
• task-456: Goal... (AWAITING_HUMAN)

Recent Messages:
• user: message...
• user: message...

---
Reply in this thread to answer the user.
```

**Key Methods:**
```python
async def escalate(question, user_id, channel_id, context, ai_response, confidence)
def _determine_recipient(project_name, question) -> str
def _format_escalation_message(...) -> str
async def _send_dm(recipient_id, message)
```

**Topic Routes:**
```python
TOPIC_ROUTES = {
    'alex': ['billing', 'payment', 'cost', 'price', 'invoice', 'account'],
    'brian': ['usage', 'quota', 'limit', 'rate', 'capacity']
}
```

---

### 7. ChannelContextManager (`hitl/channel_context_manager.py`)

**Purpose:** Manage channel-to-project mappings and context

**Configuration File:** `config/channel_mappings.json`
```json
{
  "channels": {
    "C01234ABCD": {
      "project_name": "glassy",
      "owner": "alex",
      "description": "Glassy platform development",
      "created_at": "2026-01-18T10:30:00"
    }
  },
  "admin_users": ["U01234", "U56789"]
}
```

**Key Methods:**
```python
def get_project_for_channel(channel_id) -> Optional[str]
def get_channel_context(channel_id, task_store, message_history) -> Optional[ChannelContext]
def register_channel(channel_id, project_name, owner, description) -> bool
def is_admin(user_id) -> bool
```

---

## Message Flow Examples

### Example 1: DM Help Command

```
User DM: "help"

1. SlackClient receives message event
2. MessageRouter.route_message(event)
3. Detects DM (channel starts with 'D')
4. Calls _handle_dm()
5. IntentClassifier.classify("help") → Intent.HELP
6. CommandParser._show_help()
7. Returns help text
8. SlackClient.say(help_text)

User receives: Help message with available commands
```

### Example 2: Project Channel Question

```
User in #spectacles-glassy: "@Spectacles what tasks are running?"

1. SlackClient receives app_mention event
2. MessageRouter.route_message(event)
3. Detects @mention (text starts with '<@U...')
4. Calls _handle_mention()
5. IntentClassifier.classify("what tasks are running?") → Intent.QUESTION
6. ChannelContextManager.get_project_for_channel("C123") → "glassy"
7. AIQAHandler.answer_question()
   a. _build_context() → Gets glassy project info, active tasks, recent messages
   b. _generate_response() → Calls Gemini with context
   c. _extract_confidence() → 0.9 (has task IDs)
   d. Not escalated (confidence > 0.6)
8. Returns AI answer
9. SlackClient.say(answer, thread_ts=message_ts)

User receives: AI answer in thread
```

### Example 3: Billing Question Escalation

```
User DM: "What is the billing for this month?"

1. SlackClient receives message event
2. MessageRouter.route_message(event)
3. Detects DM
4. Calls _handle_dm()
5. IntentClassifier.classify() → Intent.QUESTION
6. AIQAHandler.answer_question()
   a. _should_auto_escalate() → True (contains "billing")
   b. _escalate_to_human()
   c. HumanRouter.escalate()
      - _determine_recipient() → "alex" (billing keyword)
      - _format_escalation_message()
      - _send_dm("U_ALEX", formatted_message)
7. Returns "escalated" message
8. SlackClient.say(escalation_message)

User receives: "🆘 I've escalated your question to a human..."
Alex receives DM: Formatted escalation with full context
```

### Example 4: Thread Reply

```
Bot in #channel (thread_ts=123.000): "Task task-456 requires approval..."
User replies in thread: "approved"

1. SlackClient receives message event with thread_ts=123.000, ts=123.456
2. MessageRouter.route_message(event)
3. Detects thread (thread_ts != ts)
4. Calls _handle_thread_reply()
5. Extract task_id from thread context (future enhancement)
6. Process approval (future: resume task)

Currently: Handled as regular message, but detected as thread
```

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SLACK_BOT_TOKEN` | - | Bot user OAuth token (xoxb-...) |
| `SLACK_APP_TOKEN` | - | App-level token for Socket Mode (xapp-...) |
| `GOOGLE_AI_API_KEY` | - | Gemini API key for AI Q&A |
| `SLACK_AI_ENABLED` | `false` | Enable AI Q&A features |
| `SLACK_AI_CONFIDENCE_THRESHOLD` | `0.6` | Min confidence for direct answer |
| `SLACK_MESSAGE_HISTORY_LIMIT` | `20` | Max messages in context |
| `SLACK_CHANNEL_MAPPINGS_FILE` | `config/channel_mappings.json` | Channel config path |

### Slack App Permissions

**Bot Token Scopes:**
- `channels:manage` - Create project channels
- `channels:read` - List and access public channels
- `channels:history` - Read message history for context
- `chat:write` - Send messages and replies
- `im:history` - Read DM history
- `im:write` - Send DMs
- `users:read` - Look up user information
- `app_mentions:read` - Respond to @mentions

**Event Subscriptions:**
- `message.channels` - Messages in channels
- `message.im` - Direct messages
- `app_mention` - When bot is @mentioned

---

## Testing

### Unit Tests

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_message_router.py` | 17 | MessageRouter routing logic |
| `tests/test_intent_classifier.py` | 10 | Intent classification |
| `tests/test_command_parser.py` | 8 | Command parsing |
| `tests/test_channel_context.py` | 11 | Channel management |
| `tests/test_ai_qa_handler.py` | 15 | AI Q&A logic |
| `tests/test_human_router.py` | 14 | Human escalation |

**Total:** 75+ unit tests

### Integration Tests

**File:** `tests/integration/test_slack_flow.py`

**Scenarios:**
- DM help flow
- DM status query flow
- DM question with AI answer
- @mention in channel
- Billing question escalation
- Channel message (no mention) ignored
- Thread reply handling
- Low confidence escalation
- Project channel context flow

**Total:** 10 integration tests

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_message_router.py -v

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=hitl --cov-report=html
```

### Manual Testing

See `tests/manual/CHANNEL_CREATION_TEST.md` for channel creation test checklist.

---

## Performance Considerations

### Response Times

| Component | Target | Actual |
|-----------|--------|--------|
| Pattern matching (IntentClassifier) | <10ms | ~5ms |
| Command execution (CommandParser) | <100ms | ~50ms |
| AI response (AIQAHandler) | <2s | ~1-2s |
| Human escalation (HumanRouter) | <500ms | ~200ms |

### Caching

- **Intent patterns:** Compiled regex cached at initialization
- **Channel mappings:** Loaded once, updated on changes
- **Task store:** Direct DB queries (consider caching for scale)

### Rate Limiting

- **Gemini API:** ~60 requests/minute (free tier)
- **Slack API:** ~1 request/second per method

---

## Security

### PII Protection

**Filtered Patterns:**
- Email addresses: `[EMAIL_REDACTED]`
- Phone numbers: `[PHONE_REDACTED]`
- SSNs: `[SSN_REDACTED]`
- Credit cards: `[CREDIT_CARD_REDACTED]`

**Filter Applied:**
- Before logging prompts
- Before storing messages
- Not applied to Gemini requests (needed for context)

### Authorization

**Admin Actions (require `admin_users` membership):**
- Create project channels
- Modify channel mappings

**User Actions (all authenticated users):**
- Query task status
- Control own tasks
- Ask questions in project channels

### Secrets Management

**DO NOT commit:**
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `GOOGLE_AI_API_KEY`

**Store in:**
- `.env` file (local, gitignored)
- GCP Secret Manager (production)
- Environment variables (Cloud Run)

---

## Troubleshooting

### Bot Doesn't Respond

**Check:**
1. Socket Mode enabled in Slack app settings
2. Event subscriptions configured (`message.im`, `message.channels`, `app_mention`)
3. Bot token and app token valid
4. Spectacles service running
5. Logs for errors: `docker logs spectacles-container`

### AI Answers Are Wrong

**Check:**
1. `GOOGLE_AI_API_KEY` set correctly
2. Channel has project mapping in `config/channel_mappings.json`
3. Sufficient context in recent messages
4. Gemini API quota not exceeded

### Escalations Not Delivered

**Check:**
1. Recipient Slack user IDs correct in HumanRouter
2. Bot has permission to DM users
3. Slack client initialized correctly
4. Logs for DM send failures

### Channel Creation Fails

**Check:**
1. User is in `admin_users` list
2. Slack app has `channels:manage` scope
3. Project name valid (lowercase, hyphens, 3-80 chars)
4. Channel name not already taken

---

## Future Enhancements

### Phase 5: Advanced Thread Support

- Extract task_id from thread parent message
- Auto-resume tasks on "approved" replies
- Thread-based approval workflow

### Phase 6: Multi-Language Support

- Detect message language
- Respond in user's language
- Translate escalation messages

### Phase 7: Rich Interactive Messages

- Slack Block Kit buttons for approvals
- Dropdown menus for task selection
- Interactive forms for channel creation

### Phase 8: Analytics & Insights

- Track question types and response times
- Measure AI accuracy and escalation rates
- User engagement metrics

---

## Related Documentation

- [SLACK_SETUP.md](SLACK_SETUP.md) - Setup guide for Slack integration
- [README.md](README.md) - Full Spectacles documentation
- [CLAUDE.md](CLAUDE.md) - Project technical reference
- [Slack API Docs](https://api.slack.com/docs) - Official Slack documentation
- [Gemini API Docs](https://ai.google.dev/docs) - Google AI documentation

---

**Last Updated:** 2026-01-18
**Version:** 1.0.0
**Maintainer:** Spectacles Team
