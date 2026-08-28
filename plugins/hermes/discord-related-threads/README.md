# discord-related-threads

A standalone user plugin for `NousResearch/hermes-agent`.

The imported `1.0.0` code preserves the existing behavior: it stores explicit
relationships between Discord work threads and can append related-thread links
to Hermes final answers. This directory also owns the design and future
implementation of **Hermes Discord Thread Attention**—automatic thread
inventory, explicit acknowledgement and reminders, and a bounded review digest.

The thread-attention feature is specified but not implemented or enabled yet.
Installing this baseline does not create the planned inventory or digest.

## Install from the collection

Hermes supports installing a plugin from a repository subdirectory:

```bash
hermes plugins install chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

The live profile path `~/.hermes/plugins/discord-related-threads` remains a
deployment target. Development and review happen in this Git directory.

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
| What is the next implementation gate? | [NEXT.md](NEXT.md) |
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
