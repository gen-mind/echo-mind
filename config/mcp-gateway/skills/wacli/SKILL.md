---
name: wacli
description: "Send and receive WhatsApp messages via the wacli CLI"
command: "wacli ${command}"
args:
  - name: command
    description: "wacli subcommand and arguments"
    required: true
tags: [whatsapp, messaging, communication]
timeout: 30
---

# WaCLI Skill

Send and receive WhatsApp messages using the wacli command-line interface.

> **Prerequisite:** Requires `wacli` CLI tool installed and configured with WhatsApp credentials.

## Overview

WaCLI is a CLI tool for WhatsApp that connects via the WhatsApp Web multi-device protocol. It allows sending and receiving messages, listing chats, and managing conversations from the command line. Requires an authenticated WhatsApp session configured in the sandbox.

## Authentication

```bash
# Login via QR code (initial setup — interactive)
wacli login

# Check connection status
wacli status

# Logout
wacli logout
```

## Sending Messages

```bash
# Send a text message (phone number with country code, no +)
wacli send 41791234567 "Hello from EchoMind!"

# Send to a saved contact by name
wacli send --name "Alice" "Meeting at 3pm today"

# Send a file/document
wacli send 41791234567 --file /tmp/report.pdf

# Send an image with caption
wacli send 41791234567 --image /tmp/photo.jpg --caption "Check this out"

# Send a voice message (audio file)
wacli send 41791234567 --audio /tmp/voice.ogg
```

## Reading Messages

```bash
# List recent chats
wacli chats

# List chats with message preview
wacli chats --preview

# Read messages from a specific contact (last 10)
wacli messages 41791234567

# Read messages with limit
wacli messages 41791234567 --limit 20

# Read unread messages
wacli unread
```

## Group Messages

```bash
# List groups
wacli groups

# Send message to a group (by group JID)
wacli send --group "120363001234567890@g.us" "Hello team!"

# Read group messages
wacli messages --group "120363001234567890@g.us"
```

## Contact Management

```bash
# List contacts
wacli contacts

# Search contacts
wacli contacts --search "Alice"

# Get contact info
wacli contact 41791234567
```

## Examples

**Send a message:**
```
command: "send 41791234567 'Hello! This is an automated message from EchoMind.'"
```

**List recent chats:**
```
command: "chats --preview"
```

**Read messages from a contact:**
```
command: "messages 41791234567 --limit 5"
```

**Send a document:**
```
command: "send 41791234567 --file /tmp/document.pdf"
```

**Check unread messages:**
```
command: "unread"
```

## Notes

- Requires WhatsApp authentication session configured in the sandbox
- Phone numbers must include country code without the `+` prefix (e.g., `41791234567` for Switzerland)
- WhatsApp Web multi-device allows connection without keeping the phone online
- Message delivery depends on the recipient's WhatsApp availability
- Group JIDs can be found via `wacli groups`
- File size limits follow WhatsApp's standard limits (16 MB for media, 100 MB for documents)
- Rate limiting: avoid sending bulk messages to prevent account restrictions
