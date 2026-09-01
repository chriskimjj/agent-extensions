# Next gate

## Upstream contract merge and official-host verification

The minimum generic host contract has been implemented and proposed in
[NousResearch/hermes-agent#100004](https://github.com/NousResearch/hermes-agent/pull/100004).
The next gate is an upstream merge followed by plugin-only verification against
the first unmodified official Hermes revision that contains that contract. The
PR fork and branch are contribution transport, not release artifacts.

The repository also exposes a pinned, non-live pre-merge preview helper so the
real two-part requirement can be reproduced without hand-patching. Passing that
preview is evidence for the candidate only; it does not satisfy or replace this
official-host gate.

Execution order:

1. Track PR CI and review. Rebase on official `main` as needed, keep the core
   change generic, and adapt the plugin's thin integration layer if maintainers
   change a contract name or payload without weakening the strict guarantees.
2. Do not declare the PR branch, personal fork, or unmerged commit as a supported
   Hermes floor. After merge, record the first official commit/version that
   exposes every probed hook and Discord adapter method.
3. Install a pinned plugin commit from its Git subdirectory into a temporary
   profile backed by that unmodified official Hermes revision. Verify discovery,
   additive DB migration, default-disabled behavior, command isolation,
   resumable backfill,
   durable delivery, and digest creation with a fake Discord boundary.
4. Verify separately that a Hermes core update preserves the installed plugin
   and state. Treat plugin code refresh as a separate operation: the current
   subdirectory installer drops `.git`, so use the pinned reinstall procedure in
   `DEPLOYMENT.md` until an updater improvement or root-repository mirror is
   explicitly adopted.
5. Record the supported official Hermes contract/revision and sanitized results
   in `evidence/`.

Gate conditions:

- The feature source, tests, and release manifest live only in this plugin
  directory.
- Installing or rolling back the feature does not patch, replace, or require a
  personal fork of Hermes source files.
- Every strict command and history guarantee has a passing behavior test on the
  declared official Hermes compatibility floor.
- The plugin fails activation clearly when a required host contract is absent.
- The existing relation link/list/unlink behavior and default-disabled posture
  still pass in a temporary profile.
- Actual channel IDs, user IDs, tokens, and message bodies are absent from Git
  and evidence.
- Live files, databases, gateway processes, and Discord remain unchanged.

## Live transition gate

Passing the non-live gate does not authorize installation. Only after separate
live-deployment approval may [DEPLOYMENT.md](DEPLOYMENT.md) be used to back up
the profile, install the single plugin artifact, select or create the suggested
`#hermes-review` channel, set its exact `digest_channel_id`, activate the
feature, run Discord smoke checks, and verify rollback.
