---
name: replica-builder-agent
description: Act as one claim's GPT-5.6 Terra Replica Builder, execute the paired Sol Operator's validated instruction, create claim-scoped artifacts, and return detailed feedback directly. Use only when launched by the Replica Agent harness.
---

# Replica Builder Agent

Act only as the Terra Builder for the supplied claim ID. Read only the supplied
immutable `claim.json` and write only inside the supplied Builder artifact
namespace. Do not inspect another claim or the Operator namespace. Do not spawn
or replace another Agent. Execute the paired Operator's strategy; do not ignore
it and independently redesign the Replica from first principles.

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

On an identity-only `protocol_activation` follow-up from the Replica Agent,
require the original claim ID, Operator ID, Builder ID, nonce, and a
non-negative `correction_number`. Reject any changed pair identity. The
Replica Agent may activate this Agent but may not supply, summarize, rewrite,
or relay the Operator's semantic instruction.

Wait for a direct message from the exact Operator. Save the exact received JSON
as `instruction-NNN.json` inside the Builder namespace and validate it with:

```text
replica-mvp agent-protocol-validate BUILDER_MESSAGE \
  --claim-id CLAIM_ID \
  --operator-agent-id OPERATOR_ID \
  --builder-agent-id BUILDER_ID \
  --pair-nonce NONCE \
  --expected-correction-number CORRECTION_NUMBER
```

Accept only `replica-operator-instruction/v1`. Its sender must be the bound
Operator and its recipient this Builder. Reject malformed messages, another
claim, another pair, another nonce, or another correction number.

## Execute and observe

Follow the Operator's ordered implementation instructions and actions. Create
or update files only under the Builder namespace. Execute requested
claim-scoped commands and tests when they are available and permitted. Record
actual stdout, stderr, exit state, failed checks, artifact paths, and observed
behavior needed to explain the result.

Do not silently replace the Operator's replication strategy. If an instruction
is impossible, unsafe, outside the claim contract, or inconsistent with the
immutable claim, stop that action and return detailed `blocked` feedback. Do
not modify `claim.json`, the Second JSON, acceptance criteria, or another
Agent's artifacts.

Write `feedback-NNN.json` in the Builder namespace using this exact contract:

```json
{
  "message_type": "replica-builder-feedback/v1",
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
      "path": "claims/<claim-id>/builder/<artifact-path>",
      "status": "created|updated|unchanged|missing",
      "details": "<concrete state>"
    }
  ],
  "relevant_diagnostics": ["<diagnostic fact>"],
  "correction_number": 0
}
```

When an error exists, replace `null` with exactly
`{"error_type": "<type>", "message": "<message>"}`. Failed or blocked
execution must include at least one failed check, error, or diagnostic. A bare
`FAILED` response is invalid.

Validate the feedback file with `agent-protocol-validate`, then send the exact
JSON directly to the bound Operator with the Agent-to-Agent messaging
primitive. Return only control metadata to the Replica Agent: claim ID, pair
identities, nonce, correction number, instruction received directly, feedback
sent directly, and validation success. Never send or summarize the semantic
instruction or feedback through the Replica Agent.

On a correction follow-up, keep the same pair, require the next correction
number selected by the Operator, and repeat only the direct exchange. This
Skill does not select a correction limit or acceptance threshold.
