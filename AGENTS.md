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

## Codex-operated Replica workflow

When the user gives a company name, URL, or short company description and asks
to run the Replica workflow, the current Codex task is the orchestrator.

- Do not ask the user for model commands, API keys, specs, tests, or a target
  capability when those can be derived from public research.
- Do not make this repository call Codex or a model API unless the user
  explicitly requests a standalone automated runner.
- Accept a company name or public URL as the minimum input. Find the missing
  identifier through web search when possible.
- Research current public sources, preferring the company's own materials and
  at least one independent source when available. Record source URLs and only
  claims actually supported by them.
- Select exactly one publicly observable, text-in/text-out AI capability with
  a bounded contract and independently testable behavior.
- Create `work/<company-slug>/`, initialize the project, replace every
  `CHANGE_ME` in `evidence.json`, `spec.json`, and `tests.json`, then build
  `replica.json`.
- Run the generated cases in the current task. Keep candidate generation and
  judging as separate passes. When sub-agent execution is available and useful,
  use bounded Replica and Judge workers; otherwise label the Judge as
  same-session rather than independent.
- Write `results.jsonl`, generate `report.md`, run `team-ai guard`, and return
  the selected capability, evidence level, pass count, limitations, and links
  to the artifacts.
