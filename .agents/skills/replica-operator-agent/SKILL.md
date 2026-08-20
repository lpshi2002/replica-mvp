---
name: replica-operator-agent
description: Bind a real GPT-5.6 Sol child Agent to one Replica claim as the Operator sibling and verify direct messaging with its paired Terra Builder. Use only when launched by the Replica Agent harness.
---

# Replica Operator Agent

Act only as the Sol Operator for the supplied claim ID. Read only the supplied
immutable `claim.json` and write only inside the supplied operator artifact
namespace. Do not inspect another claim or the Builder namespace. Do not spawn
a Builder and do not implement a Replica strategy in this harness step.

Wait for an identity-only `peer_binding` control message from the parent
Replica Agent. It must contain this claim ID, the paired Builder's canonical
Agent ID, and a nonce. Reject any conflicting binding.

Send this structured message directly to that Builder with the Agent-to-Agent
messaging primitive:

```json
{
  "type": "replica-agent-harness-ping/v1",
  "claim_id": "<claim-id>",
  "nonce": "<nonce>",
  "from_agent_id": "<operator-id>",
  "to_agent_id": "<builder-id>"
}
```

Wait for a direct message from the same Builder. Accept only
`replica-agent-harness-pong/v1` with the exact claim ID, nonce, and reversed
from/to identities. Do not ask the Replica Agent to relay it.

Return a structured completion report to the parent containing `claim_id`,
`operator_agent_id`, `builder_agent_id`, `nonce`, `ping_sent_directly`, and
`pong_received_directly`. Keep this Agent available for a future follow-up turn
with the same pair identity.
