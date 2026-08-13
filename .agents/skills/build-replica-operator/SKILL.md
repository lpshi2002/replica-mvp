---
name: build-replica-operator
description: Build, repair, test, and publish a new evidence-bound Replica operator from a ready replica-second-pass-result/v1 JSON. Use whenever a Second-pass Result arrives and the user asks Codex to implement or run the Replica. This workflow never selects a registered operator and never calls an API model generator.
---

# Build Replica Operator

Turn one ready Second-pass Result into a newly written operator. Keep Codex's
public work area separate from the evaluator vault that contains the original
JSON, frozen tests, per-case outputs, and judge results.

## Establish the two roots

Use two non-overlapping absolute paths:

- `WORKSPACE`: Codex-visible task files and the published runnable Replica.
- `EVALUATION_VAULT`: private evaluator state outside `WORKSPACE`, preferably
  outside the repository.
- `SECOND_PASS_JSON`: an incoming source file outside `WORKSPACE`.

Never place either root inside the other. Do not open, search, list, or edit the
evaluator vault while writing or repairing an operator. Preparation rejects a
Second-pass source located inside the public workspace.

## Prepare the task

Accept the Second-pass JSON path without opening the file and run:

```text
replica-mvp prepare-operator SECOND_PASS_JSON \
  --workspace WORKSPACE \
  --evaluation-vault EVALUATION_VAULT
```

The deterministic preparation command validates the Second-pass contract,
stores the source and frozen tests only in the evaluator vault, and returns a
public `request_path`, `operator_path`, and `task_dir`.

After preparation, use only the returned request as generation input. Do not
read the original Second-pass file, any intake directory, frozen test,
expected output, evaluator result, or private run.

## Write a new operator

Read the complete `operator-request.json`. Derive behavior only from its
canonical claim, contracts, acceptance criteria, supported scope, unsupported
scope, limitations, and implementation instructions.

Write `operator.json` at the returned path with this envelope:

```json
{
  "schema_version": "replica-component-generation/v1",
  "generator_identity": "codex-skill/build-replica-operator/v1",
  "component": {
    "schema_version": "replica-generated-component/v1",
    "language": "replica-expression/v1 or replica-python/v1",
    "input_contract": {},
    "output_contract": {}
  }
}
```

Copy `input_contract` and `output_contract` exactly from the request.

- Prefer `replica-expression/v1` when its advertised operators express the
  entire contract.
- Use `replica-python/v1` when control flow is required. Define
  `replicate(runtime_input)` and obey the advertised syntax, builtin, method,
  size, time, and memory limits.
- Use only caller-supplied runtime input and contract constants.
- Return explicit insufficient-information output for missing required input.
- Do not import, access files or networks, spawn processes, call models, add
  private-company assumptions, or broaden supported scope.
- Always write a new generated component. A supplied implementation is only a
  non-binding evidence hint, never an executable registered operator.

## Finalize and repair

Run:

```text
replica-mvp finalize-operator TASK_DIR \
  --workspace WORKSPACE \
  --evaluation-vault EVALUATION_VAULT \
  --report
```

Use only the sanitized status returned by the command:

- `BUILT_AND_PASSED`: finish. The returned `run_dir` is the public runnable
  Replica, not the private evaluator run.
- `VALIDATION_FAILED`: replace `operator.json` with a contract-valid version.
- `RUNTIME_FAILED`: replace it with a safer implementation.
- `EVALUATION_FAILED`: revise from the contract using only the pass count.

Repeat only while `retryable` is true. The limit is three total attempts,
including the initial implementation, so at most two repair attempts follow
the first failure. Do not edit task metadata, the request, attempt history,
tests, expectations, evaluator, or acceptance criteria.

## Verify the publication boundary

Before reporting success, confirm that the public run does not contain:

- `second-pass.json`
- `tests.json`
- `test-suite-lock.json`
- `replica_outputs.jsonl`
- `results.jsonl`

Report the implemented capability, final status, attempt count, public Replica
path, supported scope, and limitations. Call it an evidence-bounded Replica,
not an equivalent copy of the company's private system.

This directory separation prevents accidental test disclosure through normal
Codex inputs and outputs. It is not a cryptographic security boundary when
Codex and the evaluator run under the same operating-system user.
