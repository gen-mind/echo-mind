---
name: 1password
description: "Access secrets and credentials from 1Password using the op CLI"
command: "op ${command}"
args:
  - name: command
    description: "op CLI subcommand and arguments"
    required: true
tags: [1password, secrets, credentials, security]
timeout: 15
---

# 1Password Skill

Access secrets and credentials from 1Password using the op CLI.

## Overview

The 1Password CLI (`op`) provides secure access to your 1Password vaults, items, and secrets directly from the command line. Use it to retrieve passwords, API keys, and other credentials. Requires `op` CLI installed and authenticated.

## Common Subcommands

| Subcommand | Description |
|------------|-------------|
| `item list` | List all items in the default vault |
| `item get <name>` | Get an item by name or ID |
| `item get <name> --fields <field>` | Get a specific field from an item |
| `vault list` | List all vaults |
| `read "op://<vault>/<item>/<field>"` | Read a secret reference |
| `whoami` | Show current authenticated user |
| `account list` | List connected accounts |
| `item list --categories <type>` | List items by category |

## Item Categories

| Category | Description |
|----------|-------------|
| `Login` | Website login credentials |
| `Password` | Standalone passwords |
| `API Credential` | API keys and tokens |
| `Secure Note` | Encrypted notes |
| `Credit Card` | Payment cards |
| `SSH Key` | SSH keys |
| `Database` | Database credentials |

## Secret Reference Syntax

Use `op://` URIs to reference secrets:
```
op://<vault>/<item>/<field>
```

## Examples

**List all items:**
```
command: "item list"
```

**List items in a specific vault:**
```
command: "item list --vault Development"
```

**Get an item by name:**
```
command: "item get \"AWS Production\" --format json"
```

**Get a specific field (e.g., password):**
```
command: "item get \"GitHub Token\" --fields token"
```

**Read a secret reference:**
```
command: "read \"op://Development/AWS Production/access_key_id\""
```

**List all vaults:**
```
command: "vault list"
```

**List only API credentials:**
```
command: "item list --categories \"API Credential\""
```

**Check authentication status:**
```
command: "whoami"
```

## Notes

- Requires `op` CLI installed: https://1password.com/downloads/command-line/
- Authenticate first with `op signin` or biometric unlock
- Use `--format json` for machine-readable output
- Secret references (`op://`) are the preferred way to inject secrets into scripts
