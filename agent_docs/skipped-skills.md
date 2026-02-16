# Skipped Skills — Portability Assessment

> **Context**: During Phase 3 of the MCP Gateway implementation, 42 of 58 Moltbot skills were ported to EchoMind. This document explains why the remaining 16 skills were not ported and cannot run inside a Docker container on a Linux server.

---

## Summary

| Skip Reason | Count | Skills |
|-------------|-------|--------|
| macOS-only | 6 | apple-notes, apple-reminders, bear-notes, imsg, peekaboo, things-mac |
| Local hardware/network | 5 | blucli, eightctl, openhue, sonoscli, spotify-player |
| Moltbot-specific | 3 | bluebubbles, canvas, voice-call |
| Personal/non-enterprise | 2 | food-order, ordercli |

---

## macOS-only (6 skills)

These skills use macOS-specific APIs (AppleScript, Accessibility framework, macOS-only apps). Linux containers have no equivalent runtime.

### apple-notes

- **What**: Read/write Apple Notes via `memo` CLI
- **Why skipped**: `memo` calls AppleScript under the hood to interact with Notes.app. There is no Apple Notes API or web interface. The data is stored in a local SQLite database tied to macOS.
- **Alternative in EchoMind**: Use `obsidian` or `notion` skills instead.

### apple-reminders

- **What**: Manage Apple Reminders via `remindctl` CLI
- **Why skipped**: `remindctl` uses the macOS EventKit framework. No Linux equivalent exists. Apple does not expose a public Reminders API.
- **Alternative in EchoMind**: Use `trello` skill or the planned task management integration.

### bear-notes

- **What**: Search/create Bear notes via `grizzly` CLI
- **Why skipped**: Bear is a macOS/iOS-only app with no web API. `grizzly` interacts with Bear's local SQLite database and x-callback-url scheme, both macOS-only.
- **Alternative in EchoMind**: Use `obsidian` or `notion` skills instead.

### imsg

- **What**: Send/receive iMessage and SMS via CLI
- **Why skipped**: Uses the macOS Messages framework. iMessage is exclusively tied to Apple hardware and Apple ID authentication. There is no Linux iMessage client.
- **Alternative in EchoMind**: Use `wacli` (WhatsApp), `himalaya` (email), or `slack`/`discord` skills.

### peekaboo

- **What**: macOS UI automation — screenshots, window management, OCR
- **Why skipped**: Uses macOS Accessibility APIs and screen capture APIs. A headless Docker container has no display server, no windows, no screen to capture.
- **Alternative in EchoMind**: Use `camsnap` for camera capture, or `video-frames` for video frame extraction.

### things-mac

- **What**: Task management via Things 3 `things-cli`
- **Why skipped**: Things 3 is macOS/iOS-only with no web API. `things-cli` uses AppleScript to control the app. No Linux equivalent.
- **Alternative in EchoMind**: Use `trello` skill.

---

## Local Hardware / Network Required (5 skills)

These skills control physical devices on a local network. A Docker container on a remote server has no access to home/office LAN devices.

### blucli

- **What**: Control BluOS speakers (Bluesound, NAD)
- **Why skipped**: BluOS speakers are discovered via mDNS/SSDP on the local network. The CLI sends HTTP commands to speaker IP addresses. A remote Docker container cannot reach devices on a user's home network.
- **Possible future**: Could work if a local agent/bridge is deployed on the user's network.

### eightctl

- **What**: Control Eight Sleep smart mattress pod (temperature, vibration)
- **Why skipped**: Eight Sleep pods communicate via local network APIs. Same LAN isolation problem as blucli.
- **Possible future**: Eight Sleep has a cloud API — could be adapted if API access is obtained.

### openhue

- **What**: Control Philips Hue lights (on/off, brightness, color, scenes)
- **Why skipped**: Requires a Hue Bridge on the local network. The bridge must be paired via physical button press. Remote Docker containers cannot reach local bridges.
- **Possible future**: Hue has a remote cloud API — could be adapted with OAuth2 flow.

### sonoscli

- **What**: Control Sonos speakers (play, pause, volume, grouping)
- **Why skipped**: Sonos speakers are discovered via local network (SSDP/UPnP). Commands are sent directly to speaker IPs. No remote access from Docker.
- **Possible future**: Sonos has a cloud control API — could be adapted with OAuth2.

### spotify-player

- **What**: Control Spotify playback (play, pause, skip, queue)
- **Why skipped**: Requires local audio output hardware. A Docker container has no speakers, sound card, or audio subsystem. Even with the Spotify Web API, playback happens on a physical device.
- **Possible future**: Spotify Web API could control playback on the user's active device — would need OAuth2 flow.

---

## Moltbot-Specific (3 skills)

These skills depend on Moltbot's proprietary runtime, plugin architecture, or node system. They have no standalone CLI equivalent.

### bluebubbles

- **What**: Send/receive iMessage via BlueBubbles server plugin
- **Why skipped**: BlueBubbles is a Moltbot extension that runs as a plugin within Moltbot's node architecture. It requires a macOS host running the BlueBubbles server, which in turn requires a signed-in Apple ID. Not a standalone tool.
- **Alternative in EchoMind**: Use `wacli` (WhatsApp) or `himalaya` (email).

### canvas

- **What**: Render HTML/visualizations on Moltbot display nodes
- **Why skipped**: Moltbot has physical display nodes (tablets, screens) that can render HTML content. This is a Moltbot-specific UI feature. EchoMind has its own WebUI (`echo-mind-webui`) for rendering content to users.
- **Alternative in EchoMind**: The WebUI handles all user-facing rendering.

### voice-call

- **What**: Place and receive voice calls
- **Why skipped**: Implemented as a Moltbot plugin with tight coupling to Moltbot's event system and audio routing. Would require a complete VoIP integration (SIP/WebRTC) to replicate.
- **Possible future**: Could be implemented with Twilio or similar VoIP API as a new EchoMind skill.

---

## Personal / Non-Enterprise (2 skills)

These are personal consumer services not relevant to an enterprise AI platform.

### food-order

- **What**: Reorder food from Foodora (meal delivery service)
- **Why skipped**: Foodora is a personal food delivery service. Uses a custom Go CLI that authenticates with personal Foodora credentials. Not applicable to enterprise use cases.

### ordercli

- **What**: Track Foodora delivery orders in real-time
- **Why skipped**: Same as food-order — personal food delivery tracking. Tightly coupled to Foodora's consumer API.

---

## Portability Scorecard

| Category | Count | Ported? |
|----------|-------|---------|
| Direct (CLI works as-is) | 27 | Yes |
| Adapt (minor changes needed) | 8 | Yes |
| Replace (EchoMind-native reimplementation) | 3 | Yes |
| EchoMind-native (new skills) | 4 | Yes |
| **Skip (not portable)** | **16** | **No** |
| **Total** | **58** | **42 ported** |

---

## Future Considerations

Some skipped skills could become portable with architectural changes:

1. **Cloud API migration**: `openhue`, `sonoscli`, `spotify-player`, and `eightctl` all have cloud APIs. If OAuth2 flows are added to EchoMind, these could be adapted as API-based skills instead of local network skills.

2. **Local agent bridge**: If EchoMind deploys a lightweight agent on the user's local network (similar to Home Assistant), all local hardware skills (`blucli`, `openhue`, `sonoscli`, `eightctl`) could work via the bridge.

3. **VoIP integration**: `voice-call` could be reimplemented using Twilio, Vonage, or WebRTC as a standalone EchoMind skill.

4. **None of the macOS-only skills** (`apple-notes`, `apple-reminders`, `bear-notes`, `imsg`, `peekaboo`, `things-mac`) can ever be ported — they are fundamentally tied to Apple's proprietary APIs with no cross-platform equivalent.
