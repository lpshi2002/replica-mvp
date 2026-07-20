# Agent Rules

Before answering questions about prior meetings, memories, decisions, project
direction, or implementation direction, run:

```bash
team-ai context "USER_REQUEST"
```

For broad project-wide questions about the current goal, status, next actions,
or unresolved decisions, decide the meaning at the agent layer and run:

```bash
team-ai context --current-state "USER_REQUEST"
```

Use ordinary context search for questions about a specific named topic.

Before changing product code under `src/` or `tests/`, run:

```bash
team-ai context --mode implementation "USER_REQUEST"
```

Treat "회의 때 뭐 나왔지", "지난번에 뭐라고 했지", "기억 가져와줘",
"결정 내용이 뭐야", and "이 아이디어로 만들어줘" as project knowledge
recall requests.

Only use harness context when the user explicitly asks about team-ai harness,
CLI behavior, guard, verify, memory schema, AGENTS.md mechanics, project.yaml
scope rules, runtime, or compiled snapshots.

- Active project is defined in `.team-ai/project.yaml`.
- Raw materials and meeting notes live under `.team-ai/sources/`.
- Approved durable memories live under `.team-ai/memory/`.
- Product code belongs under `src/`; tests belong under `tests/`.
- Before finalizing implementation changes, run `team-ai guard`.
