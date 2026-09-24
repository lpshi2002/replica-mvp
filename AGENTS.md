# Agent Rules

For company research, Replica workflow questions, claim scoring, source
selection, replication readiness, or Replica execution, read and follow
`skills/replica-research/SKILL.md` before answering or acting. Treat that Skill
as the authoritative workflow instead of loading the same rules through
team-ai.

When the user asks to create or run the multi-claim Replica Agent harness,
spawn one dedicated Replica Agent with `model=gpt-6-astra`,
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

When the user explicitly asks to run the direct Operator/Builder protocol on a
ready harness, resume the same dedicated Replica Agent and existing child
identities instead of spawning a new pair. Give it only the harness registry
path and an instruction to follow
`.agents/skills/run-replica-agent-protocol/SKILL.md`. The root and Replica
Agent may send identity-only activation controls and receive control metadata,
but neither may relay, summarize, rewrite, or persist the semantic instruction
or feedback.

When a ready `replica-second-pass-result/v1` JSON has arrived, or the user asks
to implement, repair, test, or run the actual Replica, use the JSON-only
implementation Skill:

- Use `.agents/skills/build-replica-operator/SKILL.md` when JSON input alone can
  satisfy the full contract without file, network, or external-tool access.

The explicit Sol/Terra direct protocol route above is the exception to this
JSON-only implementation route. Do not select it unless the user asks for that
Agent protocol or supplies its ready harness registry.

Contracts that require PDF, XLSX, CSV, image, OCR, retrieval, network, or
external API access are outside the current implementation scope.

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
