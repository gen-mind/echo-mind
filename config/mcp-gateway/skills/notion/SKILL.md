---
name: notion
description: "Search, read, and create Notion pages and databases via the Notion API"
command: "${command}"
args:
  - name: command
    description: "curl command for Notion API"
    required: true
tags: [notion, wiki, knowledge-base, api]
timeout: 30
---

# Notion Skill

Search, read, and create Notion pages and databases using the [Notion API](https://developers.notion.com/). Requires `$NOTION_API_KEY` environment variable (an internal integration token).

## Authentication

All requests require:
- `Authorization: Bearer $NOTION_API_KEY`
- `Notion-Version: 2022-06-28`
- `Content-Type: application/json` (for POST/PATCH)

Base URL: `https://api.notion.com/v1/`

## Search

```bash
# Search across all pages and databases
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"query": "search term"}'

# Search with filters (pages only)
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes", "filter": {"value": "page", "property": "object"}}'

# Search databases only
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"filter": {"value": "database", "property": "object"}}'
```

## Page Operations

```bash
# Get a page
curl -s "https://api.notion.com/v1/pages/{pageId}" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28"

# Get page content (blocks)
curl -s "https://api.notion.com/v1/blocks/{pageId}/children" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28"

# Create a page in a parent page
curl -s -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"page_id": "parentPageId"},
    "properties": {
      "title": [{"text": {"content": "New Page Title"}}]
    },
    "children": [
      {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
          "rich_text": [{"text": {"content": "Page content here."}}]
        }
      }
    ]
  }'

# Create a page in a database
curl -s -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"database_id": "databaseId"},
    "properties": {
      "Name": {"title": [{"text": {"content": "New Entry"}}]},
      "Status": {"select": {"name": "In Progress"}}
    }
  }'
```

## Database Operations

```bash
# Get a database
curl -s "https://api.notion.com/v1/databases/{databaseId}" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28"

# Query a database (all entries)
curl -s -X POST "https://api.notion.com/v1/databases/{databaseId}/query" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{}'

# Query with filter
curl -s -X POST "https://api.notion.com/v1/databases/{databaseId}/query" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "property": "Status",
      "select": {"equals": "Done"}
    },
    "sorts": [{"property": "Created", "direction": "descending"}]
  }'
```

## Common Property Types

| Type | JSON Format |
|------|-------------|
| Title | `{"title": [{"text": {"content": "text"}}]}` |
| Rich Text | `{"rich_text": [{"text": {"content": "text"}}]}` |
| Select | `{"select": {"name": "Option"}}` |
| Multi-Select | `{"multi_select": [{"name": "Tag1"}, {"name": "Tag2"}]}` |
| Checkbox | `{"checkbox": true}` |
| Date | `{"date": {"start": "2026-03-01"}}` |
| Number | `{"number": 42}` |

## Examples

**Search for pages containing "roadmap":**
```
command: "curl -s -X POST \"https://api.notion.com/v1/search\" -H \"Authorization: Bearer $NOTION_API_KEY\" -H \"Notion-Version: 2022-06-28\" -H \"Content-Type: application/json\" -d '{\"query\": \"roadmap\"}'"
```

**Get all entries from a task database:**
```
command: "curl -s -X POST \"https://api.notion.com/v1/databases/abc123/query\" -H \"Authorization: Bearer $NOTION_API_KEY\" -H \"Notion-Version: 2022-06-28\" -H \"Content-Type: application/json\" -d '{}'"
```
