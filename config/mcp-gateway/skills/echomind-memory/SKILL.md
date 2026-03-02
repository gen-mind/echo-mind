---
name: echomind-memory
description: "Read and write agent long-term memory for persistent context across sessions"
command: "${command}"
args:
  - name: command
    description: "curl command for EchoMind Memory API"
    required: true
tags: [memory, persistence, context, agent, echomind]
timeout: 15
---

# EchoMind Agent Memory

Store and retrieve long-term memories that persist across chat sessions. Agent memory helps build understanding of user context, preferences, and key information over time.

> **Note:** When running inside Docker, internal API calls use the Docker network hostname.
> Authentication is handled by the MCP Gateway's service identity — no user-level auth headers
> are needed for internal service-to-service calls. For external access, use Bearer token auth.

## API Base URL

```
$ECHOMIND_API_URL/api/v1/memory/
```

> `ECHOMIND_API_URL` defaults to `http://api:8000` when not set.

## Memory Types

| Type | Description | Example |
|------|-------------|---------|
| **episodic** | Specific events or interactions | "User deployed v2.3 on 2026-02-10" |
| **semantic** | General knowledge and preferences | "User prefers Python over JavaScript" |

## Store a Memory

```bash
# Store an episodic memory
command: "curl -s -X POST ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/ -H 'Content-Type: application/json' -d '{\"user_id\": \"{user_id}\", \"type\": \"episodic\", \"content\": \"User completed the EchoMind setup wizard and connected Google Drive\", \"metadata\": {\"source\": \"onboarding\"}}'"

# Store a semantic memory
command: "curl -s -X POST ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/ -H 'Content-Type: application/json' -d '{\"user_id\": \"{user_id}\", \"type\": \"semantic\", \"content\": \"User is a backend developer who works primarily with Python and PostgreSQL\"}'"
```

## Retrieve Memories by Query

Search for relevant memories using natural language.

```bash
# Search memories by relevance
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/search?user_id={user_id}&query=deployment+preferences&limit=5'"

# Search only episodic memories
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/search?user_id={user_id}&query=recent+projects&type=episodic&limit=10'"

# Search only semantic memories
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/search?user_id={user_id}&query=programming+languages&type=semantic&limit=5'"
```

## List Memories

```bash
# List all memories for a user
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/?user_id={user_id}&limit=20"

# List with pagination
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/?user_id={user_id}&limit=20&offset=20"

# Filter by type
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/?user_id={user_id}&type=semantic"
```

## Get a Specific Memory

```bash
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/{memory_id}"
```

## Update a Memory

```bash
command: "curl -s -X PUT ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/{memory_id} -H 'Content-Type: application/json' -d '{\"content\": \"Updated memory content\"}'"
```

## Delete a Memory

```bash
command: "curl -s -X DELETE ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/{memory_id}"
```

## Response Format

Memories include:
- **id** — unique memory identifier
- **user_id** — owning user
- **type** — episodic or semantic
- **content** — memory text
- **metadata** — additional context (source, tags)
- **created_at** — when the memory was stored
- **relevance_score** — similarity score (in search results)

## Workflow Examples

### Build User Context at Session Start

```bash
# Retrieve relevant memories for the current topic
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/search?user_id=me&query=current+project+and+preferences&limit=10' | python3 -m json.tool"
```

### Save Important Context After a Session

```bash
# Store key takeaways
command: "curl -s -X POST ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/ -H 'Content-Type: application/json' -d '{\"user_id\": \"me\", \"type\": \"episodic\", \"content\": \"User resolved the authentication bug by switching from JWT to session cookies\", \"metadata\": {\"session_id\": \"sess_abc123\"}}'"
```

### Update User Preferences

```bash
# Update a known preference
command: "curl -s -X PUT ${ECHOMIND_API_URL:-http://api:8000}/api/v1/memory/mem_xyz789 -H 'Content-Type: application/json' -d '{\"content\": \"User now prefers dark mode and compact UI layout\"}'"
```

## Tips

- Store memories after significant interactions or decisions
- Use semantic memories for stable preferences, episodic for specific events
- Search memories at the start of a session to recall relevant context
- Include metadata to make memories easier to filter and organize
- Keep memory content concise and factual
