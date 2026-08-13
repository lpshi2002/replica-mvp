# Pass 2 field mapping

The deterministic compiler currently accepts only
`replica-second-pass-result/v1`.

| Source field | Public build artifact |
|---|---|
| company, capability, canonical_claim, evidence_level | `evidence.json` |
| input_contract, output_contract | `spec.json` |
| acceptance_criteria | `spec.json` and `builder-request.json` |
| supported_scope, unsupported_scope, limitations | `spec.json` and `builder-request.json` |
| implementation | non-binding hint in `builder-request.json` |
| tests | private `tests.json` and `test-suite-lock.json` |

The current schema has no authoritative asset-source collection. Populate the
public `asset-requests.json` only from verified sources supplied alongside the
contract. Do not infer URLs, licenses, or synthetic fallback rules.

When the real team Pass 2 schema arrives, add a narrow adapter that maps its
frozen `replication_contract` to the fields above. Preserve the original input,
reject placeholders, and add tests for that exact schema before expanding the
compiler.
