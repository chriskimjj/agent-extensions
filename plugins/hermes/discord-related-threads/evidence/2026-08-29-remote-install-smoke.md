# Remote subdirectory install smoke test

- Source revision: `1bb573e4096d325cc83b2d3104da97aeb4c98511`
- Source: `chriskimjj/agent-extensions/plugins/hermes/discord-related-threads`
- Installer mode: immutable `--ref`, `--no-enable`
- Target: fresh temporary `HERMES_HOME`
- Result: Hermes cloned the monorepo, selected the plugin subdirectory, read the
  manifest, and installed it under `plugins/discord-related-threads` without
  enabling it.
- Verification: the installed `__init__.py` and `plugin.yaml` SHA-256 values
  matched [the imported live baseline](2026-08-29-live-baseline.sha256).

No live Hermes profile, gateway, Discord state, or user configuration was
changed by this test.
