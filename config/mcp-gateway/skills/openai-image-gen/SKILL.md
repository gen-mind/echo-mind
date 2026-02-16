---
name: openai-image-gen
description: "Generate images using OpenAI's DALL-E API"
command: "${command}"
args:
  - name: command
    description: "curl command for OpenAI Images API"
    required: true
tags: [openai, image, ai, generation, api]
timeout: 60
max_output_bytes: 131072
---

# OpenAI Image Generation Skill

Generate and edit images using [OpenAI's Images API](https://platform.openai.com/docs/api-reference/images) (DALL-E). Requires `$OPENAI_API_KEY` environment variable.

## Authentication

All requests require:
- `Authorization: Bearer $OPENAI_API_KEY`
- `Content-Type: application/json` (for JSON requests)

Base URL: `https://api.openai.com/v1/`

## Generate Images

```bash
# Generate an image with DALL-E 3
curl -s -X POST "https://api.openai.com/v1/images/generations" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-3",
    "prompt": "A futuristic city skyline at sunset, digital art",
    "n": 1,
    "size": "1024x1024"
  }'

# Generate with specific quality and style
curl -s -X POST "https://api.openai.com/v1/images/generations" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-3",
    "prompt": "A minimalist logo for a tech startup",
    "n": 1,
    "size": "1024x1024",
    "quality": "hd",
    "style": "natural"
  }'

# Generate with DALL-E 2 (supports multiple images)
curl -s -X POST "https://api.openai.com/v1/images/generations" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-2",
    "prompt": "A watercolor painting of a mountain lake",
    "n": 4,
    "size": "512x512"
  }'

# Get result as base64 instead of URL
curl -s -X POST "https://api.openai.com/v1/images/generations" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-3",
    "prompt": "An abstract geometric pattern",
    "n": 1,
    "size": "1024x1024",
    "response_format": "b64_json"
  }'
```

## Edit Images (DALL-E 2 only)

```bash
# Edit an image with a mask (inpainting)
curl -s -X POST "https://api.openai.com/v1/images/edits" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F "image=@original.png" \
  -F "mask=@mask.png" \
  -F "prompt=A sunlit garden with flowers" \
  -F "n=1" \
  -F "size=1024x1024"
```

## Create Variations (DALL-E 2 only)

```bash
# Create variations of an existing image
curl -s -X POST "https://api.openai.com/v1/images/variations" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F "image=@source.png" \
  -F "n=2" \
  -F "size=1024x1024"
```

## Parameters

### DALL-E 3

| Parameter | Values | Default |
|-----------|--------|---------|
| `size` | `1024x1024`, `1792x1024`, `1024x1792` | `1024x1024` |
| `quality` | `standard`, `hd` | `standard` |
| `style` | `vivid`, `natural` | `vivid` |
| `n` | `1` (only 1 supported) | `1` |
| `response_format` | `url`, `b64_json` | `url` |

### DALL-E 2

| Parameter | Values | Default |
|-----------|--------|---------|
| `size` | `256x256`, `512x512`, `1024x1024` | `1024x1024` |
| `n` | `1` to `10` | `1` |
| `response_format` | `url`, `b64_json` | `url` |

## Response Format

The API returns a JSON object with a `data` array. Each item contains either a `url` (temporary, expires after 1 hour) or `b64_json` depending on the `response_format`:

```json
{
  "created": 1234567890,
  "data": [
    {
      "url": "https://oaidalleapiprodscus.blob.core.windows.net/...",
      "revised_prompt": "The actual prompt DALL-E 3 used (may differ from input)"
    }
  ]
}
```

## Examples

**Generate a landscape image:**
```
command: "curl -s -X POST \"https://api.openai.com/v1/images/generations\" -H \"Authorization: Bearer $OPENAI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"model\": \"dall-e-3\", \"prompt\": \"A serene mountain landscape at dawn\", \"size\": \"1792x1024\", \"quality\": \"hd\"}'"
```

**Generate a logo:**
```
command: "curl -s -X POST \"https://api.openai.com/v1/images/generations\" -H \"Authorization: Bearer $OPENAI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"model\": \"dall-e-3\", \"prompt\": \"Minimalist logo for AI company called EchoMind\", \"size\": \"1024x1024\", \"style\": \"natural\"}'"
```

**Generate multiple variations (DALL-E 2):**
```
command: "curl -s -X POST \"https://api.openai.com/v1/images/generations\" -H \"Authorization: Bearer $OPENAI_API_KEY\" -H \"Content-Type: application/json\" -d '{\"model\": \"dall-e-2\", \"prompt\": \"Icon designs for a weather app\", \"n\": 4, \"size\": \"512x512\"}'"
```
