# Agent Extensions

Small, inspectable extensions for agent runtimes: reusable **skills** and
runtime **plugins** live in separate top-level collections.

```text
agent-extensions/
├── skills/
│   └── e/
└── plugins/
    └── hermes/
        └── discord-related-threads/
```

## Skills

### E — Explain Again

When an answer does not land, the user can send exactly `e` or `E` instead of
having to diagnose the confusion and write a better follow-up.

```text
Confusing answer → `e` → clearer explanation
```

Install E v0.2.0:

```bash
hermes skills install https://raw.githubusercontent.com/chriskimjj/agent-extensions/e-v0.2.0/skills/e/SKILL.md
```

[Read the contract, safety boundary, and verification notes.](skills/e/)

## Plugins

### Hermes: discord-related-threads

The existing Hermes plugin registers explicit relationships between Discord
work threads and appends related-thread links to final answers. Its directory
also owns the accepted design for the planned thread-inventory, acknowledgement,
reminder, and bounded-digest feature.

```bash
hermes plugins install chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

The imported `1.0.0` baseline contains the existing relationship behavior.
The thread-attention feature described in its project documents is not yet
implemented or enabled.

[Open the plugin source and project documents.](plugins/hermes/discord-related-threads/)

## Included extensions

| Kind | Extension | Current boundary | Version | License |
| --- | --- | --- | ---: | --- |
| Skill | [`e`](skills/e/) | Exact `e`/`E` re-explains the active answer without resuming the task | 0.2.0 | MIT |
| Hermes plugin | [`discord-related-threads`](plugins/hermes/discord-related-threads/) | Existing relationship feature imported; thread-attention feature specified but not implemented | 1.0.0 | Not declared |

## Trust and release boundary

- Each extension keeps its own manifest, documentation, evidence, and license.
- There is no repository-wide license covering every extension.
- Compatibility is claimed only for runtimes actually tested.
- Version tags use an extension prefix, such as `e-v0.2.0`.
- Live runtime directories are deployment targets, not development sources.
- A versioned release is created only after its immutable revision passes the
  extension's clean-install checks.

## Maintenance

Changes are reviewed and verified per extension. Prior acceptance of one
extension or release does not authorize later bytes or a different extension.
