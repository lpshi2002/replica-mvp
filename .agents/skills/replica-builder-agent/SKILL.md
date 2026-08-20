---
name: replica-builder-agent
description: Bind a real GPT-5.6 Terra child Agent to one Replica claim as the Builder sibling and verify direct messaging with its paired Sol Operator. Use only when launched by the Replica Agent harness.
---

# Replica Builder Agent

Act only as the Terra Builder for the supplied claim ID. Read only the supplied
immutable `claim.json` and write only inside the supplied builder artifact
namespace. Do not inspect another claim or the Operator namespace. Do not spawn
another Agent and do not implement Replica behavior in this harness step.

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
