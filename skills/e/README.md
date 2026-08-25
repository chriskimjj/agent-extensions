# E — Explain Again

**Press E to understand.**

E is a one-character Agent Skill for recovering understanding inside an active AI conversation. Send exactly `e` or `E`; the agent re-explains the immediately preceding answer without treating the message as approval to continue the underlying task.

## Why this skill exists

**Origin.** E was designed for the moment when a user knows an answer did not land but cannot yet formulate a detailed follow-up question.

**The friction.** The user otherwise has to diagnose what they did not understand and write a longer prompt, while a terse reply can be mistaken for consent to continue a task.

**Who it helps.** It helps people who need a clearer explanation within an ongoing AI conversation, especially when technical language or missing conceptual links make the previous answer hard to follow.

**What changes.** Exact `e` or `E` becomes a context-local understanding-recovery command with an explicit read-only boundary: explain the current answer, preserve accuracy and uncertainty, and do not resume the work.

## Quick start

Install the released version in Hermes Agent:

```bash
hermes skills install https://raw.githubusercontent.com/chriskimjj/agent-skills/e-v0.2.0/skills/e/SKILL.md
```

Ask for any explanation, then send:

```text
e
```

Expected behavior: the agent starts with a clearer explanation in the conversation's language, defines necessary technical terms in ordinary language, preserves important conditions and uncertainty, and performs no underlying action.

## Trigger contract

E runs only when the trimmed message is exactly:

```text
e
E
```

It does not trigger for `e?`, `ee`, `/e`, `e 설명해`, or a sentence containing `e`.

## Safety boundary

E is not yes, approval, confirmation, continuation, or authorization. During an E response, the agent must not:

- resume or repeat the underlying task;
- edit files or settings;
- send messages or publish anything;
- purchase or delete anything;
- use tools merely to continue the work;
- aggregate unrelated threads, sessions, or private project history.

A read-only lookup is allowed only when one missing fact is strictly necessary to explain the existing answer accurately, and it must not advance the underlying task.

## Verification evidence

The exact `SKILL.md` in this release has SHA-256:

```text
d0a554566d10f3e74c68307978b6cd5a3597d72874fba38d7303c4eff63f588b
```

Before publication it passed:

- the official Agent Skills validator at inspected revision `69ef37e9424c0a7ea9dd2293b559e43ec8176379`;
- Hermes local quarantine, security scan, isolated install, discovery, prompt load, and cleanup;
- 14 behavior and architecture tests;
- T01–T12 bounded behavior fixtures for both baseline and candidate;
- independent human review of all 24 recorded responses;
- exact candidate/package hash comparison;
- privacy and secret scans with no blocking findings.

One Hermes security scanner caution classified the rule for selecting necessary source context as possible context exfiltration. Human review accepted it as a conservative false positive because E limits itself to the current conversation or thread, forbids unrelated/private context aggregation, and forbids external transmission and task resumption.

After publication, the immutable remote commit must be read back and clean-installed again before the release is called remotely verified.

## Known limitation

In the final bounded sample, the new self-contained E produced 31.0% more response characters than the previous version and passed the mobile-concision proxy in 9 of 11 applicable cases versus 11 of 11 for the baseline. Accuracy, uncertainty, isolation, and safety still passed. This is a future calibration signal, not a claim that every E response will be shorter.

Compatibility is currently evidenced only for Hermes Agent. Other Agent Skills clients are untested.

## Files

```text
e/
├── README.md
├── SKILL.md
└── LICENSE
```

## License

MIT License. See [`LICENSE`](LICENSE).

Copyright © 2026 Chris A. Kim.
