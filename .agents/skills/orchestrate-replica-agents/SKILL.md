---
name: orchestrate-replica-agents
description: Orchestrate a completed company research JSON or standalone Second JSON with real Codex Astra Operator and Terra Builder sibling Agents, concurrent sessions for all selected claims, direct peer messaging, and a claim-scoped lifecycle registry. Use for the production Replica Agent harness, not for implementing or correcting Replica behavior.
---

# Orchestrate Replica Agents

Run this Skill only inside a dedicated Replica Agent spawned by its parent with
`model=gpt-6-astra`, `reasoning_effort=medium`, and `fork_turns=none`. Require the completed research or
standalone Second JSON path, run
directory, this Replica Agent's canonical task path, and its parent task path.
Do not replace child Agents with Python workers, functions, role labels, or
sequential implementation calls.

## Prepare canonical state

If the console script is unavailable, set `PYTHONPATH` to `<repo-root>/src` and
use `python3 -m replica_mvp` for every command below. Use Python 3.12 or newer.

Run:

```text
replica-mvp agent-harness-init SECOND_JSON RUN_DIR \
  --replica-agent-id REPLICA_AGENT_ID \
  --parent-agent-id PARENT_AGENT_ID \
  --model-runtime codex
```

This command calls `parse_second_pass()`, writes `agent-harness.json`, and
creates `claims/<claim-id>/claim.json`, `builder-context.json`, `operator/`, and
`builder/`. For a company research input it selects only `ready` + `build`
claims, preserves the complete Second-pass workflow, findings, and scenario
contracts in `claim.json` with sealed tests and evaluation cases moved to
`evaluator-vault/<claim-id>/claim-sealed.json`, and follows the Second-pass `handoff.selected_scenario_id`
or `handoff.scenario_priority`. Without either, preserve the researched scenario
order and record that fallback; never reorder by dependency cost or convenience.
Codex is recorded as a narrow model-runtime overlay and does not cause an
unrelated commercial retrieval, storage, or side-effect scenario to be chosen.
Every researched claim, executed or not, is listed in the registry's
`company_claims` with its verdict and not-executed reason, and
`research_source` binds the research file's hash. When no claim is executable,
init finishes the harness as `COMPLETED_WITHOUT_EXECUTION` and writes the
company result at once; report it and stop.
Explicit modality-specific dependencies remain unchanged.
`builder-context.json` contains the public implementation context with test
expectations and reference facts removed. Treat the source, `claim.json`, and
`builder-context.json` as immutable. The Replica Agent alone owns registry
updates. Each child may write only inside its own recorded artifact namespace.

Prepare pairs in research order using `agent-harness-start` before spawning.
Skip claims registered as `RESEARCH_INCOMPLETE`: their recorded
`research_gaps` must be closed in pass-2 research (`agent-bundle-prepare
--supplement`) before a pair may start. Report them; never start them.
The registry's active_claim_id serializes pair creation and peer binding only;
it is not an execution concurrency limit. Every selected claim gets its own
concurrent pair: max_concurrent_pairs equals claim_count. Generate a unique nonce for
each claim. A failure in one claim must not stop the other active claim.

## Spawn the sibling pair

Spawn the Operator with the real Agent primitive using all of:

- `model: gpt-6-astra`
- `reasoning_effort: medium`
- `fork_turns: none`
- a claim-ordinal task name such as `operator_001`
- a task containing only the claim ID, that claim's `claim.json` path, its
  operator artifact namespace, this Replica Agent ID, and an instruction to
  read `.agents/skills/replica-operator-agent/SKILL.md`; include model runtime
  `codex`

Record the returned canonical Agent ID with `agent-harness-spawned`, including
the exact requested model, `--requested-reasoning-effort medium`, and this Replica
Agent ID as parent. Missing or mismatched effort is rejected for the Astra Operator.

Spawn the Builder independently from the Replica Agent, never from the
Operator, using all of:

- `model: gpt-5.6-terra`
- `reasoning_effort: high`
- `fork_turns: none`
- a matching claim-ordinal task name such as `builder_001`
- a task containing only the same claim ID and `builder-context.json`, its builder
  artifact namespace, the Operator's canonical Agent ID, and an instruction
  to read `.agents/skills/replica-builder-agent/SKILL.md`; include the claim
  nonce and model runtime `codex` in this task

Record the returned Builder ID with `--requested-reasoning-effort high`. Missing
or mismatched effort is rejected for the Terra Builder. Do not infer the effort
of historical runs from this new policy. The registry links peers only
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
pair-creation slot. Keep both canonical Agent IDs; later work must
reuse this same pair through follow-up turns instead of spawning correction
Agents.

In prepare-only mode, stop after every claim is `READY_FOR_PROTOCOL` or `CREATION_FAILED`. Return the
registry path and exact runtime spawn/message results. Before returning, run
`replica-mvp agent-harness-finish REGISTRY`; it must reject any nonterminal
claim.

Do not implement Replica strategy, Builder execution, judging, correction,
aggregation, or Final Replica JSON yourself. Use the declared protocol and final
evaluator commands for an authorized implementation run.

## Full implementation mode: activate every selected pair

When the parent instruction explicitly requests a full implementation run, do
not stop after smoke setup. Prepare and link all selected pairs first. Read
and follow the sibling `run-replica-agent-protocol/SKILL.md` in this same Agent.
After all pair creation and smoke controls are resolved, start continuity for
every ready pair, then activate all Operators without waiting for any claim to
finish. This startup barrier prevents an early claim from finishing while later
pairs are still being created: N selected functions require N concurrent pairs. Interleave direct-message control events for all active claims. If the
actual Agent tool rejects a spawn for capacity, report that concrete limitation;
never silently substitute a fixed-size wave or simulated Agents. Existing
harness scheduling metadata is upgraded by agent-continuity-start. Reuse each
pair's original identities for
corrections; never create substitute pairs. These lifecycle controls do not
permit relaying semantic instructions, feedback or private evaluator evidence.

Only this Replica Agent writes the registry. Await each registry-mutating CLI
command, including candidate finalization, before issuing another registry
mutation. Children can keep implementing and exchanging direct messages while a
final evaluation command runs. Buffer their control notifications until that
command returns, then reload the registry. Finish only after every selected claim
has its execution terminal and successful development candidates have final
results. Report per-claim control status, output paths, and started_at/finished_at
plus peak_active_pairs so actual overlap across selected pairs is reviewable.
