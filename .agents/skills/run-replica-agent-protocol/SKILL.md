---
name: run-replica-agent-protocol
description: Resume one ready Sol Operator and Terra Builder pair into a persistent direct claim session that completes only at an explicit terminal state. Use only after the Replica Agent harness has recorded the pair as READY_FOR_PROTOCOL.
---

# Run Replica Agent Protocol

Run this Skill only inside the same dedicated Replica Agent that created the
supplied `agent-harness.json`. Require the registry path. The Replica Agent may
update continuity control state only through the `agent-continuity-*` commands;
it must not edit the registry directly. The selected claim must be
`READY_FOR_PROTOCOL`, and this Replica Agent's canonical ID must match the
registry. Reject missing, replaced, or cross-claim Agent identities.

This Skill establishes lifecycle continuity only. It does not judge acceptance,
select a correction limit, implement correction reasoning, aggregate claims,
or create Final Replica JSON.

## Activate the existing pair

For one ready claim, reuse its recorded Operator and Builder. Never spawn a
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
  "persistent_claim_session": true
}
```

Tell each sibling to follow its existing claim Skill. Do not include strategy,
instructions, code, execution observations, or feedback in either activation.
Run `agent-continuity-start` with the exact pair IDs and nonce. The Sol
Operator sends `replica-operator-instruction/v1` directly to the Terra Builder.
The Builder sends `replica-builder-feedback/v1` directly to that Operator.
Both stay inside those activated turns and use bounded native `wait_agent`
between direct rounds. Do not issue another follow-up for a correction.

## Preserve the non-relay path

Accept only control metadata from the siblings: exact claim, stable pair IDs,
nonce, round number, direct send/receive flags, and local validation success.
Record each sequential round with `agent-continuity-round`. Reject a report
that contains or summarizes a semantic payload. If either child returns final
before terminal, run `agent-continuity-premature`, interrupt the remaining
peer, and stop without respawn.

Do not receive, forward, summarize, rewrite, or persist the instruction or
feedback in the Replica Agent registry. After a direct terminal exchange and
ack, run `agent-continuity-terminal`; only then may both child turns return
final. Leave the source Second JSON and every derived `claim.json` unchanged.
