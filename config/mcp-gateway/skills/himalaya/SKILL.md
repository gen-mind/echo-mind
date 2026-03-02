---
name: himalaya
description: "Read and send emails via IMAP/SMTP using curl or the himalaya CLI"
command: "${command}"
args:
  - name: command
    description: "himalaya CLI command or curl IMAP/SMTP command"
    required: true
tags: [email, imap, smtp, messaging]
timeout: 30
max_output_bytes: 131072
---

# Himalaya Skill

Read and send emails using the himalaya CLI or curl with IMAP/SMTP protocols.

## Overview

Himalaya is a CLI email client supporting IMAP and SMTP. This skill provides email access for reading, searching, and sending messages. Can also use curl with IMAP for direct mailbox access. For sending emails, EchoMind's MCP `send_email` tool is also available as an alternative.

## Himalaya CLI

### List Messages

```bash
# List recent messages in INBOX (default 10)
himalaya list

# List messages in a specific folder
himalaya list -f "Sent"

# List with page size
himalaya list -s 20

# List messages on a specific page
himalaya list -p 2 -s 10
```

### Read Messages

```bash
# Read a message by sequence number
himalaya read 1

# Read in plain text (strip HTML)
himalaya read 1 -t plain

# Read headers only
himalaya read 1 -H
```

### Search Messages

```bash
# Search by subject
himalaya search "subject:meeting"

# Search by sender
himalaya search "from:alice@example.com"

# Search by date range
himalaya search "since:2026-02-01 before:2026-02-15"

# Combined search
himalaya search "from:boss subject:urgent unseen"
```

### Send Messages

```bash
# Send a simple email
himalaya send <<EOF
From: me@example.com
To: recipient@example.com
Subject: Hello from EchoMind

This is the message body.
EOF

# Reply to a message
himalaya reply 1 <<EOF
Thanks for the update!
EOF

# Forward a message
himalaya forward 1 --to forwarded@example.com
```

### Folder Management

```bash
# List all folders/mailboxes
himalaya folders

# Create a new folder
himalaya folder create "Projects"

# Move a message to a folder
himalaya move 1 -f "Archive"
```

## Curl with IMAP

```bash
# List mailbox folders
curl -s --url "imaps://imap.gmail.com" -u "user@gmail.com:app-password" --request "LIST \"\" *"

# Fetch recent message headers from INBOX
curl -s --url "imaps://imap.gmail.com/INBOX" -u "user@gmail.com:app-password" --request "FETCH 1:5 (BODY[HEADER.FIELDS (FROM SUBJECT DATE)])"

# Fetch a specific message body
curl -s --url "imaps://imap.gmail.com/INBOX;UID=123" -u "user@gmail.com:app-password"

# Search for unseen messages
curl -s --url "imaps://imap.gmail.com/INBOX" -u "user@gmail.com:app-password" --request "SEARCH UNSEEN"
```

## Examples

**List recent inbox messages:**
```
command: "himalaya list -s 5"
```

**Read a specific message:**
```
command: "himalaya read 1 -t plain"
```

**Search for messages from a sender:**
```
command: "himalaya search 'from:alice@example.com'"
```

**Send a quick email:**
```
command: "echo -e 'From: me@example.com\nTo: recipient@example.com\nSubject: Quick note\n\nHello from EchoMind!' | himalaya send"
```

**List all folders:**
```
command: "himalaya folders"
```

## Notes

- Himalaya config is stored in `~/.config/himalaya/config.toml` — must be configured in the sandbox
- For Gmail, use App Passwords (not regular passwords) with IMAP enabled
- EchoMind's MCP `send_email` tool is an alternative for sending without IMAP/SMTP setup
- IMAP search syntax follows RFC 3501 (UNSEEN, SINCE, FROM, SUBJECT, etc.)
- Himalaya supports multiple accounts via named profiles in config
