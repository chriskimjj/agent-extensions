# Architecture decision records

Only choices that are costly to reverse or operationally significant belong
here. Active records use the compact status, context, decision, rationale, and
consequences format; superseded records remain for history.

## Active

- [ADR-0001: Auto-inventory Hermes threads and keep reminders optional](0001-auto-inventory-with-optional-reminders.md)
- [ADR-0004: Ship one plugin for stock Hermes instead of a maintained Hermes fork](0004-stock-hermes-plugin-distribution.md)
- [ADR-0005: Offer a pinned pre-merge preview without redefining the supported release](0005-pinned-pre-merge-preview.md)

## Superseded history

- [ADR-0002: Keep the feature plugin-owned behind a generic Discord history boundary](0002-plugin-owned-feature-with-generic-history-boundary.md)
  was replaced by ADR-0003 when source ownership moved to the extensions
  collection.
- [ADR-0003: Keep standalone plugin source in the extensions monorepo](0003-standalone-plugin-source-in-extensions-monorepo.md)
  was replaced by ADR-0004 when coordinated core-patch deployment was rejected
  in favor of one plugin on an official stock-Hermes compatibility floor.
- [Legacy Hermes Lab ADR-0007: explicit pre-dispatch stamps](legacy-hermes-lab-0007-explicit-stamps.md)
  was replaced by ADR-0001 when automatic discovery became the primary need.

Runtime source ownership, existing-database compatibility, long-running
scheduling, and cross-channel expansion may justify future ADRs. Reversible
command aliases and reaction text belong in [SPEC.md](../../SPEC.md).
