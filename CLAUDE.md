# Agent Rules (Claude Code)

This repository is driven by two agent runtimes. `AGENTS.md` holds the Codex
routing rules. This file holds the Claude Code rules and is authoritative for a
Claude session. The workflow logic itself is shared; only the runtime
primitives differ.

At the start of a Replica task, read `context/project-direction.md` for the
shared project goal, confirmed decisions, proposals, and open questions.
Codex and Claude Code use this same file; update it in place when the user
changes the project direction. Execution procedures remain in the Skills below.

When the user requests a Codex/Claude debate (for example, "토론해" or
"서로 리뷰해"), use the installed `agent-debate` skill and read
`context/README.md`. Resume only the explicitly identified task; ordinary
project work does not create a discussion folder.

For company research, Replica workflow questions, claim scoring, source
selection, replication readiness, or Replica execution, read and follow
`skills/replica-research/SKILL.md` before answering or acting. That file is the
shared, runtime-neutral Skill used by both Codex and Claude; treat it as the
authoritative workflow. Read it directly by path — it is not installed under `.claude/skills/`.

A company evaluation request — a company name, URL, or description — runs the
full route by default: both research passes, then `single-harness-init` on the
completed `research.json`, one implementer for every selected claim, final
evaluation (the frozen public web demo for a claim whose selected
scenario has a `demo_plan`, otherwise sealed bundle evaluation), and
`agent-harness-finish`, which writes
`final-results/company-claims.json` for every researched claim. The request
itself approves this full run; stop after pass 2 only when the user asks for
research only. Research with no executable claim still ends with that company
result.

For the implementation step of a company evaluation, the root session follows
the single-implementer steps in the "Execute" section of
`skills/replica-research/SKILL.md`. Initialize with `--model-runtime claude
--model claude-opus-5 --reasoning-effort medium`, matching
`.claude/agents/replica-implementer.md`. Spawn each claim's implementer with
`Agent`, `subagent_type: replica-implementer`, `run_in_background: true`, giving
it only the run directory and claim ID; record the returned agent ID with
`single-agent-start`; after `agent-bundle-retry`, resume the same agent with
`SendMessage` and point it to its `retry-feedback-NNN.json`. The root reads
control results and the implementer's short report, never edits or judges the
implementation, and does not pass screenshots or run values to it.

When the user asks for the Operator/Builder pair route (the multi-claim Replica
Agent harness), spawn one dedicated
Replica Agent with the `general-purpose` subagent type and
`model: opus`. Give it only the Second JSON path, run directory, canonical
parent identity, and an instruction to follow
`.claude/skills/orchestrate-replica-agents/SKILL.md`. The root may wait for and
report lifecycle results but must not relay Operator/Builder semantic messages.
The Replica Agent itself creates each claim's Operator and Builder children with
explicit `opus` and `sonnet` model requests.

When a pair-route harness is ready, or the user asks to run the
direct Operator/Builder protocol on one, resume the same dedicated Replica Agent and existing child
identities instead of spawning a new pair. Give it only the harness registry
path and an instruction to follow
`.claude/skills/run-replica-agent-protocol/SKILL.md`. The root and Replica Agent
may send identity-only activation controls and receive control metadata, but
neither may relay, summarize, rewrite, or persist the semantic instruction or
feedback.

The standalone JSON-only route (`build-replica-operator`) was removed on
2026-10-08 because a Replica is delivered as a web app. A standalone
`replica-second-pass-result/v1` JSON is not an implementation entry point;
run company research so the claim reaches the harness routes above. Never
narrow a company claim to a JSON demo because it needs files or search.

These are direct implementation routes even if the Skills are not shown in the
current session's selector. Never route this work through a registered
Operator, the removed `replicate` command, an external generator command, or an
API model generator.

## Runtime model policy

On the default single-implementer route, `single-agent-start` rejects a model or
effort that differs from what `single-harness-init` recorded. On the pair route,
the harness records a requested model per Agent and `agent-harness-spawned`
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

## Verification

Product code belongs under `src/`; tests belong under `tests/`.
Before finalizing code changes, run the relevant tests and the repository suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Before finalizing any changes, run `git diff --check` and review
`git status --short` and any staged file list for credentials, local databases,
and generated outputs that should remain untracked.
