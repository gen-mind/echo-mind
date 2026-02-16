---
name: discord
description: "Send messages and manage Discord channels via the Discord API"
command: "${command}"
args:
  - name: command
    description: "curl command for Discord API"
    required: true
tags: [discord, messaging, communication, api]
timeout: 15
---

# Discord Skill

Send messages and manage Discord channels using the [Discord API](https://discord.com/developers/docs/intro). Requires `$DISCORD_BOT_TOKEN` environment variable.

## Authentication

All requests require:
- `Authorization: Bot $DISCORD_BOT_TOKEN`
- `Content-Type: application/json` (for POST/PATCH)

Base URL: `https://discord.com/api/v10/`

## Send Messages

```bash
# Send a message to a channel
curl -s -X POST "https://discord.com/api/v10/channels/{channelId}/messages" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello from EchoMind!"}'

# Send a message with an embed
curl -s -X POST "https://discord.com/api/v10/channels/{channelId}/messages" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "embeds": [{
      "title": "Status Update",
      "description": "Build passed successfully.",
      "color": 3066993,
      "fields": [
        {"name": "Tests", "value": "42 passed", "inline": true},
        {"name": "Coverage", "value": "98%", "inline": true}
      ]
    }]
  }'

# Reply to a message
curl -s -X POST "https://discord.com/api/v10/channels/{channelId}/messages" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Reply text", "message_reference": {"message_id": "messageId"}}'

# Edit a message
curl -s -X PATCH "https://discord.com/api/v10/channels/{channelId}/messages/{messageId}" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Updated message"}'

# Delete a message
curl -s -X DELETE "https://discord.com/api/v10/channels/{channelId}/messages/{messageId}" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"
```

## Channel Operations

```bash
# Get channel info
curl -s "https://discord.com/api/v10/channels/{channelId}" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"

# List guild (server) channels
curl -s "https://discord.com/api/v10/guilds/{guildId}/channels" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"

# Get messages from a channel (most recent)
curl -s "https://discord.com/api/v10/channels/{channelId}/messages?limit=20" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"

# Get messages before a specific message
curl -s "https://discord.com/api/v10/channels/{channelId}/messages?before={messageId}&limit=20" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"
```

## Guild (Server) Operations

```bash
# Get guild info
curl -s "https://discord.com/api/v10/guilds/{guildId}" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"

# List guild members
curl -s "https://discord.com/api/v10/guilds/{guildId}/members?limit=100" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"

# Get a specific member
curl -s "https://discord.com/api/v10/guilds/{guildId}/members/{userId}" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"
```

## Reactions

```bash
# Add a reaction (URL-encode the emoji)
curl -s -X PUT "https://discord.com/api/v10/channels/{channelId}/messages/{messageId}/reactions/%F0%9F%91%8D/@me" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"

# Add a custom emoji reaction
curl -s -X PUT "https://discord.com/api/v10/channels/{channelId}/messages/{messageId}/reactions/emojiName:emojiId/@me" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN"
```

## Required Bot Permissions

| Permission | Required For |
|------------|-------------|
| `Send Messages` | Sending messages in channels |
| `Read Message History` | Reading channel messages |
| `Embed Links` | Sending rich embeds |
| `Add Reactions` | Adding emoji reactions |
| `View Channels` | Listing and accessing channels |

## Embed Color Values

| Color | Value |
|-------|-------|
| Green (success) | `3066993` |
| Red (error) | `15158332` |
| Blue (info) | `3447003` |
| Yellow (warning) | `16776960` |
| Purple | `10181046` |

## Examples

**Send a message:**
```
command: "curl -s -X POST \"https://discord.com/api/v10/channels/123456789/messages\" -H \"Authorization: Bot $DISCORD_BOT_TOKEN\" -H \"Content-Type: application/json\" -d '{\"content\": \"Deployment complete!\"}'"
```

**List server channels:**
```
command: "curl -s \"https://discord.com/api/v10/guilds/987654321/channels\" -H \"Authorization: Bot $DISCORD_BOT_TOKEN\""
```

**Get recent messages:**
```
command: "curl -s \"https://discord.com/api/v10/channels/123456789/messages?limit=10\" -H \"Authorization: Bot $DISCORD_BOT_TOKEN\""
```
