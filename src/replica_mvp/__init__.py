"""Build and evaluate evidence-bounded AI replicas."""

from .agent_harness import (
    finalize_agent_candidate,
    finish_agent_continuity,
    finish_agent_harness,
    prepare_agent_harness,
    record_agent_continuity_round,
    record_agent_premature_completion,
    record_direct_agent_message,
    record_released_agent,
    record_agent_spawn,
    record_agent_spawn_failure,
    start_agent_claim,
    start_agent_continuity,
)
from .agent_execution import (
    advance_agent_execution,
    advance_agent_execution_from_paths,
    create_agent_execution_state,
    create_agent_execution_state_file,
    load_agent_execution_state_file,
    replica_success_criteria,
)
from .agent_protocol import (
    validate_agent_protocol_message,
    validate_agent_protocol_message_from_path,
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
    "finalize_agent_candidate",
    "finalize_codex_operator",
    "freeze_test_suite",
    "init_project",
    "finish_agent_harness",
    "finish_agent_continuity",
    "prepare_agent_harness",
    "record_agent_continuity_round",
    "record_agent_premature_completion",
    "record_direct_agent_message",
    "record_released_agent",
    "record_agent_spawn",
    "record_agent_spawn_failure",
    "start_agent_claim",
    "start_agent_continuity",
    "validate_agent_protocol_message",
    "validate_agent_protocol_message_from_path",
    "advance_agent_execution",
    "advance_agent_execution_from_paths",
    "create_agent_execution_state",
    "create_agent_execution_state_file",
    "load_agent_execution_state_file",
    "replica_success_criteria",
    "receive_second_pass",
    "parse_second_pass",
    "prepare_codex_operator",
    "run_built_replica",
    "assess_replica_completion",
    "write_final_report",
    "write_report",
]
