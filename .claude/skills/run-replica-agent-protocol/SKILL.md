---
name: run-replica-agent-protocol
description: Resume ready Claude Operator and Builder pairs into Replica execution sessions with Medium-High tests and at most three corrections. Use only after the Replica Agent harness has recorded each pair as READY_FOR_PROTOCOL.
---

# Run Replica Agent Protocol

Run this Skill only inside the same dedicated Replica Agent that created the
supplied `agent-harness.json`. Require the registry path. The Replica Agent may
update continuity control state only through the `agent-continuity-*` commands;
it must not edit the registry directly. The selected claim must be
`READY_FOR_PROTOCOL`, and this Replica Agent's ID must match the registry.
Reject missing, replaced, or cross-claim Agent identities.

This Skill enforces global execution policy and lifecycle metadata. It does not
analyze failures, write corrections, relay semantic messages, aggregate claims,
or invent Final Replica JSON. It must invoke `agent-candidate-finalize` for
every successful Builder candidate. A legacy component enters the existing
evaluation/publication pipeline; an implementation bundle is hash-bound as
`IMPLEMENTATION_READY` without claiming final reproduction.

## Activate the existing pair

For each ready claim, reuse its recorded Operator and Builder. Process claims
independently; a terminal failure does not change another claim. Never spawn a
protocol or correction replacement. Resume each child with `SendMessage`
addressed to the registry's exact recorded Agent ID, which continues that agent
with its context intact. Give both only this identity envelope:

```json
{
  "type": "protocol_activation",
  "claim_id": "<claim-id>",
  "operator_agent_id": "<operator-id>",
  "builder_agent_id": "<builder-id>",
  "nonce": "<claim-nonce>",
  "correction_number": 0,
  "persistent_claim_session": true,
  "replica_execution_loop": true,
  "maximum_corrections": 3,
  "repo_root": "<absolute repository root>",
  "mailbox_root": "<absolute claims/<claim-id>/mailbox>",
  "cli_invocation": ["python3", "-m", "replica_mvp"]
}
```

Tell each child to follow its existing claim Skill. Do not include strategy,
instructions, code, execution observations, or feedback in either activation.
The repository path, mailbox root, and CLI invocation are execution controls,
not a semantic relay. Require Python 3.12 or newer, not exactly 3.12, and set
`PYTHONPATH` to `<repo-root>/src` when the console script is unavailable.

Run `agent-continuity-start` with the exact pair IDs and nonce.

## Drive one round at a time

A Claude subagent ends its turn instead of blocking on a peer, so the Replica
Agent supplies the clock. Each round is three activations and no more:

1. `SendMessage` the Operator with the envelope above at the current
   `correction_number`. It writes and validates
   `replica-operator-execution-instruction/v1` into `mailbox/to-builder/` and
   returns control metadata only.
2. `SendMessage` the Builder with the same envelope. It reads that instruction
   from the mailbox, executes it, writes
   `replica-builder-execution-feedback/v1` into `mailbox/to-operator/`, and
   returns control metadata only.
3. `SendMessage` the Operator again. It reads the feedback from the mailbox,
   runs `agent-execution-advance`, and returns the resulting execution state as
   control metadata only.

Never read, list, copy, or summarize a mailbox file. Never place a child's
returned text into another child's message. If a child returns anything other
than control metadata, discard the semantic content, do not forward it, and
treat a repeated violation as a continuity failure.

## Preserve the non-relay path

Accept only control metadata from the children: exact claim, stable pair IDs,
nonce, correction number, direct send/receive flags, instruction and feedback
hashes, Operator execution state, pass/total counts, failed-check count, frozen
suite hash, Judge identity/mode, and local contract-validation success. Record
each sequential round with:

```text
replica-mvp agent-continuity-round REGISTRY CLAIM_ID \
  --round-number ROUND \
  --operator-agent-id OPERATOR_ID --builder-agent-id BUILDER_ID \
  --nonce NONCE \
  --operator-to-builder-direct --builder-to-operator-direct
```

The two direct flags assert that the instruction and feedback bodies passed
between the children without the Replica Agent receiving, forwarding,
summarizing, rewriting, or persisting either one. The mailbox satisfies that.
Do not pass them if you inspected a mailbox body.

Reject a report containing or summarizing a semantic payload. Validate that
success has every criterion passed and zero failed checks. Treat any
contradictory aggregate PASS as a false success and fail closed.

For `CORRECTION_REQUIRED`, require the next number only; do not write or suggest
correction content. `SUCCESS` may terminal after correction 0, 1, 2, or 3.
`FAILED` is valid only after correction 3. Reject count greater than 3.

Call `agent-continuity-terminal --execution-state EXECUTION_STATE` after the
Operator and Builder complete a terminal exchange through the mailbox. The state
path must be the exact `execution-state.json` in the bound Operator namespace.
This lets the harness verify the immutable claim hash, pair binding, PASS/FAIL
decision, criterion results, failed-check count, suite hash, Judge metadata, and
correction count instead of trusting a terminal label. If either child returns
final before terminal, run `agent-continuity-premature`, stop the remaining peer
with `TaskStop`, and stop without respawn.

After a `SUCCESS` execution terminal, read the exact `candidate_path` bound in
the execution result and finalize that path:

```text
replica-mvp agent-candidate-finalize \
  REGISTRY CLAIM_ID BOUND_CANDIDATE_PATH
```

For `operator.json`, this command reuses `prepare-operator` and
`finalize-operator`, runs the frozen evaluation and determinism checks, writes
the completion assessment and final reports, and requires `RESULT_SUCCESS` or
records `RESULT_FAILED`. For `implementation/manifest.json`, it validates the
selected scenario, dependency record, entrypoint, command, declared file set,
paths, symlinks, and hashes, then requires `IMPLEMENTATION_READY`. This state is
only a verified implementation handoff; it is not `RESULT_SUCCESS`,
`reproduced`, or published final output. Never replace either outcome with the
earlier Agent feedback label. Failed and aborted execution claims have no
candidate-finalization step.

After every successful execution claim has `RESULT_SUCCESS`, `RESULT_FAILED`, or
`IMPLEMENTATION_READY` and every other claim has its execution terminal, run
`agent-harness-finish`. Require `EXECUTION_SUCCESS` only when every claim has a
published passing result, `IMPLEMENTATION_READY` when all remaining claims are
verified bundles or published results, or `EXECUTION_COMPLETED_WITH_FAILURES`
when any claim failed or aborted. Never rewrite one claim result because of
another claim's outcome.

Do not receive, forward, summarize, rewrite, or persist the instruction or
feedback in the Replica Agent registry. After a terminal exchange and ack, run
`agent-continuity-terminal`; only then may both children return final. Leave the
source Second JSON and every derived `claim.json` unchanged.

## Divergence from the Codex route

The Codex counterpart is `.agents/skills/run-replica-agent-protocol/SKILL.md`.
There, both children stay parked inside one activated turn and exchange every
round directly with `wait_agent`, and the Replica Agent issues exactly one
follow-up per child. Claude has no blocking peer wait, so the Replica Agent
issues one activation per child per round instead. The correction cap, the
fail-closed validation, the artifact ownership, and the non-relay rule are
unchanged. Keep the two Skills in step when the contract changes.
