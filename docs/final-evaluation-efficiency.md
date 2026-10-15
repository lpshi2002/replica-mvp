# Final evaluation efficiency

The browser tester can plan several actions on the currently observed UI. The
runner still executes and records each action separately. It cancels a plan's
remaining actions on an unexpected UI change or failed postcondition and asks
the tester again with fresh evidence. Semantic judgment remains a separate
model call per case. A plan is not a cached result or a replacement for testing
the app through its screens.

Before each planned action, including the first after a model response, the
runner checks the original DOM node and compares the page with the observation
used for planning. Changes to other field values, disabled/read-only state,
options, ARIA state, page text or navigation cancel the remaining actions.
Each accepted field action is checked against its full resulting value. A fill
followed by Enter on the same field is allowed; two submissions are not.
Dialogs, transient alerts, console errors and popups are recorded and passed to
the independent judge. An `effect.status=ok` confirms input acceptance only.

`wait_for` uses text already observed on the UI and a bounded timeout. A new
result or unobserved condition returns control to the tester. Evidence or page
observation failure blocks the case. Exhausting model decisions is reported as
`model_call_limit`, separately from the atomic `action_limit`.

`web-demo`, `agent-bundle-evaluate` and `agent-web-recover` accept:

- `--tester-mode plan` (default) or `single` for one model decision per action.
- `--cache-ttl 5m` (default), `1h`, or `inherit`. This controls only Claude
  evaluation subprocesses, not global settings or the candidate's model calls.
- `--stable-model-prefix` opts into Claude's
  `--exclude-dynamic-system-prompt-sections`. This changes message placement and
  is **not enabled by default**; validate behavior before adopting it.
- Existing role-specific model flags remain independent. Do not silently lower
  judge quality when comparing tester costs.

The effective tester mode and cache options are recorded in evaluation
identity. Changing them requires fresh observations; it cannot reuse previous
passing verdicts. Calls record prompt hashes, input byte sizes, configured TTL,
raw usage and CLI list-price estimates. The actual cache-write TTL must be
checked in `usage.cache_creation`; an option alone does not prove savings.

## Controlled cost comparison

`web-demo` and `agent-bundle-evaluate` also accept
`--input-cases-from PREVIOUS_DEMO_DIRECTORY`. This loads the prior drawn inputs
for the **same frozen plan and candidate**, verifies recorded evidence hashes,
and runs every selected case again in a fresh browser/app state. It reuses no
judgments, action results, code review or screenshots. Missing drawn inputs are
an error rather than permission to silently generate a different comparison.
It cannot be combined with `--resume-from` or evaluation recovery.

Use one immutable app, the whole frozen plan, identical role models and the
same generated input values for both runs. Count tester, judge, source review,
input generation and metered app calls. Include plan output, rejected plans,
fallback and recovery calls. Charge shared input generation to both first-run
scenarios when computing savings; show experimental spend separately.

Inspect cache reads as well as writes. A second evaluation of the same app can
read the first evaluation's large code-review prefix even when every judgment
is fresh. Do not count that cross-run advantage as first-company savings. If
needed, measure a supplementary review with a neutral unique prefix before the
unchanged review payload. Preserve the original result and receipt, report the
supplement's cost, and label a substituted cost as a component-adjusted
comparison rather than the total of one uninterrupted execution. Common CLI
prefixes and model sampling can still differ. See the
[measured claim-001 comparison](evaluation-efficiency-2026-10-13.md).

Compare individual expectation IDs and evidence, not just pass totals. Review
every newly passing or regressed verdict. A single paired run establishes an
observed comparison, not statistical quality equivalence. Local tests with
known injected defects are also required to check that the optimizer does not
hide errors. Keep provider limits, incomplete evidence and product failures
distinct.

Procedure reuse across cases and further lossy observation compression are not
enabled. They remain conditional follow-ups from the
[design debate](../context/tasks/final-evaluation-browser-cost-a7073e42/conclusion.md).

## Judge evidence corrections (2026-10-15)

The judge now receives every recorded screen observation as an ordered shallow
page delta. Apply `removed_page_keys`, then replace keys in `page_changes`;
omitted keys retain their preceding values. Empty deltas still mark another
observation. This preserves returns to earlier states, disappearing content,
repeated lines, field identities, and transient evidence without resending
unchanged page sections. It preserves what the observer collected; the existing
browser observation limits are unchanged.

Changed UTF-8 text files are sent in full under `content`, with
`content_status: complete`. The old 4,000-byte excerpt could cut a UTF-8
character in half and silently remove the whole excerpt. Read failures,
invalid UTF-8, and NUL-containing binary files now have explicit `unavailable`
status and a reason; removed files are distinct from empty text files. The
judge must not infer unavailable contents and must return `not_evaluated` if
the required result cannot otherwise be established.

These corrections can increase judge input size. No new paid-model cost or
quality comparison was run; the October 13 measurements above describe the
earlier evaluator. Changing the evaluator invalidates reuse of old judgments
under the existing checkpoint policy; historical runs are left intact.

Validation: seven new regression tests cover state recurrence/disappearance,
field identity and transient evidence, unchanged observations, complete Unicode
and ASCII outputs, unavailable files, and a local browser-to-judge integration.
All 401 repository tests passed. The ten preserved claim-001 cases also round-trip
all 169 observations exactly through the new representation, without model calls.
