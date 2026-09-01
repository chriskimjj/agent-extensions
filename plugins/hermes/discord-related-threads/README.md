# discord-related-threads

[![Discord related threads CI](https://github.com/chriskimjj/agent-extensions/actions/workflows/discord-related-threads.yml/badge.svg)](https://github.com/chriskimjj/agent-extensions/actions/workflows/discord-related-threads.yml)

A standalone user plugin for `NousResearch/hermes-agent`.
Distributed under the [MIT License](LICENSE).

Version `1.1.0` preserves the original explicit related-thread tool and footer,
and implements **Hermes Discord Thread Attention**: automatic metadata-only
inventory, acknowledgement and reminders, durable delivery, and a bounded daily
review digest. Recognized control commands are handled before agent dispatch and
do not call an LLM.

Thread attention is opt-in and defaults to disabled. Installing the code alone
does not collect threads or send Discord messages. The current `1.1.0`
development proof now uses stock lifecycle APIs. Its remaining generic host
contracts are proposed in
[NousResearch/hermes-agent#100004](https://github.com/NousResearch/hermes-agent/pull/100004),
but an open PR is not an official compatibility floor. It is therefore not yet
the plugin-only release.
The supported release target is one plugin on an unmodified official Hermes
version, plus a configured Discord channel ID; see
[ARCHITECTURE.md](ARCHITECTURE.md) and [NEXT.md](NEXT.md).

There are therefore two deliberately different paths:

| Path | Hermes host | Status |
| --- | --- | --- |
| Stock-Hermes plugin install | First official Hermes release containing the required contract | Intended supported release; not available yet |
| Pinned pre-merge preview | A dedicated Hermes Git branch with the exact reviewed PR connector | Available for non-live evaluation only |

## Install from the collection

Hermes supports installing a plugin from a repository subdirectory:

```bash
hermes plugins install chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

This is the intended final installation command. Do not enable thread attention
from the current development revision until [STATUS.md](STATUS.md) records a
stock-Hermes compatibility floor and a passing plugin-only install smoke. The
live profile path `~/.hermes/plugins/discord-related-threads` remains a
deployment target; development and review happen in this Git directory.

A Hermes core update preserves that separately installed plugin directory, but
does not update the plugin's own code. The current monorepo-subdirectory install
also needs a deliberate pinned reinstall instead of `hermes plugins update`;
the verified distinction and safe procedure live in
[DEPLOYMENT.md](DEPLOYMENT.md#hermes와-플러그인-업데이트의-구분).

## Evaluate the complete feature before upstream merge

The plugin repository includes a fail-closed preview helper for people who need
to evaluate both required pieces now. It fetches the exact connector commit
from the upstream PR, applies it on a dedicated Hermes branch, installs the
current public plugin commit into a separately supplied preview profile, and
runs Plugin Doctor. It refuses the default live `~/.hermes`, leaves the plugin
disabled, and never starts a gateway or writes to Discord.

Run it first without `--apply` to inspect the resolved plan:

```bash
python plugins/hermes/discord-related-threads/scripts/install_preview.py \
  --hermes-root /absolute/path/to/hermes-agent \
  --hermes-home /absolute/path/to/hermes-preview
```

Repeat the same command with `--apply` only after reviewing the plan. Exact
preconditions, effects, rollback, and the optional `--hermes-command` override
are authoritative in
[DEPLOYMENT.md](DEPLOYMENT.md#병합-전-프리뷰-설치비릴리스).

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
[ADR-0004: one plugin for stock Hermes](docs/adr/0004-stock-hermes-plugin-distribution.md),
with
[ADR-0005: pinned pre-merge preview](docs/adr/0005-pinned-pre-merge-preview.md)
covering the temporary evaluation path.
ADR-0004 keeps this extensions monorepo as the source while rejecting a
maintained Hermes fork or coordinated core-patch release. The earlier
manual-stamp-only design is
kept as a local historical record in
[legacy Hermes Lab ADR-0007](docs/adr/legacy-hermes-lab-0007-explicit-stamps.md).

Exact command characters, Korean keyboard aliases, and deterministic
confirmation responses remain in [SPEC.md](SPEC.md).
