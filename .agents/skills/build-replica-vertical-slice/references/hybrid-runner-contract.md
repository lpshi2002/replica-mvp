# Hybrid runner contract

`run_hybrid.py` starts `attempts/attempt-NN/implementation/replica.py` in an
isolated Python process and sends one JSON object on standard input:

```json
{
  "schema_version": "replica-hybrid-request/v1",
  "input": {},
  "assets": [],
  "assets_dir": "absolute task asset directory",
  "output_dir": "absolute candidate output directory"
}
```

The implementation must emit exactly one standard JSON value on stdout. It may
write generated files only below `output_dir` and should return paths relative
to that directory. Resolve each `assets[].materialized_path` below
`assets_dir`; do not use a source URL or source-local path at runtime.

The runner uses `python -I`, a minimal environment, a timeout, and an output
size limit. These controls do not prevent arbitrary filesystem or network
access by Python code. Review claim-specific code and dependencies before
running it. Do not pass evaluator-vault paths, frozen tests, secrets, or private
documents in the request.
