"""Build and evaluate evidence-bounded AI replicas."""

from .agent_harness import (
    finish_agent_harness,
    prepare_agent_harness,
    record_direct_agent_message,
    record_released_agent,
    record_agent_spawn,
    record_agent_spawn_failure,
    start_agent_claim,
)
from .builder import run_built_replica
from .completion import assess_replica_completion
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .evaluation import evaluate_frozen_suite, freeze_test_suite
from .intake import receive_second_pass
from .plan_safety import assess_plan_safety
from .project import build_project, evaluate_project, init_project, write_report
from .reporting import write_final_report
from .second_pass import parse_second_pass

__all__ = [
    "assess_plan_safety",
    "build_project",
    "evaluate_frozen_suite",
    "evaluate_project",
    "finalize_codex_operator",
    "freeze_test_suite",
    "init_project",
    "finish_agent_harness",
    "prepare_agent_harness",
    "record_direct_agent_message",
    "record_released_agent",
    "record_agent_spawn",
    "record_agent_spawn_failure",
    "start_agent_claim",
    "receive_second_pass",
    "parse_second_pass",
    "prepare_codex_operator",
    "run_built_replica",
    "assess_replica_completion",
    "write_final_report",
    "write_report",
]
