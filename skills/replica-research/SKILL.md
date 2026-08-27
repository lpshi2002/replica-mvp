---
name: replica-research
description: Research a company from public sources in two passes, score and select replicable claims, prepare replication-ready contracts, and optionally run Replica evaluations. Use when the user provides a company name, URL, or description; asks about Replica source policy, claim scoring, selection, research.json, replication readiness, or claim execution; or wants an existing company research artifact reviewed or updated.
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
  explicitly requests a standalone automated runner or starts the Agent harness
  with its explicit `--model-runtime` setting.
- Perform company research in two passes. Stop after pass 2 unless the user
  asks to build, run, or evaluate a Replica.
- Create the authoritative `work/<company-slug>/research.json` from
  `../../templates/company-research.json` when research starts.
- Save normalized findings directly to that file throughout the work. Complete
  its pass-1 claims first, mark `pass_1_complete`, then add `second_pass` to
  each selected claim and finally mark `pass_2_complete`.
- Store source URLs, supporting excerpts, and findings rather than full page
  copies. Do not create separate pass files or raw-source archives unless a
  source cannot be revisited and retaining it is necessary.

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

## Run pass 1: discover claims broadly

1. Open the company's official product and technical pages.
2. Review the complete technical or engineering blog index and open every
   individual post. Do not infer relevance from titles alone.
3. Search each discovered system, product, and feature name separately.
4. Check relevant executive and engineer interviews, conference talks, and
   technical job postings.
5. Record source URLs and supporting excerpts, extract claims broadly,
   normalize their wording, split claims that are too broad to test, and merge
   duplicates.
6. Create a testable restatement and routing for each candidate. Score from
   the recorded public evidence and state uncertainty instead of guessing.

Do not collect implementation datasets, freeze final contracts, design final
tests, or create per-capability projects during pass 1.

For every candidate, record the original claim, source evidence, testable
restatement, routing, `replicable`, score evidence, total, selection state, and
reason in `research.json`.

## Score candidates

Assign only these three scores:

| Axis | 0 | 1 | 2 |
|---|---|---|---|
| `moat` | simple feature | some differentiation | repeatedly emphasized core moat |
| `business` | add-on | customer convenience | purchase or retention driver |
| `separability` | sales, brand, or contract | mixed technical and business | bounded input-to-output capability |

Set `total = moat + business + separability`, from 0 to 6. Do not collect or
score `observability` or `judgeability`.

Select every replicable claim with `total >= 4` for pass 2. Do not select
claims with `total <= 3`. Route a non-replicable claim to `evidence_request`
even when its total is 4 or higher.

## Run pass 2: prepare replication claim by claim

Work on one selected claim at a time. Start from its pass-1 sources, reopen
relevant pages, and search exact feature, system, and product names with
input, output, demo, customer, partner, technical, interview, and job terms.
Do not recrawl unrelated company pages.

Collect enough public evidence to decide and prepare replication:

- canonical claim, exact input, process, output, and boundaries;
- supporting and contradictory evidence and explicit unknowns;
- usable datasets, sample documents, schemas, formats, APIs, and SDKs;
- open-source implementations, papers, and patents as technical clues;
- benchmarks, reference answers, rules, or other evaluation assets;
- access method, coverage, license or usage limits, and a synthetic fallback
  when required inputs are not public;
- implementation paths that perform the full documented workflow, including
  fidelity-critical model, API, OSS, data, and side-effect dependencies,
  limitations, and open questions. Do not present a rule-based shortcut or
  test double as the implementation path unless the public scenario explicitly
  defines it as production behavior.
- when a text or supported-vision model is required, mark that step so the
  harness-selected `codex` or `claude` local CLI runtime can replace only the
  generative model. Do not switch the whole claim to an unrelated commercial
  retrieval or storage scenario merely to obtain a model. Keep embeddings,
  OCR, speech, audio, video, and other modality-specific dependencies explicit
  when the selected runtime cannot perform them.

Attach the result to that claim's `second_pass` field in the same
`research.json`. Use `confirmed`, `refined`, `merged`, or `rejected` for its
status. Record each source's URL, source type, supported finding, and supported
claim field.

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

Pass 2 is complete when every selected claim has a readiness decision and
every ready contract is complete.

## Execute only on request

When the user asks to start actual replication, expand one ready contract into
`work/<company-slug>/runs/<capability-slug>/evidence.json`, `spec.json`, and
`tests.json`, then build `replica.json`.

For the Sol/Terra Agent harness, pass the authoritative completed
`work/<company-slug>/research.json` directly to `agent-harness-init`. Do not
flatten away `workflow`, `findings.datasets_apis`, `findings.oss_papers_patents`,
`findings.access_license`, `findings.impl_path`, or alternate replication
scenarios. The harness selects `ready` + `build` claims, gives Sol the complete
immutable Second-pass claim, and gives Terra a public `builder-context.json`
without test expectations or reference facts.

Set `--model-runtime codex` on the Codex route and `--model-runtime claude` on
the Claude route. The harness still selects the most self-sufficient researched
scenario. The model runtime is a narrow execution overlay for supported model
steps, not a reason to select a different scenario. A bundle that actually
declares the selected CLI promotes an `oss_only` dependency level to
`commercial_api` while preserving the selected scenario ID, input, and output.

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
under the claim's run directory. Do not duplicate company research into
another report unless the user explicitly requests an export.

Report selected and skipped capabilities, evidence levels, pass counts,
readiness, limitations, and artifact links. Never describe public-scope
implementation feasibility as original-product equivalence.
