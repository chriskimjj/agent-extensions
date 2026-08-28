# When the answer doesn’t land, press E.

You shouldn’t need to understand your confusion<br>
before you can ask for a clearer explanation.

No prompt engineering.<br>
No carefully written follow-up.<br>
No accidental “yes.”

Just send:

```text
e
```

**E re-explains the answer—and stops there.**

### Before → `e` → After

**Before:** The answer does not land.<br>
**Input:** `e`<br>
**After:** The explanation is rebuilt—clearer, accurate about important limits, and structured to follow.

E does not merely shorten text. It aims to make the answer:

- **Easy enough to follow.** Necessary technical terms are explained in ordinary language.
- **Accurate enough to trust.** Conditions, exceptions, uncertainty, and trade-offs stay intact.
- **Structured enough to use.** Related ideas are connected as a process instead of left as isolated definitions.

**You do not have to diagnose your own confusion first.** E recovers the immediately preceding answer from the current conversation, explains it again, and performs no underlying action.

## Why this skill exists

**Origin.** E was designed for the moment when a user knows an AI answer did not land but cannot yet formulate a detailed follow-up question.

**The friction.** Without E, the user must first work out what they failed to understand, translate that confusion into a better prompt, and hope a terse reply is not mistaken for consent to continue the task.

**Who it helps.** It helps people who need a clearer explanation inside an active AI conversation—especially when technical language, compressed reasoning, or a missing conceptual link makes the previous answer hard to follow.

**What changes.** Exact `e` or `E` becomes a context-local understanding-recovery command: make the current answer easier, accurate, and structured; preserve its important limits; and stop without resuming the work.

## Quick start

Install E v0.2.0 after the versioned release tag is available:

```bash
hermes skills install https://raw.githubusercontent.com/chriskimjj/agent-extensions/e-v0.2.0/skills/e/SKILL.md
```

Ask for any explanation, then send exactly:

```text
e
```

Expected behavior: the agent begins with the clearer explanation in the conversation’s language, defines necessary technical terms in ordinary language, reconnects the missing reasoning, preserves important uncertainty, and performs no underlying action.

## Why one letter is different

“Explain that more simply” works when you already know what to ask. E is for the earlier moment: you only know that the answer did not land.

Its contract is deliberately narrow:

- **Exact-token:** only trimmed `e` or `E` triggers it.
- **Context-local:** it uses the immediately preceding answer or clearly active topic—not unrelated sessions or private project history.
- **Read-only:** it explains; it does not continue.
- **Self-contained:** E owns the complete behavior instead of routing through another explanation skill.

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

A versioned release is created only after the exact immutable remote commit is read back and clean-installed again.

One Hermes security scanner caution classified the rule for selecting necessary source context as possible context exfiltration. Human review accepted it as a conservative false positive because E limits itself to the current conversation or thread, forbids unrelated/private context aggregation, and forbids external transmission and task resumption.

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
