---
status: accepted
date: 2026-09-01
supersedes: []
---

# Offer a pinned pre-merge preview without redefining the supported release

## Context

ADR-0004 correctly keeps the supported product to one plugin on an unmodified
official Hermes release. While the required generic host contract remains in
upstream review, however, installing only the public plugin cannot exercise
thread attention. Users need an honest, reproducible way to evaluate both
pieces without mistaking an unmerged fork for the supported release or letting
plugin runtime code silently patch its host.

## Decision

Publish a clearly labelled **pre-merge preview install** beside the plugin. The
helper fetches the exact connector commit from the upstream PR ref, verifies the
Hermes checkout descends from the reviewed base, refuses local changes in files
the connector touches, and applies it on a dedicated Git branch. It installs an
exact public plugin commit into an explicitly supplied non-default
`HERMES_HOME`, leaves the plugin disabled, and runs Plugin Doctor. It never
edits the default `~/.hermes`, configuration, gateway state, or Discord, and it
does not vendor or load a core patch from plugin runtime code.

This is a non-release evaluation path. ADR-0004 remains the release boundary:
official support begins only after the generic contract is merged and the
plugin-only stock-Hermes verification gate passes. The preview pin must fail
closed when the PR ref, base ancestry, changed host files, or Doctor result no
longer matches the recorded evidence.

## Rationale

A pinned external helper makes the real two-part pre-merge requirement visible
and reproducible. It avoids the misleading claim that the plugin alone works
today while keeping temporary host mutation out of the plugin loader and out
of the live profile. A floating fork installer would be easier to type but
could silently install different host code on different days.

## Consequences

Preview users maintain a separate Hermes branch and profile and must treat
merge conflicts as a stop condition. The helper may need a new reviewed pin
when the upstream PR changes. It is deprecated once an official Hermes floor
contains the contract; the normal plugin installer then becomes the only
supported path. No preview run authorizes live activation.
