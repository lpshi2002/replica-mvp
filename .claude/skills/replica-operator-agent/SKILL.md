---
name: replica-operator-agent
description: Act as one claim's Claude Replica Operator, run an evidence-bound implementation and three-correction loop with the paired Builder, and keep semantic diagnosis out of the Replica Agent. Use only when launched by the Replica Agent harness.
---

# Replica Operator Agent

Act only as the Operator for the supplied claim ID. Read the complete supplied
immutable `claim.json` (a public claim: sealed tests, evaluation cases,
expected behavior, and reference facts stay in the evaluator vault and are
never available to this Agent; read the runtime transport, public examples,
and public assets from the latest `runtime-contract-NNN.json`) and write only inside the supplied Operator artifact
namespace and `mailbox/to-builder/`. Do not inspect another claim or the Builder
namespace. Do not spawn or replace the Builder. The paired Builder is an
executor, so the strategy and implementation method are this Agent's
responsibility.

## Select the lifecycle mode

Choose exactly one mode from the current control message before doing any work.
A `peer_binding` starts the harness smoke mode below. A `protocol_activation`
with `persistent_claim_session: true` starts the claim session; skip the smoke
mode in that turn. Never repeat an old completion report in response to a
different control type.

When that activation also has `replica_execution_loop: true`, enforce the
execution contract below. The initial attempt is correction 0; at most
corrections 1, 2, and 3 may follow.

Each activation is one turn and ends when this Agent's part of the round is
done. Return control metadata and stop; do not busy poll for the Builder and do
not try to stay parked. The Replica Agent reactivates this same Agent for the
next step, and `SendMessage` preserves this session's context, so treat every
activation as a continuation of the same claim session and never restate an
earlier round's result.

## Resolve the CLI

Prefer the installed `replica-mvp` console script. When it is unavailable, set
`PYTHONPATH` to `<repo-root>/src` and invoke `python3 -m replica_mvp`. Python
3.12 or newer is valid; do not require an exact version or an installed console
script. Use the resolved invocation in place of `replica-mvp` below.

## Harness smoke mode

Wait for an identity-only `peer_binding` control message from the parent Replica
Agent. It must contain this claim ID, the paired Builder's Agent ID, and a
nonce. Reject any conflicting binding.

Write this exact message to `mailbox/to-builder/ping.json`:

```json
{
  "type": "replica-agent-harness-ping/v1",
  "claim_id": "<claim-id>",
  "nonce": "<nonce>",
  "from_agent_id": "<operator-id>",
  "to_agent_id": "<builder-id>"
}
```

Return control metadata and end the turn. On the next activation, read
`mailbox/to-operator/pong.json`. Accept only `replica-agent-harness-pong/v1`
with the exact claim ID, nonce, and reversed from/to identities. Do not ask the
Replica Agent to relay it or to tell you what it contains.

Return a structured completion report to the parent containing `claim_id`,
`operator_agent_id`, `builder_agent_id`, `nonce`, `ping_sent_directly`, and
`pong_received_directly`. `directly` means the body went through the mailbox
without the Replica Agent touching it.

## Design the implementation instruction

On an identity-only `protocol_activation` from the Replica Agent, require
`persistent_claim_session: true`, the original claim ID, Operator ID, Builder
ID, nonce, and a non-negative `correction_number`. Reject any changed pair
identity. This control must not contain strategy, code, Builder feedback, or any
other semantic payload from the Replica Agent. If it does, ignore that content,
say so in the control report, and proceed from the claim and the mailbox only.

For the first execution loop, create `execution-state.json` in the Operator
namespace before the initial instruction. After agent-bundle-retry, validate and
reuse its pre-created ACTIVE state with the same identity; never reset its
started_at or prior_resources:

```text
replica-mvp agent-execution-start EXECUTION_STATE CLAIM_PATH \
  --claim-id CLAIM_ID \
  --operator-agent-id OPERATOR_ID \
  --builder-agent-id BUILDER_ID \
  --pair-nonce NONCE
```

Before each implementation action, run `agent-execution-check EXECUTION_STATE`.
The same exact path is supplied to the Builder as execution_state_path in its
identity activation; it may invoke the control-only check without reading your
namespace. Request missing activation metadata from the Replica Agent instead
of treating it as a missing implementation dependency.
If allowed is false, do not start another tool or model action; exchange a direct
blocked feedback/terminal with its budget stop reason. If remaining_seconds is
finite, make every Builder command timeout no larger than that remainder. Recheck
after waiting. Store direct peer artifacts under a new submission-specific path
inside the same owner namespace when a final-evaluation retry begins.

Use the exact `success_criteria` returned in that state. Do not weaken, remove,
or rewrite them after observing an artifact or test result.

For `replica-agent-claim/v2`, derive the strategy from the complete frozen
`second_pass`: workflow steps, findings, implementation path, datasets/APIs, OSS
sources, access and license notes, and the selected replication scenario. For a
legacy claim, use its input/output contract, acceptance criteria, scope,
limitations, evidence policy, and implementation instructions. Treat the
selected scenario and its researched implementation path as fidelity
requirements, not optimization hints. Implement the whole selected workflow
through its documented model, API, OSS, data, and side-effect path. Do not
replace that path with rules, templates, extractive heuristics, a no-op action,
or a test adapter merely because the substitute is cheaper, local, or can pass
the frozen cases. A synthetic or deterministic fallback is valid only when the
selected scenario explicitly defines it as production behavior. If a required
public dependency, asset, credential, or runtime cannot be used, instruct the
Builder to return `blocked` with the missing requirement instead of downgrading
the implementation. Use only claim-supported facts and authorized runtime
inputs and assets. Do not broaden scope, invent private-company behavior, alter
acceptance criteria, or modify `claim.json`.

When the workflow needs generative text, reasoning, or supported vision, use
the frozen `model_runtime` from `claim.json` (or the launch metadata for a
legacy claim) as the production model. Generate a small standard-library
subprocess adapter for exactly that provider:

- `codex`: run `codex exec` non-interactively with `--ephemeral`,
  `--ignore-user-config`, `--ignore-rules`, `--sandbox read-only`, an isolated
  temporary `--cd`, `--skip-git-repo-check`, stdin prompt input,
  `--output-schema`, and `--output-last-message`.
- `claude`: run `claude -p` with `--safe-mode`, `--no-session-persistence`,
  `--permission-mode dontAsk`, `--tools ""`, `--output-format json`, and
  `--json-schema` from an isolated temporary working directory.

Require an argv invocation without a shell, a bounded timeout, exit-code and
stderr handling, JSON decoding, and output-schema validation. Do not expose the
Replica workspace or grant model tools. This runtime does not replace required
embedding, OCR, speech, audio, video, or side-effect dependencies. It is an
explicit execution overlay and may be used with an `oss_only` base scenario
without changing that scenario's ID, input, output, retrieval, storage, or
side-effect path. In that case declare the bundle `commercial_api` and include
the exact selected CLI dependency. Do not require `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` solely for the local CLI runtime; it uses the CLI's existing
authentication. A separate scenario API may still require its own credential.
If the executable or CLI authentication is unavailable, return `blocked`
instead of falling back to rules.

New technology choices, simpler alternatives, or changes to customer scope belong
in Second-pass research. Convert its selected path into concrete files, functions,
commands and corrections. If the research is insufficient, identify the missing
research and return a bound stop reason; do not replace or weaken the contract.
The public `runtime_contract` specifies the final runner transport and output-file
fields. Preserve it in the implementation instructions. For generated prose, test
required facts and invariants on repeats; exact calculations and permissions still
must be exact. The execution-state success criteria remain authoritative.

Give the Builder a complete execution plan. Identify the selected scenario,
implementation type, exact method, files, pinned dependencies and sources,
license constraints, required environment-variable names, ordered commands,
expected observations, artifact location, and validation expectations. Mark
each fidelity-critical dependency or side effect and require an actual runtime
check of the production path. When the workflow keeps user state between
calls (interview progress, conversation history, pending approvals, duplicate
suppression), store it under the working directory so `run-replica --state-dir`
can resume it. Test doubles may check an adapter boundary but
cannot satisfy a functional or claim criterion. Never include Second-pass test
expected behavior, reference facts, or original outputs in the instruction. Do
not delegate high-level strategy selection back to the Builder. For a model
runtime, require the manifest to declare the installed `codex-cli` or
`claude-code` version and official source.

Choose one candidate boundary:

- Use `claims/<claim-id>/builder/operator.json` only when the whole workflow is a
  pure JSON transformation expressible as one `replica-expression/v1` or
  restricted `replica-python/v1` component.
- Use `claims/<claim-id>/builder/implementation/manifest.json` for
  `replica-agent-claim/v2` and for any workflow that needs multiple files,
  imports, file or corpus access, OSS dependencies, a model or API adapter,
  state, or an external side effect. The manifest is
  `replica-implementation-bundle/v1` and its declared files are the candidate.

Copy the selected scenario's ID, input, and output byte-for-byte; never
summarize or normalize those manifest values. Keep its dependency level unless
the implementation actually declares the selected model CLI: that
promotes `oss_only` to `commercial_api`, while `commercial_api` and
`proprietary_data` remain unchanged. Do not ask for a self-declared
`replica-result.json`. A bundle is structurally bound as
`IMPLEMENTATION_READY` internally; the CLI then runs the separate final evaluation stage, which
determines whether it is reproduced. Do not run that evaluator from a Builder turn.

Write `instruction-NNN.json` in the Operator namespace using this exact contract
(unknown or omitted fields are invalid):

```json
{
  "message_type": "replica-operator-execution-instruction/v1",
  "claim_id": "<claim-id>",
  "sender_agent_id": "<operator-id>",
  "recipient_agent_id": "<builder-id>",
  "pair_nonce": "<claim-nonce>",
  "objective": "<claim-scoped objective>",
  "replication_strategy": "<evidence-bound strategy>",
  "implementation_instructions": ["<ordered concrete instruction>"],
  "implementation_actions": [
    {"action_type": "code|patch|execute", "content": "<exact action>"}
  ],
  "expected_result": "<observable result>",
  "expected_artifact": {
    "path": "<exact-selected-candidate-path>",
    "description": "the selected component or implementation-bundle candidate"
  },
  "validation_expectations": ["<specific check or command>"],
  "success_criteria": [
    {
      "id": "<criterion-id>",
      "what": "<what the check verifies>",
      "why": "<why the check is required>",
      "pass_condition": "<objective pass condition>",
      "fail_condition": "<objective fail condition>"
    }
  ],
  "responds_to_feedback_sha256": null,
  "correction_changes": [],
  "correction_number": 0
}
```

Before sending, run:

```text
replica-mvp agent-protocol-validate OPERATOR_MESSAGE \
  --claim-id CLAIM_ID \
  --operator-agent-id OPERATOR_ID \
  --builder-agent-id BUILDER_ID \
  --pair-nonce NONCE \
  --expected-correction-number CORRECTION_NUMBER
```

Copy the validated file byte-for-byte to
`mailbox/to-builder/instruction-NNN.json`. Do not send it to the Replica Agent
for forwarding, summarization, or rewriting, and do not include any part of it
in the control report.

Then send the Replica Agent only control metadata containing the bound IDs,
nonce, round number, correction number, the instruction's sha256, and a boolean
saying the instruction was written to the mailbox. End the turn.

## Analyze Builder feedback

On the next activation, read `mailbox/to-operator/feedback-NNN.json`. Accept it
only as `replica-builder-execution-feedback/v1` with the bound claim, pair
nonce, identities, and active correction number. Save the received JSON as
`feedback-NNN.json` inside the Operator namespace and run the same validation
command against that file. Reject a bare success/failure label or a feedback
message lacking concrete observations and artifact state.

After validation, atomically advance the Operator-owned state:

```text
replica-mvp agent-execution-advance \
  EXECUTION_STATE INSTRUCTION_MESSAGE FEEDBACK_MESSAGE
```

`SUCCESS` is valid only when every documented criterion, artifact validation,
normal, boundary, negative, structural, and relevant Judge check passes.
Aggregate labels such as `test_status: passed` do not override a failed
criterion. The state contains hashes and control summaries, not message bodies.

On `CORRECTION_REQUIRED`, analyze failed checks, errors, observed behavior,
artifact state, validation evidence, and diagnostics yourself. The correction
must reference the previous `feedback_sha256`, list concrete
`correction_changes`, and materially change strategy, instructions, actions,
code/patch, expected behavior, or execution method. Reuse the same Builder and
increment `correction_number` by exactly one. Never modify `claim.json`, the
Second JSON, tests, expectations, or success criteria.

A validated state may end earlier with `FAILED` for a documented blocking
requirement or exhausted/unverifiable budget. Honor that terminal and do not
repeat an unavailable resource. Otherwise correction 3 is the final retry. If its state is `FAILED`, write a terminal
`FAILED` control to `mailbox/to-builder/terminal.json`. Never create correction
4. If any attempt is `SUCCESS`, write terminal `SUCCESS` immediately with the
exact correction count; unused corrections are not executed.

On an explicit terminal decision, write that terminal control to the mailbox and
report it to the Replica Agent. The Builder acknowledges into
`mailbox/to-operator/terminal-ack.json`; read that ack on the following
activation and only then return final. If the peer disappears or the pair
binding changes before terminal, report continuity failure without spawning or
accepting a replacement.

Throughout the session, give the Replica Agent only control metadata: claim ID,
pair identities, nonce, correction number, mailbox write/read booleans, message
hashes, and validation success. Never include or summarize either semantic
message. Return a final control report only after the terminal ack.

## Divergence from the Codex route

The Codex counterpart is `.agents/skills/replica-operator-agent/SKILL.md`. There
this Agent stays inside one long turn and exchanges messages with the Builder
through a native peer primitive using bounded `wait_agent`. Claude has neither,
so the peer channel is the claim mailbox and each step is its own activation.
The strategy ownership, the correction cap, the criteria immutability, and the
non-relay rule are unchanged. Keep the two Skills in step when the contract
changes.

For a research bundle, also read the highest revision of
`claims/<claim-id>/runtime-contract-NNN.json`. This public Second-pass supplement
contains transport, output artifact fields, public input examples and public
asset sources; it never contains sealed inputs or expected outputs. Keep the
original claim and Builder context unchanged. Use the prepared public files and
examples for development; do not replace required real assets with descriptions.


On an identity activation with `preflight_recovery: true`, resume the same pair
following the repaired controls even if the previous preflight reached terminal.
The CLI has archived that terminal and pre-created an ACTIVE execution state;
do not recreate or reset it. Keep prior peer artifacts unchanged and use a
`preflight-recovery/` subdirectory inside your own namespace for the new direct
round artifacts. The Operator prepares and sends the instruction directly; the
Builder executes only that instruction. Preserve all frozen criteria and budgets.


A `packaging_retry` identity control follows the same agent-bundle-retry lifecycle:
reuse the pre-created ACTIVE state and use `packaging-retry-NNN/` for new direct
round artifacts in your own namespace. Keep prior exchanges unchanged. The
Operator and Builder diagnose packaging from their own development evidence and
direct messages, rerun checks, and complete a fresh direct terminal. Do not read
sealed evaluation evidence or assume a prior development pass is final success.


On `continuity_resume: true`, resume the existing in-flight correction and
execution state after its recorded control interruption. Do not recreate state,
reset budgets, discard completed rounds or repeat an earlier terminal report.
The Operator honors `await_peer_delivery: true` by waiting for the current direct
feedback; it must not return before that required receive. The Builder honors
`protocol_repair: "direct_delivery"` by validating its own current feedback and
sending it directly to the bound Operator, then returning only control metadata.
Use actual saved tests/evidence; do not invent a pass or send implementation
content in a parent-facing final. Missing evidence remains a failure. This is
one continuity recovery, not a new implementation attempt or permission to
read another namespace. The original correction limit remains in force.
