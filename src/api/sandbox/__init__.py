"""
Sandbox container management for ephemeral agent execution.

This package provides the infrastructure for running agents in isolated
Docker containers. The SandboxManager maintains a warm pool of pre-created
containers and manages their lifecycle through assignment, activation, and
destruction.

NOTE: SandboxManager currently lives in the API service for simplicity.
It should be decoupled to its own dedicated service in a future phase
to allow independent scaling and reduce API service complexity.
"""
