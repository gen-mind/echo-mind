---
name: gemini
description: "Interact with Google Gemini AI via the Gemini CLI"
command: "${command}"
args:
  - name: command
    description: "Gemini CLI command or curl command for Gemini API"
    required: true
tags: [gemini, ai, google, llm]
timeout: 60
max_output_bytes: 131072
---

# Gemini Skill

Interact with Google Gemini AI via the Gemini API.

## Overview

Access Google's Gemini models for text generation, chat, and embeddings using curl requests to the `generativelanguage.googleapis.com` API. Requires the `$GEMINI_API_KEY` environment variable to be set.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `generateContent` | Single-turn text generation |
| `streamGenerateContent` | Streaming text generation |
| `embedContent` | Generate text embeddings |
| `countTokens` | Count tokens in text |

## Available Models

| Model | Description |
|-------|-------------|
| `gemini-2.0-flash` | Fast, efficient model for most tasks |
| `gemini-2.0-pro` | Most capable model for complex tasks |
| `gemini-1.5-flash` | Lightweight, high-speed model |

## Examples

**Generate text content:**
```
command: "curl -s -X POST \"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"contents\":[{\"parts\":[{\"text\":\"Explain quantum computing in 3 sentences\"}]}]}'"
```

**Generate with system instruction:**
```
command: "curl -s -X POST \"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=$GEMINI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"system_instruction\":{\"parts\":[{\"text\":\"You are a helpful coding assistant.\"}]},\"contents\":[{\"parts\":[{\"text\":\"Write a Python function to sort a list\"}]}]}'"
```

**Count tokens:**
```
command: "curl -s -X POST \"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:countTokens?key=$GEMINI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"contents\":[{\"parts\":[{\"text\":\"Hello, how are you?\"}]}]}'"
```

**Generate embeddings:**
```
command: "curl -s -X POST \"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=$GEMINI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"model\":\"models/text-embedding-004\",\"content\":{\"parts\":[{\"text\":\"What is machine learning?\"}]}}'"
```

**Streaming response:**
```
command: "curl -s -X POST \"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?key=$GEMINI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"contents\":[{\"parts\":[{\"text\":\"Write a short poem about coding\"}]}]}'"
```

## Notes

- Set `GEMINI_API_KEY` in your environment before using this skill
- Responses are JSON; pipe through `jq` for readable output
- Rate limits apply based on your API plan
