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
  explicitly requests a standalone automated runner.
- Perform company research in two passes. Stop after pass 2 unless the user
  asks to build, run, or evaluate a Replica.
- Create the authoritative `work/<company-slug>/research.json` from
  `../../templates/company-research.json` when research starts.
- During pass 1, workers continuously checkpoint their assigned scope under
  `work/<company-slug>/first_pass/`; the orchestrator is the only writer of
  normalized claims in `research.json`. Worker claims are provisional,
  source-backed observations. Complete the normalized pass-1 claims, resolve
  every deferred observation, mark `pass_1_complete`, then add the pass-2
  decision to every claim before marking `pass_2_complete`.
- Store source URLs, supporting excerpts, and findings rather than full page
  copies. `research.json` is authoritative. First-pass checkpoint files are
  resumable worker state, not separate research reports. Do not create
  raw-source archives unless a source cannot be revisited and retaining it is
  necessary.

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
9. write the normalized claims and deferred resolutions to
   `research.json`; and
10. run `replica-mvp finalize-pass-1 work/<company>` to validate the result and
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

Do not open extra sources solely to complete implementation datasets, freeze
final contracts, design final tests, or create per-capability projects during
pass 1. Always preserve replication material encountered in the assigned
research.

For every candidate, record the original claim, source evidence,
`customer_basis`, `ai_basis`, `workflow`, `replication_leads`, testable
restatement, routing, and duplicate or child-claim merge history in
`research.json`. Every whole-workflow claim is handed to pass 2; pass 1 does
not rank or select. Do not record or infer `replicable` during pass 1.

## Run pass 2: prepare replication claim by claim

Work on one pass-1 whole-workflow claim at a time. Carry its `sources`,
`customer_basis`, `ai_basis`, `workflow`, and
`replication_leads` forward. Deepen those leads first, then reopen relevant
pages and search exact feature, system, and product names with input, output,
demo, customer, partner, technical, interview, and job terms. Do not recrawl
unrelated company pages.

Collect enough public evidence to decide and prepare replication of the whole
claim. Its documented steps explain the E2E process while its input and final
deliverable define the acceptance contract.

- whether the claim is replicable from public or synthetic inputs;
- canonical claim, exact input, process, output, and boundaries;
- supporting and contradictory evidence and explicit unknowns;
- usable datasets, sample documents, schemas, formats, APIs, and SDKs;
- open-source implementations, papers, and patents as technical clues;
- benchmarks, reference answers, rules, or other evaluation assets;
- access method, coverage, license or usage limits, and a synthetic fallback
  when required inputs are not public;
- minimum implementation path, limitations, and open questions.

Attach the findings, E2E decision, and replication contract to the claim's
`second_pass` in the same `research.json`. Use `confirmed`, `refined`, `merged`,
or `rejected` for claim status. Record each source's URL, source type,
supported finding, and supported claim field. Record replicability and its
evidence-based reason only in pass 2.

## Decide readiness

Finish a claim only after every research question is answered or
marked not publicly known. Require:

- at least one supporting official primary source for the canonical claim;
- supported or explicitly unknown input, process, output, and boundaries;
- independent corroboration when available;
- recorded contradictions and limitations;
- a usable public input source or explicit synthetic fallback;
- an implementation path and evaluation assets.

Set `readiness.status` to `ready`, `partial`, or `blocked`. Do not require an
arbitrary source count and do not infer missing details.

For a ready claim with handoff `build`, freeze its
`second_pass.replication_contract` with the E2E input/output contract,
acceptance criteria, output schema, exclusions, and at least three test cases:
normal, boundary, and insufficient-information. Leave no placeholders.

Pass 2 is complete when every pass-1 claim has a readiness decision and every
ready claim contract is complete.

## Execute only on request

When the user asks to start actual replication, expand one ready claim contract into
`work/<company-slug>/runs/<capability-slug>/evidence.json`, `spec.json`, and
`tests.json`, then build `replica.json`.

Run the frozen cases without changing their expectations after seeing output.
Keep candidate generation and judging as separate passes. If the same session
judges the output, label the Judge as same-session rather than independent.

Write execution-only `replica_outputs.jsonl`, `results.jsonl`, and `report.md`
under the claim's run directory. Do not duplicate company research into
another report unless the user explicitly requests an export.

Report executed and skipped capabilities, evidence levels, pass counts,
readiness, limitations, and artifact links. Never describe public-scope
implementation feasibility as original-product equivalence.
