# Agent Docs

Task-specific context files for AI assistants. These are **not auto-loaded** - reference them when needed.

## When to Use

- Complex multi-step tasks
- Domain-specific knowledge
- Integration guides
- Troubleshooting procedures

## Structure

```
agent_docs/
├── README.md                    # This file
├── connectors/                  # Connector implementation guides
│   ├── teams-connector.md
│   └── google-drive-connector.md
├── deployment/                  # Deployment procedures
│   ├── kubernetes-setup.md
│   └── docker-compose-local.md
└── troubleshooting/             # Debug guides
    ├── nats-issues.md
    └── qdrant-issues.md
```

## Usage

Reference these docs in your prompts when working on related tasks:

```
"I'm implementing a new Teams connector. See agent_docs/connectors/teams-connector.md for context."
```

## Adding New Docs

1. Create markdown file in appropriate subfolder
2. Keep focused on one topic
3. Include code examples where helpful
4. Update this README if adding new categories