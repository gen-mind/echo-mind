---
name: nano-banana-pro
description: "Generate images using Google Gemini's image generation capabilities"
command: "${command}"
args:
  - name: command
    description: "curl command for Gemini image generation API"
    required: true
tags: [gemini, image, ai, generation, google]
timeout: 60
max_output_bytes: 131072
---

# Nano Banana Pro Skill

Generate images using Google Gemini's image generation capabilities via the Generative Language API. Requires `$GEMINI_API_KEY` environment variable.

## Authentication

All requests require a valid Gemini API key passed as a query parameter:
- `?key=$GEMINI_API_KEY`

Base URL: `https://generativelanguage.googleapis.com/v1beta/models`

## Generate Images from Text

```bash
# Generate an image from a text prompt
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [{"text": "Generate an image of a sunset over mountains"}]
    }],
    "generationConfig": {
      "responseModalities": ["TEXT", "IMAGE"]
    }
  }'

# Generate with specific image dimensions
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [{"text": "A photorealistic cat wearing a tiny hat, 1024x1024"}]
    }],
    "generationConfig": {
      "responseModalities": ["TEXT", "IMAGE"]
    }
  }'
```

## Save Generated Image

```bash
# Generate and save image to file (extracts base64 from response)
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [{"text": "Generate an image of a futuristic city"}]
    }],
    "generationConfig": {
      "responseModalities": ["TEXT", "IMAGE"]
    }
  }' | python3 -c "
import json, sys, base64
resp = json.load(sys.stdin)
for part in resp['candidates'][0]['content']['parts']:
    if 'inlineData' in part:
        data = base64.b64decode(part['inlineData']['data'])
        with open('output.png', 'wb') as f:
            f.write(data)
        print('Saved to output.png')
        break
"
```

## Edit Images (Image + Text Input)

```bash
# Edit an existing image with a text instruction
IMAGE_B64=$(base64 -i input.png)
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"contents\": [{
      \"parts\": [
        {\"inlineData\": {\"mimeType\": \"image/png\", \"data\": \"$IMAGE_B64\"}},
        {\"text\": \"Add a rainbow to the sky in this image\"}
      ]
    }],
    \"generationConfig\": {
      \"responseModalities\": [\"TEXT\", \"IMAGE\"]
    }
  }"
```

## List Available Models

```bash
# List models that support image generation
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" \
  | python3 -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin)['models'] if 'generateContent' in m.get('supportedGenerationMethods',[])]"
```

## Examples

**Generate an image and save it:**
```
command: "curl -s -X POST 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY' -H 'Content-Type: application/json' -d '{\"contents\":[{\"parts\":[{\"text\":\"A watercolor painting of a forest\"}]}],\"generationConfig\":{\"responseModalities\":[\"TEXT\",\"IMAGE\"]}}'"
```

**List available models:**
```
command: "curl -s 'https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY'"
```
