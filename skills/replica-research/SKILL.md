---
name: replica-research
description: Research a company from public sources in two passes, score claims, judge replication feasibility claim by claim, prepare replication-ready contracts, and optionally run Replica evaluations. Use when the user provides a company name, URL, or description; asks about Replica source policy, claim scoring, selection, research.json, replication readiness, or claim execution; or wants an existing company research artifact reviewed or updated.
---

# Replica Research

Turn public company claims into bounded, testable capabilities without claiming
access to private models, prompts, code, training data, customer data, or
internal systems.

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
  `pass_1_complete`, then add `second_pass` to each selected claim and finally
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
source URL and supporting excerpt immediately when found, before opening the
next source or running the next query. It must also persist assigned,
completed, and remaining scope after each source. Never rely on a worker's
final chat response for research data. If context compacts or the worker
restarts, resume from the checkpoint's remaining scope without repeating
completed work.

After all five scopes are complete, read their checkpoints and:

1. combine supporting sources for equivalent claims;
2. normalize wording, split claims that are too broad to test, and remove
   duplicates;
3. create a testable restatement and routing for each candidate;
4. score from recorded public evidence and state uncertainty instead of
   guessing;
5. write the deduplicated candidates to `research.json`; and
6. run `replica-mvp finalize-pass-1 work/<company>` to validate the result and
   mark pass 1 complete.

Do not collect implementation datasets, freeze final contracts, design final
tests, or create per-capability projects during pass 1.

For every candidate, record the original claim, source evidence, testable
restatement, routing, score evidence, total, selection state, and reason in
`research.json`. Do not record or infer `replicable` during pass 1.

## Score candidates

Assign only these three scores:

| Axis | 0 | 1 | 2 |
|---|---|---|---|
| `moat` | simple feature | some differentiation | repeatedly emphasized core moat |
| `business` | add-on | customer convenience | purchase or retention driver |
| `separability` | sales, brand, or contract | mixed technical and business | bounded input-to-output capability |

Set `total = moat + business + separability`, from 0 to 6. Do not collect or
score `observability` or `judgeability`.

Select every claim with `total >= 4` for pass 2. Do not select claims with
`total <= 3`. `separability` is only one score axis; it is not a replication
feasibility verdict. Judge `replicable` only during pass 2.

## Run pass 2: prepare replication claim by claim

Work on one selected claim at a time. Start from its pass-1 sources, reopen
relevant pages, and search exact feature, system, and product names with
input, output, demo, customer, partner, technical, interview, and job terms.
Do not recrawl unrelated company pages.

Collect enough public evidence to decide and prepare replication:

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

Finish a selected claim only after every research question is answered or
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

Pass 2 is complete when every selected claim has a readiness decision and
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

Report selected and skipped capabilities, evidence levels, pass counts,
readiness, limitations, and artifact links. Never describe public-scope
implementation feasibility as original-product equivalence.
