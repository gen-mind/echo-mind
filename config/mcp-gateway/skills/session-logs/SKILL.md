---
name: session-logs
description: "Search and browse conversation history via EchoMind's session API"
command: "${command}"
args:
  - name: command
    description: "curl command for EchoMind Session API"
    required: true
tags: [sessions, history, search, api]
timeout: 15
---

# Session Logs

Search and browse conversation history using EchoMind's Session API. View past sessions, retrieve messages, and search across conversation history.

> **Note:** When running inside Docker, internal API calls use the Docker network hostname.
> Authentication is handled by the MCP Gateway's service identity — no user-level auth headers
> are needed for internal service-to-service calls. For external access, use Bearer token auth.

## API Base URL

```
$ECHOMIND_API_URL/api/v1/sessions/
```

> `ECHOMIND_API_URL` defaults to `http://api:8000` when not set.

## List Sessions

Retrieve a paginated list of chat sessions for a user.

```bash
# List recent sessions
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/?user_id={user_id}&limit=10"

# List sessions with offset for pagination
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/?user_id={user_id}&limit=10&offset=20"

# List sessions for a specific assistant
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/?user_id={user_id}&assistant_id={assistant_id}&limit=10"
```

## Get Session Messages

Retrieve all messages from a specific session.

```bash
# Get messages for a session
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/{session_id}/messages"

# Get messages with limit
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/{session_id}/messages?limit=50"
```

## Search Sessions

Search across session content.

```bash
# Search across all sessions for a user
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/search?user_id={user_id}&query=deployment+issue"

# Search with date range
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/search?user_id={user_id}&query=bug&from=2026-01-01&to=2026-02-01'"
```

## Get Session Details

```bash
# Get session metadata (title, created_at, message count)
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/{session_id}"
```

## Response Format

Sessions include:
- **id** — unique session identifier
- **title** — auto-generated or user-set session title
- **assistant_id** — the assistant used in this session
- **created_at** — session creation timestamp
- **updated_at** — last activity timestamp
- **message_count** — number of messages in the session

Messages include:
- **role** — "user" or "assistant"
- **content** — message text
- **created_at** — message timestamp
- **metadata** — additional context (sources, tool calls)

## Examples

**View last 5 sessions:**
```
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/?user_id=me&limit=5 | python3 -m json.tool"
```

**Get full conversation from a session:**
```
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/abc123/messages | python3 -m json.tool"
```

**Search for a topic:**
```
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/sessions/search?user_id=me&query=kubernetes' | python3 -m json.tool"
```
