---
name: orchestrate-replica-agents
description: Orchestrate a completed company research JSON or standalone Second JSON with real Codex Sol Operator and Terra Builder sibling Agents, sequential claim scheduling, direct peer messaging, and a claim-scoped lifecycle registry. Use for the production Replica Agent harness, not for implementing or correcting Replica behavior.
---

# Orchestrate Replica Agents

Run this Skill only inside a dedicated Replica Agent spawned by its parent with
`model=gpt-5.6-sol` and `fork_turns=none`. Require the completed research or
standalone Second JSON path, run
directory, this Replica Agent's canonical task path, and its parent task path.
Do not replace child Agents with Python workers, functions, role labels, or
sequential implementation calls.

## Prepare canonical state

Run:

```text
replica-mvp agent-harness-init SECOND_JSON RUN_DIR \
  --replica-agent-id REPLICA_AGENT_ID \
  --parent-agent-id PARENT_AGENT_ID
```

This command calls `parse_second_pass()`, writes `agent-harness.json`, and
creates `claims/<claim-id>/claim.json`, `builder-context.json`, `operator/`, and
`builder/`. For a company research input it selects only `ready` + `build`
claims, preserves the complete Second-pass workflow, findings, and scenario
contracts in `claim.json`, and chooses the most self-sufficient scenario first.
`builder-context.json` contains the public implementation context with test
expectations and reference facts removed. Treat the source, `claim.json`, and
`builder-context.json` as immutable. The Replica Agent alone owns registry
updates. Each child may write only inside its own recorded artifact namespace.

Process registry claims in order, one active pair at a time. Never activate an
unbounded set of pairs. For each claim run `agent-harness-start` before any
spawn. Generate one unique nonce for that claim before spawning either child.

## Spawn the sibling pair

Spawn the Operator with the real Agent primitive using all of:

- `model: gpt-5.6-sol`
- `fork_turns: none`
- a claim-ordinal task name such as `operator_001`
- a task containing only the claim ID, that claim's `claim.json` path, its
  operator artifact namespace, this Replica Agent ID, and an instruction to
  read `.agents/skills/replica-operator-agent/SKILL.md`

Record the returned canonical Agent ID with `agent-harness-spawned`, including
the exact requested model and this Replica Agent ID as parent.

Spawn the Builder independently from the Replica Agent, never from the
Operator, using all of:

- `model: gpt-5.6-terra`
- `fork_turns: none`
- a matching claim-ordinal task name such as `builder_001`
- a task containing only the same claim ID and `builder-context.json`, its builder
  artifact namespace, the Operator's canonical Agent ID, and an instruction
  to read `.agents/skills/replica-builder-agent/SKILL.md`; include the claim
  nonce in this task

Record the returned Builder ID in the same way. The registry links peers only
after both spawns have succeeded and proves siblinghood by their identical
`parent_agent_id`.

If either spawn is rejected, run `agent-harness-failed`. Do not create a
placeholder or fall back to another model. If one sibling already exists,
interrupt it after recording the failure. Only after the interrupt tool
confirms release, run `agent-harness-released REGISTRY CLAIM_ID --agent-id
ORPHAN_ID`; until then the claim remains active and the harness cannot advance
or finish. Do not mark the pair ready.

## Verify direct peer messaging

Send the Operator this complete identity-only control envelope; omit no field:

```json
{
  "type": "peer_binding",
  "claim_id": "<claim-id>",
  "operator_agent_id": "<operator-id>",
  "builder_agent_id": "<builder-id>",
  "nonce": "<claim-nonce>"
}
```

Do not carry a semantic ping or pong through the Replica Agent.

The Operator sends a structured ping directly to its allowed Builder. The
Builder validates it and sends a structured pong directly to its allowed
Operator. Wait for both Agents' structured completion reports. Accept the
smoke test only when both reports contain the exact claim ID, peer IDs, and
nonce.

Then record the two observed directions separately:

```text
replica-mvp agent-harness-message REGISTRY CLAIM_ID \
  --direction operator_to_builder \
  --sender-agent-id OPERATOR_ID --recipient-agent-id BUILDER_ID \
  --nonce NONCE

replica-mvp agent-harness-message REGISTRY CLAIM_ID \
  --direction builder_to_operator \
  --sender-agent-id BUILDER_ID --recipient-agent-id OPERATOR_ID \
  --nonce NONCE
```

The second record makes the pair `READY_FOR_PROTOCOL` and releases the
sequential scheduling slot. Keep both canonical Agent IDs; later work must
reuse this same pair through follow-up turns instead of spawning correction
Agents.

Stop after every claim is `READY_FOR_PROTOCOL` or `CREATION_FAILED`. Return the
registry path and exact runtime spawn/message results. Before returning, run
`replica-mvp agent-harness-finish REGISTRY`; it must reject any nonterminal
claim.

Do not implement Replica strategy, Builder execution, judging,
correction, aggregation, or Final Replica JSON in this Skill.
