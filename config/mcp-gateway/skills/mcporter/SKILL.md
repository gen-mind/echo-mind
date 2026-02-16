---
name: mcporter
description: "Manage and debug MCP servers and connections"
command: "${command}"
args:
  - name: command
    description: "MCP management command"
    required: true
tags: [mcp, server, debugging, development]
timeout: 30
---

# MCPorter Skill

Manage and debug MCP (Model Context Protocol) servers and connections. Useful for listing available servers, inspecting tools, testing transport connectivity, and diagnosing configuration issues.

## List MCP Servers

```bash
# List running MCP servers via npx
npx @modelcontextprotocol/inspector --list

# Check if a specific MCP server process is running
ps aux | grep mcp

# List available MCP server packages
npm search @modelcontextprotocol
```

## Inspect Server Tools

```bash
# Inspect tools exposed by an MCP server using the inspector
npx @modelcontextprotocol/inspector --server stdio --command "node /path/to/server.js"

# Inspect tools via SSE transport
npx @modelcontextprotocol/inspector --server sse --url http://localhost:8080/sse

# List tools from a running server (stdio transport)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | node /path/to/server.js
```

## Test Connections

```bash
# Test stdio transport
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | node /path/to/server.js

# Test SSE transport endpoint
curl -s -N http://localhost:8080/sse

# Health check for HTTP-based MCP servers
curl -s http://localhost:8080/health
```

## Debug Transport Issues

```bash
# Debug stdio server with verbose logging
MCP_LOG_LEVEL=debug node /path/to/server.js

# Check if SSE port is in use
lsof -i :8080

# Monitor MCP server logs
tail -f /tmp/mcp-server.log

# Test JSON-RPC ping
echo '{"jsonrpc":"2.0","id":1,"method":"ping"}' | node /path/to/server.js
```

## Configuration

```bash
# View Claude Code MCP config
cat ~/.claude/claude_desktop_config.json

# Validate MCP server config JSON
python3 -c "import json; json.load(open('mcp-config.json')); print('Valid JSON')"
```

## Examples

**List tools from a server:**
```
command: "echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}' | node /path/to/server.js"
```

**Test SSE connection:**
```
command: "curl -s -m 5 http://localhost:8080/sse"
```

**Inspect a server interactively:**
```
command: "npx @modelcontextprotocol/inspector --server stdio --command 'node /path/to/server.js'"
```
