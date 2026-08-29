# discord-related-threads

A standalone user plugin for `NousResearch/hermes-agent`.

Version `1.1.0` preserves the original explicit related-thread tool and footer,
and implements **Hermes Discord Thread Attention**: automatic metadata-only
inventory, acknowledgement and reminders, durable delivery, and a bounded daily
review digest. Recognized control commands are handled before agent dispatch and
do not call an LLM.

Thread attention is opt-in and defaults to disabled. Installing the code alone
does not collect threads or send Discord messages. Enabling it also requires the
paired generic Hermes gateway boundaries described in
[ARCHITECTURE.md](ARCHITECTURE.md) and a configured Discord channel ID; use
[DEPLOYMENT.md](DEPLOYMENT.md) for installation and rollback.

## Install from the collection

Hermes supports installing a plugin from a repository subdirectory:

```bash
hermes plugins install chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

This command installs only the plugin portion. Do not enable thread attention
until the matching Hermes core revision is installed and validated. The live
profile path `~/.hermes/plugins/discord-related-threads` remains a deployment
target; development and review happen in this Git directory.

The exact command grammar, feature configuration, and digest behavior live in
[SPEC.md](SPEC.md). The default review-channel name is `#hermes-review`, but the
runtime routes only by the configured `digest_channel_id` and never creates or
guesses a channel.

## Document map

Each fact has one authoritative document.

| Question | Authority |
| --- | --- |
| What and why are we building? | [PRODUCT.md](PRODUCT.md) |
| What do the domain terms mean? | [CONTEXT.md](CONTEXT.md) |
| What are the commands and behaviors? | [SPEC.md](SPEC.md) |
| What are the components and boundaries? | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Why were costly choices made? | [docs/adr/](docs/adr/) |
| How is it installed and rolled back? | [DEPLOYMENT.md](DEPLOYMENT.md) |
| What has actually been observed? | [STATUS.md](STATUS.md) |
| What is the next delivery gate? | [NEXT.md](NEXT.md) |
| Where does reproducible verification go? | [evidence/](evidence/) |

## Current decisions

The active architectural decisions are
[ADR-0001: automatic inventory with optional reminders](docs/adr/0001-auto-inventory-with-optional-reminders.md)
and
[ADR-0003: standalone plugin source in the extensions monorepo](docs/adr/0003-standalone-plugin-source-in-extensions-monorepo.md).
ADR-0003 supersedes ADR-0002's former source-placement decision while retaining
the generic Hermes history boundary. The earlier manual-stamp-only design is
kept as a local historical record in
[legacy Hermes Lab ADR-0007](docs/adr/legacy-hermes-lab-0007-explicit-stamps.md).

Exact command characters, Korean keyboard aliases, and deterministic
confirmation responses remain in [SPEC.md](SPEC.md).
