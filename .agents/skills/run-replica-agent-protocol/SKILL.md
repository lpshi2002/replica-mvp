---
name: run-replica-agent-protocol
description: Resume a ready Sol Operator and Terra Builder pair for one direct claim-scoped implementation instruction and detailed execution feedback exchange. Use only after the Replica Agent harness has recorded the pair as READY_FOR_PROTOCOL.
---

# Run Replica Agent Protocol

Run this Skill only inside the same dedicated Replica Agent that created the
supplied `agent-harness.json`. Require the registry path and read it without
modifying it. Every selected claim must be `READY_FOR_PROTOCOL`, and this
Replica Agent's canonical ID must match the registry. Reject missing, replaced,
or cross-claim Agent identities.

This Skill connects one initial role-execution exchange. It does not judge
acceptance, select a correction limit, run a correction loop, aggregate
claims, or create Final Replica JSON.

## Activate the existing pair

For each ready claim, reuse its recorded Operator and Builder. Never spawn a
protocol or correction replacement. Activate the Builder first with
`followup_task` so it is waiting for the direct instruction, then activate the
Operator. Give both only this identity control envelope:

```json
{
  "type": "protocol_activation",
  "claim_id": "<claim-id>",
  "operator_agent_id": "<operator-id>",
  "builder_agent_id": "<builder-id>",
  "nonce": "<claim-nonce>",
  "correction_number": 0
}
```

Tell each sibling to follow its existing claim Skill. Do not include strategy,
instructions, code, execution observations, or feedback in either activation.
The Sol Operator sends `replica-operator-instruction/v1` directly to the Terra
Builder. The Builder executes it and sends `replica-builder-feedback/v1`
directly to the same Operator.

## Preserve the non-relay path

Wait only for each sibling's control-metadata report. Require the exact claim,
pair identities, nonce, correction number, direct send/receive flags, and local
contract-validation success. Reject a report that contains or summarizes a
semantic payload.

Do not receive, forward, summarize, rewrite, or persist the instruction or
feedback in the Replica Agent registry. Stop after one validated initial
instruction/feedback exchange per selected claim. Leave the source Second JSON
and every derived `claim.json` unchanged.
