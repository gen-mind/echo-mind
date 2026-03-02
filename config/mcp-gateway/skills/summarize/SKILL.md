---
name: summarize
description: "Fetch and extract content from URLs for summarization"
command: "curl -sL -m 30 --max-filesize 10485760 ${url} | head -c ${max_chars}"
args:
  - name: url
    description: "URL to fetch content from"
    required: true
  - name: max_chars
    description: "Maximum characters to return"
    required: false
    default: "100000"
tags: [summarize, web, utility]
timeout: 45
max_output_bytes: 131072
---

# Summarize Skill

Fetches and extracts raw content from URLs. The skill handles the content retrieval — the LLM agent provides the actual summarization, analysis, or processing of the returned content.

## Usage Patterns

### Fetch a Web Page

Retrieve the full content of a web page for the agent to summarize:

```
url: "https://example.com/article"
```

### Fetch with Character Limit

Limit the returned content to a specific size (useful for very large pages):

```
url: "https://example.com/long-document"
max_chars: "50000"
```

### Content Types

The skill works with any URL that `curl` can fetch:

- **HTML pages** — returns raw HTML; the agent extracts meaningful text
- **Plain text files** — returns text directly
- **JSON APIs** — returns raw JSON for the agent to parse
- **Markdown documents** — returns raw markdown
- **RSS/Atom feeds** — returns XML feed content

### Constraints

- **Timeout**: 30-second connection timeout prevents hanging on slow servers
- **File size limit**: 10 MB maximum download size prevents memory issues
- **Output limit**: Controlled by `max_chars` (default 100,000 characters)
- **Redirects**: Follows redirects automatically (`-L` flag)
- **Silent mode**: Suppresses progress bars and error noise (`-s` flag)

### Example Workflows

1. **Summarize an article**: Fetch the URL, then ask the agent to provide a concise summary
2. **Extract key points**: Fetch documentation, then ask the agent to list main takeaways
3. **Compare sources**: Fetch multiple URLs in sequence, then ask the agent to compare
4. **Monitor changes**: Fetch a page periodically to check for updates
