---
name: github
description: "Interact with GitHub using the gh CLI — repos, PRs, issues, releases"
command: "gh ${command}"
args:
  - name: command
    description: "gh subcommand and arguments (e.g., 'pr list --repo owner/repo')"
    required: true
tags: [github, git, development, api]
timeout: 60
max_output_bytes: 262144
---

# GitHub CLI Skill

Interact with GitHub directly using the [gh CLI](https://cli.github.com/). Supports repositories, pull requests, issues, releases, actions, and the GitHub API.

## Repository Operations

```bash
# View current repo info
gh repo view

# View a specific repo
gh repo view owner/repo

# List your repos
gh repo list

# List org repos
gh repo list my-org --limit 20

# Clone a repo
gh repo clone owner/repo
```

## Pull Requests

```bash
# List open PRs
gh pr list

# List PRs with filters
gh pr list --state merged --author @me --limit 10

# View PR details
gh pr view 123

# View PR diff
gh pr diff 123

# Create a PR
gh pr create --title "Add feature" --body "Description here"

# Create PR with base branch
gh pr create --base develop --title "Feature" --body "Details"

# Merge a PR
gh pr merge 123 --squash

# Checkout a PR locally
gh pr checkout 123

# List PR checks
gh pr checks 123

# Review a PR
gh pr review 123 --approve
gh pr review 123 --request-changes --body "Please fix X"
```

## Issues

```bash
# List open issues
gh issue list

# List issues with labels
gh issue list --label bug --label urgent

# Create an issue
gh issue create --title "Bug report" --body "Steps to reproduce..."

# Create issue with labels and assignees
gh issue create --title "Fix login" --label bug --assignee user1

# View issue details
gh issue view 456

# Close an issue
gh issue close 456

# Reopen an issue
gh issue reopen 456

# Add a comment
gh issue comment 456 --body "Fixed in PR #123"
```

## Releases

```bash
# List releases
gh release list

# View latest release
gh release view --repo owner/repo

# Create a release
gh release create v1.0.0 --title "v1.0.0" --notes "Release notes here"

# Create release from tag with auto-generated notes
gh release create v1.0.0 --generate-notes

# Upload assets to a release
gh release upload v1.0.0 ./dist/app.zip
```

## Actions & Workflows

```bash
# List recent workflow runs
gh run list

# List runs for a specific workflow
gh run list --workflow build.yml

# View run details
gh run view 12345

# Watch a running workflow
gh run watch 12345

# Re-run a failed workflow
gh run rerun 12345

# List workflows
gh workflow list

# Trigger a workflow
gh workflow run build.yml
```

## GitHub API Access

```bash
# Get repo info as JSON
gh api repos/owner/repo

# List PR comments
gh api repos/owner/repo/pulls/123/comments

# GraphQL query
gh api graphql -f query='{ viewer { login } }'

# Paginated results
gh api repos/owner/repo/issues --paginate

# Create a comment via API
gh api repos/owner/repo/issues/123/comments -f body="Comment text"
```

## Common Flags

| Flag | Description |
|------|-------------|
| `--repo owner/repo` | Target a specific repository |
| `--json field1,field2` | Output specific fields as JSON |
| `--jq '.[]'` | Filter JSON output with jq expressions |
| `--limit N` | Limit number of results |
| `--state open/closed/merged/all` | Filter by state |
| `--label name` | Filter by label |
| `--assignee user` | Filter by assignee |
| `--author user` | Filter by author (`@me` for yourself) |
| `--web` | Open in browser instead of terminal |

## Examples

**List open PRs as JSON with specific fields:**
```
command: "pr list --json number,title,author --limit 5"
```

**View repo details for a specific repo:**
```
command: "repo view owner/repo"
```

**Create an issue with labels:**
```
command: "issue create --title 'Bug: login fails' --label bug --body 'Steps to reproduce...'"
```

**Get release info as JSON:**
```
command: "release list --json tagName,publishedAt --limit 3"
```

**Check CI status for a PR:**
```
command: "pr checks 42 --repo owner/repo"
```
