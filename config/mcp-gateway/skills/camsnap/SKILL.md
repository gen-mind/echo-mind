---
name: camsnap
description: "Capture snapshots from RTSP/ONVIF network cameras"
command: "${command}"
args:
  - name: command
    description: "ffmpeg or curl command for camera capture"
    required: true
tags: [camera, rtsp, snapshot, media, iot]
timeout: 30
---

# CamSnap Skill

Capture snapshots and short clips from RTSP/ONVIF network cameras using ffmpeg or curl.

## Overview

CamSnap enables capturing single frames or short recordings from IP cameras that expose RTSP streams or ONVIF snapshot endpoints. Useful for security monitoring, time-lapse photography, and IoT camera integration.

## RTSP Snapshot (ffmpeg)

```bash
# Capture a single frame from an RTSP stream
ffmpeg -y -rtsp_transport tcp -i "rtsp://user:pass@192.168.1.100:554/stream1" -frames:v 1 -q:v 2 snapshot.jpg

# Capture with timeout (5 seconds max)
ffmpeg -y -rtsp_transport tcp -stimeout 5000000 -i "rtsp://camera.local:554/live" -frames:v 1 snapshot.jpg

# Capture a 10-second clip
ffmpeg -y -rtsp_transport tcp -i "rtsp://user:pass@192.168.1.100:554/stream1" -t 10 -c copy clip.mp4
```

## ONVIF Snapshot (curl)

```bash
# Grab snapshot from ONVIF-compatible camera HTTP endpoint
curl -s -o snapshot.jpg "http://192.168.1.100/onvif-http/snapshot?auth=YWRtaW46cGFzcw=="

# With basic auth
curl -s -u admin:password -o snapshot.jpg "http://192.168.1.100/snap.jpg"

# MJPEG single frame capture
curl -s --max-time 5 "http://192.168.1.100/video.mjpg" | ffmpeg -y -i pipe:0 -frames:v 1 frame.jpg
```

## Stream Information

```bash
# Probe camera stream details (codec, resolution, framerate)
ffprobe -rtsp_transport tcp -i "rtsp://user:pass@192.168.1.100:554/stream1" 2>&1 | grep -E "Stream|Duration"

# List available RTSP streams (common paths)
# /stream1, /live, /cam/realmonitor, /h264, /media/video1
```

## Common RTSP URL Patterns

| Brand | URL Pattern |
|-------|-------------|
| Hikvision | `rtsp://user:pass@IP:554/Streaming/Channels/101` |
| Dahua | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Reolink | `rtsp://user:pass@IP:554/h264Preview_01_main` |
| Generic ONVIF | `rtsp://user:pass@IP:554/stream1` |
| Amcrest | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |

## Examples

**Capture a single snapshot from a Hikvision camera:**
```
command: "ffmpeg -y -rtsp_transport tcp -stimeout 5000000 -i 'rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101' -frames:v 1 -q:v 2 /tmp/snapshot.jpg && echo 'Snapshot saved to /tmp/snapshot.jpg'"
```

**Record a 15-second clip:**
```
command: "ffmpeg -y -rtsp_transport tcp -stimeout 5000000 -i 'rtsp://admin:pass@192.168.1.100:554/stream1' -t 15 -c copy /tmp/clip.mp4 && echo 'Clip saved to /tmp/clip.mp4'"
```

**Grab snapshot via HTTP:**
```
command: "curl -s -u admin:password -o /tmp/snapshot.jpg 'http://192.168.1.100/snap.jpg' && echo 'Snapshot saved' || echo 'Failed to capture'"
```

## Notes

- Requires network access to camera IP addresses from the sandbox
- RTSP transport: use `-rtsp_transport tcp` for reliable capture over networks
- Set `-stimeout` (in microseconds) to avoid hanging on unreachable cameras
- Camera credentials should be stored in environment variables for security
- For ONVIF discovery, cameras must be on the same network segment
