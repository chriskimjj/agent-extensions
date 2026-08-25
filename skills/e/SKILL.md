---
name: e
description: Use when the user sends exactly `e` or `E`; re-explain the immediately preceding answer or active topic with no assumed background knowledge while remaining read-only and never resuming the underlying task.
metadata:
  hermes:
    version: 0.2.0
    created_by: agent
    tags:
      - explanation
      - plain-language
      - context-callback
      - mobile
      - safety
---

# E — Explain Again

## Overview

`E` is a self-contained, read-only, context-local understanding-recovery command. When the user sends one letter, it re-explains the immediately preceding answer or active topic with no assumed background knowledge.

This skill owns the complete E behavior: exact trigger detection, target recovery, explanation quality, output language, and the no-action safety boundary. Do not route E through another explanation or callback skill.

## Exact Trigger

Load and execute only when the user's trimmed message is exactly:

```text
e
E
```

Do not trigger for `e?`, `ee`, `/e`, `e 설명해`, a sentence containing `e`, or any other extra character. If the exact-token gate fails, stop applying this skill and process the message normally.

## Target Recovery

Choose one target in this order:

1. The immediately preceding substantive assistant answer in the current conversation or thread.
2. If that answer depends on a user-provided question, source, image, or quotation, include only the source context necessary to explain the answer accurately.
3. If no preceding assistant answer exists, use the most recent clearly active topic in the current conversation or thread.
4. If no target exists or more than one target is equally plausible, ask one short clarification in the language of the current conversation instead of guessing.

Stay inside the current conversation or thread. Do not aggregate sibling threads, unrelated sessions, global project history, or private context merely to make the response appear complete.

## Explanation Contract

Write in the user's language or the language of the current conversation unless the user has requested another language.

The response must:

1. Begin with the direct explanation, not a meta-introduction.
2. Assume no background knowledge. Supply the missing conceptual links needed to follow the answer.
3. Keep every necessary technical term accurate. At first mention, give the technical term, explain it immediately in ordinary language, and state its role in this context.
4. Connect related concepts as a process or causal flow when that is clearer than isolated definitions.
5. Use a short analogy only when it materially improves understanding; never let the analogy replace the real concept.
6. Give one concrete example when the concept would otherwise remain abstract.
7. Preserve important conditions, exceptions, limits, trade-offs, and uncertainty. Simpler must not mean less true.
8. Respect an explicitly requested audience, format, language, and length when compatible with accurate explanation.
9. When the preceding answer is already simple, shorten or restructure it rather than paraphrasing every sentence.
10. End when the concept is understandable. Do not add a quiz, recap, unsolicited next steps, or task-completion Coda.

Use natural paragraphs by default. Add large-unit headings only when the explanation is genuinely complex. Keep the response concise enough for mobile reading without omitting a link the reader needs.

## Read-Only and No-Resumption Boundary

`E` explains existing context. **E is not yes, approval, confirmation, continuation, or authorization.**

An E response:

- must not approve a recommendation or decision;
- must not resume, repeat, or continue the underlying task;
- must not invoke tools or perform a new lookup merely to continue the work;
- must not edit files, messages, todo items, settings, repositories, or external systems;
- must not purchase or send anything;
- must not publish or release anything;
- must not delete anything;
- must not configure or deploy anything;
- must not otherwise create side effects;
- must not invent missing context or turn uncertainty into certainty.

A read-only lookup is allowed only when one missing fact is strictly necessary to explain the existing answer accurately. It must not advance the underlying task.

### Canonical Safety Example

```text
Assistant: I recommend deleting the obsolete files. Shall I proceed?
User: e
```

Explain why deletion was recommended, what would change, and what the risks are. Do not delete anything and do not treat `e` as consent.

## Verification Checklist

Before replying, verify:

- [ ] The trimmed message is exactly `e` or `E`.
- [ ] The target comes only from the current conversation or thread.
- [ ] The answer uses the user's language or the language of the current conversation.
- [ ] A reader with no assumed background knowledge can follow the explanation.
- [ ] Necessary technical terms remain accurate and are explained at first mention.
- [ ] Conditions, exceptions, limits, and uncertainty are preserved.
- [ ] No underlying task, tool call, approval, or side effect was resumed.
- [ ] The answer is concise and mobile-readable.
