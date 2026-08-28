---
status: accepted
date: 2026-08-28
supersedes:
  - legacy-hermes-lab-0007-explicit-stamps.md
---

# Auto-inventory Hermes threads and keep reminders optional

## Context

The primary risk is not only forgetting a thread that Chris has already seen.
It is failing to notice a Hermes work thread before Discord removes it from the
normal channel list. The previous opt-in-only design required visiting a thread
before stamping it, so it could not cover the very threads Chris had never
discovered. Posting an arbitrary prompt also helps only after discovery and
usually creates an agent turn, token usage, and transcript noise. Discord does
not expose a supported bot event proving that a particular user merely opened
or read a thread.

## Decision

Use two distinct layers. Automatically inventory every Discord thread that
Hermes creates or participates in, without requiring a user command. Treat
observable owner interaction or a future explicit acknowledgement as a proxy
for having noticed it, without claiming true read status. Separately, allow
Chris to schedule optional reminders for threads already seen.

Merge automatic-discovery candidates and explicit-reminder candidates into the
bounded daily digest sent to a configured Discord channel. Preserve the agreed
maximum of ten links plus an undisplayed remainder count, fair rotation,
default 09:00 Asia/Seoul schedule, and at-least-once delivery. Let source
threads archive normally and do not post keepalive messages into them.

Control commands must be intercepted before agent dispatch and mutate local
state only after authorization. Their exact prefix, aliases, and response UX
are reversible specification choices defined in `SPEC.md`, not part of this
ADR. The former `!t` and `!done` examples are not the current command contract.

## Rationale

Automatic inventory closes the discovery gap while the bounded digest prevents
a complete thread inventory from becoming a new source of noise. Keeping
explicit reminders separate preserves a precise statement of user intent for
known open loops. Reusing Hermes's persistent thread participation records,
Discord recovery enumeration, existing plugin, and profile-local SQLite avoids
a second bot or a keepalive daemon.

## Consequences

The inventory may include threads Chris has read without interacting with,
because read state is not observable to the bot. Acknowledgement and closure
therefore need a low-friction control surface. Automatic-candidate timing,
deduplication, re-exposure, and allocation between the two candidate classes
and the initial historical-backfill policy are reversible choices maintained
in `SPEC.md`. Command vocabulary is also maintained outside this ADR in
`SPEC.md`. Discord archive or permission failures must be reported as state
rather than silently dropping an inventoried thread.
