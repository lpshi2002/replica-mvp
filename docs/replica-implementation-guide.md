# Implementation and evaluation commands

Use `PYTHONPATH=src python3 -m replica_mvp` from the repository root in place of
`replica-mvp` when the package is not installed. All paths below are placeholders.

## Work with a bounded context

Start from `implementation-context.json` and the current runtime contract. Its
`selected_scenario` is the complete implementation contract; other scenarios are
an index, with `claim.json` available when an omitted research fact is needed.
For older contexts containing full `available_scenarios`, extract the selected
scenario and interface with a JSON reader instead of printing that duplicate list.

Keep `implementer/current-state.md` under roughly 80 lines: bundle path, completed
work, current failure, checks and exit codes, owned process IDs, and the next step.
Refresh it after a meaningful milestone and before compaction. Resume from that
file and targeted source ranges; retain the append-only development log as history.
Search filenames/symbols first and read the relevant ranges. Save long logs to
scratch files and inspect the failing section. Stop a process using its own PID.

Claude project settings use a 120,000-token auto-compact window. This is an initial
operational choice, not a measured optimum or a guaranteed cost reduction. Existing
sessions may need to reload settings; check `/autocompact` when continuing them.
The supported setting and precedence are documented in the
[Claude model configuration](https://code.claude.com/docs/en/model-config#set-the-auto-compact-window).

## Package without source archaeology

Create `implementation/manifest.json` with exactly these fields. Copy the selected
scenario's `input` and `output` into the contract fields without changing them.
List each source file with its SHA-256; keep scratch data outside the bundle.

```json
{
  "schema_version": "replica-implementation-bundle/v1",
  "claim_id": "claim-001",
  "scenario_id": "<selected scenario id>",
  "implementation_type": "hybrid",
  "dependency_level": "commercial_api",
  "input_contract": "<copy selected_scenario.input with its original type>",
  "output_contract": "<copy selected_scenario.output with its original type>",
  "entrypoint": "app.py",
  "command": ["python3", "app.py"],
  "dependencies": [],
  "environment_variables": [],
  "files": [{"path": "app.py", "sha256": "<actual file hash>"}],
  "runtime": {"transport": "web_app", "port_argument": "--port",
              "base_path_argument": "--base-path", "ready_path": "/health"}
}
```

A company-app feature (`interface.mount_path` in the context) is started as
`python3 app.py --port 51234 --base-path /claim-001` and must answer every page,
asset, form action, request and redirect under `/claim-001/`; `ready_path` is
relative to that base path. The shared shell serves the feature menu at `/` and
adds a sidebar and a shared stylesheet to each HTML page; the stylesheet styles
plain HTML elements, so a feature needs little or no CSS of its own. Omit `base_path_argument` only when the
context has no `mount_path`. To see the whole company app with every bound feature:

```sh
replica-mvp serve-company REGISTRY --open
```

Use the contract's dependency level; dependencies, when present, have `name`,
`version`, `source` (HTTP/S URL), and `license`. For a JSON runtime omit `runtime`.
Check packaging before a model-backed test, without changing the registry:

```sh
replica-mvp agent-bundle-check RUN_DIR CLAIM_ID MANIFEST
```

## Test the changed behavior

Run local deterministic checks first. When an AI browser check is needed, select
the affected cases; repeat `--case` to select several. Every output directory must
be new. A partial selection cannot establish full reproduction.

```sh
replica-mvp web-demo PLAN --manifest MANIFEST --output NEW_SCRATCH --case CASE_ID
```

`--tester-model`, `--judge-model`, `--instance-model`, and `--code-review-model`
override roles independently. Omission preserves the existing provider default;
record a model change explicitly instead of silently lowering judgment quality.
The tester observes field length and checked state, can read a long field in
chunks, and uses `wait_for` on visible text or one long `wait` for a known timer.
Waiting polls the browser locally without additional model calls.

The orchestrator imports every development demo for cumulative cost reporting:

```sh
replica-mvp agent-development-register REGISTRY CLAIM_ID SCRATCH
```

Final evaluation runs the entire frozen plan. On a provider limit, the shared
run gate stops later model calls. Retain the bundle and stop retrying until the
provider is available. The orchestrator resumes evaluation with:

```sh
replica-mvp agent-web-recover REGISTRY CLAIM_ID --reason "provider available" --clear-usage-limit
```

Omit `--clear-usage-limit` unless the provider reset is known. Recovery preserves
old results and uses the same bound bundle/plan. The same evaluator/settings reuse
verified completed cases and drawn inputs; an evaluator/settings change keeps the
inputs but obtains fresh evidence. Interrupted cases restart from their beginning.
Same-version continuation retains the remaining active evaluation time budget;
a changed evaluator records a new observation budget. A quota pause between runs
does not consume it. Single-implementer development time also stops at bind and
resumes on implementation retry; unknown idle time inside a live worker is retained.

Use `agent-bundle-retry` only for an actual implementation failure. A web evaluation
interruption uses recovery, without reopening implementation or consuming another
candidate submission. Three distinct evaluated candidates remain the limit.
