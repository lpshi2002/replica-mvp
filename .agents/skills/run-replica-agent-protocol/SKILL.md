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
or invent Final Replica JSON. It must invoke `agent-candidate-finalize` for
every successful Terra candidate. A legacy component enters the existing
evaluation/publication pipeline; an implementation bundle is hash-bound as
`IMPLEMENTATION_READY` without claiming final reproduction.

## Activate the existing pair

For each ready claim, reuse its recorded Operator and Builder. Process claims
independently; a terminal failure does not change another claim. Never spawn a
protocol or correction replacement. A plain `send_message` does not start a
new turn for a completed Agent. Start each round by activating any completed
participant with `followup_task`, Builder first and then Operator. Reuse the
registry's exact canonical IDs; never spawn a replacement. Both follow-ups
contain only this identity envelope:

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
  "python_module_invocation": ["python3", "-m", "replica_mvp"]
}
```

Tell each sibling to follow its existing claim Skill. Do not include strategy,
instructions, code, execution observations, or feedback in either activation.
The repository path and Python module invocation are execution controls, not a
semantic relay. Use `["py", "-3", "-m", "replica_mvp"]` on Windows. Require
Python 3.12 or newer, not exactly 3.12, and set `PYTHONPATH` to
`<repo-root>/src` when the console script is unavailable.
Run `agent-continuity-start` with the exact pair IDs and nonce. The Sol
Operator sends `replica-operator-execution-instruction/v1` directly to the
Terra Builder. The Builder sends
`replica-builder-execution-feedback/v1` directly to that Operator.
An Agent may use bounded native `wait_agent` and stay active between direct
rounds. It may also yield a control-only round report after its required direct
send or receive. In that case, reactivate the same canonical Agent ID for the
next round; this is a round pause, not premature claim completion.

Do not wait forever for a round action. Track a control fingerprint from the
registry and Operator execution state plus only the existence, size, and mtime
of instruction/feedback artifacts; never inspect their semantic bodies. Reset
the stall count on any change. Request control-only status after 60 seconds.
Abort only after five consecutive 60-second waits with the same fingerprint
and two unanswered status requests. Immediately recompute the fingerprint
before mutation and cancel the abort if anything changed. Otherwise interrupt
the stalled child, record a claim-scoped abort with
`agent-continuity-premature` and a timeout reason, interrupt its peer, and
continue with the next ready claim.

## Preserve the non-relay path

Accept only control metadata from the siblings: exact claim, stable pair IDs,
nonce, correction number, direct send/receive flags, instruction and feedback
hashes, Operator execution state, pass/total counts, failed-check count, frozen
suite hash, Judge identity/mode, and local contract-validation success. Record
each sequential round with `agent-continuity-round`. Reject a report containing
or summarizing a semantic payload. Validate that success has every criterion
passed and zero failed checks. Treat any contradictory aggregate PASS as a
false success and fail closed.

If feedback contract validation fails before execution-state advance, allow at
most two protocol-envelope repairs at the same correction number. Reactivate
the exact same Builder ID with the identity envelope plus
`"protocol_repair": "feedback"`; do not relay the invalid body or validator
diagnostics. The Builder reruns its local validator and resends a valid
same-round feedback. This does not consume an implementation correction. Abort
the claim only after two unchanged invalid repairs.

For `CORRECTION_REQUIRED`, require the next number only; do not write or
suggest correction content. `SUCCESS` may terminal after correction 0, 1, 2,
or 3. `FAILED` is valid only after correction 3. Reject count greater than 3.
Call `agent-continuity-terminal --execution-state EXECUTION_STATE` after the
Operator and Builder complete a direct terminal exchange. The state path must
be the exact `execution-state.json` in the bound Operator namespace. This lets
the harness verify the immutable claim hash, pair binding, PASS/FAIL decision,
criterion results, failed-check count, suite hash, Judge metadata, and
correction count instead of trusting a terminal label. Run
`agent-continuity-premature` only when a child returns before completing its
required direct action for the current round, returns semantic content to the
Replica Agent, or changes the bound identity. A validated control-only report
confirming that the instruction or feedback was sent directly is a round pause:
keep the claim active and reactivate that same child when its next direct
message is queued. A real abort is claim-scoped: interrupt the remaining peer,
do not replace the pair, continue with the next `READY_FOR_PROTOCOL` claim,
and never let a failed, aborted, or blocked claim stop unrelated claims.

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

After every successful execution claim has `RESULT_SUCCESS`, `RESULT_FAILED`,
or `IMPLEMENTATION_READY` and every other claim has its execution terminal, run
`agent-harness-finish`. Require `EXECUTION_SUCCESS` only when every claim has a
published passing result, `IMPLEMENTATION_READY` when all remaining claims are
verified bundles or published results, or `EXECUTION_COMPLETED_WITH_FAILURES`
when any claim failed or aborted. Never rewrite one claim result because of
another claim's outcome.

Do not receive, forward, summarize, rewrite, or persist the instruction or
feedback in the Replica Agent registry. After a direct terminal exchange and
ack, run `agent-continuity-terminal`; only then is the claim final. Earlier
child finals satisfying the round-pause rule above are control yields, not
terminal claim results. Leave the source Second JSON and every derived
`claim.json` unchanged.
