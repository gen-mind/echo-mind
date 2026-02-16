---
name: echomind-documents
description: "Manage documents in EchoMind — list, view status, and track processing"
command: "${command}"
args:
  - name: command
    description: "curl command for EchoMind Document API"
    required: true
tags: [documents, management, api, echomind]
timeout: 15
---

# EchoMind Document Management

Manage documents in EchoMind — list uploaded and synced documents, check processing status, and view document metadata.

> **Note:** When running inside Docker, internal API calls use the Docker network hostname.
> Authentication is handled by the MCP Gateway's service identity — no user-level auth headers
> are needed for internal service-to-service calls. For external access, use Bearer token auth.

## API Base URL

```
$ECHOMIND_API_URL/api/v1/documents/
```

> `ECHOMIND_API_URL` defaults to `http://api:8000` when not set.

## List Documents

Retrieve documents for a user with optional filtering.

```bash
# List all documents
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/?user_id={user_id}&limit=20"

# Filter by status
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/?user_id={user_id}&status=completed"

# Filter by connector
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/?user_id={user_id}&connector_id={connector_id}"

# Paginate results
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/?user_id={user_id}&limit=20&offset=40"
```

## Get Document Details

```bash
# Get document metadata and processing status
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/{document_id}"
```

Returns:
- **id** — unique document identifier
- **title** — document title or filename
- **source** — origin (upload, Google Drive, OneDrive, etc.)
- **connector_id** — associated connector (if synced)
- **status** — processing state (see below)
- **mime_type** — file type (application/pdf, text/plain, etc.)
- **chunk_count** — number of indexed chunks
- **created_at** — ingestion timestamp
- **updated_at** — last processing timestamp
- **metadata** — additional source-specific metadata

## Document Status Values

| Status | Description |
|--------|-------------|
| `pending` | Queued for processing |
| `extracting` | Content extraction in progress |
| `chunking` | Text chunking in progress |
| `embedding` | Vector embedding in progress |
| `completed` | Fully processed and searchable |
| `failed` | Processing failed (check error details) |
| `deleted` | Marked for deletion |

## Get Document Chunks

```bash
# List chunks for a document
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/{document_id}/chunks?limit=50"
```

## Check Processing Errors

```bash
# Get document with error details
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/{document_id} | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('error', 'No errors'))\""
```

## Examples

**List recently added documents:**
```
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/?user_id=me&limit=5&sort=-created_at' | python3 -m json.tool"
```

**Check if a document finished processing:**
```
command: "curl -s ${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/doc_abc123 | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'{d[\"title\"]}: {d[\"status\"]}')\""
```

**Count documents by status:**
```
command: "curl -s '${ECHOMIND_API_URL:-http://api:8000}/api/v1/documents/?user_id=me&status=failed' | python3 -c \"import sys,json; r=json.load(sys.stdin); print(f'Failed documents: {len(r.get(\"items\", r)) if isinstance(r, dict) else len(r)}')\""
```
