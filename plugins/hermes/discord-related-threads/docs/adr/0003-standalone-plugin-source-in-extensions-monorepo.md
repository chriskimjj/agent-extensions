---
status: superseded
date: 2026-08-29
supersedes:
  - 0002-plugin-owned-feature-with-generic-history-boundary.md
superseded_by:
  - 0004-stock-hermes-plugin-distribution.md
---

# Keep standalone plugin source in the extensions monorepo

## Context

`discord-related-threads` is a user-specific Hermes plugin, while the small
history-exclusion seam it needs belongs to the shared Hermes Discord adapter.
Hermes's repository rules keep user and third-party plugins out of the core
tree, and the Hermes plugin installer supports a Git repository subdirectory.
The existing public `agent-skills` repository already held reusable agent
extensions but its name did not cover runtime plugins.

## Decision

Rename the collection to `agent-extensions` and keep `skills/` and `plugins/`
as separate top-level families. Make
`plugins/hermes/discord-related-threads/` the authoritative Git location for
this plugin's code, tests, product contract, and ADRs. Import the exact live
`1.0.0` plugin files as the baseline, then develop future plugin behavior here.

Keep only the generic, plugin-agnostic Discord history-exclusion boundary and
its core tests in the Hermes Agent feature worktree. The adapter must not know
the thread-attention commands, ledgers, or digest policy. Treat both live
`~/.hermes/plugins/discord-related-threads` and `~/.hermes/hermes-agent` as
deployment targets rather than development sources.

## Rationale

This gives the standalone plugin a reviewable upstream without mixing personal
domain logic into Hermes core or creating a separate repository per small
extension. The monorepo remains directly installable with
`chriskimjj/agent-extensions/plugins/hermes/discord-related-threads`, while the
core patch can follow Hermes's normal contribution and upgrade path.

## Consequences

Changes spanning the feature require two identifiable revisions: one in this
collection for plugin behavior and, until the generic seam is upstream, one in
Hermes Agent. Deployment manifests must pin both. The old local project path is
only a workspace compatibility symlink and is not part of the public source
contract. The plugin currently has no declared open-source license; publishing
it in this repository does not grant permissions beyond applicable law.
