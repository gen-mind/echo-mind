---
name: blogwatcher
description: "Monitor RSS/Atom feeds for new content"
command: "${command}"
args:
  - name: command
    description: "blogwatcher command or curl command for RSS/Atom feeds"
    required: true
tags: [rss, atom, feeds, monitoring, web]
timeout: 30
---

# Blog Watcher Skill

Monitor RSS/Atom feeds for new content using curl and standard parsing tools. Fetch, parse, and check feeds for updates.

## Fetch an RSS Feed

```bash
# Fetch an RSS feed
curl -s https://example.com/feed.xml

# Fetch with user-agent header
curl -s -A "EchoMind/1.0" https://example.com/rss

# Fetch Atom feed
curl -s https://example.com/atom.xml

# Fetch with timeout
curl -s --max-time 15 https://example.com/feed
```

## Parse Feed Titles

```bash
# Extract titles from RSS feed using xmllint
curl -s https://example.com/feed.xml | xmllint --xpath '//item/title/text()' -

# Extract titles from Atom feed
curl -s https://example.com/atom.xml | xmllint --xpath '//*[local-name()="entry"]/*[local-name()="title"]/text()' -

# Parse with Python for better formatting
curl -s https://example.com/feed.xml | python3 -c "
import sys, xml.etree.ElementTree as ET
tree = ET.parse(sys.stdin)
for item in tree.findall('.//item'):
    title = item.find('title').text
    link = item.find('link').text
    print(f'- {title}\n  {link}\n')
"
```

## Check for New Posts

```bash
# Get latest post date from RSS
curl -s https://example.com/feed.xml | xmllint --xpath '//item[1]/pubDate/text()' -

# Get latest N items with dates
curl -s https://example.com/feed.xml | python3 -c "
import sys, xml.etree.ElementTree as ET
tree = ET.parse(sys.stdin)
for item in tree.findall('.//item')[:5]:
    title = item.find('title').text
    date = item.find('pubDate').text if item.find('pubDate') is not None else 'N/A'
    print(f'[{date}] {title}')
"
```

## Monitor Multiple Feeds

```bash
# Check multiple feeds in sequence
for feed in 'https://blog1.com/feed' 'https://blog2.com/rss'; do
  echo "=== $feed ==="
  curl -s "$feed" | xmllint --xpath '//item[1]/title/text()' - 2>/dev/null
  echo
done
```

## Discover Feeds

```bash
# Look for RSS/Atom links in a webpage
curl -s https://example.com | python3 -c "
import sys, re
html = sys.stdin.read()
links = re.findall(r'<link[^>]*type=[\"'](application/(rss|atom)\+xml)[\"'][^>]*href=[\"']([^\"']+)[\"']', html)
for match in links:
    print(f'{match[0]}: {match[2]}')
"

# Check common feed paths
for path in /feed /rss /atom.xml /feed.xml /rss.xml /index.xml; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://example.com$path")
  [ "$code" = "200" ] && echo "Found: https://example.com$path"
done
```

## Examples

**Fetch latest posts from a blog:**
```
command: "curl -s https://blog.example.com/feed.xml | python3 -c \"import sys, xml.etree.ElementTree as ET; tree = ET.parse(sys.stdin); [print(f'- {item.find(\\\"title\\\").text}') for item in tree.findall('.//item')[:5]]\""
```

**Check if a feed has new content since a date:**
```
command: "curl -s -H 'If-Modified-Since: Mon, 10 Feb 2026 00:00:00 GMT' -w '\\n%{http_code}' https://example.com/feed.xml | tail -1"
```

**Fetch an Atom feed:**
```
command: "curl -s https://example.com/atom.xml"
```
