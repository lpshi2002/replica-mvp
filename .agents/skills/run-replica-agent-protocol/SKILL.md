---
name: run-replica-agent-protocol
description: Resume ready Astra Operator and Terra Builder pairs into direct Replica execution sessions with Medium-High tests and at most three corrections. Use only after the Replica Agent harness has recorded each pair as READY_FOR_PROTOCOL.
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
evaluation/publication pipeline; an implementation bundle is hash-bound, then
automatically executed and evaluated by a separate evaluator process. Final
reproduction never comes from the Builder feedback label.

## Activate the existing pair

For each ready claim, reuse its recorded Operator and Builder. Activate every
selected pair before waiting for any implementation to finish. In full
implementation mode, finish pair registration and smoke for all selected claims,
start every ready continuity session, then activate all Operators: N functions
require N concurrent pairs. Interleave
control events for all active claims and keep their namespaces separate. Process claims independently; a terminal failure does not change another claim. Never spawn a
protocol or correction replacement. A plain `send_message` does not start a
new turn for a completed Agent. Start each round by activating the Operator
first. Wait for control metadata confirming that its validated instruction was
sent directly, then activate the Builder to receive that queued message. After
the Builder confirms its validated feedback was sent directly, reactivate the
Operator if it yielded. Reuse the registry's exact canonical IDs; never spawn
a replacement. Every follow-up contains only this identity envelope:

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
  "execution_state_path": "<absolute bound Operator namespace>/execution-state.json",
  "python_module_invocation": ["python3", "-m", "replica_mvp"]
}
```

Replace `correction_number: 0` with the current round number on later rounds.

Tell each sibling to follow its existing claim Skill. Do not include strategy,
instructions, code, execution observations, or feedback in either activation.
The repository path and Python module invocation are execution controls, not a
semantic relay. The execution_state_path is likewise control metadata; derive
it from the recorded Operator namespace and include it for both siblings. The
Builder may invoke the control-only agent-execution-check CLI on this exact path
without reading the state or other Operator files. Use `["py", "-3", "-m", "replica_mvp"]` on Windows. Require
Python 3.12 or newer, not exactly 3.12, and set `PYTHONPATH` to
`<repo-root>/src` when the console script is unavailable.
Run `agent-continuity-start` with the exact pair IDs and nonce. The Astra
Operator sends `replica-operator-execution-instruction/v1` directly to the
Terra Builder. The Builder sends
`replica-builder-execution-feedback/v1` directly to that Operator.
After an Agent completes its required direct send, prefer a control-only
round yield while its peer works, freeing active runtime capacity for other
claims. Resume its same canonical identity when peer output arrives. An Agent
may use a bounded native wait for a short handoff, but must not occupy an active
thread solely to wait while another selected pair is blocked by capacity. In that case, reactivate the same canonical Agent ID for the
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
or 3. `FAILED` is valid after correction 3 or an earlier validated blocking/budget
stop recorded in execution-state.json. Reject count greater than 3.
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
paths, symlinks, and hashes, then invokes the final bundle evaluator. The default
uses the harness-selected native model CLI and records `same_session`; it does
not require a user-written judge script. Require `RESULT_SUCCESS` only for
`reproduced`; other evaluated outcomes are `RESULT_FAILED`. Failed and aborted
development claims have no candidate-finalization step.

`--bind-only` deliberately leaves `IMPLEMENTATION_READY` for a scheduled external
evaluator. It is an intermediate state. Newly initialized harnesses refuse
`agent-harness-finish` while any bundle remains unevaluated. After all successful
development claims have final results and all others have their execution
terminal, finish the harness. Its aggregate is `EXECUTION_SUCCESS` only when all
claims have passing published results; otherwise `EXECUTION_COMPLETED_WITH_FAILURES`.
Never change one claim's result because another claim failed.
For company research, finish also writes `final-results/company-claims.json`
with every researched claim; report the run from that file so unexecuted and
blocked claims keep their reasons and the denominator stays visible.

Do not receive, forward, summarize, rewrite, or persist the instruction or
feedback in the Replica Agent registry. After a direct terminal exchange and
ack, run `agent-continuity-terminal`; only then is the claim final. Earlier
child finals satisfying the round-pause rule above are control yields, not
terminal claim results. Leave the source Second JSON and every derived
`claim.json` unchanged.


## Final bundle evaluation after the development terminal

Harness initialization freezes a separate evaluator plan from the researched
scenario. Keep its tests, expectations, reference facts, outputs and per-case
marks outside Builder access. If a plan lacks runnable checks, transport,
criterion coverage or representative novel/metamorphic cases, request an additive
Second-pass supplement via `agent-bundle-prepare REGISTRY CLAIM_ID --supplement JSON`.
Do not invent a new implementation method or modify frozen claim files. A plan
prepared after implementation is explicitly retrospective and cannot establish
pre-implementation isolation.

`agent-candidate-finalize` runs the separate evaluator automatically. To resume
an explicit `--bind-only` handoff, use `agent-bundle-evaluate REGISTRY CLAIM_ID`.
For an already configured external evaluator, add `--judge-command JSON_ARGV
--judge-identity NAME --judge-mode same_session|independent`. The command receives
JSON on stdin and returns `{pass, reason}`; it must honor `timeout_seconds`.
Declare same_session unless independence has actually been established. Never
use Builder development tests as the judge. Native CLI errors or unavailable
modality inspection leave the relevant quality or fidelity checks unverified.

The command executes the same hashed entrypoint in disposable runtime directories,
checks both repeated outputs, preserves private execution evidence, and publishes
code, separate public examples, file outputs, replica-result.json and a technical
completion assessment. It creates no new narrative result report. Final state is
RESULT_SUCCESS only for reproduced; other outcomes remain RESULT_FAILED with their
actual reproduction status. IMPLEMENTATION_READY continues to mean unevaluated.
A candidate cannot guess sealed answers through repeated submissions; at most three
submissions per scenario are allowed and all prior attempts remain bound.

For a failed final result that can be corrected within the same frozen contract,
`agent-bundle-retry REGISTRY CLAIM_ID` reopens the original pair. It preserves the
code, execution-state metadata and final evidence, carries development time and
resource history, and counts all final submissions against the same evaluation
budget and three-submission cap. The Operator uses the pre-created ACTIVE state;
do not call agent-execution-start again. Activate the same identities and nonce.
The Operator diagnoses and sends corrections directly to the Builder using its
own development evidence and public aggregate status. The Replica Agent must
never relay sealed examples, expected values or private judge reasons. Keep
semantic peer artifacts in submission-specific paths inside their existing owner
namespaces so an earlier exchange is not overwritten. A changed implementation
must complete development and be rebound before final evaluation. Unchanged
candidates cannot be resubmitted. Missing research or a changed contract requires
a separate Second-pass experiment instead of weakening the existing plan.


## Recover a repaired preflight control failure

After a runtime control defect has been repaired, the same Replica Agent may run
`agent-continuity-retry-preflight REGISTRY CLAIM_ID` once. This is restricted to a
bound environment stop with measured zero implementation actions, no tests run
and no candidate; other failures must not use this route. The CLI archives the
original terminal evidence and preserves the frozen claim, pair identities,
start time and resource history. It refuses exhausted or unverifiable budgets.
Start continuity again for the same IDs and nonce, then activate the Operator
with the complete identity envelope plus `"preflight_recovery": true`. Activate
the Builder only after the Operator confirms its direct instruction send. Do
not relay the prior stop reason or write a replacement instruction. This is a
recorded control recovery, not a successful implementation or a new experiment.


If direct delivery or reactivation hits the runtime's active-thread limit,
pause only peers that have completed their required direct action and are now
waiting. Retry the same sender/recipient and unchanged validated message after
capacity is released. Do not pause active implementation merely to serialize
features, replace identities, or relay the message. Record any capacity delay.


If initial bundle binding rejects undeclared files after a successful development
terminal, the same `agent-bundle-retry` command can reopen the original pair for
packaging repair before sealed evaluation. It revalidates that narrow rejection,
archives the declared source and prior control state, preserves budgets, and
allows at most two packaging retries. These do not count as sealed submissions
because the evaluator has not run. Send the normal identity activation with
`packaging_retry` set to its one-based recorded retry number. The Operator and
Builder exchange the correction directly, rerun development checks, and terminal
again before finalization. Do not relay rejection diagnostics or edit the bundle.


## One bounded recovery of an interrupted direct delivery

Keep an observed premature or non-control return recorded as ABORTED. After the
control problem is addressed, `agent-continuity-resume REGISTRY CLAIM_ID` may
resume that same pair once if the original execution state is still active and
its budget remains available. It archives the control abort in the registry and
preserves the execution-state bytes, correction number, completed rounds and
all evidence. A repeated abort or a development terminal cannot use this path.
Never read, summarize, forward or persist the misrouted semantic final body.
Activate the original Operator at the existing correction number with
`continuity_resume: true` and `await_peer_delivery: true`, then activate the
original Builder with `continuity_resume: true` and
`protocol_repair: "direct_delivery"`. Include the complete identity envelope and
bound execution_state_path. The siblings recover their own direct exchange from
their own files and history. Require local validation and actual direct delivery
before recording a round or terminal; neither parent supplies semantic content.
