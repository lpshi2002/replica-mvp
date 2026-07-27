---
name: replica-research
description: Research a company from public sources in two passes, collect only its AI technology claims with quoted evidence of why each is AI, judge replication feasibility claim by claim, prepare replication-ready contracts, and optionally run Replica evaluations. Use when the user provides a company name, URL, or description; asks about Replica source policy, AI claim qualification, research.json, replication readiness, or claim execution; or wants an existing company research artifact reviewed or updated.
---

# Replica Research

Turn a company's public AI technology claims into bounded, testable
capabilities without claiming access to private models, prompts, code, training
data, customer data, or internal systems.

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
  normalized claims in `research.json`. Complete its pass-1 claims, mark
  `pass_1_complete`, then add `second_pass` to every pass-1 claim and finally
  mark `pass_2_complete`.
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

## Qualify AI technology claims

Pass 1 collects only claims about **AI technology the company applies**, and
records the quoted evidence for why each one qualifies. A claim enters the
candidate list only when both tests pass against recorded public sources.

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
| `source_index` | 1-based index into `sources` carrying the attribution |
| `quote` | verbatim excerpt from that source containing the attribution |

`quote` must be contained in that source's recorded `excerpt` and must contain
every term in `signals`; `finalize-pass-1` checks both, so widen the `excerpt`
to cover the AI sentence rather than quoting from memory. A claim without a
qualifying quote is excluded, not weakened.

Exclude and record the reason:

| Reason | Excluded |
|---|---|
| `outcome_metric` | speed, accuracy, cost, or efficiency numbers restating a workflow already captured |
| `non_technical` | funding, customers, partnerships, pricing, hiring, certifications, security posture, market positioning |
| `no_ai_attribution` | real work with no quotable AI attribution, including deterministic rule, template, or integration automation |

An umbrella phrase such as "AI-powered platform" fails A1 on its own: it names
no work. Qualify the specific capability the page describes instead, or exclude
it. Vendor sites apply the phrase to everything, so it separates nothing.

Do not judge moat, business value, replication feasibility, or priority here.
Pass 1 answers only whether this is an AI technology claim and what evidence
says so.

## Collect one claim per workflow, not per step

Replica reproduces the **whole workflow of one feature**. A claim is therefore
one workflow: a real input enters, the system does its work, and a deliverable
comes out that someone acts on. Collect at that unit so pass 1 and the
replication target agree.

**The step test.** When claim X's output is consumed by claim Y inside the same
feature and is never delivered on its own, X is a step of Y. Record it in Y's
`workflow.steps` and do not carry it as its own claim. When the company
delivers that output on its own — a standalone product, an API endpoint, a
separate page for buying it — it is its own workflow.

Split a claim only where workflows are distinct: different input, different
deliverable, different user acting on it. "AI for submissions, claims, and
renewals" is three workflows. Never split within a workflow to make a claim
easier to test — that produces a step, and a step is not a replication target.

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
source URL, supporting excerpt, and any replication leads encountered there
immediately when found, before opening the next source or running the next
query. It must also persist assigned, completed, and remaining scope after each
source. Never rely on a worker's final chat response for research data. If
context compacts or the worker restarts, resume from the checkpoint's remaining
scope without repeating completed work.

After all five scopes are complete, read their checkpoints and:

1. combine supporting sources for equivalent claims;
2. apply the step test across scopes: fold every step-level claim into the
   workflow claim it serves, as a `workflow.steps` entry, and record it in
   `merged_from`;
3. normalize wording, remove duplicates, and split a claim only where it covers
   distinct workflows;
4. re-apply A1 and A2 to every merged claim, because merging changes wording;
5. keep the strongest `ai_basis` quote among the merged sources and repoint
   every `source_index`, in `ai_basis`, each step, and each deduplicated
   `replication_leads` entry, at the combined `sources` list;
6. create a testable restatement and routing for each candidate, stated at the
   workflow's input and deliverable rather than at one stage;
7. write the deduplicated candidates to `research.json`; and
8. run `replica-mvp finalize-pass-1 work/<company>` to validate the result and
   mark pass 1 complete.

Two claims are the same claim when they describe the same input, the same
output, and the same AI mechanism. Workers see one scope each, so the same
workflow usually arrives as a marketing sentence from one scope and its stages
from another; consolidating them is the orchestrator's job.

Do not open extra sources solely to complete implementation datasets, freeze
final contracts, design final tests, or create per-capability projects during
pass 1. Always preserve replication material encountered in the assigned
research.

For every candidate, record the original claim, source evidence, `ai_basis`,
`workflow`, `replication_leads`, testable restatement, routing, and merge history
in `research.json`. Every candidate is handed to pass 2; pass 1 does not rank or
select. Do not record or infer `replicable` during pass 1.

## Run pass 2: prepare replication claim by claim

Work on one pass-1 claim at a time. Carry its `sources`, `ai_basis`, `workflow`,
and `replication_leads` forward as the starting evidence for that claim. Deepen
those leads first, then reopen relevant pages and search exact feature, system,
and product names with input, output, demo, customer, partner, technical,
interview, and job terms. Do not recrawl unrelated company pages.

Collect enough public evidence to decide and prepare replication of the whole
workflow. Deepen each stage in `workflow.steps`, but keep the unit intact: the
replication target is the end-to-end feature, not a stage of it.

- whether the claim is replicable from public or synthetic inputs;
- canonical claim, exact input, process, output, and boundaries;
- supporting and contradictory evidence and explicit unknowns;
- usable datasets, sample documents, schemas, formats, APIs, and SDKs;
- open-source implementations, papers, and patents as technical clues;
- benchmarks, reference answers, rules, or other evaluation assets;
- access method, coverage, license or usage limits, and a synthetic fallback
  when required inputs are not public;
- minimum implementation path, limitations, and open questions.

Attach the result to that claim's `second_pass` field in the same
`research.json`. Use `confirmed`, `refined`, `merged`, or `rejected` for its
status. Record each source's URL, source type, supported finding, and supported
claim field. Record `second_pass.replicable` and its evidence-based reason here,
never under `first_pass`. Route a non-replicable claim to `evidence_request` or
`reject` as appropriate.

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

For a `confirmed` or `refined` claim that is `ready` with handoff `build`,
freeze `second_pass.replication_contract` with the input/output contract,
acceptance criteria, output schema, exclusions, and at least three test cases:
normal, boundary, and insufficient-information. Leave no placeholders.

Pass 2 is complete when every pass-1 claim has a readiness decision and
every ready contract is complete.

## Execute only on request

When the user asks to start actual replication, expand one ready contract into
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
