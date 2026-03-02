---
name: slack
description: "Send messages and interact with Slack channels via the Slack Web API"
command: "${command}"
args:
  - name: command
    description: "curl command for Slack API"
    required: true
tags: [slack, messaging, communication, api]
timeout: 15
---

# Slack Skill

Send messages and interact with Slack channels using the [Slack Web API](https://api.slack.com/web). Requires `$SLACK_BOT_TOKEN` environment variable (a Bot User OAuth Token starting with `xoxb-`).

## Authentication

All requests require:
- `Authorization: Bearer $SLACK_BOT_TOKEN`
- `Content-Type: application/json` (for POST requests)

Base URL: `https://slack.com/api/`

## Send Messages

```bash
# Send a message to a channel
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "C01ABCDEF", "text": "Hello from EchoMind!"}'

# Send a message with blocks (rich formatting)
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "C01ABCDEF",
    "blocks": [
      {"type": "header", "text": {"type": "plain_text", "text": "Status Update"}},
      {"type": "section", "text": {"type": "mrkdwn", "text": "*Build passed* :white_check_mark:\nAll 42 tests passing."}}
    ]
  }'

# Send a threaded reply
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "C01ABCDEF", "thread_ts": "1234567890.123456", "text": "Reply in thread"}'

# Update a message
curl -s -X POST "https://slack.com/api/chat.update" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "C01ABCDEF", "ts": "1234567890.123456", "text": "Updated message"}'
```

## Channel Operations

```bash
# List public channels
curl -s "https://slack.com/api/conversations.list?types=public_channel&limit=100" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# List channels the bot is a member of
curl -s "https://slack.com/api/conversations.list?types=public_channel,private_channel&limit=100" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Get channel history (recent messages)
curl -s "https://slack.com/api/conversations.history?channel=C01ABCDEF&limit=20" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Get channel info
curl -s "https://slack.com/api/conversations.info?channel=C01ABCDEF" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Get thread replies
curl -s "https://slack.com/api/conversations.replies?channel=C01ABCDEF&ts=1234567890.123456" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
```

## User Operations

```bash
# List workspace users
curl -s "https://slack.com/api/users.list?limit=100" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Get user info
curl -s "https://slack.com/api/users.info?user=U01ABCDEF" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Look up user by email
curl -s "https://slack.com/api/users.lookupByEmail?email=user@example.com" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
```

## Reactions

```bash
# Add a reaction
curl -s -X POST "https://slack.com/api/reactions.add" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "C01ABCDEF", "timestamp": "1234567890.123456", "name": "thumbsup"}'
```

## Required Bot Scopes

| Scope | Required For |
|-------|-------------|
| `chat:write` | Sending messages |
| `channels:read` | Listing public channels |
| `channels:history` | Reading channel messages |
| `groups:read` | Listing private channels |
| `users:read` | Listing users |
| `users:read.email` | Looking up users by email |
| `reactions:write` | Adding reactions |

## Examples

**Send a message to #general:**
```
command: "curl -s -X POST \"https://slack.com/api/chat.postMessage\" -H \"Authorization: Bearer $SLACK_BOT_TOKEN\" -H \"Content-Type: application/json\" -d '{\"channel\": \"general\", \"text\": \"Deployment complete!\"}'"
```

**List channels:**
```
command: "curl -s \"https://slack.com/api/conversations.list?types=public_channel&limit=20\" -H \"Authorization: Bearer $SLACK_BOT_TOKEN\""
```

**Get recent messages from a channel:**
```
command: "curl -s \"https://slack.com/api/conversations.history?channel=C01ABCDEF&limit=10\" -H \"Authorization: Bearer $SLACK_BOT_TOKEN\""
```
