# Agent Rules

For company research, Replica workflow questions, claim scoring, source
selection, replication readiness, or Replica execution, read and follow
`skills/replica-research/SKILL.md` before answering or acting. Treat that Skill
as the authoritative workflow instead of loading the same rules through
team-ai.

A company evaluation request — a company name, URL, or description — runs the
full route by default: both research passes, then `agent-harness-init` on the
completed `research.json`, the Operator/Builder protocol for every selected
claim, sealed bundle evaluation, and `agent-harness-finish`, which writes
`final-results/company-claims.json` for every researched claim. The request
itself approves this full run; stop after pass 2 only when the user asks for
research only. Research with no executable claim still ends with that company
result.

For the implementation step of a company evaluation, or when the user asks to
create or run the multi-claim Replica Agent harness, spawn one dedicated
Replica Agent with `model=gpt-6-astra`,
`reasoning_effort=medium`, and `fork_turns=none`. Give it only the Second JSON path, run directory, canonical
parent identity, and an instruction to follow
`.agents/skills/orchestrate-replica-agents/SKILL.md`. The root may wait for and
report lifecycle results but must not relay Operator/Builder semantic
messages. The Replica Agent itself creates each claim's sibling children with
explicit `gpt-6-astra` Operator (`reasoning_effort=medium`) and `gpt-5.6-terra`
Builder (`reasoning_effort=high`) model requests. Specify both efforts explicitly
when spawning the pair. For actual implementation, create one pair for every
selected function and activate all pairs concurrently: N functions mean N pairs.
Do not wait for another feature to finish before activating the next pair.

When a company evaluation reaches a ready harness, or the user asks to run the
direct Operator/Builder protocol on one, resume the same dedicated Replica Agent and existing child
identities instead of spawning a new pair. Give it only the harness registry
path and an instruction to follow
`.agents/skills/run-replica-agent-protocol/SKILL.md`. The root and Replica
Agent may send identity-only activation controls and receive control metadata,
but neither may relay, summarize, rewrite, or persist the semantic instruction
or feedback.

The JSON-only implementation Skill is a separate route for a standalone
`replica-second-pass-result/v1` JSON, not for company research:

- Use `.agents/skills/build-replica-operator/SKILL.md` when that JSON alone can
  satisfy the full contract without file, network, or external-tool access.

Only that JSON-only route excludes contracts that require PDF, XLSX, CSV,
image, OCR, retrieval, network, or external API access. The bundle route runs
such contracts, so never narrow a company claim to a JSON demo because it
needs files or search.

These are direct implementation routes even if the Skills are not shown in the
current session's selector. Never route this work through a registered
Operator, the removed `replicate` command, an external generator command, or
an API model generator.

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
Replica workflow questions covered by the Skill are exempt unless the user
explicitly asks about meeting or decision history.

Treat "회의 때 뭐 나왔지", "지난번에 뭐라고 했지", "기억 가져와줘",
"결정 내용이 뭐야", and "이 아이디어로 만들어줘" as project knowledge
recall requests.

Before changing product code under `src/` or `tests/`, run:

```bash
team-ai context --mode implementation "USER_REQUEST"
```

Only use harness context when the user explicitly asks about team-ai harness,
CLI behavior, guard, verify, memory schema, AGENTS.md mechanics, project.yaml
scope rules, runtime, or compiled snapshots.

- `.team-ai` is a Git-ignored local link to the project state managed by
  `../team-ai/projects/replica-mvp`; never stage or commit it.
- Active project is defined in `.team-ai/project.yaml`.
- Raw materials and meeting notes live under `.team-ai/sources/`.
- Approved durable memories live under `.team-ai/memory/`.
- Product code belongs under `src/`; tests belong under `tests/`.
- Before finalizing implementation changes, run `team-ai guard`.
