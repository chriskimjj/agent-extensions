# Architecture decision records

Only choices that are costly to reverse or operationally significant belong
here. Active records use the compact status, context, decision, rationale, and
consequences format; superseded records remain for history.

## Active

- [ADR-0001: Auto-inventory Hermes threads and keep reminders optional](0001-auto-inventory-with-optional-reminders.md)
- [ADR-0003: Keep standalone plugin source in the extensions monorepo](0003-standalone-plugin-source-in-extensions-monorepo.md)

## Superseded history

- [ADR-0002: Keep the feature plugin-owned behind a generic Discord history boundary](0002-plugin-owned-feature-with-generic-history-boundary.md)
  was replaced by ADR-0003. The generic core boundary remains; only source
  placement changed.
- [Legacy Hermes Lab ADR-0007: explicit pre-dispatch stamps](legacy-hermes-lab-0007-explicit-stamps.md)
  was replaced by ADR-0001 when automatic discovery became the primary need.

Runtime source ownership, existing-database compatibility, long-running
scheduling, and cross-channel expansion may justify future ADRs. Reversible
command aliases and reaction text belong in [SPEC.md](../../SPEC.md).
