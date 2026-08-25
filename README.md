# Agent Skills that solve the moment—not just describe the mechanism.

The first release starts with a concrete interaction failure: an AI answer that does not land.

Without E, the user has to diagnose the confusion and write a better follow-up. **E asks for one letter.**

```text
Confusing answer → `e` → clearer explanation
```

**Designed to be easy to follow, accurate about important limits, and structured to use.**

E restores the missing conceptual links in the current answer without treating `e` as approval to continue the underlying task.

## Why this skill exists

**Origin.** This collection grew from the need to turn useful local Agent Skills into public artifacts that solve a real interaction problem—not merely expose another mechanism.

**The friction.** A skill can sound useful while its actual transformation is buried under features, badges, installation steps, or policy language. It can also look publishable while its exact files, license, privacy boundary, runtime behavior, and installation path remain unverified.

**Who it helps.** It is for people who want small, inspectable Agent Skills whose value is obvious before installation and whose behavior boundaries remain explicit afterward.

**What changes.** Each skill leads with the concrete moment it improves, shows the input-to-outcome transformation, and then earns trust through a separately reviewed manifest, license, safety boundary, and runtime evidence.

## Quick start

The first skill is **E — Explain Again**.

Install E v0.2.0 after the versioned release tag is available:

```bash
hermes skills install https://raw.githubusercontent.com/chriskimjj/agent-skills/e-v0.2.0/skills/e/SKILL.md
```

Ask Hermes for an explanation, then send exactly:

```text
e
```

E rebuilds the immediately preceding answer in clearer language, reconnects missing reasoning, preserves important uncertainty, and stops without resuming the task.

[See why E exists, how its one-letter contract works, and what was verified.](skills/e/)

## Included skills

| Skill | Problem it addresses | Transformation | Version | License | Runtime evidence |
|---|---|---|---:|---|---|
| [`e`](skills/e/) | The answer did not land, but the user cannot yet formulate a better follow-up | Active answer → exact `e`/`E` → easier, accurate, structured explanation with no task resumption | 0.2.0 | MIT | Hermes Agent verified locally; immutable remote clean-install is a release gate |

## Trust and release boundary

Strong positioning does not weaken the evidence boundary:

- A repository or release URL is not treated as proof by itself.
- Public files come from an explicit allowlist and exact manifest.
- Privacy, provenance, links, format, behavior, and installation are checked separately.
- Compatibility is claimed only for runtimes actually tested.
- Tags use a skill prefix such as `e-v0.2.0` because this repository contains multiple skills.
- There is no repository-wide license covering every future skill. Read the `LICENSE` file inside each skill directory.
- A versioned release is created only after the immutable remote commit passes clean-install verification.

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
