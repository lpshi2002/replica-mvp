# Agent Rules

Before answering questions about prior meetings, memories, decisions, project
direction, or implementation direction, run:

```bash
team-ai context "USER_REQUEST"
```

For broad project-wide questions about the current goal, status, next actions,
or unresolved decisions, decide the meaning at the agent layer and run:

```bash
team-ai context --current-state "USER_REQUEST"
```

Use ordinary context search for questions about a specific named topic.

Before changing product code under `src/` or `tests/`, run:

```bash
team-ai context --mode implementation "USER_REQUEST"
```

Treat "회의 때 뭐 나왔지", "지난번에 뭐라고 했지", "기억 가져와줘",
"결정 내용이 뭐야", and "이 아이디어로 만들어줘" as project knowledge
recall requests.

Only use harness context when the user explicitly asks about team-ai harness,
CLI behavior, guard, verify, memory schema, AGENTS.md mechanics, project.yaml
scope rules, runtime, or compiled snapshots.

- Active project is defined in `.team-ai/project.yaml`.
- Raw materials and meeting notes live under `.team-ai/sources/`.
- Approved durable memories live under `.team-ai/memory/`.
- Product code belongs under `src/`; tests belong under `tests/`.
- Before finalizing implementation changes, run `team-ai guard`.

## Codex-operated Replica workflow

When the user gives a company name, URL, or short company description and asks
to run the Replica workflow, the current Codex task is the orchestrator.

- Do not ask the user for model commands, API keys, specs, tests, or a target
  capability when those can be derived from public research.
- Do not make this repository call Codex or a model API unless the user
  explicitly requests a standalone automated runner.
- Accept a company name or public URL as the minimum input. Find the missing
  identifier through web search when possible.
- Research current public sources in two passes: broad claim discovery, then
  claim-specific replication research.
- Use official product and technical pages, API and developer docs, help docs,
  public demos, engineering blogs, white papers, release notes, and official
  GitHub repositories or SDKs as primary evidence.
- Use official press releases, IR or regulatory filings, customer or partner
  announcements, official databases or registries, research papers, patents,
  and high-trust reporting such as Reuters, Bloomberg, FT, or WSJ as supporting
  evidence. Treat patents as implementation clues, not proof of a deployed
  product.
- Treat executive or engineer interviews, conference talks, and official job
  postings as supporting technical leads. Treat investor materials, PitchBook,
  TechCrunch, LinkedIn, and Crunchbase as discovery leads only; verify their
  claims against primary or independent evidence before using them.
- In pass 1, optimize for breadth. Open the company's official product and
  technical pages, review the complete technical or engineering blog index,
  and open each individual post; do not infer relevance from titles alone.
  Record source URLs, extract supported claim candidates broadly, normalize
  their wording, and merge duplicates. Do not collect implementation datasets,
  finalize test contracts, or create per-capability Replica projects in pass 1.
  The model proposes each testable restatement and routing classification; a
  person must confirm, edit, or reject it before scoring.
- Score each confirmed candidate from 0 to 2 on three axes only:
  `moat` (simple feature / some differentiation / repeatedly emphasized core
  moat), `business` (add-on / customer convenience / purchase or retention
  driver), and `separability` (sales, brand, or contract / mixed technical and
  business / bounded input-to-output capability).
- Set `total` to the three-axis sum from 0 to 6. Do not collect or score
  `observability` or `judgeability`. Select every confirmed, replicable claim
  with `total >= 4` for second-pass claim research.
- Keep one authoritative research artifact per company:
  `work/<company-slug>/research.json`. During pass 1, record every candidate in
  that file with the claim, source URL and supporting excerpt, testable
  restatement, routing, `replicable`, the three scores and their evidence,
  `total`, selection state, and reason. Route non-replicable claims to an
  evidence request instead of the Replica implementation flow.
- In pass 2, optimize for depth and work one selected claim at a time. Start
  from that claim's pass-1 source references; do not recrawl unrelated company
  pages. Separately search the exact feature, system, and product names plus
  relevant input, output, demo, customer, partner, technical, interview, and
  job terms. Reopen relevant pass-1 pages and inspect their claim-specific
  evidence. Collect enough public material to decide and prepare replication:
  usable datasets or sample documents, schemas and formats, APIs and SDKs,
  open-source implementations, papers and patents as technical clues, and
  benchmarks, reference answers, or other evaluation assets. Record access
  method, format, coverage, license or usage limits, and a synthetic-data
  fallback when the required input is not publicly available.
- Attach the second-pass result to the selected claim's `second_pass` field in
  the same `research.json`. It contains `canonical_claim`, `status`,
  `research_questions`, `sources`, `input`, `process`, `output`, `boundaries`,
  `contradictions`, `data_sources`, `implementation_evidence`,
  `evaluation_assets`, `replication_plan`, `readiness`, `limitations`,
  `open_questions`, and `handoff`. Use `confirmed`, `refined`, `merged`, or
  `rejected` for `status`. Every source records its URL, source type, the
  supported finding, and which claim field it supports.
- A second-pass result is complete only when every research question is
  answered or explicitly marked not publicly known; the canonical claim has
  at least one supporting official primary source; input, process, output, and
  boundaries are supported or explicitly unknown; independent corroboration
  is included when available; contradictions and limitations are recorded;
  required inputs have a usable public source or an explicit synthetic
  fallback; an implementation path and evaluation assets are identified; and
  `readiness.status` is `ready`, `partial`, or `blocked`. Do not require an
  arbitrary source count and do not infer missing details.
- For claims with status `confirmed` or `refined`, readiness `ready`, and
  handoff `build`, store the frozen input/output contract, acceptance criteria,
  output schema, exclusions, and at least three test cases in
  `second_pass.replication_contract`. Pass 2 is complete when all selected
  claims have a readiness decision and every ready contract has no placeholder.
- Do not create per-claim dossier, `evidence.json`, `spec.json`, or `tests.json`
  files during research. Only when Replica execution actually starts, expand
  one ready claim's frozen contract into
  `work/<company-slug>/runs/<capability-slug>/`, then build `replica.json`.
- Run each claim's generated cases in the current task. Keep candidate
  generation and judging as separate passes. When sub-agent execution is
  available and useful, use bounded Replica and Judge workers; otherwise label
  the Judge as same-session rather than independent.
- Write execution-only `results.jsonl` and `report.md` under that claim's run
  directory. Do not duplicate the company research into another report unless
  the user explicitly requests an export. Run `team-ai guard`, then return the
  capabilities, evidence levels, pass counts, limitations, and links to the
  artifacts.
