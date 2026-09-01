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

The Hermes plugin keeps its original explicit relationship tool and related-link
footer. Version `1.1.0` also implements an opt-in, metadata-only thread inventory,
acknowledgement, reminder, and bounded daily digest without LLM calls.

```bash
hermes plugins install chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

Thread attention is implemented but defaults to disabled. It is not yet a
supported plugin-only release because its remaining generic Hermes host contract
is still under review in
[NousResearch/hermes-agent#100004](https://github.com/NousResearch/hermes-agent/pull/100004).
Do not enable the development feature on a live profile until the plugin records
an official compatible Hermes floor.

[Open the plugin source and project documents.](plugins/hermes/discord-related-threads/)

## Included extensions

| Kind | Extension | Current boundary | Version | License |
| --- | --- | --- | ---: | --- |
| Skill | [`e`](skills/e/) | Exact `e`/`E` re-explains the active answer without resuming the task | 0.2.0 | MIT |
| Hermes plugin | [`discord-related-threads`](plugins/hermes/discord-related-threads/) | Relationship feature retained; thread attention implemented, default-disabled, awaiting official host contract | 1.1.0-dev | Not declared |

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

GitHub redirects the former `chriskimjj/agent-skills` repository name to this
repository, and the previously published E v0.2.0 raw URL remains reachable.
Do not create a new repository named `agent-skills`, because reusing that name
would replace the redirect.
