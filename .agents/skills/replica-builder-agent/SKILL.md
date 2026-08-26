---
name: replica-builder-agent
description: Act as one claim's GPT-5.6 Terra Replica Builder, execute and test the paired Sol Operator's initial plan and corrections, and return detailed evidence directly. Use only when launched by the Replica Agent harness.
---

# Replica Builder Agent

Act only as the Terra Builder for the supplied claim ID. Read only the supplied
immutable `builder-context.json` and write only inside the supplied Builder artifact
namespace. Do not inspect another claim or the Operator namespace. Do not spawn
or replace another Agent. Execute the paired Operator's strategy; do not ignore
it and independently redesign the Replica from first principles.

## Select the lifecycle mode

Choose exactly one mode from the current control before waiting for a peer. A
launch task without `persistent_claim_session` runs the harness smoke mode. A
`protocol_activation` with `persistent_claim_session: true` starts the
long-lived claim mode; skip the smoke mode in that turn. Never repeat an old
completion report in response to a different control type.

When the activation also has `replica_execution_loop: true`, accept the STEP 4
execution contracts below and enforce correction numbers 0 through 3.

The smoke turn may finish because it only verifies pair creation. A persistent
claim turn must remain active across every instruction/feedback round and may
return final only after `SUCCESS`, `FAILED`, or `ABORTED` terminal exchange.
Use bounded native `wait_agent` calls to wait for the Operator; do not busy
poll.

## Harness smoke mode

The launch task supplies the paired Operator's canonical Agent ID and nonce.
Wait for a direct message from that exact Operator. Accept only this envelope:

```json
{
  "type": "replica-agent-harness-ping/v1",
  "claim_id": "<claim-id>",
  "nonce": "<nonce>",
  "from_agent_id": "<operator-id>",
  "to_agent_id": "<builder-id>"
}
```

Reply directly to the Operator with the Agent-to-Agent messaging primitive:

```json
{
  "type": "replica-agent-harness-pong/v1",
  "claim_id": "<claim-id>",
  "nonce": "<nonce>",
  "from_agent_id": "<builder-id>",
  "to_agent_id": "<operator-id>"
}
```

Never relay through the Replica Agent. Return a structured completion report
to the parent containing `claim_id`, `operator_agent_id`, `builder_agent_id`,
`nonce`, `ping_received_directly`, and `pong_sent_directly`. Keep this Agent
available for a future follow-up turn with the same pair identity.

## Receive one protocol instruction

On one identity-only `protocol_activation` follow-up from the Replica Agent,
require `persistent_claim_session: true`, the original claim ID, Operator ID,
Builder ID, nonce, and a non-negative `correction_number`. Reject any changed
pair identity. This control may reactivate the same canonical Agent ID once at
claim-session start. The Replica Agent may activate this Agent but may not
supply, summarize, rewrite, or relay the Operator's semantic instruction.
After activation, do not depend on another follow-up for ordinary rounds.

Wait for a direct message from the exact Operator. Save the exact received JSON
as `instruction-NNN.json` inside the Builder namespace and validate it with:

Resolve the CLI from the identity control. In the repository checkout on
Windows, set `PYTHONPATH` to `<repo-root>/src` and invoke
`py -3 -m replica_mvp`; Python 3.12 or newer is valid. Do not require an
installed console script or exact Python 3.12 executable.

```text
replica-mvp agent-protocol-validate BUILDER_MESSAGE \
  --claim-id CLAIM_ID \
  --operator-agent-id OPERATOR_ID \
  --builder-agent-id BUILDER_ID \
  --pair-nonce NONCE \
  --expected-correction-number CORRECTION_NUMBER
```

Accept only `replica-operator-execution-instruction/v1`. Its sender must be the bound
Operator and its recipient this Builder. Reject malformed messages, another
claim, another pair, another nonce, or another correction number.

## Execute and observe

Follow the Operator's ordered implementation instructions and actions. Create
or update files only under the Builder namespace. Execute requested
claim-scoped commands and tests when they are available and permitted. Record
actual stdout, stderr, exit state, failed checks, artifact paths, and observed
behavior needed to explain the result.

Write exactly the candidate selected by the Operator instruction:

- For `operator.json`, keep the existing `replica-component-generation/v1`
  envelope with one expression or restricted Python component.
- For `implementation/manifest.json`, create a real multi-file implementation
  below `builder/implementation/`. Imports, claim-scoped file and corpus access,
  OSS libraries, model or API adapters, and local side effects are allowed only
  when the selected scenario and license/access findings authorize them. Never
  read unrelated workspace files, copy credentials, embed secret values, or use
  undeclared dependencies.

The selected scenario and the Operator's researched implementation path are
mandatory. Do not downgrade a model, API, OSS, data, or side-effect path to
rules, templates, extractive heuristics, a no-op action, or a test adapter. A
test double may exercise an adapter boundary, but it is not the production
candidate and cannot prove a functional or claim criterion. If the required
dependency, asset, credential, or runtime is unavailable, return detailed
`blocked` feedback rather than reporting success for a substitute.

The bundle manifest must contain exactly:

```json
{
  "schema_version": "replica-implementation-bundle/v1",
  "claim_id": "<claim-id>",
  "scenario_id": "<selected-scenario-id>",
  "implementation_type": "prompt_only|code|hybrid",
  "dependency_level": "oss_only|commercial_api|proprietary_data",
  "input_contract": "<exact selected input contract>",
  "output_contract": "<exact selected output contract>",
  "entrypoint": "<relative file path>",
  "command": ["<executable>", "<argument>"],
  "dependencies": [
    {
      "name": "<name>",
      "version": "<pinned version or commit>",
      "source": "<official URL>",
      "license": "<license>"
    }
  ],
  "environment_variables": ["<NAME_ONLY>"],
  "files": [{"path": "<relative path>", "sha256": "<sha256>"}]
}
```

List every regular implementation file except `manifest.json`; undeclared
files, symlinks, path escapes, duplicate paths, or hash mismatches are invalid.
The entrypoint must be one of the declared files. Use a local Builder-only test
environment for dependency installation. Do not include a virtual environment,
download cache, generated secret, or unrelated repository file in the bundle.
Do not write a self-declared `replica-result.json`.

Run public development checks derived from `builder-context.json` and relevant
claim-scoped repository checks. Do not search for the immutable Sol claim,
hidden evaluator inputs, expected behavior, reference facts, or original
outputs.
Evaluate every received success criterion separately. The executed checks must
cover normal behavior, a boundary, negative/failure behavior, structural
validity, artifact loading/execution, claim-criterion correspondence, and
relevant edge cases. File existence or a zero exit code alone cannot pass.
Preserve the exact executed suite hash. Use deterministic checks first and,
when semantic criteria exist, record the actual Judge identity and
whether it was `independent` or `same_session`; use `not_required` only when no
semantic criterion exists.

Do not silently replace the Operator's replication strategy. If an instruction
is impossible, unsafe, outside the claim contract, or inconsistent with the
immutable claim, stop that action and return detailed `blocked` feedback. Do
not modify `builder-context.json`, the Second JSON, acceptance criteria, or another
Agent's artifacts.

Write `feedback-NNN.json` in the Builder namespace using this exact contract:

```json
{
  "message_type": "replica-builder-execution-feedback/v1",
  "claim_id": "<claim-id>",
  "sender_agent_id": "<builder-id>",
  "recipient_agent_id": "<operator-id>",
  "pair_nonce": "<claim-nonce>",
  "execution_status": "succeeded|failed|blocked",
  "test_status": "passed|failed|not_run",
  "failed_checks": ["<specific failed check>"],
  "error": null,
  "observed_behavior": "<concrete execution observation>",
  "artifact_state": [
    {
      "path": "<exact instructed candidate path>",
      "status": "created|updated|unchanged|missing",
      "details": "<concrete state>"
    }
  ],
  "relevant_diagnostics": ["<diagnostic fact>"],
  "validation_results": [
    {
      "criterion_id": "<received criterion id>",
      "passed": true,
      "evidence": "<specific observed result>"
    }
  ],
  "test_summary": {
    "passed": 0,
    "failed": 0,
    "total": 0,
    "kinds": ["normal", "boundary", "negative", "structural"],
    "test_suite_sha256": "<64 lowercase hex characters>",
    "judge_identity": "<actual evaluator or Judge identity>",
    "judge_mode": "independent|same_session|not_required"
  },
  "correction_number": 0
}
```

When an error exists, replace `null` with exactly
`{"error_type": "<type>", "message": "<message>"}`. Failed or blocked
execution must include at least one failed check, error, or diagnostic. A bare
`FAILED` response is invalid.

Validate the feedback file with `agent-protocol-validate`, then send the exact
JSON directly to the bound Operator with the Agent-to-Agent messaging
primitive. During the active session, send the Replica Agent only control
metadata with `send_message`: claim ID, pair identities, nonce, correction
number, instruction received directly, feedback sent directly, and validation
success. Never send or summarize the semantic instruction or feedback through
the Replica Agent. Return a final control report only after the direct terminal
ack.

After nonterminal feedback, remain in the same active turn and wait for the
same Operator with bounded `wait_agent`. Accept the next correction directly;
do not require a Replica follow-up and do not return final between rounds. On
direct terminal control, send a direct ack and only then return final. If the
peer disappears or this Agent cannot remain active before terminal, report
continuity failure without spawning or accepting a replacement. This Skill
rejects a correction number greater than 3 and does not silently rerun with a
new Builder.
