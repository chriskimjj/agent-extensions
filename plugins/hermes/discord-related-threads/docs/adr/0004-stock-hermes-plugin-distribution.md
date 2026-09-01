---
status: accepted
date: 2026-09-01
supersedes:
  - 0003-standalone-plugin-source-in-extensions-monorepo.md
---

# Ship one plugin for stock Hermes instead of a maintained Hermes fork

## Context

The development proof kept the feature logic in `discord-related-threads`, but
made deployment depend on a second Hermes Agent revision containing seven
prototype gateway boundaries. That proved the behavior and exposed the host
capabilities the plugin needs, but it would make every user install and upgrade
two coordinated source trees. Chris wants the feature to be reusable as a
normal Hermes plugin rather than as a personal Hermes fork.

Stock Hermes already provides public plugin surfaces for pre-dispatch policy,
native platform handlers, supervised background tasks, unload cleanup,
normalized platform events, and capability-gated platform actions. It does not
yet guarantee every strict requirement of this feature: an exact control
message must be separated before Discord text coalescing, consumed only after
the normal Hermes authorization decision, and excluded by message ID from all
later history reconstruction paths.

## Decision

Make `plugins/hermes/discord-related-threads/` the only feature source and the
only installable release artifact. A supported release runs on an unmodified,
official Hermes version and is installed with the normal plugin installer. It
must not require a user-maintained Hermes fork, an install-time core patch, or
replacement of live Hermes source files.

Use documented stock plugin APIs for every capability they cover. If a strict
requirement still needs host support, contribute the smallest generic,
plugin-agnostic contract upstream to Hermes and set the plugin's minimum
supported Hermes contract accordingly. Thread-attention commands, state,
scheduling, templates, and Discord policy never move into Hermes core. Until
the required generic contracts are available in stock Hermes, the new thread
attention feature is not a releasable or live-deployable plugin-only build.

The local `feat/discord-predispatch-thread-routing` branch and commit
`b20695a4cb` remain development evidence only. They may be mined for generic
tests or reduced upstream changes, but they are not a release dependency and
do not need a personal remote fork.

## Rationale

One plugin plus a declared stock-Hermes compatibility floor gives users a
normal install and upgrade path. A maintained fork or bundled patch would hide
an ongoing two-product support burden. Adapter monkeypatching, duplicated auth
rules, deleting Discord commands, or silently weakening history isolation
would make installation look simpler while losing the guarantees already
accepted in the product contract.

## Consequences

The current `1.1.0` development proof must be refactored away from its
prototype-only hooks and adapter assumptions before release. The next gate is
replacement of covered boundaries with documented plugin APIs and isolation of
the smallest remaining upstream contracts. Deployment manifests pin one plugin
revision and a compatible official Hermes version, not a second core commit.
Live activation remains blocked until a temporary-profile test proves that the
official Hermes checkout stays unmodified and all command/history guarantees
still hold.
