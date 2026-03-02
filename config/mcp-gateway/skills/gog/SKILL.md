---
name: gog
description: "Interact with Google Workspace APIs — Drive, Docs, Sheets, Calendar"
command: "${command}"
args:
  - name: command
    description: "curl command for Google Workspace API"
    required: true
tags: [google, workspace, drive, docs, sheets, api]
timeout: 30
---

# GoG (Google on the Go) Skill

Interact with Google Workspace APIs via curl — Drive, Docs, Sheets, and Calendar.

## Overview

Access Google Workspace services using OAuth Bearer tokens. This skill uses EchoMind's connector OAuth tokens to authenticate API requests. All commands use curl with the Google APIs REST endpoints.

## Google Drive

```bash
# List files in Drive (first 10)
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/drive/v3/files?pageSize=10&fields=files(id,name,mimeType,modifiedTime)" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for f in data.get('files', []):
    print(f'{f[\"name\"]} ({f[\"mimeType\"]}) - {f[\"id\"]}')
"

# Search for files by name
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/drive/v3/files?q=name+contains+'report'&fields=files(id,name,mimeType)"

# Download a file by ID
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/drive/v3/files/FILE_ID?alt=media" -o downloaded_file

# Export Google Doc as PDF
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/drive/v3/files/FILE_ID/export?mimeType=application/pdf" -o document.pdf

# List files in a specific folder
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/drive/v3/files?q='FOLDER_ID'+in+parents&fields=files(id,name,mimeType)"
```

## Google Docs

```bash
# Get document content
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://docs.googleapis.com/v1/documents/DOCUMENT_ID" | python3 -c "
import sys, json
doc = json.load(sys.stdin)
print(f'Title: {doc[\"title\"]}')
for elem in doc.get('body', {}).get('content', []):
    para = elem.get('paragraph', {})
    for e in para.get('elements', []):
        text = e.get('textRun', {}).get('content', '')
        if text.strip():
            print(text, end='')
"

# Get document metadata only
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://docs.googleapis.com/v1/documents/DOCUMENT_ID?fields=title,revisionId"
```

## Google Sheets

```bash
# Read a range from a spreadsheet
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://sheets.googleapis.com/v4/spreadsheets/SPREADSHEET_ID/values/Sheet1!A1:D10" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for row in data.get('values', []):
    print('\t'.join(row))
"

# Read entire first sheet
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://sheets.googleapis.com/v4/spreadsheets/SPREADSHEET_ID/values/Sheet1"

# Write values to a range
curl -s -X PUT -H "Authorization: Bearer $GOOGLE_TOKEN" \
  -H "Content-Type: application/json" \
  "https://sheets.googleapis.com/v4/spreadsheets/SPREADSHEET_ID/values/Sheet1!A1:B2?valueInputOption=RAW" \
  -d '{"values": [["Name", "Score"], ["Alice", "95"]]}'

# Append a row
curl -s -X POST -H "Authorization: Bearer $GOOGLE_TOKEN" \
  -H "Content-Type: application/json" \
  "https://sheets.googleapis.com/v4/spreadsheets/SPREADSHEET_ID/values/Sheet1!A:B:append?valueInputOption=RAW" \
  -d '{"values": [["Bob", "88"]]}'
```

## Google Calendar

```bash
# List upcoming events (next 10)
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=10&timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)&orderBy=startTime&singleEvents=true" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for event in data.get('items', []):
    start = event['start'].get('dateTime', event['start'].get('date'))
    print(f'{start} - {event[\"summary\"]}')
"

# List events for a specific date range
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=2026-02-01T00:00:00Z&timeMax=2026-02-28T23:59:59Z&singleEvents=true&orderBy=startTime"

# Create a calendar event
curl -s -X POST -H "Authorization: Bearer $GOOGLE_TOKEN" \
  -H "Content-Type: application/json" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events" \
  -d '{
    "summary": "Team Meeting",
    "start": {"dateTime": "2026-02-20T10:00:00+01:00"},
    "end": {"dateTime": "2026-02-20T11:00:00+01:00"},
    "description": "Weekly sync"
  }'
```

## Examples

**List recent Drive files:**
```
command: "curl -s -H 'Authorization: Bearer $GOOGLE_TOKEN' 'https://www.googleapis.com/drive/v3/files?pageSize=5&orderBy=modifiedTime+desc&fields=files(id,name,modifiedTime)' | python3 -c \"import sys, json; [print(f'{f[\\\"name\\\"]} - {f[\\\"modifiedTime\\\"]}') for f in json.load(sys.stdin).get('files', [])]\""
```

**Read a spreadsheet range:**
```
command: "curl -s -H 'Authorization: Bearer $GOOGLE_TOKEN' 'https://sheets.googleapis.com/v4/spreadsheets/SPREADSHEET_ID/values/Sheet1!A1:E10' | python3 -c \"import sys, json; [print('\\t'.join(r)) for r in json.load(sys.stdin).get('values', [])]\""
```

**List today's calendar events:**
```
command: "curl -s -H 'Authorization: Bearer $GOOGLE_TOKEN' 'https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=2026-02-16T00:00:00Z&timeMax=2026-02-16T23:59:59Z&singleEvents=true&orderBy=startTime' | python3 -c \"import sys, json; [print(f'{e[\\\"start\\\"].get(\\\"dateTime\\\", e[\\\"start\\\"].get(\\\"date\\\"))} {e[\\\"summary\\\"]}') for e in json.load(sys.stdin).get('items', [])]\""
```

## Notes

- Uses EchoMind connector OAuth tokens — `$GOOGLE_TOKEN` is populated from the user's connected Google account
- Scopes required: `drive.readonly`, `documents.readonly`, `spreadsheets`, `calendar.readonly` (or `calendar` for write)
- Google API rate limits apply — typically 100 requests per 100 seconds per user
- File IDs and Spreadsheet IDs can be extracted from Google URLs
