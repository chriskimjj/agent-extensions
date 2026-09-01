# Hermes Agent plugins

Standalone user plugins for `NousResearch/hermes-agent`. Each plugin directory
is directly installable from this monorepo because Hermes accepts a repository
subdirectory in the plugin identifier.

| Plugin | Status |
| --- | --- |
| [`discord-related-threads`](discord-related-threads/) | Relationship feature retained; thread attention implemented and default-disabled while its generic upstream host contract is reviewed |

```bash
hermes plugins install chriskimjj/agent-extensions/plugins/hermes/discord-related-threads
```

Installation alone does not activate thread attention. Its current development
revision requires the unmerged generic host contract in
[NousResearch/hermes-agent#100004](https://github.com/NousResearch/hermes-agent/pull/100004);
see the plugin's `STATUS.md` before enabling it.
