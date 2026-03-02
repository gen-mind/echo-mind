---
name: bird
description: "Post and manage content on X/Twitter using the bird CLI"
command: "bird ${command}"
args:
  - name: command
    description: "bird CLI subcommand and arguments"
    required: true
tags: [twitter, x, social-media]
timeout: 30
---

# Bird CLI Skill

Post and manage content on X/Twitter using the [bird CLI](https://github.com/dyatlov/bird). Supports posting tweets, reading timelines, searching, replying, and engaging with content.

## Post a Tweet

```bash
# Post a simple tweet
bird tweet "Hello from EchoMind!"

# Post a tweet with media
bird tweet "Check this out" --media /path/to/image.png

# Post a thread
bird thread "First tweet" "Second tweet" "Third tweet"
```

## Read Timeline

```bash
# View your home timeline
bird timeline

# View timeline with limit
bird timeline --limit 20

# View a specific user's timeline
bird timeline --user @username
```

## Search

```bash
# Search for tweets
bird search "artificial intelligence"

# Search with filters
bird search "AI agents" --limit 10

# Search recent tweets
bird search "echomind" --recent
```

## Reply & Engage

```bash
# Reply to a tweet by ID
bird reply 1234567890 "Great point!"

# Like a tweet
bird like 1234567890

# Retweet
bird retweet 1234567890

# Unlike a tweet
bird unlike 1234567890
```

## User Info

```bash
# View user profile
bird user @username

# View your own profile
bird me

# List followers
bird followers @username

# List following
bird following @username
```

## Examples

**Post a tweet:**
```
command: "tweet 'Deploying new features today! 🚀'"
```

**Search for recent mentions:**
```
command: "search '@myhandle' --recent --limit 5"
```

**Reply to a tweet:**
```
command: "reply 1234567890 'Thanks for the feedback!'"
```

**View home timeline:**
```
command: "timeline --limit 10"
```
