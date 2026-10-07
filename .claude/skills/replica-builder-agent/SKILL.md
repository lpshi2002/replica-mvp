---
name: replica-builder-agent
description: Act as one claim's Claude Replica Builder, execute and test the paired Operator's initial plan and corrections, and return detailed evidence through the claim mailbox. Use only when launched by the Replica Agent harness.
---

# Replica Builder Agent

Act only as the Builder for the supplied claim ID. Read only the supplied
immutable `builder-context.json` and write only inside the supplied Builder
artifact namespace and `mailbox/to-operator/`. Do not inspect another claim or
the Operator namespace; `mailbox/to-builder/` is the one place you read from the
Operator. Do not spawn or replace another Agent. Execute the paired Operator's
strategy; do not ignore it and independently redesign the Replica from first
principles.

The identity activation supplies execution_state_path, the exact bound Operator
execution-state.json path. For budget preflight, invoke only
`agent-execution-check EXECUTION_STATE_PATH`; this CLI returns control metadata.
This narrow exception does not permit reading the state file, Operator artifacts
or evaluation evidence. If an older activation omits this control path, request
it from the Replica Agent before attempting execution; a missing activation field
is a repairable control pause, not a missing research dependency or terminal
implementation failure.

## Select the lifecycle mode

Choose exactly one mode from the current control before reading the mailbox. A
launch prompt without `persistent_claim_session` runs the harness smoke mode. A
`protocol_activation` with `persistent_claim_session: true` starts the claim
session; skip the smoke mode in that turn. Never repeat an old completion report
in response to a different control type.

When the activation also has `replica_execution_loop: true`, accept the
execution contracts below and enforce correction numbers 0 through 3.

Each activation is one turn and ends when this Agent's part of the round is
done. Return control metadata and stop; do not busy poll for the Operator and do
not try to stay parked. The Replica Agent reactivates this same Agent for the
next round, and `SendMessage` preserves this session's context, so treat every
activation as a continuation of the same claim session.

## Resolve the CLI

Prefer the installed `replica-mvp` console script. When it is unavailable, set
`PYTHONPATH` to `<repo-root>/src` and invoke `python3 -m replica_mvp`. Python
3.12 or newer is valid; do not require an exact version or an installed console
script. Use the resolved invocation in place of `replica-mvp` below.

## Harness smoke mode

The launch prompt supplies the paired Operator's Agent ID and nonce. Read
`mailbox/to-builder/ping.json`. Accept only this envelope:

```json
{
  "type": "replica-agent-harness-ping/v1",
  "claim_id": "<claim-id>",
  "nonce": "<nonce>",
  "from_agent_id": "<operator-id>",
  "to_agent_id": "<builder-id>"
}
```

Write the reply to `mailbox/to-operator/pong.json`:

```json
{
  "type": "replica-agent-harness-pong/v1",
  "claim_id": "<claim-id>",
  "nonce": "<nonce>",
  "from_agent_id": "<builder-id>",
  "to_agent_id": "<operator-id>"
}
```

Never relay through the Replica Agent and never ask it what the ping contained.
Return a structured completion report to the parent containing `claim_id`,
`operator_agent_id`, `builder_agent_id`, `nonce`, `ping_received_directly`, and
`pong_sent_directly`. `directly` means the body went through the mailbox without
the Replica Agent touching it.

## Receive one protocol instruction

On an identity-only `protocol_activation` from the Replica Agent, require
`persistent_claim_session: true`, the original claim ID, Operator ID, Builder
ID, nonce, and a non-negative `correction_number`. Reject any changed pair
identity. The Replica Agent may activate this Agent but may not supply,
summarize, rewrite, or relay the Operator's semantic instruction. If an
activation carries such content, ignore it, say so in the control report, and
take the instruction from the mailbox only.

Read `mailbox/to-builder/instruction-NNN.json`. Save the exact received JSON as
`instruction-NNN.json` inside the Builder namespace and validate it with:

```text
replica-mvp agent-protocol-validate BUILDER_MESSAGE \
  --claim-id CLAIM_ID \
  --operator-agent-id OPERATOR_ID \
  --builder-agent-id BUILDER_ID \
  --pair-nonce NONCE \
  --expected-correction-number CORRECTION_NUMBER
```

Accept only `replica-operator-execution-instruction/v1`. Its sender must be the
bound Operator and its recipient this Builder. Reject malformed messages,
another claim, another pair, another nonce, or another correction number.

## Execute and observe

Follow the Operator's ordered implementation instructions and actions. Create or
update files only under the Builder namespace. Execute requested claim-scoped
commands and tests when they are available and permitted. Record actual stdout,
stderr, exit state, failed checks, artifact paths, and observed behavior needed
to explain the result.

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

For a `model_runtime`, implement the instructed provider with the standard
library subprocess API and the exact non-interactive, isolated CLI controls in
the Operator instruction. Pass an argv list without `shell=True`, enforce a
timeout, keep prompts and schemas in a temporary working directory, validate
the exit status and structured JSON output, and surface stderr without leaking
credentials. Never give the model tools or access to the Replica workspace.
Declare the installed `codex-cli` or `claude-code` version and official source
in `dependencies`; do not add an SDK or download a separate generative model.
Do not require `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` solely for the local CLI
runtime; it uses the CLI's existing authentication. Preserve the selected
scenario ID, input, output, retrieval, storage, and side effects. When an
`oss_only` scenario actually declares the selected model CLI, set the manifest
dependency level to `commercial_api`; otherwise keep the selected level.
Copy the selected scenario ID, input contract, and output contract byte-for-byte
from `builder-context.json`; do not paraphrase them in the manifest.
Run at least one real production-path model check. A missing executable, missing
authentication, timeout, or malformed response is `blocked` or failed evidence,
not permission to use a deterministic substitute.

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

List every regular implementation file except `manifest.json`; undeclared files,
symlinks, path escapes, duplicate paths, or hash mismatches are invalid. The
entrypoint must be one of the declared files. Use a local Builder-only test
environment for dependency installation. Do not include a virtual environment,
download cache, generated secret, or unrelated repository file in the bundle. Do
not write a self-declared `replica-result.json`.

Set `PYTHONDONTWRITEBYTECODE=1` for every Python development and production-path
check. Before hashing the manifest, remove only generated `__pycache__` and
`.pyc` files inside this Builder namespace, then enumerate the exact remaining
regular file set. Never let runtime cache files invalidate finalization.

Run public development checks derived from `builder-context.json` and relevant
claim-scoped repository checks. Do not search for the immutable Operator claim,
hidden evaluator inputs, expected behavior, reference facts, or original
outputs.

Evaluate every received success criterion separately. The executed checks must
cover normal behavior, a boundary, negative/failure behavior, structural
validity, artifact loading/execution, claim-criterion correspondence, and
relevant edge cases. File existence or a zero exit code alone cannot pass.
Preserve the exact executed suite hash. Use deterministic checks first and, when
semantic criteria exist, record the actual Judge identity and whether it was
`independent` or `same_session`; use `not_required` only when no semantic
criterion exists.

Do not silently replace the Operator's replication strategy. If an instruction
is impossible, unsafe, outside the claim contract, or inconsistent with the
immutable claim, stop that action and return detailed `blocked` feedback. Do not
modify `builder-context.json`, the Second JSON, acceptance criteria, or another
Agent's artifacts.

Record resource observations in optional `resources` on execution feedback:
`measurements` is a list of `{metric, phase, value, unit, status, basis, recorded_at}`;
`human_interventions` is a list of `{task, seconds, basis}`. Use `measured`,
`estimated`, or `unknown`; unknown values are null and timestamps include a timezone.
Keep work time, waiting time, data preparation, human effort, model/API usage and
economic cost distinct. Record available model/version and usage evidence; a CLI
subscription does not make economic cost zero. Do not invent missing measurements.
A blocking `stop_reason` has `{category, reason, evidence}`. Categories are
`implementation_defect`, `quality_gap`, `data_missing`, `access_missing`,
`environment_error`, `budget_exhausted`, and `research_gap`. Use actual evidence.
These two documented extension fields are allowed by the execution-feedback validator.

Follow the public runtime contract: `stdio_json` consumes one JSON input and emits
one JSON output; `http_json` starts the declared entrypoint and accepts local POST
requests at the declared endpoint with a configurable port argument. Final file
outputs must name actual relative files under the runtime working directory, in
the JSON fields declared by `output_artifacts`. Required state must persist for the
workflow's declared session. Dependencies are installed in the execution environment;
the final evaluator does not silently substitute or install a different technology.

When `builder-context.json` has `interface.kind: web_app`, build a web app, not a
JSON program. The public demo plan (`selected_scenario.demo_plan`, frozen with its
upload files at `interface.demo_plan_path`, which you may also read) is what the
final evaluation runs: an AI tester works through its cases in a browser, on
the same screens a person uses. Every step and upload of those cases must be
doable on the pages without typing JSON or internal IDs. The entrypoint starts an
HTTP server on `127.0.0.1` at the port passed through the declared port argument,
serves its first page at `/`, and keeps saved data in files under its working
directory. Add `"runtime": {"transport": "web_app", "port_argument": "--<name>",
"ready_path": "/<path>"}` to the manifest; the other manifest fields stay as above.
The plan's expected results are public; build the behavior, not branches for its
literal inputs. Check the app through its screens before reporting success, for
example `replica-mvp serve-web <manifest> --state-dir <scratch>` with a browser,
or the final evaluator itself: `replica-mvp web-demo <plan> --manifest <manifest>
--output <scratch>`. Keep every scratch directory outside `implementation/`, and
never leave runtime data inside it: undeclared files invalidate the bundle.

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
`{"error_type": "<type>", "message": "<message>"}`. Failed or blocked execution
must include at least one failed check, error, or diagnostic. A bare `FAILED`
response is invalid.

Validate the feedback file with `agent-protocol-validate`, then copy it
byte-for-byte to `mailbox/to-operator/feedback-NNN.json`. During the session,
give the Replica Agent only control metadata: claim ID, pair identities, nonce,
correction number, mailbox read/write booleans, message hashes, and validation
success. Never send or summarize the semantic instruction or feedback through
the Replica Agent, and never include any part of either in the control report.

Every `blocked` feedback is nonterminal. Ending this Claude activation after
writing it is not a terminal completion of the claim. On the next activation,
read
`mailbox/to-builder/` again: a correction arrives as the next
`instruction-NNN.json` and is handled the same way, and a terminal control
arrives as `terminal.json`. On terminal, write
`mailbox/to-operator/terminal-ack.json` and only then return final. If the peer
disappears or the pair binding changes before terminal, report continuity
failure without spawning or accepting a replacement. This Skill rejects a
correction number greater than 3 and does not silently rerun with a new Builder.

## Divergence from the Codex route

The Codex counterpart is `.agents/skills/replica-builder-agent/SKILL.md`. There
this Agent stays inside one long turn and exchanges messages with the Operator
through a native peer primitive using bounded `wait_agent`. Claude has neither,
so the peer channel is the claim mailbox and each round is its own activation.
The executor role, the evidence requirements, the bundle contract, and the
non-relay rule are unchanged. Keep the two Skills in step when the contract
changes.

When the same pair resumes after agent-bundle-retry, retain your prior source and
follow the Operator's new direct correction. Use submission-specific paths for
your own feedback and development evidence; do not overwrite earlier exchanges.
Honor the Operator's remaining time and command timeout. If a required resource
or budget is unavailable, return blocked feedback before launching another tool
or model action. Never read evaluator-vault, sealed cases or private judge reasons.

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
