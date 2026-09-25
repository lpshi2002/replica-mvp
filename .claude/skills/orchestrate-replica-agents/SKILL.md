---
name: orchestrate-replica-agents
description: Orchestrate a completed company research JSON or standalone Second JSON with real Claude Operator and Builder child Agents, concurrent sessions for all selected claims, a claim-scoped filesystem peer mailbox, and a lifecycle registry. Use for the production Replica Agent harness, not for implementing or correcting Replica behavior.
---

# Orchestrate Replica Agents

Run this Skill only inside a dedicated Replica Agent spawned by its parent with
`subagent_type: general-purpose` and `model: opus`. Require the completed
research or standalone Second JSON path, run directory, this Replica Agent's
canonical ID, and its parent's ID. Do not replace child Agents with Python
workers, functions, role labels, or sequential implementation calls.

## Resolve the CLI

Prefer the installed `replica-mvp` console script. When it is unavailable, set
`PYTHONPATH` to `<repo-root>/src` and invoke `python3 -m replica_mvp`. Python
3.12 or newer is valid; do not require an exact version. Use the resolved
invocation in place of `replica-mvp` below and pass it to every child.

## Prepare canonical state

Run:

```text
replica-mvp agent-harness-init SECOND_JSON RUN_DIR \
  --replica-agent-id REPLICA_AGENT_ID \
  --parent-agent-id PARENT_AGENT_ID \
  --replica-agent-model claude-opus-5 \
  --operator-model claude-opus-5 \
  --builder-model claude-sonnet-5 \
  --model-runtime claude
```

The model flags are required on the Claude route. They default to the Codex
models, and `agent-harness-spawned` rejects any spawn whose model does not match
what init recorded, so omitting them makes every Claude spawn unrecordable.

This command calls `parse_second_pass()`, writes `agent-harness.json`, and
creates `claims/<claim-id>/claim.json`, `builder-context.json`, `operator/`, and
`builder/`. For a company research input it selects only `ready` + `build`
claims, preserves the complete Second-pass workflow, findings, and scenario
contracts in `claim.json`, and follows the Second-pass `handoff.selected_scenario_id`
or `handoff.scenario_priority`. Without either, preserve the researched scenario
order and record that fallback; never reorder by dependency cost or convenience.
Claude is recorded as a narrow model-runtime overlay and does not cause an
unrelated commercial retrieval, storage, or side-effect scenario to be chosen.
Explicit modality-specific dependencies remain unchanged.
`builder-context.json` contains the public implementation context with test
expectations and reference facts removed. Treat the source, `claim.json`, and
`builder-context.json` as immutable. The Replica Agent alone owns registry
updates. Each child may write only inside its own recorded artifact namespace.

Create the peer channel for each claim before its first spawn:

```text
mkdir -p RUN_DIR/claims/CLAIM_ID/mailbox/to-builder
mkdir -p RUN_DIR/claims/CLAIM_ID/mailbox/to-operator
```

`mailbox/` is a child-owned peer channel, not a Replica Agent artifact. The
Replica Agent creates the two directories and then never reads, lists, copies,
edits, or deletes a file inside either one. The Operator writes only into
`to-builder/`; the Builder writes only into `to-operator/`; each reads only the
other's directory. This is the Claude substitute for Codex sibling messaging,
which is unavailable because a Claude subagent can address only agents it
spawned itself.

Prepare pairs in research order using `agent-harness-start` before spawning.
Skip claims registered as `RESEARCH_INCOMPLETE`: their recorded
`research_gaps` must be closed in pass-2 research (`agent-bundle-prepare
--supplement`) before a pair may start. Report them; never start them.
The registry's active_claim_id serializes pair creation and peer binding only;
it is not an execution concurrency limit. Every selected claim gets its own
concurrent pair: max_concurrent_pairs equals claim_count. Generate a unique nonce for
each claim. A failure in one claim must not stop the other active claim.

## Spawn the pair

Spawn the Operator with the `Agent` tool using all of:

- `subagent_type: general-purpose`
- `model: opus`
- `run_in_background: true`
- `description` naming the claim ordinal, such as `operator 001`
- a `prompt` containing only the claim ID, that claim's `claim.json` path, its
  operator artifact namespace, its mailbox paths, the resolved CLI invocation,
  the repository root, this Replica Agent's ID, and an instruction to read
  `.claude/skills/replica-operator-agent/SKILL.md`; include model runtime
  `claude`

Record the returned Agent ID with:

```text
replica-mvp agent-harness-spawned REGISTRY CLAIM_ID \
  --role operator --agent-id OPERATOR_ID \
  --parent-agent-id REPLICA_AGENT_ID \
  --requested-model claude-opus-5
```

Spawn the Builder independently from the Replica Agent, never from the Operator,
using all of:

- `subagent_type: general-purpose`
- `model: sonnet`
- `run_in_background: true`
- a matching claim-ordinal `description` such as `builder 001`
- a `prompt` containing only the same claim ID, its `builder-context.json` path,
  its builder artifact namespace, its mailbox paths, the resolved CLI
  invocation, the repository root, the Operator's Agent ID, the claim nonce, and
  an instruction to read `.claude/skills/replica-builder-agent/SKILL.md`; include
  model runtime `claude`

Record it the same way with `--role builder --requested-model claude-sonnet-5`.
The registry links peers only after both spawns have succeeded and proves the
pair by their identical `parent_agent_id`.

If either spawn is rejected, run `agent-harness-failed`. Do not create a
placeholder or fall back to another model. If one child already exists, stop it
with `TaskStop` after recording the failure. Only after the stop is confirmed,
run `agent-harness-released REGISTRY CLAIM_ID --agent-id ORPHAN_ID`; until then
the claim remains active and the harness cannot advance or finish. Do not mark
the pair ready.

## Verify the peer channel

Send the Operator this complete identity-only control envelope with
`SendMessage`; omit no field:

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

The Operator writes a structured ping into `to-builder/`. Activate the Builder
with the same envelope; it reads that ping, validates it, and writes a
structured pong into `to-operator/`. Reactivate the Operator once so it reads
the pong. Wait for each child's structured completion report. Accept the smoke
test only when both reports contain the exact claim ID, peer IDs, and nonce.
Never open a mailbox file to check this yourself; the children's reports and the
CLI are the only evidence.

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
pair-creation slot. Keep both Agent IDs; later work must reuse this same
pair through `SendMessage` follow-ups instead of spawning correction Agents.

In prepare-only mode, stop after every claim is `READY_FOR_PROTOCOL` or `CREATION_FAILED`. Return the
registry path and exact runtime spawn/message results. Before returning, run
`replica-mvp agent-harness-finish REGISTRY`; it must reject any nonterminal
claim.

For an authorized full implementation run, follow the sibling
`run-replica-agent-protocol/SKILL.md` in this same Replica Agent. Create and
link every selected pair first, then start all ready pair sessions before
activating Operators without waiting for another claim to finish;
N functions require N concurrent pair sessions. Serialize registry mutations,
not feature completion. Fill pending pairs before blocking final evaluations.
Report a real runtime capacity rejection instead of silently switching to waves.
Do not implement Replica strategy, Builder execution, judging, correction,
aggregation, or Final Replica JSON in this Skill.

## Divergence from the Codex route

The Codex counterpart is `.agents/skills/orchestrate-replica-agents/SKILL.md`.
Two differences are deliberate and load-bearing:

- Peer messages travel through `claims/<claim-id>/mailbox/` instead of a native
  Agent-to-Agent primitive, because a Claude subagent cannot address a peer it
  did not spawn.
- The Replica Agent activates each child in turn rather than binding both and
  standing back, because a Claude subagent ends its turn instead of blocking on
  `wait_agent`.

Neither difference relaxes the non-relay rule. The Replica Agent still carries
only identity and control metadata and never touches a mailbox body. Keep the
two Skills in step when the contract changes.
