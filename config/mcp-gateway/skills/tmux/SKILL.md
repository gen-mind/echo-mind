---
name: tmux
description: "Manage tmux sessions, windows, and panes for terminal multiplexing"
command: "tmux ${command}"
args:
  - name: command
    description: "tmux subcommand and arguments"
    required: true
tags: [tmux, terminal, session]
timeout: 10
---

# tmux Skill

Manage tmux sessions, windows, and panes for terminal multiplexing.

## Overview

tmux is a terminal multiplexer that lets you create, manage, and navigate multiple terminal sessions. This skill provides access to all tmux subcommands for session management, window splitting, and remote command execution.

## Common Subcommands

| Subcommand | Description |
|------------|-------------|
| `new-session -s <name>` | Create a new named session |
| `list-sessions` | List all active sessions |
| `attach -t <name>` | Attach to an existing session |
| `detach -t <name>` | Detach a session |
| `kill-session -t <name>` | Kill a session |
| `split-window -h` | Split pane horizontally |
| `split-window -v` | Split pane vertically |
| `send-keys -t <target> '<keys>' Enter` | Send keystrokes to a pane |
| `capture-pane -t <target> -p` | Capture and print pane contents |
| `select-window -t <index>` | Switch to a window by index |
| `new-window -n <name>` | Create a new named window |

## Target Syntax

Targets use the format `session:window.pane`:

| Target | Description |
|--------|-------------|
| `mysession` | Session named "mysession" |
| `mysession:0` | Window 0 in "mysession" |
| `mysession:0.1` | Pane 1 in window 0 of "mysession" |

## Examples

**Create a new session:**
```
command: "new-session -d -s dev"
```

**List all sessions:**
```
command: "list-sessions"
```

**Split window and run a command:**
```
command: "split-window -h -t dev"
```

**Send a command to a pane:**
```
command: "send-keys -t dev:0.0 'python app.py' Enter"
```

**Capture pane output:**
```
command: "capture-pane -t dev:0.0 -p"
```

**Kill a session:**
```
command: "kill-session -t dev"
```

**Create a new named window:**
```
command: "new-window -t dev -n logs"
```
