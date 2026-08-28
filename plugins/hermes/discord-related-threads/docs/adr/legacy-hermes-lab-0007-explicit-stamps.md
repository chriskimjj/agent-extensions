---
status: superseded
date: 2026-08-28
supersedes: []
superseded_by:
  - 0001-auto-inventory-with-optional-reminders.md
---

# Track Discord thread attention with explicit pre-dispatch stamps

Superseded by
[ADR-0001: Auto-inventory Hermes threads and keep reminders optional](0001-auto-inventory-with-optional-reminders.md).
This record remains as the history of the earlier opt-in-only design.

## Context

Discord auto-archives inactive threads and removes them from the normal channel
list without deleting their messages. With many Hermes work threads, keeping
every thread active or listing every stale thread in a digest would replace the
visibility problem with noise. Hermes also needs to distinguish durable work
that Chris intends to revisit from disposable conversation without asking an
LLM to infer that intent on every message.

## Decision

Allow Discord threads to archive normally and keep attention state in a
separate, durable local ledger. Threads are untracked by default; Chris opts a
thread into the ledger only by posting an exact, namespaced stamp such as
`!t 3d`, and removes it with `!done`. Do not bulk-stamp historical threads or
send periodic keepalive prompts.

Implement stamps in the existing `discord-related-threads` user plugin using
Hermes's `pre_gateway_dispatch` hook. For a matching Discord thread message,
the plugin must first apply the normal Hermes authorization decision, then
write the server/thread identity, state, review time, and update time to its
profile-local SQLite store and return `{"action": "skip"}`. The stamp must not
enter agent dispatch, create a model turn, or require a model-visible tool.
Hermes's existing Discord processing lifecycle supplies the success reaction.
Automation must run through the Hermes bot account, never through an automated
normal Discord user account.

A future review job may surface only ledger entries whose review time is due,
with up to ten actionable links in a configured Discord destination channel.
When more entries are due, it reports the undisplayed remainder as a count. It
must not use Discord inactivity alone as proof that a thread needs attention,
and it must not reactivate threads merely to keep them visible.

## Rationale

An explicit stamp is a small but reliable statement of human intent. Opt-in
tracking scales better than a complete stale-thread digest, while interception
before agent dispatch avoids immediate LLM cost and transcript pollution.
Reusing the enabled plugin and its SQLite infrastructure avoids a second bot,
daemon, or core Hermes change. Exact `!`-prefixed commands are less likely to
collide with normal prose than `-`-prefixed commands and remain visibly
distinct from Hermes's native slash-command surface.

## Consequences

Chris must stamp an open loop once for it to reappear later; unmarked threads
may archive without reminders. Because `pre_gateway_dispatch` runs before the
gateway's ordinary authorization stage, authorization before every ledger
mutation is a security invariant. A stamp posted while the same thread's agent
turn is active may be queued and applied after that turn rather than
immediately. The short stamp message remains in Discord history even though it
does not trigger an agent turn; filtering or deleting handled stamp messages is
an optional later refinement, not part of the initial implementation.

The implementation contract, current status, and future project-local
decisions are maintained in
[Hermes Discord Thread Attention](../../README.md).
