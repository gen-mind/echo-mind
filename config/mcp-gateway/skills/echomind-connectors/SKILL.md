---
name: echomind-connectors
description: "Manage data connectors in EchoMind — list, sync, and check status"
command: 'echo "Use the MCP connectors_list(), connector_status(), connector_search(), and connector_sync() tools. This skill provides documentation only."'
tags: [connectors, sync, data-sources, echomind]
timeout: 5
---

# EchoMind Connector Management

Manage data connectors that sync external sources into EchoMind's knowledge base. This is a documentation-only skill — use the MCP tools listed below.

> **Note:** When running inside Docker, internal API calls use the Docker network hostname.
> Authentication is handled by the MCP Gateway's service identity — no user-level auth headers
> are needed for internal service-to-service calls. For external access, use Bearer token auth.

## Available MCP Tools

### connectors_list(user_id)

List all active data connectors for a user.

```
connectors_list(user_id="user_12345")
```

Returns connectors with:
- **id** — connector identifier
- **type** — connector type (google_drive, onedrive, gmail, etc.)
- **name** — user-given connector name
- **status** — connection state (active, syncing, error)
- **last_sync** — timestamp of last successful sync
- **document_count** — number of documents synced

### connector_status(connector_id)

Get detailed sync status for a specific connector.

```
connector_status(connector_id="conn_abc123")
```

Returns:
- **sync_state** — idle, syncing, error
- **last_sync** — last successful sync timestamp
- **next_sync** — scheduled next sync
- **documents_synced** — total documents
- **documents_pending** — documents awaiting processing
- **error** — error message (if any)

### connector_search(connector_id, query, collection, limit)

Search within a specific connector's documents.

```
connector_search(
    connector_id="conn_abc123",
    query="quarterly report",
    collection="user_12345",
    limit=10
)
```

Parameters:
- **connector_id** (required) — target connector
- **query** (required) — search query
- **collection** (required) — vector collection to search
- **limit** (optional, default: 5) — maximum results

### connector_sync(connector_id, user_id)

Trigger a manual sync for a connector.

```
connector_sync(
    connector_id="conn_abc123",
    user_id="user_12345"
)
```

Initiates an immediate sync. The sync runs asynchronously — use `connector_status()` to track progress.

## Available Connector Types

| Type | Description | Synced Content |
|------|-------------|----------------|
| **Google Drive** | Google Workspace files | Docs, Sheets, Slides, PDFs |
| **OneDrive** | Microsoft 365 files | Word, Excel, PowerPoint, PDFs |
| **Gmail** | Email messages | Emails and attachments |
| **Calendar** | Calendar events | Event details and descriptions |
| **Contacts** | Contact directory | Contact information |

## Workflow Examples

### Check All Connectors

```
connectors_list(user_id="user_12345")
```

Review each connector's status and last sync time.

### Troubleshoot a Failing Connector

```
# 1. Get detailed status
connector_status(connector_id="conn_abc123")

# 2. Check the error message
# 3. Trigger a manual re-sync
connector_sync(connector_id="conn_abc123", user_id="user_12345")

# 4. Monitor sync progress
connector_status(connector_id="conn_abc123")
```

### Search a Specific Data Source

```
# 1. List connectors to find the right one
connectors_list(user_id="user_12345")

# 2. Search within that connector's documents
connector_search(
    connector_id="conn_abc123",
    query="budget proposal",
    collection="user_12345",
    limit=5
)
```

## Tips

- Connectors sync on a schedule (configurable per connector)
- Use `connector_sync()` for immediate updates when you know new content exists
- Check `connector_status()` after a sync to verify completion
- If a connector shows "error" status, check the error details before retrying
