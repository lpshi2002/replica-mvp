# Agent Rules (Claude Code)

This repository is driven by two agent runtimes. `AGENTS.md` holds the Codex
routing rules. This file holds the Claude Code rules and is authoritative for a
Claude session. The workflow logic itself is shared; only the runtime
primitives differ.

For company research, Replica workflow questions, claim scoring, source
selection, replication readiness, or Replica execution, read and follow
`skills/replica-research/SKILL.md` before answering or acting. That file is the
shared, runtime-neutral Skill used by both Codex and Claude; treat it as the
authoritative workflow instead of loading the same rules through team-ai. Read
it directly by path — it is not installed under `.claude/skills/`.

When a ready `replica-second-pass-result/v1` JSON has arrived, or the user asks
to implement, repair, test, or run the actual Replica, use the JSON-only
implementation Skill:

- Use `.claude/skills/build-replica-operator/SKILL.md` when JSON input alone can
  satisfy the full contract without file, network, or external-tool access.

When the user asks to create or run the multi-claim Replica Agent harness,
spawn one dedicated Replica Agent with the `general-purpose` subagent type and
`model: opus`. Give it only the Second JSON path, run directory, canonical
parent identity, and an instruction to follow
`.claude/skills/orchestrate-replica-agents/SKILL.md`. The root may wait for and
report lifecycle results but must not relay Operator/Builder semantic messages.
The Replica Agent itself creates each claim's Operator and Builder children with
explicit `opus` and `sonnet` model requests.

When the user explicitly asks to run the direct Operator/Builder protocol on a
ready harness, resume the same dedicated Replica Agent and existing child
identities instead of spawning a new pair. Give it only the harness registry
path and an instruction to follow
`.claude/skills/run-replica-agent-protocol/SKILL.md`. The root and Replica Agent
may send identity-only activation controls and receive control metadata, but
neither may relay, summarize, rewrite, or persist the semantic instruction or
feedback.

The explicit Operator/Builder protocol route above is the exception to the
JSON-only implementation route. Do not select it unless the user asks for that
Agent protocol or supplies its ready harness registry.

Contracts that require PDF, XLSX, CSV, image, OCR, retrieval, network, or
external API access are outside the current implementation scope.

These are direct implementation routes even if the Skills are not shown in the
current session's selector. Never route this work through a registered
Operator, the removed `replicate` command, an external generator command, or an
API model generator.

## Runtime model policy

The harness records a requested model per Agent and `agent-harness-spawned`
rejects any spawn whose model does not match what `agent-harness-init`
recorded. A Claude session must therefore pass its own policy at init:

```text
--replica-agent-model claude-opus-5 \
--operator-model claude-opus-5 \
--builder-model claude-sonnet-5
```

The defaults remain the Codex models, so an unflagged init still produces a
Codex harness. The role split matches the Codex Sol/Terra split: the Operator
owns strategy, evidence-bound diagnosis, and correction design, so it takes the
stronger reasoning model; the Builder executes an ordered plan, runs tests, and
reports concrete observations, and is explicitly forbidden from redesigning the
Replica, so it takes the faster model. The Replica Agent runs no semantics but
enforces fail-closed policy, so it matches the Operator.

## Claude runtime primitives

The Codex Skills assume Codex-native Agent primitives. The Claude Skills under
`.claude/skills/` use these equivalents, and the differences are load-bearing:

| Codex | Claude Code |
|---|---|
| spawn with `model` and `fork_turns: none` | `Agent` with `subagent_type: general-purpose`, `model`, `run_in_background: true` |
| canonical task path | the agent name/ID returned by `Agent`, listed by `ListAgents` |
| `followup_task` on a completed Agent | `SendMessage` to that agent, which resumes it with its context intact |
| `send_message` control to a peer | `SendMessage` |
| `wait_agent` bounded blocking wait | **no equivalent** — a Claude subagent ends its turn instead of blocking |
| direct sibling-to-sibling messaging | **not available** — an agent can only address agents it spawned |

The last two rows mean the Codex protocol cannot be transliterated. A Claude
Operator and Builder are both children of the Replica Agent, so neither can
address the other, and neither can stay parked waiting for the other.

The Claude Skills therefore move the peer channel to a claim-scoped filesystem
mailbox at `claims/<claim-id>/mailbox/` and have the Replica Agent alternate
child turns. This preserves the invariant the design actually protects: the
Operator's instruction and the Builder's feedback pass between the two children
without the Replica Agent receiving, forwarding, summarizing, rewriting, or
persisting either body. The Replica Agent carries only identity and control
metadata, exactly as in the Codex route. `--operator-to-builder-direct` and
`--builder-to-operator-direct` assert that non-relay property, not an in-memory
transport.

## Project knowledge

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

Use ordinary context search for questions about a specific named topic. Replica
workflow questions covered by the Skill are exempt unless the user explicitly
asks about meeting or decision history.

Treat "회의 때 뭐 나왔지", "지난번에 뭐라고 했지", "기억 가져와줘",
"결정 내용이 뭐야", and "이 아이디어로 만들어줘" as project knowledge recall
requests.

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
