---
name: video-frames
description: "Extract frames from video files using ffmpeg"
command: "${command}"
args:
  - name: command
    description: "ffmpeg command for frame extraction"
    required: true
tags: [video, ffmpeg, media, extraction]
timeout: 120
max_output_bytes: 65536
---

# Video Frames Skill

Extract frames from video files using ffmpeg.

## Overview

Use ffmpeg to extract individual frames, thumbnails, frame sequences, and animated GIFs from video files. Supports all common video formats (MP4, MKV, AVI, MOV, WebM).

## Common Patterns

| Pattern | Description |
|---------|-------------|
| Extract frame at timestamp | Get a single frame at a specific time |
| Extract frames at interval | Get one frame every N seconds |
| Extract all frames | Dump every frame as an image |
| Create thumbnail grid | Generate a contact sheet |
| Create GIF | Convert a clip to animated GIF |

## Key ffmpeg Options

| Option | Description |
|--------|-------------|
| `-ss <time>` | Seek to timestamp (HH:MM:SS or seconds) |
| `-t <duration>` | Limit duration |
| `-vframes <n>` | Limit number of output frames |
| `-vf "fps=<n>"` | Set output frame rate |
| `-vf "select='eq(ptype,I)'"` | Extract only keyframes |
| `-q:v <n>` | JPEG quality (2=best, 31=worst) |
| `-s <WxH>` | Resize output frames |

## Examples

**Extract a single frame at 10 seconds:**
```
command: "ffmpeg -ss 10 -i video.mp4 -vframes 1 -q:v 2 frame.jpg"
```

**Extract one frame every 5 seconds:**
```
command: "ffmpeg -i video.mp4 -vf \"fps=1/5\" -q:v 2 frames/frame_%04d.jpg"
```

**Extract frames from a specific time range:**
```
command: "ffmpeg -ss 00:01:00 -t 30 -i video.mp4 -vf \"fps=1\" -q:v 2 clip_%03d.jpg"
```

**Create a thumbnail (resized frame):**
```
command: "ffmpeg -ss 5 -i video.mp4 -vframes 1 -s 320x240 -q:v 2 thumbnail.jpg"
```

**Create an animated GIF from a clip:**
```
command: "ffmpeg -ss 00:00:30 -t 5 -i video.mp4 -vf \"fps=10,scale=480:-1:flags=lanczos\" -loop 0 output.gif"
```

**Extract only keyframes (I-frames):**
```
command: "ffmpeg -i video.mp4 -vf \"select='eq(pict_type,I)'\" -vsync vfr -q:v 2 keyframe_%03d.jpg"
```

**Create a thumbnail contact sheet:**
```
command: "ffmpeg -i video.mp4 -vf \"fps=1/10,scale=160:-1,tile=5x4\" -vframes 1 -q:v 2 contact_sheet.jpg"
```
