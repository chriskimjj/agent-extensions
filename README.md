# Agent Skills by Chris A. Kim

A collection of independently reviewed Agent Skills. Each skill is released as its own publication unit with its own provenance and license disposition.

## Why this skill exists

**Origin.** This collection grew from the need to turn useful local Agent Skills into public artifacts without copying private workspaces or treating a repository push as proof of quality.

**The friction.** A skill can look publishable while its exact files, license, privacy boundary, runtime behavior, or installation path are still unverified.

**Who it helps.** It is for people who want small, inspectable Agent Skills with explicit behavior boundaries and evidence-bounded compatibility claims.

**What changes.** Each published skill is separated into `skills/<name>/`, carries its own license and provenance disposition, and is released from an exact reviewed manifest rather than an entire private source tree.

## Quick start

The first skill in the collection is **E**, a one-character understanding-recovery command for AI conversations.

After release `e-v0.2.0` is published, install it in Hermes Agent with:

```bash
hermes skills install https://raw.githubusercontent.com/chriskimjj/agent-skills/e-v0.2.0/skills/e/SKILL.md
```

Then ask Hermes for an explanation and send exactly:

```text
e
```

E re-explains the immediately preceding answer without treating `e` as approval to continue or perform the underlying task.

## Included skills

| Skill | Purpose | Version | License | Runtime evidence |
|---|---|---:|---|---|
| [`e`](skills/e/) | Re-explain the active answer with one character while remaining read-only | 0.2.0 | MIT | Hermes Agent verified locally; remote immutable-revision verification follows publication |

## Trust and release boundary

- A repository or release URL is not treated as proof by itself.
- Public files come from an explicit allowlist and exact manifest.
- Privacy, provenance, links, format, behavior, and installation evidence are checked separately.
- Compatibility is claimed only for runtimes actually tested.
- Tags use a skill prefix such as `e-v0.2.0` because this repository contains multiple skills.
- There is no repository-wide license covering every future skill. Read the `LICENSE` file inside each skill directory.

## Repository structure

```text
agent-skills/
├── README.md
└── skills/
    └── e/
        ├── README.md
        ├── SKILL.md
        └── LICENSE
```

## Maintenance

Each update requires a fresh manifest, review, approval, remote read-back, and clean-install check. Prior acceptance does not authorize later bytes.
