---
name: echomind-search
description: "Search your documents and knowledge base using EchoMind's RAG pipeline"
command: 'echo "Use the MCP search_documents() and search_collections() tools for RAG search. This skill provides documentation only."'
tags: [search, rag, qdrant, documents, echomind]
timeout: 5
---

# EchoMind RAG Search

Search your documents and knowledge base using EchoMind's vector similarity search powered by Qdrant. This is a documentation-only skill — use the MCP tools listed below.

## Available MCP Tools

### search_collections()

List available vector collections scoped to the current user, group, or organization.

```
search_collections()
```

Returns collections with:
- **name** — collection identifier
- **scope** — user, group, or org
- **document_count** — number of documents indexed
- **vector_count** — number of chunks stored

### search_documents(query, collection, limit, score_threshold)

Perform vector similarity search against a collection.

```
search_documents(
    query="How do I configure OAuth?",
    collection="user_12345",
    limit=5,
    score_threshold=0.7
)
```

Parameters:
- **query** (required) — natural language search query
- **collection** (required) — target collection name
- **limit** (optional, default: 5) — maximum results to return
- **score_threshold** (optional, default: 0.7) — minimum similarity score (0.0–1.0)

Returns ranked results with:
- **document_id** — source document identifier
- **chunk_text** — matched text content
- **score** — similarity score
- **metadata** — source file name, page number, section

### get_document(document_id)

Get metadata for a specific document.

```
get_document(document_id="doc_abc123")
```

Returns:
- **title** — document title
- **source** — origin (connector, upload)
- **status** — processing state
- **created_at** — ingestion timestamp
- **chunk_count** — number of indexed chunks

### get_document_chunks(document_id, limit)

Retrieve the full content of a document as ordered chunks.

```
get_document_chunks(document_id="doc_abc123", limit=50)
```

Returns ordered chunks with text content and metadata.

## Search Workflow

### Step 1: Discover Collections

```
search_collections()
```

Identify the right collection to search (user-scoped, group-scoped, or org-scoped).

### Step 2: Search for Relevant Content

```
search_documents(
    query="deployment configuration",
    collection="user_12345",
    limit=10,
    score_threshold=0.65
)
```

### Step 3: Get Full Document (if needed)

```
get_document_chunks(document_id="doc_abc123")
```

## Tips

- **Lower score_threshold** (e.g., 0.5) for broader results, **higher** (e.g., 0.8) for precise matches
- **Search multiple collections** if the user has access to group or org collections
- **Combine results** from different collections for comprehensive answers
- **Use get_document_chunks** to read the full source when a search result needs more context
- Queries work best as natural language questions or topic descriptions
