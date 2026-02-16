---
name: sherpa-onnx-tts
description: "Generate speech audio offline using Sherpa-ONNX text-to-speech models"
command: "${command}"
args:
  - name: command
    description: "sherpa-onnx-offline-tts command"
    required: true
tags: [tts, speech, audio, offline, onnx]
timeout: 60
max_output_bytes: 65536
---

# Sherpa-ONNX TTS Skill

Generate speech audio offline using Sherpa-ONNX text-to-speech models — no internet required.

> **Prerequisite:** Requires Sherpa-ONNX models mounted at the configured path. See Sherpa-ONNX documentation for model downloads.

## Overview

Sherpa-ONNX provides offline text-to-speech synthesis using ONNX Runtime. Models run locally without GPU requirements, making it suitable for sandboxed environments. Supports multiple languages and voices via VITS/PIPER models. Model files must be mounted in the sandbox volume.

## Basic Usage

```bash
# Generate speech from text (VITS model)
sherpa-onnx-offline-tts \
  --vits-model=/models/tts/vits-piper-en_US-amy-medium/en_US-amy-medium.onnx \
  --vits-tokens=/models/tts/vits-piper-en_US-amy-medium/tokens.txt \
  --vits-data-dir=/models/tts/vits-piper-en_US-amy-medium/espeak-ng-data \
  --output-filename=/tmp/output.wav \
  "Hello, this is a test of the text to speech system."

# With speed control (0.5 = slow, 1.0 = normal, 2.0 = fast)
sherpa-onnx-offline-tts \
  --vits-model=/models/tts/vits-piper-en_US-amy-medium/en_US-amy-medium.onnx \
  --vits-tokens=/models/tts/vits-piper-en_US-amy-medium/tokens.txt \
  --vits-data-dir=/models/tts/vits-piper-en_US-amy-medium/espeak-ng-data \
  --speed=1.2 \
  --output-filename=/tmp/output.wav \
  "Speaking a bit faster now."

# With specific speaker ID (multi-speaker models)
sherpa-onnx-offline-tts \
  --vits-model=/models/tts/model.onnx \
  --vits-tokens=/models/tts/tokens.txt \
  --vits-data-dir=/models/tts/espeak-ng-data \
  --sid=2 \
  --output-filename=/tmp/output.wav \
  "Using speaker number two."
```

## Available Model Types

| Model Type | Quality | Speed | Languages |
|------------|---------|-------|-----------|
| VITS (Piper) | Good | Fast | 30+ languages |
| VITS (MMS) | Good | Fast | 1000+ languages |
| Matcha | High | Medium | English, Chinese |

## Common Voice Models (Piper)

| Model | Language | Voice |
|-------|----------|-------|
| `en_US-amy-medium` | English (US) | Female, medium quality |
| `en_US-danny-low` | English (US) | Male, low quality |
| `en_GB-alba-medium` | English (UK) | Female, medium quality |
| `de_DE-thorsten-medium` | German | Male, medium quality |
| `fr_FR-siwis-medium` | French | Female, medium quality |
| `es_ES-davefx-medium` | Spanish | Male, medium quality |
| `it_IT-riccardo-x_low` | Italian | Male, extra low quality |
| `zh_CN-huayan-medium` | Chinese | Female, medium quality |

## Reading from File

```bash
# Read text from a file
sherpa-onnx-offline-tts \
  --vits-model=/models/tts/vits-piper-en_US-amy-medium/en_US-amy-medium.onnx \
  --vits-tokens=/models/tts/vits-piper-en_US-amy-medium/tokens.txt \
  --vits-data-dir=/models/tts/vits-piper-en_US-amy-medium/espeak-ng-data \
  --output-filename=/tmp/narration.wav \
  "$(cat /tmp/script.txt)"
```

## Output Conversion

```bash
# Convert WAV to MP3 (smaller file size)
ffmpeg -i /tmp/output.wav -codec:a libmp3lame -qscale:a 2 /tmp/output.mp3

# Convert WAV to OGG
ffmpeg -i /tmp/output.wav -codec:a libvorbis -qscale:a 5 /tmp/output.ogg
```

## Examples

**Generate English speech:**
```
command: "sherpa-onnx-offline-tts --vits-model=/models/tts/vits-piper-en_US-amy-medium/en_US-amy-medium.onnx --vits-tokens=/models/tts/vits-piper-en_US-amy-medium/tokens.txt --vits-data-dir=/models/tts/vits-piper-en_US-amy-medium/espeak-ng-data --output-filename=/tmp/speech.wav 'Welcome to EchoMind. How can I help you today?'"
```

**Generate German speech at slower speed:**
```
command: "sherpa-onnx-offline-tts --vits-model=/models/tts/vits-piper-de_DE-thorsten-medium/de_DE-thorsten-medium.onnx --vits-tokens=/models/tts/vits-piper-de_DE-thorsten-medium/tokens.txt --vits-data-dir=/models/tts/vits-piper-de_DE-thorsten-medium/espeak-ng-data --speed=0.8 --output-filename=/tmp/german.wav 'Willkommen bei EchoMind.'"
```

**Generate and convert to MP3:**
```
command: "sherpa-onnx-offline-tts --vits-model=/models/tts/vits-piper-en_US-amy-medium/en_US-amy-medium.onnx --vits-tokens=/models/tts/vits-piper-en_US-amy-medium/tokens.txt --vits-data-dir=/models/tts/vits-piper-en_US-amy-medium/espeak-ng-data --output-filename=/tmp/output.wav 'Converting this to MP3 format.' && ffmpeg -y -i /tmp/output.wav -codec:a libmp3lame -qscale:a 2 /tmp/output.mp3 && echo 'Saved to /tmp/output.mp3'"
```

## Notes

- Model files must be pre-downloaded and mounted in the sandbox volume at `/models/tts/`
- Output format is WAV (PCM 16-bit) — use ffmpeg to convert to MP3/OGG
- No internet connection required — fully offline inference
- CPU-only — no GPU needed, typical generation speed is 5-10x realtime
- Sample rate depends on the model (typically 22050 Hz)
- For long texts, consider splitting into sentences for better prosody
