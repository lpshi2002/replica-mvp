---
name: run-replica-agent-protocol
description: Resume ready Sol Operator and Terra Builder pairs into direct Replica execution sessions with Medium-High tests and at most three corrections. Use only after the Replica Agent harness has recorded each pair as READY_FOR_PROTOCOL.
---

# Run Replica Agent Protocol

Run this Skill only inside the same dedicated Replica Agent that created the
supplied `agent-harness.json`. Require the registry path. The Replica Agent may
update continuity control state only through the `agent-continuity-*` commands;
it must not edit the registry directly. The selected claim must be
`READY_FOR_PROTOCOL`, and this Replica Agent's canonical ID must match the
registry. Reject missing, replaced, or cross-claim Agent identities.

This Skill enforces global execution policy and lifecycle metadata. It does not
analyze failures, write corrections, relay semantic messages, aggregate claims,
or create Final Replica JSON.

## Activate the existing pair

For each ready claim, reuse its recorded Operator and Builder. Process claims
independently; a terminal failure does not change another claim. Never spawn a
protocol or correction replacement. A plain `send_message` does not start a
new turn for a completed Agent, so activate the Builder once with
`followup_task`, then activate the Operator once. Both follow-ups must target
the registry's exact canonical IDs. Give both only this identity envelope:

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
  "python_module_invocation": ["py", "-3", "-m", "replica_mvp"]
}
```

Tell each sibling to follow its existing claim Skill. Do not include strategy,
instructions, code, execution observations, or feedback in either activation.
The repository path and Python module invocation are execution controls, not a
semantic relay. Require Python 3.12 or newer, not exactly 3.12, and set
`PYTHONPATH` to `<repo-root>/src` when the console script is unavailable.
Run `agent-continuity-start` with the exact pair IDs and nonce. The Sol
Operator sends `replica-operator-execution-instruction/v1` directly to the
Terra Builder. The Builder sends
`replica-builder-execution-feedback/v1` directly to that Operator.
Both stay inside those activated turns and use bounded native `wait_agent`
between direct rounds. Do not issue another follow-up for a correction.

## Preserve the non-relay path

Accept only control metadata from the siblings: exact claim, stable pair IDs,
nonce, correction number, direct send/receive flags, instruction and feedback
hashes, Operator execution state, pass/total counts, failed-check count, frozen
suite hash, Judge identity/mode, and local contract-validation success. Record
each sequential round with `agent-continuity-round`. Reject a report containing
or summarizing a semantic payload. Validate that success has every criterion
passed and zero failed checks. Treat any contradictory aggregate PASS as a
false success and fail closed.

For `CORRECTION_REQUIRED`, require the next number only; do not write or
suggest correction content. `SUCCESS` may terminal after correction 0, 1, 2,
or 3. `FAILED` is valid only after correction 3. Reject count greater than 3.
Call `agent-continuity-terminal --correction-count N` after the Operator and
Builder complete a direct terminal exchange. If either child returns final
before terminal, run `agent-continuity-premature`, interrupt the remaining
peer, and stop without respawn.

After every ready claim has its own execution terminal, run
`agent-harness-finish`. Require `EXECUTION_SUCCESS` when all claims passed or
`EXECUTION_COMPLETED_WITH_FAILURES` when any claim failed or aborted. Never
rewrite one claim result because of another claim's outcome.

Do not receive, forward, summarize, rewrite, or persist the instruction or
feedback in the Replica Agent registry. After a direct terminal exchange and
ack, run `agent-continuity-terminal`; only then may both child turns return
final. Leave the source Second JSON and every derived `claim.json` unchanged.
