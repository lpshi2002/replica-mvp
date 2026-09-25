---
name: replica-research
description: Research a company from public sources in two passes, collect only customer-facing AI capability claims with direct evidence, preserve each feature as one end-to-end workflow, judge replication feasibility claim by claim, prepare replication-ready contracts, and optionally run Replica evaluations. Use when the user provides a company name, URL, or description; asks about Replica source policy, AI claim qualification, research.json, replication readiness, or claim execution; or wants an existing company research artifact reviewed or updated.
---

# Replica Research

Turn a company's public, customer-facing AI product claims into bounded,
testable capabilities without claiming access to private models, prompts,
code, training data, customer data, or internal systems.

## Orchestrate

- Accept a company name, public URL, or short description as the minimum input.
- Find a missing official URL through web search when possible.
- Do not ask the user for model commands, API keys, specs, tests, or a target
  capability when public research can derive them.
- Keep this repository from calling Codex or a model API unless the user
  explicitly requests a standalone automated runner or starts the Agent harness
  with its explicit `--model-runtime` setting.
- Perform company research in two passes. Stop after pass 2 unless the user
  asks to build, run, or evaluate a Replica.
- Create the authoritative `work/<company-slug>/research.json` from
  `../../templates/company-research.json` when research starts.
- During pass 1, workers continuously checkpoint their assigned scope under
  `work/<company-slug>/first_pass/`; the orchestrator is the only writer of
  normalized claims in `research.json`. Worker claims are provisional,
  source-backed observations. Complete the normalized pass-1 claims, resolve
  every deferred observation, and mark `pass_1_complete`.
- During pass 2, act as the orchestrator: spawn one `replica-second-pass` worker
  per claim, and after all finish, attach their fragments to the claims and mark
  `pass_2_complete`.
- Store source URLs, supporting excerpts, and findings rather than full page
  copies. `research.json` is authoritative. First-pass checkpoint files are
  resumable worker state, and second-pass fragments under
  `work/<company-slug>/second_pass/` are merge scaffolding kept for audit;
  neither is a separate research report. Do not create raw-source archives
  unless a source cannot be revisited and retaining it is necessary.

## Apply the source policy

Prefer sources in this order:

1. Official product and technical pages, API and developer docs, help docs,
   public demos, engineering blogs, white papers, release notes, official
   GitHub repositories, and SDKs.
2. Official press releases, IR and regulatory filings, and customer, partner,
   or strategic-investor announcements.
3. Official databases and registries, research papers, and patents.
4. Executive or engineer interviews, conference talks, and official job
   postings.
5. High-trust reporting such as Reuters, Bloomberg, FT, and WSJ.
6. Investor materials, PitchBook, TechCrunch, LinkedIn, and Crunchbase as
   discovery leads only.

Treat patents as implementation clues, not proof of a deployed product.
Verify discovery leads against official primary or reliable independent
evidence before relying on them.

Engineering blogs, repositories, interviews, talks, and job postings may
explain how the company works internally. Use them as implementation clues,
but do not turn an internal employee workflow into a Replica claim unless the
same workflow is also offered to external users or documented in a customer
deployment.

## Qualify AI technology claims

Pass 1 collects only claims about **customer-facing AI technology the company
offers**, and records the quoted evidence for why each one qualifies. A claim
enters the candidate list only when C0, C1, A1, and A2 all pass against recorded
public sources.

**C0 — the source attributes the work to this company.** The source must say
that the company, its named product, or a documented customer deployment
performs the work. An official-domain article saying only that "AI can" do the
work is industry commentary, not a company claim. Keep it only as a discovery
lead unless another source directly attributes the workflow to the company.

**C1 — an external user receives the capability.** The source must document a
public company product or an actual customer deployment. Internal engineering,
research, sales, support, or operations use does not qualify merely because the
company uses an agent or another AI tool. Record the external audience and the
verbatim delivery evidence in `customer_basis`:

| Field | Content |
|---|---|
| `delivery` | `public_product` or `customer_deployment` |
| `subject` | exact company, product, or deployed-customer name in the quote |
| `audience` | the external user who receives or acts on the output |
| `source_index` | 1-based index into `sources` carrying the evidence |
| `quote` | verbatim excerpt showing the product or customer deployment |

**A1 — the claim names work the system performs.** It states an input the
system takes and an output or decision it produces. A capacity, an outcome, or
a company property is not work.

**A2 — a public source attributes that work to AI machinery, in its own
words.** Look for a model, LLM, agent, machine learning, NLP, fine-tuning,
retrieval or embeddings, classification, extraction, or generation performed by
a model. The attribution must be quotable verbatim from a recorded source.
Never infer AI from a product's name, a page's overall framing, or the fact
that the company sells AI.

Record the outcome as `ai_basis` on the claim:

| Field | Content |
|---|---|
| `mechanism` | what the AI does, as input → output |
| `signals` | the AI terms the source actually uses |
| `work_signals` | exact terms in the quote naming the claimed work |
| `source_index` | 1-based index into `sources` carrying the attribution |
| `quote` | verbatim excerpt from that source containing the attribution |

`quote` must be contained in that source's recorded `excerpt`. At least one
sentence in the quote must contain every term in both `signals` and
`work_signals`; a generic AI sentence followed by an unrelated feature
sentence is not attribution. `finalize-pass-1` checks this, so copy the shortest
direct sentence rather than a broad marketing paragraph. A claim without a
qualifying quote is excluded, not weakened.

Exclude and record the reason:

| Reason | Excluded |
|---|---|
| `outcome_metric` | speed, accuracy, cost, or efficiency numbers restating a workflow already captured |
| `non_technical` | funding, customers, partnerships, pricing, hiring, certifications, security posture, market positioning |
| `no_ai_attribution` | real work with no quotable AI attribution, including deterministic rule, template, or integration automation |
| `internal_workflow` | the company uses AI internally, but does not offer that workflow to external users |

Workers do not have enough cross-scope evidence to finally reject these cases.
Put them in `deferred` for the orchestrator instead:

| Reason | Deferred observation |
|---|---|
| `no_company_attribution` | the current source discusses AI work generally, but another scope may attribute it to the company |
| `no_customer_delivery` | the current source does not establish a public product or customer deployment |
| `not_workflow` | the current source shows a model, platform property, UI idea, architecture, or mechanism that may belong to a workflow elsewhere |

An umbrella phrase such as "AI-powered platform" fails A1 on its own: it names
no work. Qualify the specific capability the page describes instead, or exclude
it. Vendor sites apply the phrase to everything, so it separates nothing.

Do not judge moat, business value, replication feasibility, or priority here.
Pass 1 answers only whether this is an AI technology claim and what evidence
says so.

## Collect one claim per whole workflow

Replica evaluates the **whole workflow of one customer-facing feature**, so a
claim is that entire workflow: a real input enters, the system performs the
documented work, and a final deliverable or decision reaches an external user.
Normal, boundary, and insufficient-information tests exercise this whole unit.

Do not create a separate claim merely because an intermediate output is
observable or separately testable. When an output is consumed by the next
operation inside the same customer task and is not independently delivered,
record it in the parent claim's `workflow.steps`. It becomes its own claim only
when an external user can invoke and receive it as a standalone product,
endpoint, or separately documented workflow.

When a broad workflow and narrower examples are both found, keep the broad
workflow and absorb the examples as sources, steps, input variants, or output
variants. Channel, industry, and document-type variations do not create new
claims when the customer goal and final deliverable remain the same. Split only
when the external user, initiating input, customer goal, or final deliverable
is genuinely different.

Record the shape as `workflow` on the claim:

| Field | Content |
|---|---|
| `input` | what enters the workflow, as the sources describe it |
| `steps` | documented stages in order, each with `step` and `source_index` |
| `output` | the deliverable that leaves the workflow |

Every step needs a `source_index` pointing at the source that documents it.
Record only stages the sources state. Do not infer intermediate steps to make
the workflow look complete — pass 2 fills implementation detail, and an empty
`steps` list is the honest record when a source describes a feature only as a
whole.

A performance number about one stage belongs in the workflow claim that stage
serves, not in a claim of its own.

## Preserve replication leads found during pass 1

Pass 1 does not deepen implementation research, but it must not discard useful
replication material encountered while qualifying a claim. Record each public
sample input, output example, schema or format, API or SDK, implementation clue,
or evaluation asset in that claim's `replication_leads`:

| Field | Content |
|---|---|
| `kind` | short material type such as `input_sample`, `output_example`, or `api_schema` |
| `source_index` | 1-based index into the claim's `sources` carrying or linking the material |
| `finding` | what the material can contribute to replication |

Use an empty list when none was encountered. The number of leads is never a
pass-1 selection rule. Do not follow extra links solely to complete replication
materials during pass 1; pass 2 deepens the saved leads and fills their gaps.

## Run pass 1: fan out five collection scopes

Act as the pass-1 orchestrator. Use the worker contract in
`agents/replica-first-pass.md` and assign these five scopes:

1. `official_surfaces`: the official company site, product and feature pages,
   technical and developer docs, API docs, help docs, public demos, white
   papers, release notes, official GitHub repositories, and SDKs.
2. `engineering_blog`: review the complete technical or engineering blog
   index and open every individual post. Never infer relevance from titles.
3. `discovered_names`: search every discovered product, system, feature, and
   internal technical name as a separate query to find related official
   material.
4. `people_and_organizations`: executive and engineer interviews, conference
   talks, technical job postings, and official customer or partner
   announcements.
5. `supplementary_sources`: filings, papers, patents, official databases, and
   high-trust reporting. Treat investor materials, TechCrunch, LinkedIn, and
   Crunchbase only as discovery leads and reconfirm them with official or
   reliable evidence.

Start `official_surfaces`, `engineering_blog`, `people_and_organizations`, and
`supplementary_sources` first. Start `discovered_names` after collecting their
discovered-name lists; rerun that scope if the other workers later add names.
Run independent scopes in parallel up to the environment's concurrency limit.

Each worker owns one checkpoint file under `work/<company>/first_pass/` and
must create it before browsing. A worker must persist every claim with its
source URL, `customer_basis`, `ai_basis`, and any replication leads encountered
there immediately when found. It must also persist every source-supported
stage in the whole workflow, every unresolved observation as `deferred`, and
assigned, completed, and remaining scope before moving on. Never rely on a
worker's final chat response for research data. If context compacts or the
worker restarts, resume from the checkpoint's remaining scope without repeating
completed work.

After all five scopes are complete, read their checkpoints and:

1. exclude internal company use unless another source proves the same workflow
   is a public product or customer deployment;
2. resolve every `deferred` observation by promoting it to a claim, attaching
   it as evidence or a step on a claim, or excluding it with a rationale; record
   that decision in `deferred_resolutions`;
3. combine supporting sources for equivalent E2E workflows and
   record duplicate provisional IDs in `merged_from`;
4. apply the step test across scopes: when a provisional claim is only a stage
   of a broader customer workflow, fold its documented work and sources into
   the parent claim instead of keeping another claim;
5. merge channel, industry, document-type, and product-surface variants when
   they serve the same customer goal and final deliverable; split only
   independently invoked workflows with a different user, input, goal, or
   final deliverable;
6. remove platform properties, UI concepts, and shared architectures from the
   claim list, preserving useful implementation evidence on the relevant claim
   when a parent is known;
7. re-apply C0, C1, A1, and A2 after normalization;
8. keep the strongest `customer_basis` and `ai_basis` evidence and repoint all
   source indexes after combining sources;
9. record one `candidate_resolutions` decision for every checkpoint claim so
   no collected candidate disappears without a recorded outcome;
10. write the normalized claims and both resolution lists to `research.json`;
    and
11. run `replica-mvp finalize-pass-1 work/<company>` to validate the result and
    mark pass 1 complete.

Two claims are the same claim when they describe the same customer goal,
initiating input, final deliverable, and AI workflow. A narrower description of
one stage is supporting evidence for its parent workflow, not another claim.
Workers see one scope each, so cross-scope step folding, parent merging, and
deferred resolution belong to the orchestrator.

Each `deferred_resolutions` item contains `deferred_id`, `decision`, optional
`target_id`, and `rationale`. Use `promoted_to_claim` or `attached_to_claim`
with a final claim ID, or `excluded` without a target. Finalization fails if any
checkpoint deferred ID is missing, duplicated, or points at a missing target.

Each `candidate_resolutions` item contains `candidate_id` (a checkpoint claim
ID), `decision`, optional `target_id`, and `rationale`. Use `kept_as_claim` or
`merged_into_claim` with a final claim ID, or `excluded` without a target.
`merged_into_claim` and `excluded` need a rationale. Finalization fails if any
checkpoint candidate is missing, duplicated, or points at a missing target, and
if a final claim is not originated by at least one candidate or promoted
deferred item. Excluded candidates count toward `summary.excluded_count`.

Finalization also fails when a checkpoint's `assignment.assigned` item is
neither in `progress.completed` nor in `progress.skipped` with a reason, and
it refuses research whose `workflow.status` is past pass 1. Re-running it
during pass 1 is safe; changing pass-1 results after pass 2 starts needs a new
research version.

Do not open extra sources solely to complete implementation datasets, freeze
final contracts, design final tests, or create per-capability projects during
pass 1. Always preserve replication material encountered in the assigned
research.

For every candidate, record the original claim, source evidence,
`customer_basis`, `ai_basis`, `workflow`, `replication_leads`, testable
restatement, routing, and duplicate or child-claim merge history in
`research.json`. Every whole-workflow claim is handed to pass 2; pass 1 does
not rank or select. Do not record or infer `replicable` during pass 1.

## Run pass 2: fan out one worker per claim

Act as the pass-2 orchestrator. Do not research claims yourself in this pass.
Use the worker contract in `agents/replica-second-pass.md`.

Pass 2 does not produce a report. It produces the material a replication agent
needs to build and test the capability, so every worker answers one question:
can a replication agent build this with what has been collected, and if not,
what is missing?

### Build a brief for each claim

Build it **only from `research.json`** — do not search at this stage. The brief
carries `company`, `claim_id`, `slug`, `testable_claim`, `workflow`, `ai_basis`,
`customer_basis`, `sources`, and `replication_leads`, plus three derived fields.

**`search_names`.** Pass 1 records no per-claim name list, so derive one from
`customer_basis.subject`, `ai_basis.work_signals`, the proper nouns in
`testable_claim` and `workflow.steps`, and the path segments of
`sources[].url`. When the first-pass checkpoints are still present, read their
company-wide `progress.discovered_names` as a candidate pool and adopt a name
**only when it literally appears in this claim's own text**; drop the rest.
Record `names_source` as `derived` or `derived+checkpoint`.

**`routing`.** Derive it. **Do not read `first_pass.routing`** — record it in
`routing_raw` for audit and classify from scratch. That field is a free string
the code never validates, so its values are whatever one producer happened to
write; observed values carried almost no discriminating power (17 of 19 claims
identical), and translating such a value into our axes manufactures detail the
input never contained. Not reading it also closes the back door by which a
quality judgement — "high accuracy", "unique", "strong moat" — would restore the
scoring pass 1 retired.

Classify into `commodity_task`, `domain_specialized`,
`workflow_orchestration`, `novel_technique`, or `proprietary_data_bound`, on the
axis "where is replication hard", from three fields and no others:
`ai_basis.mechanism`, the number of `workflow.steps`, and
`replication_leads[].kind`. Assign one to three values.

**`bucket_depth`.** Look it up from `routing`; do not decide it. Take the
per-bucket maximum when routing has several values (`shallow` < `deep`).

| | evidence | datasets_apis | oss_papers_patents | eval_assets | access_license | impl_path |
|---|---|---|---|---|---|---|
| `commodity_task` | shallow | deep | deep | shallow | shallow | shallow |
| `domain_specialized` | deep | deep | shallow | deep | shallow | shallow |
| `workflow_orchestration` | deep | shallow | shallow | shallow | shallow | deep |
| `novel_technique` | shallow | shallow | deep | deep | shallow | deep |
| `proprietary_data_bound` | shallow | deep | shallow | shallow | deep | shallow |

Depth allocates effort only. It never removes a bucket from investigation and is
only ever `deep` or `shallow`; `not_applicable` is a bucket state a worker
records after looking, never a depth assigned before.

### Spawn and collect

Spawn one `replica-second-pass` worker per claim, up to the environment's
concurrency limit, and run the rest in later waves. Each worker researches only
its own claim, must not modify `research.json`, writes
`work/<company>/second_pass/<slug>.json`, and returns one status line.

**Do not fold claims before research.** A pass-1 claim that is really a step of
another workflow is detected by the worker that researched it, which returns
`status: merged` and `handoff: merge`. An orchestrator that collapses claims up
front decides without evidence, never investigates what it collapsed, and erases
the difference between "researched and found to be a step" and "never looked".
Collect the `merge` results and report them instead.

When every worker has finished, attach each fragment to its claim's
`second_pass`, recompute `workflow.pass_2` and `summary`
(`ready_count`, `partial_count`, `blocked_count`), and set `workflow.status` to
`pass_2_complete`.

## Decide readiness

Finish a claim only after every research question is answered or
marked not publicly known. Require:

- at least one supporting official primary source for the canonical claim;
- supported or explicitly unknown input, process, and output;
- `workflow.boundaries` resolved to `stated` or `undisclosed`, never
  `unchecked`;
- independent corroboration when available;
- recorded contradictions and limitations;
- a usable public input source or explicit synthetic fallback;
- an implementation path and evaluation assets.

Set `readiness.status` to `ready`, `partial`, or `blocked`. Do not require an
arbitrary source count and do not infer missing details. Record `replicable` and
its evidence-based reason here; pass 1 never carries it.

Pass 1 records no boundaries, so pass 2 establishes them by **reopening the
claim's own official source URLs** — re-reading its own evidence, not recrawling
unrelated pages. Record the outcome as a state, not a string: `stated` when the
company published its conditions, `undisclosed` when those sources were reopened
and state none, and `unchecked` when they could not be reached. Only
`undisclosed` licenses setting conditions ourselves; `unchecked` blocks `ready`,
because collapsing the two produces a contract built on invented conditions.

### Freeze the contract as a scenario array

For a `confirmed` or `refined`, `ready` claim with handoff `build`, freeze
`second_pass.replication_contract` as an **array of scenarios**, each one
implementation path with its own conditions. Otherwise leave it `null`.

Scenarios exist because of what is not known; what is known needs none. **One
scenario is normal** — published conditions plus one obvious route give an array
of length one. Several scenarios mean unresolved unknowns, not diligence.
**Maximum three.** Split on implementation paths and attach conditions to each
path rather than multiplying conditions against paths. The count follows from
the resolved buckets, not from a guess made before research.

Order scenarios most self-sufficient first — `oss_only`, `commercial_api`,
`proprietary_data`. Execution runs the first and stops once it reproduces, so
the position where a claim first reproduces is itself the finding.

Each scenario carries `id`, `self_sufficiency`, `boundaries` with
`boundaries_origin` (`company` or `ours`), `input`, `output` including its
structure and format, `acceptance_criteria`, `out_of_scope`, `evidence_level`,
`sources`, and `tests` with at least `normal`, `boundary`, and
`insufficient-information`. Leave no placeholders. These names match what
`replica-mvp init`, `build`, and `evaluate` actually read: the exclusions field
is `out_of_scope`, and there is no separate output-schema field because
`spec.json` has only `output_description`.

`evidence_level` measures how strong the evidence is; `self_sufficiency`
measures how much the build leans on others. Judge each per scenario and do not
map one onto the other.

For a question-answer capability, also freeze a public `experience` object using
the `replica-experience/v1` contract. Include a public or synthetic
`runtime_input`, the question field, example questions, and an evidence-level
comparison summary. Keep it separate from the frozen evaluation cases and
never copy test inputs or expected outputs into it. Use `direct` only when a
same-question original output and its source are recorded; otherwise use the
claim's `public` or `claim_only` evidence level.

If a same-question original output is captured after the run is published,
record it separately with `replica-original-observations/v1`: original name,
exact question, observed output, source, and capture timestamp. Display it as a
user-provided observation. Require a timezone-aware ISO 8601 capture timestamp.
It must not change the frozen run evidence level or be described as
independently verified unless separate evidence supports that claim.

For non-question-answer capabilities, preserve the input and output contracts
so the published run can be experienced through one generic JSON-input seam.
Render object and array outputs as structured JSON, plain string outputs as
text, and `text/html` outputs only to an explicit new preview file outside the
published run. Never overwrite or automatically open an HTML result.

After a successful build, stop the workflow at the published file bundle.
Report the public run path and the generated implementation, result, assessment,
and report files. Do not create or publish a browser UI as part of this workflow.

For a question-answer capability, include a small robustness matrix in the
frozen evaluation: Korean and English paraphrases when both are in scope, one
representative typo, an unsupported personal-fact question, and an urgent
request when the safety rules require escalation. Keep public experience
examples distinct from every robustness case and expected output.

Pass 2 is complete when every pass-1 claim has a readiness decision and every
ready claim contract is complete.

For the Sol/Terra bundle route, also prepare the executable evaluation data described
in `../../docs/replica-bundle-execution.md`. Reuse existing findings and cases. Add
only genuinely missing transport details, criterion/check mappings, materially new
inputs, invariant/changed-fact relations, separate public examples, and input/output
asset records. Research any new technical alternative here, not in Sol or Terra.
The selected scenario may include `evaluation`; `handoff.experiment_budget` holds
development time/cost limits and stopping policy. Freeze them before implementation.
Generated wording may vary under a `contract` repeat policy; required deterministic
fields still use exact assertions. Missing data is a research gap, not permission
to lower acceptance criteria. Preserve old contracts and runs when supplementing.

## Execute only on request

For a standalone run, when the user asks to start actual replication, expand
**one scenario** of a ready claim contract into
`work/<company-slug>/runs/<capability-slug>/<scenario-id>/evidence.json`,
`spec.json`, and `tests.json`, then build `replica.json`. One scenario is one
run directory.

Run the scenarios in the order the contract froze them, most self-sufficient
first. **Stop as soon as one reproduces** — when its `normal`, `boundary`, and
`insufficient-information` cases all pass — and do not run the rest. Move to the
next scenario when any case fails, keeping the failed run's `results.jsonl` and
`report.md`.

For the Sol/Terra Agent harness, pass the authoritative completed
`work/<company-slug>/research.json` directly to `agent-harness-init`. Do not
flatten away `workflow`, `findings.datasets_apis`, `findings.oss_papers_patents`,
`findings.access_license`, `findings.impl_path`, or alternate replication
scenarios. The harness selects `ready` + `build` claims, gives Sol the complete
immutable Second-pass claim, and gives Terra a public `builder-context.json`
without test expectations or reference facts.

Set `--model-runtime codex` on the Codex route and `--model-runtime claude` on
the Claude route. The harness follows the researched `handoff.selected_scenario_id` or
`handoff.scenario_priority`; without either it runs the first scenario in the
frozen order and records that selection basis. It evaluates only that scenario
and does not fall back to the next one after a failed evaluation. The model
runtime is a narrow execution overlay for supported model steps, not a reason to
select a different scenario. A bundle that actually declares the selected CLI
promotes an `oss_only` dependency level to `commercial_api` while preserving the
selected scenario ID, input, and output.

When producing the standalone `replica-second-pass-result/v1` build input for
a question-answer capability, copy the frozen public `experience` object to
its top-level `experience` field. A successful finalize publishes it as
`experience.json`; the user then runs `replica-mvp experience RUN_DIR` without
supplying another profile.

When a ready `replica-second-pass-result/v1` artifact is already available,
use `.agents/skills/build-replica-operator/SKILL.md` for implementation. That
repo-discoverable Skill makes Codex write a new operator from the prepared
contract, keeps frozen tests in a separate evaluator vault, and does not select
a registered operator or call a model API from this repository.

Run the frozen cases without changing their expectations after seeing output.
Keep candidate generation and judging as separate passes. If the same session
judges the output, label the Judge as same-session rather than independent.

Write execution-only `replica_outputs.jsonl`, `results.jsonl`, and `report.md`
under the scenario's run directory. Do not duplicate company research into
another report unless the user explicitly requests an export.

Report executed and skipped capabilities, evidence levels, pass counts,
readiness, limitations, and artifact links. Report **which scenario reproduced**,
since the position where a claim first reproduces is the finding: an `oss_only`
reproduction says the capability has little proprietary wall, a
`proprietary_data` one says data access is the wall. Mark the scenario set as
non-exhaustive — if every scenario fails, report that these paths did not
reproduce it, never that the capability cannot be replicated. Never describe
public-scope implementation feasibility as original-product equivalence.
