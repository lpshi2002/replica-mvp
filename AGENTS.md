# Agent Rules

## Replica workflow

For company research, Replica workflow questions, claim scoring, source
selection, replication readiness, or Replica execution, read and follow
`skills/replica-research/SKILL.md` before answering or acting. Treat that Skill
as the authoritative product workflow.

## Repository boundaries

- `.team-ai` is Git-ignored local verification state; never stage or commit it.
- Product code belongs under `src/`; tests belong under `tests/`.
- Generated company work belongs under `work/` and stays untracked.

## Verification

Before finalizing repository changes, run all three checks:

```bash
PYTHONPATH=src python -m unittest discover -s tests
team-ai verify
team-ai guard
```

Do not use team-ai as the source of collaboration rules, meeting recall, or
product direction. Moltbook owns collaboration; the Replica Skill owns the
product workflow.
