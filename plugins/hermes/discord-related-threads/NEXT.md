# Next gate

## Stock-Hermes plugin compatibility refactor

The next gate is to turn the verified two-source development proof into one
installable plugin that runs on an unmodified official Hermes checkout. The
local prototype core branch is input to this analysis, not a release artifact.

Execution order:

1. Preserve the now-passing stock lifecycle path: Discord connect uses
   `register_platform_handler`, background work uses supervised tasks, unload
   removes native listeners, and bot-authored native messages provide live
   participation/delivery observations.
2. Isolate the smallest irreducible host contracts for pre-coalescing control
   classification, reuse of the normal authorization decision, and message-ID
   history exclusion, plus the public Discord participation snapshot, metadata
   lookup and delivery-target validation used for backfill. Specify them
   generically and prepare focused upstream Hermes tests; do not include
   thread-attention commands or policy in core.
3. Preserve the explicit hook-contract probe now present alongside the adapter
   method probe, and add the small generic `PluginContext.supports_hook` host
   API it consumes. An unsupported Hermes host must keep the existing relation
   feature intact but refuse thread-attention activation with an actionable
   local error instead of silently weakening guarantees.
4. Install the plugin from its Git subdirectory into a temporary profile backed
   by an unmodified official Hermes revision. Verify discovery, additive DB
   migration, default-disabled behavior, command isolation, resumable backfill,
   durable delivery, and digest creation with a fake Discord boundary.
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
