---
name: gifgrep
description: "Search and download GIFs from various sources"
command: "${command}"
args:
  - name: command
    description: "gifgrep command or curl command for GIF search APIs"
    required: true
tags: [gif, search, media, fun]
timeout: 15
---

# GIF Grep Skill

Search and download GIFs from Giphy and Tenor APIs using curl. Find the perfect GIF for any occasion.

## Giphy Search

Requires `$GIPHY_API_KEY` environment variable.

```bash
# Search for GIFs
curl -s "https://api.giphy.com/v1/gifs/search?api_key=$GIPHY_API_KEY&q=funny+cat&limit=5" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for gif in data['data']:
    print(f'{gif[\"title\"]}: {gif[\"images\"][\"original\"][\"url\"]}')
"

# Get trending GIFs
curl -s "https://api.giphy.com/v1/gifs/trending?api_key=$GIPHY_API_KEY&limit=5" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for gif in data['data']:
    print(f'{gif[\"title\"]}: {gif[\"images\"][\"original\"][\"url\"]}')
"

# Get a random GIF by tag
curl -s "https://api.giphy.com/v1/gifs/random?api_key=$GIPHY_API_KEY&tag=celebration" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['data']['images']['original']['url'])
"

# Get GIF by ID
curl -s "https://api.giphy.com/v1/gifs/xT9IgzoKnwFNkISg8?api_key=$GIPHY_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['data']['images']['original']['url'])
"
```

## Tenor Search

Requires `$TENOR_API_KEY` environment variable.

```bash
# Search for GIFs on Tenor
curl -s "https://tenor.googleapis.com/v2/search?key=$TENOR_API_KEY&q=thumbs+up&limit=5" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for result in data['results']:
    print(f'{result[\"content_description\"]}: {result[\"media_formats\"][\"gif\"][\"url\"]}')
"

# Get trending GIFs from Tenor
curl -s "https://tenor.googleapis.com/v2/featured?key=$TENOR_API_KEY&limit=5" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for result in data['results']:
    print(f'{result[\"content_description\"]}: {result[\"media_formats\"][\"gif\"][\"url\"]}')
"
```

## Download a GIF

```bash
# Download a GIF by URL
curl -sL "https://media.giphy.com/media/xT9IgzoKnwFNkISg8/giphy.gif" -o output.gif

# Download with original filename
curl -sLOJ "https://media.giphy.com/media/xT9IgzoKnwFNkISg8/giphy.gif"
```

## Examples

**Search Giphy for reaction GIFs:**
```
command: "curl -s 'https://api.giphy.com/v1/gifs/search?api_key=$GIPHY_API_KEY&q=mind+blown&limit=3&rating=g' | python3 -c \"import sys, json; data = json.load(sys.stdin); [print(g['images']['original']['url']) for g in data['data']]\""
```

**Get a random celebration GIF:**
```
command: "curl -s 'https://api.giphy.com/v1/gifs/random?api_key=$GIPHY_API_KEY&tag=celebration&rating=g' | python3 -c \"import sys, json; print(json.load(sys.stdin)['data']['images']['original']['url'])\""
```

**Search Tenor:**
```
command: "curl -s 'https://tenor.googleapis.com/v2/search?key=$TENOR_API_KEY&q=happy+dance&limit=3' | python3 -c \"import sys, json; [print(r['media_formats']['gif']['url']) for r in json.load(sys.stdin)['results']]\""
```
