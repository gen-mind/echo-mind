---
name: openai-whisper
description: "Transcribe audio using OpenAI Whisper API (cloud-based, no local model needed)"
command: "${command}"
args:
  - name: command
    description: "curl command for OpenAI Audio transcription API"
    required: true
tags: [whisper, audio, transcription, openai, api]
timeout: 120
max_output_bytes: 262144
---

# OpenAI Whisper Skill

Transcribe audio using OpenAI's Whisper API — cloud-based, no local model download needed.

## Overview

Uses OpenAI's Audio API for speech-to-text transcription and translation. Unlike local Whisper models, this approach requires no GPU, no model download, and no setup beyond an API key. Set `$OPENAI_API_KEY` in the environment.

## Transcription

```bash
# Basic transcription
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@recording.mp3 \
  -F model=whisper-1

# With language hint (improves accuracy)
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@audio.wav \
  -F model=whisper-1 \
  -F language=en

# Plain text output (no JSON wrapper)
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@meeting.m4a \
  -F model=whisper-1 \
  -F response_format=text

# Verbose JSON with word-level timestamps
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@lecture.mp3 \
  -F model=whisper-1 \
  -F response_format=verbose_json \
  -F "timestamp_granularities[]=word"

# With custom prompt for domain-specific vocabulary
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@tech_talk.mp3 \
  -F model=whisper-1 \
  -F prompt="EchoMind, Kubernetes, Qdrant, NATS JetStream"
```

## Translation (Non-English to English)

```bash
# Translate non-English audio to English text
curl -s -X POST https://api.openai.com/v1/audio/translations \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@german_audio.mp3 \
  -F model=whisper-1

# Translation with plain text output
curl -s -X POST https://api.openai.com/v1/audio/translations \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@french_meeting.wav \
  -F model=whisper-1 \
  -F response_format=text
```

## Subtitle Generation

```bash
# Generate SRT subtitles
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@video.mp4 \
  -F model=whisper-1 \
  -F response_format=srt

# Generate WebVTT subtitles
curl -s -X POST https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@video.mp4 \
  -F model=whisper-1 \
  -F response_format=vtt
```

## Supported Formats

| Format | Extension | Max Size |
|--------|-----------|----------|
| MP3 | `.mp3` | 25 MB |
| WAV | `.wav` | 25 MB |
| M4A | `.m4a` | 25 MB |
| FLAC | `.flac` | 25 MB |
| OGG | `.ogg` | 25 MB |
| WebM | `.webm` | 25 MB |
| MP4 | `.mp4` | 25 MB |

## Response Formats

| Format | Description |
|--------|-------------|
| `json` | JSON with `text` field (default) |
| `text` | Plain text |
| `verbose_json` | JSON with timestamps, segments, metadata |
| `srt` | SubRip subtitle format |
| `vtt` | WebVTT subtitle format |

## Examples

**Transcribe an MP3 recording:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H 'Authorization: Bearer $OPENAI_API_KEY' -F file=@/tmp/recording.mp3 -F model=whisper-1"
```

**Transcribe with language hint and plain text output:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H 'Authorization: Bearer $OPENAI_API_KEY' -F file=@/tmp/audio.wav -F model=whisper-1 -F language=de -F response_format=text"
```

**Translate French audio to English:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/translations -H 'Authorization: Bearer $OPENAI_API_KEY' -F file=@/tmp/french.mp3 -F model=whisper-1 -F response_format=text"
```

**Generate SRT subtitles:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H 'Authorization: Bearer $OPENAI_API_KEY' -F file=@/tmp/video.mp4 -F model=whisper-1 -F response_format=srt"
```

## Notes

- Maximum file size: 25 MB per request
- For larger files, split with ffmpeg: `ffmpeg -i long_audio.mp3 -f segment -segment_time 600 -c copy chunk_%03d.mp3`
- `$OPENAI_API_KEY` must be set in the environment
- The `language` parameter uses ISO 639-1 codes (`en`, `de`, `fr`, `ja`, `zh`, etc.)
- The `prompt` parameter helps with domain-specific terms, acronyms, and proper nouns
- Translation endpoint only supports translating TO English
