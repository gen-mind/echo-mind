---
name: trello
description: "Manage Trello boards, lists, and cards via the Trello REST API"
command: "${command}"
args:
  - name: command
    description: "curl command for Trello API"
    required: true
tags: [trello, project-management, api]
timeout: 30
---

# Trello Skill

Manage Trello boards, lists, and cards using the [Trello REST API](https://developer.atlassian.com/cloud/trello/rest/). Requires `$TRELLO_API_KEY` and `$TRELLO_TOKEN` environment variables.

## Authentication

All requests require `key` and `token` query parameters:

```
?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN
```

Base URL: `https://api.trello.com/1/`

## Board Operations

```bash
# List all boards for the authenticated user
curl -s "https://api.trello.com/1/members/me/boards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Get a specific board
curl -s "https://api.trello.com/1/boards/{boardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Get all lists on a board
curl -s "https://api.trello.com/1/boards/{boardId}/lists?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Get all cards on a board
curl -s "https://api.trello.com/1/boards/{boardId}/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"
```

## List Operations

```bash
# Get cards in a list
curl -s "https://api.trello.com/1/lists/{listId}/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Create a new list on a board
curl -s -X POST "https://api.trello.com/1/lists?name=New+List&idBoard={boardId}&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Archive a list
curl -s -X PUT "https://api.trello.com/1/lists/{listId}/closed?value=true&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"
```

## Card Operations

```bash
# Get a specific card
curl -s "https://api.trello.com/1/cards/{cardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Create a card
curl -s -X POST "https://api.trello.com/1/cards?idList={listId}&name=Card+Title&desc=Description&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Move a card to a different list
curl -s -X PUT "https://api.trello.com/1/cards/{cardId}?idList={newListId}&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Add a comment to a card
curl -s -X POST "https://api.trello.com/1/cards/{cardId}/actions/comments?text=Comment+text&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Add a label to a card
curl -s -X POST "https://api.trello.com/1/cards/{cardId}/idLabels?value={labelId}&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Update a card (name, description, due date, etc.)
curl -s -X PUT "https://api.trello.com/1/cards/{cardId}?name=Updated+Title&due=2026-03-01T12:00:00.000Z&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"

# Delete a card
curl -s -X DELETE "https://api.trello.com/1/cards/{cardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"
```

## Common Query Parameters

| Parameter | Description |
|-----------|-------------|
| `fields` | Comma-separated list of fields to return |
| `filter` | Filter results (e.g., `open`, `closed`, `all`) |
| `limit` | Max number of results |
| `members` | Include member data (`true`/`false`) |
| `labels` | Include label data (`true`/`false`) |

## Examples

**List all boards:**
```
command: "curl -s \"https://api.trello.com/1/members/me/boards?fields=name,url&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\""
```

**Create a card in a list:**
```
command: "curl -s -X POST \"https://api.trello.com/1/cards?idList=abc123&name=Fix+login+bug&desc=Users+cannot+log+in&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\""
```

**Move a card to Done:**
```
command: "curl -s -X PUT \"https://api.trello.com/1/cards/card123?idList=doneListId&key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\""
```
