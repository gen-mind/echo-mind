---
name: openai-whisper-api
description: "Transcribe audio files using OpenAI's Whisper API"
command: "${command}"
args:
  - name: command
    description: "curl command for OpenAI Audio API"
    required: true
tags: [openai, whisper, audio, transcription, api]
timeout: 120
max_output_bytes: 262144
---

# OpenAI Whisper API Skill

Transcribe audio files using OpenAI's Whisper API.

## Overview

Use OpenAI's Audio API to transcribe speech from audio files into text. Supports multiple audio formats and languages. Requires the `$OPENAI_API_KEY` environment variable to be set.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/v1/audio/transcriptions` | Transcribe audio to text |
| `/v1/audio/translations` | Translate audio to English text |

## Supported Audio Formats

| Format | Extension |
|--------|-----------|
| MP3 | `.mp3` |
| WAV | `.wav` |
| M4A | `.m4a` |
| FLAC | `.flac` |
| OGG | `.ogg` |
| WebM | `.webm` |
| MP4 | `.mp4` |

## Response Formats

| Format | Description |
|--------|-------------|
| `json` | Simple JSON with text field (default) |
| `text` | Plain text output |
| `verbose_json` | JSON with timestamps and metadata |
| `srt` | SubRip subtitle format |
| `vtt` | WebVTT subtitle format |

## Examples

**Basic transcription (MP3):**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H \"Authorization: Bearer $OPENAI_API_KEY\" -F file=@recording.mp3 -F model=whisper-1"
```

**Transcription with language hint:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H \"Authorization: Bearer $OPENAI_API_KEY\" -F file=@audio.wav -F model=whisper-1 -F language=en"
```

**Transcription as plain text:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H \"Authorization: Bearer $OPENAI_API_KEY\" -F file=@meeting.m4a -F model=whisper-1 -F response_format=text"
```

**Transcription with timestamps (verbose JSON):**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H \"Authorization: Bearer $OPENAI_API_KEY\" -F file=@lecture.mp3 -F model=whisper-1 -F response_format=verbose_json"
```

**Generate SRT subtitles:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/transcriptions -H \"Authorization: Bearer $OPENAI_API_KEY\" -F file=@video.mp4 -F model=whisper-1 -F response_format=srt"
```

**Translate non-English audio to English:**
```
command: "curl -s -X POST https://api.openai.com/v1/audio/translations -H \"Authorization: Bearer $OPENAI_API_KEY\" -F file=@german_audio.mp3 -F model=whisper-1"
```

## Notes

- Maximum file size: 25 MB
- Set `OPENAI_API_KEY` in your environment before using this skill
- For longer files, split into segments before transcribing
- The `language` parameter uses ISO 639-1 codes (e.g., `en`, `de`, `fr`, `ja`)
