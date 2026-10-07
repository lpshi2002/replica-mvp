# Agent Rules

At the start of a Replica task, read `context/project-direction.md` for the
shared project goal, confirmed decisions, proposals, and open questions.
Codex and Claude Code use this same file; update it in place when the user
changes the project direction. Execution procedures remain in the Skills below.

When the user requests a Codex/Claude debate (for example, "토론해" or
"서로 리뷰해"), use the installed `agent-debate` skill and read
`context/README.md`. Resume only the explicitly identified task; ordinary
project work does not create a discussion folder.

For company research, Replica workflow questions, claim scoring, source
selection, replication readiness, or Replica execution, read and follow
`skills/replica-research/SKILL.md` before answering or acting. Treat that Skill
as the authoritative workflow.

A company evaluation request — a company name, URL, or description — runs the
full route by default: both research passes, then `single-harness-init` on the
completed `research.json`, one implementer for every selected claim, final
evaluation (the frozen public web demo for a claim whose selected
scenario has a `demo_plan`, otherwise sealed bundle evaluation), and
`agent-harness-finish`, which writes
`final-results/company-claims.json` for every researched claim. The request
itself approves this full run; stop after pass 2 only when the user asks for
research only. Research with no executable claim still ends with that company
result.

For the implementation step of a company evaluation, the root session follows
the single-implementer steps in the "Execute" section of
`skills/replica-research/SKILL.md`. Initialize with `--model-runtime codex` and
the init defaults (`gpt-6-astra`, reasoning effort `low`) unless the user names
another model. Spawn each claim's implementer with that model and effort and
`fork_turns=none`, giving it only the run directory, claim ID, and an
instruction to follow `.agents/skills/replica-implementer/SKILL.md`; record its
thread ID with `single-agent-start` (a canonical task path cannot be matched to a
Codex session log, so its usage would stay unknown); after
`agent-bundle-retry`, send `followup_task` to the same implementer and point it
to its `retry-feedback-NNN.json`. The root reads control results and the
implementer's short report, never edits or judges the implementation, and does
not pass screenshots or run values to it.

When the user asks for the Operator/Builder pair route (the multi-claim Replica
Agent harness), spawn one dedicated
Replica Agent with `model=gpt-6-astra`,
`reasoning_effort=medium`, and `fork_turns=none`. Give it only the Second JSON path, run directory, canonical
parent identity, and an instruction to follow
`.agents/skills/orchestrate-replica-agents/SKILL.md`. The root may wait for and
report lifecycle results but must not relay Operator/Builder semantic
messages. The Replica Agent itself creates each claim's sibling children with
explicit `gpt-6-astra` Operator (`reasoning_effort=medium`) and `gpt-5.6-terra`
Builder (`reasoning_effort=high`) model requests. Specify both efforts explicitly
when spawning the pair. For actual implementation, create one pair for every
selected function and activate all pairs concurrently: N functions mean N pairs.
Do not wait for another feature to finish before activating the next pair.

When a pair-route harness is ready, or the user asks to run the
direct Operator/Builder protocol on one, resume the same dedicated Replica Agent and existing child
identities instead of spawning a new pair. Give it only the harness registry
path and an instruction to follow
`.agents/skills/run-replica-agent-protocol/SKILL.md`. The root and Replica
Agent may send identity-only activation controls and receive control metadata,
but neither may relay, summarize, rewrite, or persist the semantic instruction
or feedback.

The standalone JSON-only route (`build-replica-operator`) was removed on
2026-10-08 because a Replica is delivered as a web app. A standalone
`replica-second-pass-result/v1` JSON is not an implementation entry point;
run company research so the claim reaches the harness routes above. Never
narrow a company claim to a JSON demo because it needs files or search.

These are direct implementation routes even if the Skills are not shown in the
current session's selector. Never route this work through a registered
Operator, the removed `replicate` command, an external generator command, or
an API model generator.

## Verification

Product code belongs under `src/`; tests belong under `tests/`.
Before finalizing code changes, run the relevant tests and the repository suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Before finalizing any changes, run `git diff --check` and review
`git status --short` and any staged file list for credentials, local databases,
and generated outputs that should remain untracked.
