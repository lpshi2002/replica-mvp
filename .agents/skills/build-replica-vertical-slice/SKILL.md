---
name: build-replica-vertical-slice
description: Build and test one file-aware Replica vertical slice from a ready replica-second-pass-result/v1 contract. Use when a Replica needs local or public PDF, XLSX, CSV, image, OCR, retrieval, or an approved external API and therefore cannot run in the file-free build-replica-operator sandbox.
---

# Build Replica Vertical Slice

Build one ready claim end to end. Reuse `build-replica-operator` when the full
contract can run from JSON input without files, network, or external tools.
Do not build a generic document framework before a ready contract requires it.

## Establish boundaries

Use non-overlapping absolute roots:

- `WORKSPACE`: public task, prepared assets, implementation, and runnable output.
- `EVALUATION_VAULT`: original contract and frozen tests. Do not inspect it while building.
- `SECOND_PASS_JSON`: source outside `WORKSPACE`.

Treat the separation as structural, not cryptographic. Use only public or
explicitly approved assets. Never use credentials, customer documents, or
private company data without explicit authorization.

## Route before building

Read neither the source JSON nor frozen tests. Run the compiler first:

```text
python scripts/compile_contract.py SECOND_PASS_JSON \
  --workspace WORKSPACE \
  --evaluation-vault EVALUATION_VAULT
```

Read the returned public `request_path` only.

- If JSON input alone can satisfy every criterion, stop this workflow and use
  `.agents/skills/build-replica-operator/SKILL.md`.
- If files or approved external capabilities are required, continue here.
- If the contract is incomplete, not `ready`, or not `build`, stop without
  inventing missing behavior.

The compiler supports only `replica-second-pass-result/v1`. Do not guess a
mapping for a new team schema. Add a focused adapter only after receiving a
real sample and field definitions. See `references/pass2-field-mapping.md`.

## Materialize only required assets

Fill the generated `asset-requests.json` from verified public sources or an
explicit contract-provided synthetic fallback. Record unknown licenses as
unknown; do not infer permission. Then run:

```text
python scripts/materialize_assets.py TASK_DIR/asset-requests.json \
  --task-dir TASK_DIR
```

The materializer accepts `http`, `https`, and local files, writes content
hashes, and refuses to overwrite an existing manifest. Do not substitute an
unavailable required asset with unrelated data.

## Implement one claim-specific candidate

Create only:

```text
TASK_DIR/attempts/attempt-01/implementation/replica.py
```

Start from `assets/hybrid-implementation.py`. Implement the smallest pipeline
that satisfies the public request. Parse, calculate, and validate
deterministically. Use a model only for a criterion that cannot be evaluated
deterministically, ground every factual value in the supplied assets, and
return explicit insufficient-information output rather than guessing.

Do not hardcode fixture values, workbook row numbers, PDF page contents, or
hidden expected outputs. Do not open the evaluator vault.

## Run public development cases

Use only user-provided or public development inputs:

```text
python scripts/run_hybrid.py TASK_DIR \
  --attempt 1 \
  --input INPUT_JSON
```

The runner provides the input, `assets.json`, asset directory, and a candidate
output directory through the stdin envelope described in
`references/hybrid-runner-contract.md`. It is process isolation, not a secure
sandbox. Review new implementation dependencies and external effects before
execution.

## Freeze and evaluate

Keep candidate generation and evaluation separate. The Builder must not read
frozen inputs, expected values, per-case results, or evaluator-vault paths.
Use deterministic assertions first. Require an explicitly configured
independent Judge for semantic criteria; otherwise report the evaluation as
blocked instead of silently using the Builder.

Submit a frozen candidate through the private evaluator adapter:

```text
python scripts/evaluate_hybrid.py TASK_DIR \
  --evaluation-vault EVALUATION_VAULT \
  --attempt 1
```

Use only its sanitized status, failure class, and pass count. Do not open the
private artifacts it creates.

Allow at most three frozen candidate submissions. After a failure, reveal
only the failure class and pass count. Never change frozen expectations after
seeing output. Record `same-workspace` when stronger isolation is unavailable.

Stop after the first candidate that passes normal, boundary, and
insufficient-information cases. Report the public behavior reproduced,
assets and dependencies used, attempt count, isolation level, limitations,
and unsupported scope. Never claim equivalence with the private product.
