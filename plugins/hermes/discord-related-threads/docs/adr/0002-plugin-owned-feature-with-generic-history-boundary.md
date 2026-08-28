---
status: superseded
date: 2026-08-28
superseded_by:
  - 0003-standalone-plugin-source-in-extensions-monorepo.md
---

# Keep the feature plugin-owned behind a generic Discord history boundary

Superseded by
[ADR-0003](0003-standalone-plugin-source-in-extensions-monorepo.md),
which retains the generic history boundary and moves the standalone plugin's
authoritative source out of the Hermes Agent core worktree.

## Context

The existing `pre_gateway_dispatch` hook can intercept a control command before
an agent turn, but Discord also reconstructs model context through missed-message
recovery, recent-channel history, and reply-anchored history. A plugin-only
intercept therefore cannot by itself guarantee that an old human-authored
control command will never re-enter a Hermes session or LLM input.

Putting command-specific parsing and state into the Discord adapter would close
that gap but would couple a personal thread-attention policy to a shared platform
adapter. Reaching into private adapter fields from a live plugin would avoid a
source change at the cost of a brittle monkeypatch that can silently break on a
Hermes upgrade. Development directly in the dirty live installation would also
make review and rollback unreliable.

## Decision

Keep thread-attention domain behavior in `discord-related-threads`: command
parsing, authorization parity, inventory and reminder state, delivery and
history-exclusion ledgers, scheduling, and deterministic message templates.

Widen the Hermes Discord adapter only with a generic, read-only history
exclusion boundary that every path constructing Hermes input applies. The
adapter does not know `!s`, `!r`, `!c`, digest policy, or plugin table shapes;
the plugin supplies the exclusion decision. Do not implement this integration
by monkeypatching private adapter members.

Keep the human-readable contract in this project. Keep authoritative code and
tests in a dedicated Hermes Agent Git feature worktree, currently
`feat/discord-predispatch-thread-routing` at
`~/.hermes/worktrees/discord-predispatch-thread-routing`. Treat the live
`~/.hermes/hermes-agent` and `~/.hermes/plugins/discord-related-threads` paths
as deployment targets for a tested, identifiable source revision, not as the
place where development begins.

## Rationale

This preserves the simple plugin ownership the user wants while closing the
non-obvious history-reconstruction path at its actual owner. A generic adapter
boundary follows Hermes's narrow-core guidance and can serve other
non-conversational plugins without embedding this product's vocabulary in the
platform layer. A clean Git worktree makes tests, review, source attribution,
and rollback reproducible while keeping the running installation untouched
during development.

## Consequences

The first version requires a small Hermes Agent source change in addition to
the plugin. Hermes upgrades must preserve or upstream that generic boundary;
the history integration must fail closed for excluded messages if the boundary
is unavailable.

The document contract and implementation live in different locations, so
implementation reviews must check both rather than treating either live path as
the source of truth. Packaging, backup, database-migration, restart, and
rollback steps are defined separately in `DEPLOYMENT.md`.
