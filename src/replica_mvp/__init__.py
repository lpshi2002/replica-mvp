"""Build and evaluate evidence-bounded AI replicas."""

from .builder import run_built_replica
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .evaluation import evaluate_frozen_suite, freeze_test_suite
from .intake import receive_second_pass
from .plan_safety import assess_plan_safety
from .project import (
    build_project,
    evaluate_project,
    finalize_first_pass,
    init_project,
    write_report,
)
from .reporting import write_final_report

__all__ = [
    "assess_plan_safety",
    "build_project",
    "evaluate_frozen_suite",
    "evaluate_project",
    "finalize_codex_operator",
    "finalize_first_pass",
    "freeze_test_suite",
    "init_project",
    "receive_second_pass",
    "prepare_codex_operator",
    "run_built_replica",
    "write_final_report",
    "write_report",
]
