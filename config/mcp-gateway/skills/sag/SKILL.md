---
name: sag
description: "Generate speech audio using ElevenLabs text-to-speech API"
command: "${command}"
args:
  - name: command
    description: "curl command for ElevenLabs TTS API"
    required: true
tags: [tts, speech, audio, elevenlabs, api]
timeout: 60
max_output_bytes: 131072
---

# Say (SAG) Skill

Generate speech audio using the ElevenLabs text-to-speech API. Convert text to natural-sounding speech, list available voices, and manage voice settings.

Requires `$ELEVENLABS_API_KEY` environment variable.

## Text-to-Speech

```bash
# Generate speech and save to file
curl -s -X POST "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello from EchoMind!",
    "model_id": "eleven_monolingual_v1",
    "voice_settings": {
      "stability": 0.5,
      "similarity_boost": 0.5
    }
  }' \
  --output speech.mp3

# Generate with streaming
curl -s -X POST "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM/stream" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is streamed audio output.",
    "model_id": "eleven_monolingual_v1"
  }' \
  --output streamed_speech.mp3

# Generate with multilingual model
curl -s -X POST "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bonjour, comment allez-vous?",
    "model_id": "eleven_multilingual_v2"
  }' \
  --output french_speech.mp3
```

## List Voices

```bash
# List all available voices
curl -s "https://api.elevenlabs.io/v1/voices" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for voice in data['voices']:
    labels = ', '.join(f'{k}: {v}' for k, v in voice.get('labels', {}).items())
    print(f'{voice[\"name\"]} (ID: {voice[\"voice_id\"]}) - {labels}')
"

# Get details for a specific voice
curl -s "https://api.elevenlabs.io/v1/voices/21m00Tcm4TlvDq8ikWAM" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" | python3 -c "
import sys, json
v = json.load(sys.stdin)
print(f'Name: {v[\"name\"]}')
print(f'ID: {v[\"voice_id\"]}')
print(f'Category: {v.get(\"category\", \"N/A\")}')
print(f'Labels: {v.get(\"labels\", {})}')
"
```

## List Models

```bash
# List available TTS models
curl -s "https://api.elevenlabs.io/v1/models" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" | python3 -c "
import sys, json
for model in json.load(sys.stdin):
    print(f'{model[\"name\"]} (ID: {model[\"model_id\"]})')
    print(f'  Languages: {len(model.get(\"languages\", []))}')
    print(f'  Description: {model.get(\"description\", \"N/A\")[:80]}')
    print()
"
```

## Voice Settings

| Setting | Range | Description |
|---------|-------|-------------|
| `stability` | 0.0 - 1.0 | Higher = more consistent, lower = more expressive |
| `similarity_boost` | 0.0 - 1.0 | Higher = closer to original voice |
| `style` | 0.0 - 1.0 | Style exaggeration (v2 models only) |
| `use_speaker_boost` | boolean | Enhance speaker clarity |

## Check Usage

```bash
# Check subscription and usage info
curl -s "https://api.elevenlabs.io/v1/user/subscription" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" | python3 -c "
import sys, json
sub = json.load(sys.stdin)
print(f'Tier: {sub[\"tier\"]}')
print(f'Characters used: {sub[\"character_count\"]}/{sub[\"character_limit\"]}')
print(f'Remaining: {sub[\"character_limit\"] - sub[\"character_count\"]}')
"
```

## Examples

**Generate speech with Rachel voice:**
```
command: "curl -s -X POST 'https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM' -H 'xi-api-key: $ELEVENLABS_API_KEY' -H 'Content-Type: application/json' -d '{\"text\": \"Welcome to EchoMind.\", \"model_id\": \"eleven_monolingual_v1\"}' --output /tmp/speech.mp3"
```

**List all voices:**
```
command: "curl -s 'https://api.elevenlabs.io/v1/voices' -H 'xi-api-key: $ELEVENLABS_API_KEY' | python3 -c \"import sys, json; [print(f'{v[\\\"name\\\"]}: {v[\\\"voice_id\\\"]}') for v in json.load(sys.stdin)['voices']]\""
```

**Check remaining character quota:**
```
command: "curl -s 'https://api.elevenlabs.io/v1/user/subscription' -H 'xi-api-key: $ELEVENLABS_API_KEY' | python3 -c \"import sys, json; s=json.load(sys.stdin); print(f'Remaining: {s[\\\"character_limit\\\"]-s[\\\"character_count\\\"]} chars')\""
```
