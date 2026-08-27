from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

from .agent_execution import load_agent_execution_state_file
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .second_pass import MODEL_RUNTIMES, parse_second_pass


HARNESS_SCHEMA = "replica-agent-harness/v1"
SOL_MODEL = "gpt-5.6-sol"
TERRA_MODEL = "gpt-5.6-terra"
REGISTRY_NAME = "agent-harness.json"
FINAL_RESULT_SCHEMA = "replica-agent-final-result/v1"
IMPLEMENTATION_RESULT_SCHEMA = "replica-agent-implementation-result/v1"
CANDIDATE_NAME = "operator.json"
BUNDLE_MANIFEST_NAME = "implementation/manifest.json"
IMPLEMENTATION_BUNDLE_SCHEMA = "replica-implementation-bundle/v1"
BUILDER_CONTEXT_SCHEMA = "replica-builder-context/v1"
MAX_BUNDLE_FILES = 256
MAX_BUNDLE_BYTES = 20_000_000
PUBLIC_RESULTS_ROOT = "final-results"
EVALUATOR_VAULT_ROOT = "evaluator-vault"
FINAL_ARTIFACT_NAMES = {
    "replica_result",
    "replica",
    "evaluation_summary",
    "report_json",
    "report_markdown",
}
FAILED_RESULT_STATUSES = {
    "VALIDATION_FAILED",
    "RUNTIME_FAILED",
    "EVALUATION_FAILED",
}
MODEL_RUNTIME_DEPENDENCIES = {
    "codex": "codex-cli",
    "claude": "claude-code",
}


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reject_nonstandard_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(
            value,
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")


def _read_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid Agent harness registry: {error}") from None
    if (
        not isinstance(registry, dict)
        or registry.get("schema_version") != HARNESS_SCHEMA
        or not isinstance(registry.get("claims"), list)
        or not isinstance(registry.get("scheduling"), dict)
    ):
        raise ValueError("invalid Agent harness registry")
    return registry


def _replace_registry(path: Path, registry: dict[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    _write_new_json(temporary_path, registry)
    temporary_path.replace(path)


def _claim_record(registry: dict[str, Any], claim_id: str) -> dict[str, Any]:
    for claim in registry["claims"]:
        if isinstance(claim, dict) and claim.get("claim_id") == claim_id:
            return claim
    raise ValueError(f"unknown claim identity: {claim_id}")


def _builder_context(
    claim_id: str,
    payload: dict[str, Any],
    model_runtime: str,
) -> dict[str, Any]:
    if payload.get("schema_version") != "replica-agent-claim/v2":
        public_contract = deepcopy(payload)
        public_contract.pop("tests", None)
        return {
            "schema_version": BUILDER_CONTEXT_SCHEMA,
            "claim_id": claim_id,
            "model_runtime": {
                "provider": model_runtime,
                "transport": "local_cli",
            },
            "contract": public_contract,
        }

    second_pass = payload["second_pass"]
    scenarios = second_pass["replication_contract"]
    selected = next(
        scenario
        for scenario in scenarios
        if scenario["id"] == payload["selected_scenario_id"]
    )
    public_scenario = deepcopy(selected)
    public_scenario.pop("tests", None)
    return {
        "schema_version": BUILDER_CONTEXT_SCHEMA,
        "claim_id": claim_id,
        "model_runtime": deepcopy(payload["model_runtime"]),
        "company": deepcopy(payload["company"]),
        "first_pass": deepcopy(payload.get("first_pass")),
        "workflow": deepcopy(second_pass.get("workflow")),
        "findings": deepcopy(second_pass.get("findings")),
        "selected_scenario": public_scenario,
        "available_scenarios": [
            {
                key: deepcopy(scenario.get(key))
                for key in ("id", "self_sufficiency", "boundaries")
            }
            for scenario in scenarios
        ],
        "input_contract": deepcopy(payload["input_contract"]),
        "output_contract": deepcopy(payload["output_contract"]),
        "acceptance_criteria": deepcopy(payload["acceptance_criteria"]),
    }


def prepare_agent_harness(
    second_pass: Any,
    run_dir: Path,
    *,
    replica_agent_id: str,
    parent_agent_id: str,
    replica_agent_model: str = SOL_MODEL,
    operator_model: str = SOL_MODEL,
    builder_model: str = TERRA_MODEL,
    model_runtime: str = "codex",
) -> dict[str, Any]:
    """Prepare deterministic state for real Agent orchestration."""
    if not _is_nonempty_text(replica_agent_id) or not _is_nonempty_text(
        parent_agent_id
    ):
        raise ValueError("invalid Replica Agent identity")
    if not all(
        _is_nonempty_text(model)
        for model in (replica_agent_model, operator_model, builder_model)
    ):
        raise ValueError("invalid Agent model policy")
    if model_runtime not in MODEL_RUNTIMES:
        raise ValueError("invalid Replica model runtime")
    canonical = parse_second_pass(second_pass, model_runtime=model_runtime)
    run_dir.mkdir(parents=True, exist_ok=False)
    claims_root = run_dir / "claims"
    claims_root.mkdir()
    claims = []
    for canonical_claim in canonical["claims"]:
        claim_id = canonical_claim["claim_id"]
        claim_dir = claims_root / claim_id
        operator_dir = claim_dir / "operator"
        builder_dir = claim_dir / "builder"
        operator_dir.mkdir(parents=True)
        builder_dir.mkdir()
        claim_namespace = f"claims/{claim_id}"
        claim_payload_path = f"{claim_namespace}/claim.json"
        builder_context_path = f"{claim_namespace}/builder-context.json"
        _write_new_json(
            run_dir / claim_payload_path,
            canonical_claim["payload"],
        )
        _write_new_json(
            run_dir / builder_context_path,
            _builder_context(
                claim_id,
                canonical_claim["payload"],
                model_runtime,
            ),
        )
        claims.append(
            {
                "claim_id": claim_id,
                "claim_payload_owner": "replica_agent",
                "claim_payload_path": claim_payload_path,
                "builder_context_owner": "replica_agent",
                "builder_context_path": builder_context_path,
                "status": "PENDING",
                "namespace": claim_namespace,
                "operator": {
                    "agent_id": None,
                    "allowed_peer_agent_id": None,
                    "artifact_namespace": f"{claim_namespace}/operator",
                    "artifact_owner": "operator",
                    "claim_id": claim_id,
                    "parent_agent_id": replica_agent_id,
                    "requested_model": operator_model,
                    "role": "operator",
                    "status": "PENDING",
                },
                "builder": {
                    "agent_id": None,
                    "allowed_peer_agent_id": None,
                    "artifact_namespace": f"{claim_namespace}/builder",
                    "artifact_owner": "builder",
                    "claim_id": claim_id,
                    "parent_agent_id": replica_agent_id,
                    "requested_model": builder_model,
                    "role": "builder",
                    "status": "PENDING",
                },
                "smoke": {
                    "nonce": None,
                    "operator_to_builder": False,
                    "builder_to_operator": False,
                },
                "continuity": {
                    "phase": "CREATED",
                    "operator_agent_id": None,
                    "builder_agent_id": None,
                    "operator_status": "NOT_STARTED",
                    "builder_status": "NOT_STARTED",
                    "completed_rounds": [],
                    "next_round": 0,
                    "correction_count": 0,
                    "terminal_state": None,
                    "failure": None,
                },
            }
        )
    registry = {
        "schema_version": HARNESS_SCHEMA,
        "status": "RUNNING",
        "claim_collection_schema": canonical["schema_version"],
        "claim_count": canonical["claim_count"],
        "model_runtime": {
            "provider": model_runtime,
            "transport": "local_cli",
        },
        "replica_agent": {
            "agent_id": replica_agent_id,
            "parent_agent_id": parent_agent_id,
            "requested_model": replica_agent_model,
            "role": "replica_agent",
            "status": "RUNNING",
        },
        "scheduling": {
            "policy": "sequential_claim_pairs",
            "active_claim_id": None,
            "completed_claim_count": 0,
            "failed_claim_count": 0,
        },
        "filesystem": {
            "registry_owner": "replica_agent",
            "shared_mutation": "forbidden",
            "public_results_root": PUBLIC_RESULTS_ROOT,
            "evaluator_vault_root": EVALUATOR_VAULT_ROOT,
        },
        "claims": claims,
    }
    _write_new_json(run_dir / REGISTRY_NAME, registry)
    return registry


def prepare_agent_harness_from_path(
    source: Path,
    run_dir: Path,
    *,
    replica_agent_id: str,
    parent_agent_id: str,
    replica_agent_model: str = SOL_MODEL,
    operator_model: str = SOL_MODEL,
    builder_model: str = TERRA_MODEL,
    model_runtime: str = "codex",
) -> dict[str, Any]:
    """Read immutable Second JSON and prepare a real-Agent harness registry."""
    try:
        second_pass = json.loads(
            source.read_bytes().decode("utf-8-sig"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"invalid JSON in {source}: {error}") from None
    return prepare_agent_harness(
        second_pass,
        run_dir,
        replica_agent_id=replica_agent_id,
        parent_agent_id=parent_agent_id,
        replica_agent_model=replica_agent_model,
        operator_model=operator_model,
        builder_model=builder_model,
        model_runtime=model_runtime,
    )


def start_agent_claim(registry_path: Path, claim_id: str) -> dict[str, Any]:
    """Activate the next claim under sequential claim-pair scheduling."""
    registry = _read_registry(registry_path)
    scheduling = registry["scheduling"]
    if scheduling.get("active_claim_id") is not None:
        raise ValueError("claim already active")
    claim = _claim_record(registry, claim_id)
    next_pending = next(
        (
            candidate
            for candidate in registry["claims"]
            if candidate.get("status") == "PENDING"
        ),
        None,
    )
    if claim is not next_pending:
        raise ValueError("claim must follow sequential schedule")
    claim["status"] = "ACTIVE"
    scheduling["active_claim_id"] = claim_id
    _replace_registry(registry_path, registry)
    return registry


def record_agent_spawn(
    registry_path: Path,
    claim_id: str,
    *,
    role: str,
    agent_id: str,
    parent_agent_id: str,
    requested_model: str,
) -> dict[str, Any]:
    """Record one successful real Agent spawn and link a complete pair."""
    if role not in {"operator", "builder"}:
        raise ValueError(f"invalid Agent role: {role}")
    if not _is_nonempty_text(agent_id):
        raise ValueError("invalid spawned Agent identity")
    registry = _read_registry(registry_path)
    if registry["scheduling"].get("active_claim_id") != claim_id:
        raise ValueError("claim is not active")
    claim = _claim_record(registry, claim_id)
    agent = claim[role]
    if agent.get("status") != "PENDING":
        raise ValueError(f"{role} Agent spawn already recorded")
    if requested_model != agent.get("requested_model"):
        raise ValueError(f"{role} Agent model request does not match policy")
    if (
        parent_agent_id != registry["replica_agent"].get("agent_id")
        or parent_agent_id != agent.get("parent_agent_id")
    ):
        raise ValueError(f"{role} Agent is not a Replica Agent child")
    existing_agent_ids = set()
    for candidate in registry["claims"]:
        for candidate_role in ("operator", "builder"):
            record = candidate.get(candidate_role)
            if isinstance(record, dict) and record.get("agent_id") is not None:
                existing_agent_ids.add(record["agent_id"])
    if agent_id in existing_agent_ids:
        raise ValueError(f"duplicate spawned Agent identity: {agent_id}")
    agent["agent_id"] = agent_id
    agent["status"] = "SPAWNED"
    peer_role = "builder" if role == "operator" else "operator"
    peer = claim[peer_role]
    if peer.get("status") == "SPAWNED":
        agent["allowed_peer_agent_id"] = peer["agent_id"]
        peer["allowed_peer_agent_id"] = agent_id
        agent["status"] = "PEER_LINKED"
        peer["status"] = "PEER_LINKED"
        claim["status"] = "PEER_LINKED"
    _replace_registry(registry_path, registry)
    return registry


def record_agent_spawn_failure(
    registry_path: Path,
    claim_id: str,
    *,
    role: str,
    reason: str,
) -> dict[str, Any]:
    """Fail one claim pair closed when a required Agent cannot be spawned."""
    if role not in {"operator", "builder"}:
        raise ValueError(f"invalid Agent role: {role}")
    if not _is_nonempty_text(reason):
        raise ValueError("Agent spawn failure requires a reason")
    registry = _read_registry(registry_path)
    scheduling = registry["scheduling"]
    if scheduling.get("active_claim_id") != claim_id:
        raise ValueError("claim is not active")
    claim = _claim_record(registry, claim_id)
    failed_agent = claim[role]
    if failed_agent.get("status") != "PENDING":
        raise ValueError(f"{role} Agent is not awaiting spawn")
    failed_agent["status"] = "CREATION_FAILED"
    peer_role = "builder" if role == "operator" else "operator"
    peer = claim[peer_role]
    if peer.get("status") == "SPAWNED":
        peer["status"] = "RELEASE_REQUIRED"
        claim["status"] = "RELEASING_AFTER_CREATION_FAILURE"
    else:
        claim["status"] = "CREATION_FAILED"
        scheduling["active_claim_id"] = None
        scheduling["failed_claim_count"] = (
            scheduling.get("failed_claim_count", 0) + 1
        )
    claim["failure"] = {"reason": reason, "role": role}
    _replace_registry(registry_path, registry)
    return registry


def record_released_agent(
    registry_path: Path,
    claim_id: str,
    *,
    agent_id: str,
) -> dict[str, Any]:
    """Confirm interruption of an orphan sibling before releasing its slot."""
    registry = _read_registry(registry_path)
    scheduling = registry["scheduling"]
    if scheduling.get("active_claim_id") != claim_id:
        raise ValueError("claim is not active")
    claim = _claim_record(registry, claim_id)
    if claim.get("status") != "RELEASING_AFTER_CREATION_FAILURE":
        raise ValueError("claim is not awaiting Agent release")
    releasable_agents = [
        claim[role]
        for role in ("operator", "builder")
        if claim[role].get("status") == "RELEASE_REQUIRED"
        and claim[role].get("agent_id") == agent_id
    ]
    if len(releasable_agents) != 1:
        raise ValueError("released Agent identity does not match orphan sibling")
    releasable_agents[0]["status"] = "RELEASED"
    claim["status"] = "CREATION_FAILED"
    scheduling["active_claim_id"] = None
    scheduling["failed_claim_count"] = (
        scheduling.get("failed_claim_count", 0) + 1
    )
    _replace_registry(registry_path, registry)
    return registry


def record_direct_agent_message(
    registry_path: Path,
    claim_id: str,
    *,
    direction: str,
    sender_agent_id: str,
    recipient_agent_id: str,
    nonce: str,
) -> dict[str, Any]:
    """Record one verified direct message between an exact sibling pair."""
    directions = {
        "operator_to_builder": ("operator", "builder"),
        "builder_to_operator": ("builder", "operator"),
    }
    if direction not in directions:
        raise ValueError(f"invalid direct message direction: {direction}")
    if not _is_nonempty_text(nonce):
        raise ValueError("direct message nonce is required")
    registry = _read_registry(registry_path)
    scheduling = registry["scheduling"]
    if scheduling.get("active_claim_id") != claim_id:
        raise ValueError("claim is not active")
    claim = _claim_record(registry, claim_id)
    if claim.get("status") not in {"PEER_LINKED", "SMOKE_IN_PROGRESS"}:
        raise ValueError("claim pair is not ready for direct messaging")
    sender_role, recipient_role = directions[direction]
    sender = claim[sender_role]
    recipient = claim[recipient_role]
    if (
        sender_agent_id != sender.get("agent_id")
        or recipient_agent_id != recipient.get("agent_id")
        or sender.get("allowed_peer_agent_id") != recipient_agent_id
        or recipient.get("allowed_peer_agent_id") != sender_agent_id
    ):
        raise ValueError("direct message does not match paired Agent identities")
    smoke = claim["smoke"]
    if smoke.get(direction) is not False:
        raise ValueError(f"direct message already recorded: {direction}")
    recorded_nonce = smoke.get("nonce")
    if recorded_nonce is not None and recorded_nonce != nonce:
        raise ValueError("direct message nonce does not match claim pair")
    smoke["nonce"] = nonce
    smoke[direction] = True
    claim["status"] = "SMOKE_IN_PROGRESS"
    if smoke["operator_to_builder"] and smoke["builder_to_operator"]:
        claim["status"] = "READY_FOR_PROTOCOL"
        claim["operator"]["status"] = "READY_FOR_PROTOCOL"
        claim["builder"]["status"] = "READY_FOR_PROTOCOL"
        claim["continuity"]["phase"] = "READY"
        scheduling["active_claim_id"] = None
        scheduling["completed_claim_count"] = (
            scheduling.get("completed_claim_count", 0) + 1
        )
    _replace_registry(registry_path, registry)
    return registry


def start_agent_continuity(
    registry_path: Path,
    claim_id: str,
    *,
    operator_agent_id: str,
    builder_agent_id: str,
    nonce: str,
) -> dict[str, Any]:
    """Bind one ready sibling pair to a single long-lived claim session."""
    if not _is_nonempty_text(nonce):
        raise ValueError("Agent continuity nonce is required")
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    if claim.get("status") != "READY_FOR_PROTOCOL":
        raise ValueError("claim pair is not ready for Agent continuity")
    operator = claim["operator"]
    builder = claim["builder"]
    if (
        operator.get("agent_id") != operator_agent_id
        or builder.get("agent_id") != builder_agent_id
        or operator.get("allowed_peer_agent_id") != builder_agent_id
        or builder.get("allowed_peer_agent_id") != operator_agent_id
    ):
        raise ValueError("Agent continuity does not match sibling identities")
    if claim.get("smoke", {}).get("nonce") != nonce:
        raise ValueError("Agent continuity nonce does not match claim pair")
    continuity = claim.get("continuity")
    if continuity is None:
        continuity = {
            "phase": "READY",
            "operator_agent_id": None,
            "builder_agent_id": None,
            "operator_status": "NOT_STARTED",
            "builder_status": "NOT_STARTED",
            "completed_rounds": [],
            "next_round": 0,
            "correction_count": 0,
            "terminal_state": None,
            "failure": None,
        }
        claim["continuity"] = continuity
    if not isinstance(continuity, dict) or continuity.get("phase") != "READY":
        raise ValueError("Agent continuity session already started")
    continuity.update(
        {
            "phase": "PAIR_ACTIVE",
            "operator_agent_id": operator_agent_id,
            "builder_agent_id": builder_agent_id,
            "operator_status": "ACTIVE_FOR_CLAIM",
            "builder_status": "ACTIVE_FOR_CLAIM",
        }
    )
    _replace_registry(registry_path, registry)
    return registry


def record_agent_continuity_round(
    registry_path: Path,
    claim_id: str,
    *,
    round_number: int,
    operator_agent_id: str,
    builder_agent_id: str,
    nonce: str,
    operator_to_builder_direct: bool,
    builder_to_operator_direct: bool,
) -> dict[str, Any]:
    """Record one direct round trip without completing the bound pair."""
    if (
        not isinstance(round_number, int)
        or isinstance(round_number, bool)
        or round_number < 0
    ):
        raise ValueError("Agent continuity round must be a non-negative integer")
    if (
        operator_to_builder_direct is not True
        or builder_to_operator_direct is not True
    ):
        raise ValueError("Agent continuity round must be directly bidirectional")
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    continuity = claim.get("continuity")
    if not isinstance(continuity, dict) or continuity.get("phase") not in {
        "PAIR_ACTIVE",
        "ROUND_TRIP_COMPLETE",
    }:
        raise ValueError("Agent continuity pair is not active")
    if (
        continuity.get("operator_agent_id") != operator_agent_id
        or continuity.get("builder_agent_id") != builder_agent_id
        or claim["operator"].get("agent_id") != operator_agent_id
        or claim["builder"].get("agent_id") != builder_agent_id
    ):
        raise ValueError("Agent continuity round changed sibling identities")
    if claim.get("smoke", {}).get("nonce") != nonce:
        raise ValueError("Agent continuity nonce does not match claim pair")
    if continuity.get("next_round") != round_number:
        raise ValueError("Agent continuity round is out of sequence")
    completed_rounds = continuity.get("completed_rounds")
    if not isinstance(completed_rounds, list):
        raise ValueError("invalid Agent continuity round history")
    completed_rounds.append(round_number)
    continuity["next_round"] = round_number + 1
    continuity["correction_count"] = max(0, round_number)
    continuity["phase"] = "ROUND_TRIP_COMPLETE"
    continuity["operator_status"] = "WAITING_FOR_PEER"
    continuity["builder_status"] = "WAITING_FOR_PEER"
    _replace_registry(registry_path, registry)
    return registry


def finish_agent_continuity(
    registry_path: Path,
    claim_id: str,
    *,
    terminal_state: str,
    operator_agent_id: str,
    builder_agent_id: str,
    nonce: str,
    terminal_acknowledged_directly: bool,
    execution_state_path: Path | None = None,
) -> dict[str, Any]:
    """Complete a long-lived pair only after an explicit direct terminal."""
    if terminal_state not in {"SUCCESS", "FAILED", "ABORTED"}:
        raise ValueError("invalid Agent continuity terminal state")
    if terminal_acknowledged_directly is not True:
        raise ValueError("Agent continuity terminal requires a direct ack")
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    continuity = claim.get("continuity")
    if not isinstance(continuity, dict) or continuity.get("phase") not in {
        "PAIR_ACTIVE",
        "ROUND_TRIP_COMPLETE",
    }:
        raise ValueError("Agent continuity pair is not active")
    if (
        continuity.get("operator_agent_id") != operator_agent_id
        or continuity.get("builder_agent_id") != builder_agent_id
        or claim["operator"].get("agent_id") != operator_agent_id
        or claim["builder"].get("agent_id") != builder_agent_id
    ):
        raise ValueError("Agent continuity terminal changed sibling identities")
    if claim.get("smoke", {}).get("nonce") != nonce:
        raise ValueError("Agent continuity nonce does not match claim pair")
    if execution_state_path is None:
        if (
            terminal_state != "ABORTED"
            and continuity.get("completed_rounds") != [0, 1, 2, 3]
        ):
            raise ValueError(
                "Agent continuity terminal requires four completed rounds"
            )
    else:
        if terminal_state == "ABORTED":
            raise ValueError("ABORTED continuity cannot claim execution success")
        expected_state_path = (
            registry_path.parent
            / claim["operator"]["artifact_namespace"]
            / "execution-state.json"
        ).resolve()
        if execution_state_path.resolve() != expected_state_path:
            raise ValueError("execution state must remain in Operator namespace")
        claim_payload_path = registry_path.parent / claim["claim_payload_path"]
        try:
            claim_payload = json.loads(
                claim_payload_path.read_text(encoding="utf-8"),
                parse_constant=_reject_nonstandard_constant,
            )
        except (OSError, ValueError) as error:
            raise ValueError(f"invalid immutable claim payload: {error}") from None
        state, state_sha256 = load_agent_execution_state_file(
            execution_state_path,
            claim_payload,
        )
        if (
            state["claim_id"] != claim_id
            or state["operator_agent_id"] != operator_agent_id
            or state["builder_agent_id"] != builder_agent_id
            or state["pair_nonce"] != nonce
        ):
            raise ValueError("execution state changed sibling binding")
        if state["status"] != terminal_state or state["terminal_state"] != terminal_state:
            raise ValueError("execution state is not the claimed terminal result")
        correction_count = state["correction_count"]
        expected_rounds = list(range(correction_count + 1))
        if continuity.get("completed_rounds") != expected_rounds:
            raise ValueError("execution terminal does not match completed rounds")
        continuity["correction_count"] = correction_count
        claim["status"] = f"EXECUTION_{terminal_state}"
        final_attempt = state["attempts"][-1]
        claim["execution_result"] = {
            "status": terminal_state,
            "correction_count": correction_count,
            "completed_rounds": expected_rounds,
            "execution_state_sha256": state_sha256,
            "candidate_path": final_attempt["candidate_path"],
            "test_suite_sha256": final_attempt["test_suite_sha256"],
            "passed_criteria": final_attempt["passed_criteria"],
            "total_criteria": final_attempt["total_criteria"],
            "failed_check_count": final_attempt["failed_check_count"],
            "judge_identity": final_attempt["judge_identity"],
            "judge_mode": final_attempt["judge_mode"],
        }
    continuity["phase"] = f"TERMINAL_{terminal_state}"
    continuity["terminal_state"] = terminal_state
    continuity["operator_status"] = "COMPLETED"
    continuity["builder_status"] = "COMPLETED"
    _replace_registry(registry_path, registry)
    return registry


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Agent final result escaped the harness run directory")
    return resolved.relative_to(root.resolve()).as_posix()


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_bundle_path(value: Any) -> bool:
    if not _is_nonempty_text(value) or "\\" in value:
        return False
    path = Path(value)
    return bool(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _selected_scenario(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("schema_version") != "replica-agent-claim/v2":
        return None
    return next(
        (
            scenario
            for scenario in payload["second_pass"]["replication_contract"]
            if scenario["id"] == payload["selected_scenario_id"]
        ),
        None,
    )


def _bundle_dependency_level(
    claim_payload: dict[str, Any],
    selected: dict[str, Any],
    dependencies: list[dict[str, str]],
) -> str | None:
    runtime = claim_payload.get("model_runtime")
    expected_runtime = (
        MODEL_RUNTIME_DEPENDENCIES.get(runtime.get("provider"))
        if isinstance(runtime, dict)
        else None
    )
    declared_runtimes = {
        dependency["name"]
        for dependency in dependencies
        if dependency["name"] in MODEL_RUNTIME_DEPENDENCIES.values()
    }
    if declared_runtimes and declared_runtimes != {expected_runtime}:
        return None
    dependency_level = selected["self_sufficiency"]
    if expected_runtime in declared_runtimes and dependency_level == "oss_only":
        return "commercial_api"
    return dependency_level


def _validate_implementation_bundle(
    run_dir: Path,
    claim_id: str,
    manifest_path: Path,
    claim_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid Terra implementation manifest: {error}") from None
    fields = {
        "schema_version",
        "claim_id",
        "scenario_id",
        "implementation_type",
        "dependency_level",
        "input_contract",
        "output_contract",
        "entrypoint",
        "command",
        "dependencies",
        "environment_variables",
        "files",
    }
    dependencies = manifest.get("dependencies")
    environment_variables = manifest.get("environment_variables")
    files = manifest.get("files")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != fields
        or manifest.get("schema_version") != IMPLEMENTATION_BUNDLE_SCHEMA
        or manifest.get("claim_id") != claim_id
        or not _is_nonempty_text(manifest.get("scenario_id"))
        or manifest.get("implementation_type") not in {"prompt_only", "code", "hybrid"}
        or manifest.get("dependency_level")
        not in {"oss_only", "commercial_api", "proprietary_data"}
        or not _safe_bundle_path(manifest.get("entrypoint"))
        or not isinstance(manifest.get("command"), list)
        or not manifest["command"]
        or not all(_is_nonempty_text(item) for item in manifest["command"])
        or not isinstance(dependencies, list)
        or not all(
            isinstance(dependency, dict)
            and set(dependency) == {"name", "version", "source", "license"}
            and all(_is_nonempty_text(dependency.get(field)) for field in dependency)
            and dependency["source"].startswith(("https://", "http://"))
            for dependency in dependencies
        )
        or not isinstance(environment_variables, list)
        or len(set(environment_variables)) != len(environment_variables)
        or not all(
            isinstance(name, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
            for name in environment_variables
        )
        or not isinstance(files, list)
        or not files
        or len(files) > MAX_BUNDLE_FILES
    ):
        raise ValueError("invalid Terra implementation bundle contract")

    file_paths = [record.get("path") for record in files if isinstance(record, dict)]
    if (
        len(file_paths) != len(files)
        or len(set(file_paths)) != len(file_paths)
        or manifest["entrypoint"] not in file_paths
    ):
        raise ValueError("invalid Terra implementation bundle files")
    bundle_root = manifest_path.parent.resolve()
    artifacts: dict[str, dict[str, str]] = {}
    total_bytes = 0
    for record in files:
        if (
            set(record) != {"path", "sha256"}
            or not _safe_bundle_path(record.get("path"))
            or not _is_sha256(record.get("sha256"))
        ):
            raise ValueError("invalid Terra implementation bundle file record")
        path = bundle_root / record["path"]
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(bundle_root)
            or _sha256(path) != record["sha256"]
        ):
            raise ValueError("Terra implementation bundle file hash mismatch")
        total_bytes += path.stat().st_size
        artifacts[record["path"]] = {
            "path": _relative_path(run_dir, path),
            "sha256": record["sha256"],
        }
    if total_bytes > MAX_BUNDLE_BYTES:
        raise ValueError("Terra implementation bundle exceeds size limit")
    present = set()
    for path in bundle_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Terra implementation bundle cannot contain symlinks")
        if path.is_file() and path != manifest_path:
            present.add(path.relative_to(bundle_root).as_posix())
    if present != set(file_paths):
        raise ValueError("Terra implementation bundle contains undeclared files")

    selected = _selected_scenario(claim_payload)
    if selected is not None:
        if (
            manifest["scenario_id"] != selected["id"]
            or manifest["dependency_level"]
            != _bundle_dependency_level(claim_payload, selected, dependencies)
            or manifest["input_contract"] != selected["input"]
            or manifest["output_contract"] != selected["output"]
        ):
            raise ValueError("Terra implementation bundle changed the selected scenario")
    elif (
        manifest["input_contract"] != claim_payload.get("input_contract")
        or manifest["output_contract"] != claim_payload.get("output_contract")
    ):
        raise ValueError("Terra implementation bundle changed the claim contract")
    return manifest, artifacts


def finalize_agent_candidate(
    registry_path: Path,
    claim_id: str,
    candidate_path: Path,
) -> dict[str, Any]:
    """Evaluate one Terra candidate and bind its published result to the claim."""
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    if (
        claim.get("status") != "EXECUTION_SUCCESS"
        or claim.get("continuity", {}).get("phase") != "TERMINAL_SUCCESS"
    ):
        raise ValueError("Agent candidate requires a successful execution terminal")
    if "final_result" in claim or "implementation_result" in claim:
        raise ValueError("Agent candidate is already finalized")

    run_dir = registry_path.parent.resolve()
    candidate_relative_path = claim.get("execution_result", {}).get(
        "candidate_path",
        f"claims/{claim_id}/builder/{CANDIDATE_NAME}",
    )
    allowed_candidates = {
        f"claims/{claim_id}/builder/{CANDIDATE_NAME}",
        f"claims/{claim_id}/builder/{BUNDLE_MANIFEST_NAME}",
    }
    if candidate_relative_path not in allowed_candidates:
        raise ValueError("Agent execution did not bind a supported Terra candidate")
    expected_candidate = run_dir / candidate_relative_path
    resolved_candidate_path = _relative_path(run_dir, expected_candidate)
    if (
        resolved_candidate_path != candidate_relative_path
        or candidate_path.is_symlink()
        or expected_candidate.parent.is_symlink()
        or candidate_path.resolve() != expected_candidate.resolve()
        or expected_candidate.is_symlink()
        or not expected_candidate.is_file()
    ):
        raise ValueError("Terra candidate must match the bound Builder artifact")

    claim_payload = run_dir / claim["claim_payload_path"]
    if (
        _relative_path(run_dir, claim_payload) != f"claims/{claim_id}/claim.json"
        or claim_payload.is_symlink()
        or not claim_payload.is_file()
    ):
        raise ValueError("Agent candidate claim payload is not immutable")
    try:
        claim_payload_value = json.loads(
            claim_payload.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid immutable claim payload: {error}") from None
    execution_state_path = (
        run_dir / claim["operator"]["artifact_namespace"] / "execution-state.json"
    )
    _, execution_state_sha256 = load_agent_execution_state_file(
        execution_state_path,
        claim_payload_value,
    )
    if execution_state_sha256 != claim["execution_result"]["execution_state_sha256"]:
        raise ValueError("Terra candidate changed the bound execution state")
    candidate_sha256 = _sha256(expected_candidate)
    if candidate_relative_path.endswith(BUNDLE_MANIFEST_NAME):
        manifest, artifacts = _validate_implementation_bundle(
            run_dir,
            claim_id,
            expected_candidate,
            claim_payload_value,
        )
        claim["status"] = "IMPLEMENTATION_READY"
        claim["implementation_result"] = {
            "schema_version": IMPLEMENTATION_RESULT_SCHEMA,
            "status": "IMPLEMENTATION_READY",
            "candidate_path": candidate_relative_path,
            "candidate_sha256": candidate_sha256,
            "execution_state_sha256": execution_state_sha256,
            "scenario_id": manifest["scenario_id"],
            "implementation_type": manifest["implementation_type"],
            "dependency_level": manifest["dependency_level"],
            "entrypoint": manifest["entrypoint"],
            "command": manifest["command"],
            "dependencies": manifest["dependencies"],
            "environment_variables": manifest["environment_variables"],
            "artifacts": artifacts,
        }
        _replace_registry(registry_path, registry)
        return registry

    if claim_payload_value.get("schema_version") == "replica-agent-claim/v2":
        raise ValueError("research claims require an implementation bundle")
    workspace = run_dir / PUBLIC_RESULTS_ROOT
    evaluator_vault = run_dir / EVALUATOR_VAULT_ROOT
    candidate_bytes = expected_candidate.read_bytes()
    prepared = prepare_codex_operator(claim_payload, workspace, evaluator_vault)
    operator_path = Path(prepared["operator_path"])
    with operator_path.open("xb") as stream:
        stream.write(candidate_bytes)
    result = finalize_codex_operator(
        Path(prepared["task_dir"]),
        workspace,
        evaluator_vault,
        include_report=True,
    )

    final_result: dict[str, Any] = {
        "schema_version": FINAL_RESULT_SCHEMA,
        "status": result["status"],
        "candidate_path": candidate_relative_path,
        "candidate_sha256": candidate_sha256,
        "execution_state_sha256": claim["execution_result"][
            "execution_state_sha256"
        ],
        "attempt": result["attempt"],
        "max_attempts": result["max_attempts"],
        "retryable": result["retryable"],
    }
    if "evaluation" in result:
        final_result["evaluation"] = result["evaluation"]

    if result["status"] == "BUILT_AND_PASSED":
        public_run_dir = Path(result["run_dir"])
        published = {
            "replica_result": public_run_dir / "replica-result.json",
            "replica": Path(result["replica_path"]),
            "evaluation_summary": public_run_dir / "evaluation-summary.json",
            "report_json": public_run_dir / "report.json",
            "report_markdown": Path(result["report_path"]),
        }
        final_result["public_run_dir"] = _relative_path(run_dir, public_run_dir)
        final_result["artifacts"] = {
            name: {
                "path": _relative_path(run_dir, path),
                "sha256": _sha256(path),
            }
            for name, path in published.items()
        }
        claim["status"] = "RESULT_SUCCESS"
    else:
        claim["status"] = "RESULT_FAILED"
    claim["final_result"] = final_result
    _replace_registry(registry_path, registry)
    return registry


def _validate_bound_artifact(
    run_dir: Path,
    record: Any,
    *,
    label: str,
) -> Path:
    if (
        not isinstance(record, dict)
        or set(record) != {"path", "sha256"}
        or not _is_nonempty_text(record.get("path"))
        or not _is_nonempty_text(record.get("sha256"))
    ):
        raise ValueError(f"invalid Agent final result artifact: {label}")
    path = run_dir / record["path"]
    if (
        _relative_path(run_dir, path) != record["path"]
        or path.is_symlink()
        or not path.is_file()
        or _sha256(path) != record["sha256"]
    ):
        raise ValueError(f"Agent final result artifact hash mismatch: {label}")
    return path


def _validate_final_result(run_dir: Path, claim: dict[str, Any]) -> None:
    final_result = claim.get("final_result")
    base_fields = {
        "schema_version",
        "status",
        "candidate_path",
        "candidate_sha256",
        "execution_state_sha256",
        "attempt",
        "max_attempts",
        "retryable",
    }
    if (
        not isinstance(final_result, dict)
        or final_result.get("schema_version") != FINAL_RESULT_SCHEMA
        or not isinstance(final_result.get("attempt"), int)
        or not isinstance(final_result.get("max_attempts"), int)
        or not isinstance(final_result.get("retryable"), bool)
        or final_result.get("execution_state_sha256")
        != claim.get("execution_result", {}).get("execution_state_sha256")
    ):
        raise ValueError("invalid Agent final result binding")

    candidate = _validate_bound_artifact(
        run_dir,
        {
            "path": final_result.get("candidate_path"),
            "sha256": final_result.get("candidate_sha256"),
        },
        label="candidate",
    )
    if candidate != (
        run_dir / "claims" / claim["claim_id"] / "builder" / CANDIDATE_NAME
    ).resolve():
        raise ValueError("invalid Agent final result candidate binding")

    if claim.get("status") == "RESULT_FAILED":
        allowed_fields = base_fields | (
            {"evaluation"} if "evaluation" in final_result else set()
        )
        if (
            set(final_result) != allowed_fields
            or final_result.get("status") not in FAILED_RESULT_STATUSES
        ):
            raise ValueError("invalid failed Agent final result")
        return

    if (
        claim.get("status") != "RESULT_SUCCESS"
        or set(final_result)
        != base_fields | {"evaluation", "public_run_dir", "artifacts"}
        or final_result.get("status") != "BUILT_AND_PASSED"
        or final_result.get("retryable") is not False
        or final_result.get("evaluation", {}).get("status") != "PASSED"
    ):
        raise ValueError("invalid successful Agent final result")
    artifacts = final_result.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != FINAL_ARTIFACT_NAMES:
        raise ValueError("invalid Agent final result artifacts")
    artifact_paths = {
        name: _validate_bound_artifact(run_dir, record, label=name)
        for name, record in artifacts.items()
    }
    public_run_dir = run_dir / final_result["public_run_dir"]
    if (
        _relative_path(run_dir, public_run_dir) != final_result["public_run_dir"]
        or public_run_dir.is_symlink()
        or not public_run_dir.is_dir()
        or not public_run_dir.resolve().is_relative_to(
            (run_dir / PUBLIC_RESULTS_ROOT / "runs").resolve()
        )
        or any(
            path.parent != public_run_dir.resolve()
            for path in artifact_paths.values()
        )
    ):
        raise ValueError("invalid Agent public result directory")
    try:
        public_result = json.loads(
            artifact_paths["replica_result"].read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid Agent public result: {error}") from None
    if (
        not isinstance(public_result, dict)
        or public_result.get("schema_version") != "replica-public-result/v1"
        or public_result.get("status") != "BUILT_AND_PASSED"
        or public_result.get("replica_id") != claim["claim_id"]
        or public_result.get("evaluation", {}).get("status") != "PASSED"
    ):
        raise ValueError("invalid Agent public result contract")


def _validate_implementation_result(run_dir: Path, claim: dict[str, Any]) -> None:
    result = claim.get("implementation_result")
    fields = {
        "schema_version",
        "status",
        "candidate_path",
        "candidate_sha256",
        "execution_state_sha256",
        "scenario_id",
        "implementation_type",
        "dependency_level",
        "entrypoint",
        "command",
        "dependencies",
        "environment_variables",
        "artifacts",
    }
    if (
        not isinstance(result, dict)
        or set(result) != fields
        or result.get("schema_version") != IMPLEMENTATION_RESULT_SCHEMA
        or result.get("status") != "IMPLEMENTATION_READY"
        or result.get("execution_state_sha256")
        != claim.get("execution_result", {}).get("execution_state_sha256")
    ):
        raise ValueError("invalid Agent implementation result binding")
    manifest_path = _validate_bound_artifact(
        run_dir,
        {
            "path": result.get("candidate_path"),
            "sha256": result.get("candidate_sha256"),
        },
        label="implementation manifest",
    )
    expected_manifest = (
        run_dir
        / "claims"
        / claim["claim_id"]
        / "builder"
        / BUNDLE_MANIFEST_NAME
    ).resolve()
    if manifest_path != expected_manifest:
        raise ValueError("invalid Agent implementation candidate binding")
    claim_payload_path = run_dir / claim["claim_payload_path"]
    try:
        claim_payload = json.loads(
            claim_payload_path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid immutable claim payload: {error}") from None
    state, state_sha256 = load_agent_execution_state_file(
        run_dir
        / claim["operator"]["artifact_namespace"]
        / "execution-state.json",
        claim_payload,
    )
    if (
        state_sha256 != result["execution_state_sha256"]
        or state.get("status") != "SUCCESS"
        or state["attempts"][-1].get("candidate_path")
        != result["candidate_path"]
    ):
        raise ValueError("Agent implementation result changed the execution binding")
    manifest, expected_artifacts = _validate_implementation_bundle(
        run_dir,
        claim["claim_id"],
        manifest_path,
        claim_payload,
    )
    summary_fields = {
        "scenario_id",
        "implementation_type",
        "dependency_level",
        "entrypoint",
        "command",
        "dependencies",
        "environment_variables",
    }
    if (
        any(result[field] != manifest[field] for field in summary_fields)
        or result.get("artifacts") != expected_artifacts
    ):
        raise ValueError("Agent implementation result changed the Terra bundle")


def record_agent_premature_completion(
    registry_path: Path,
    claim_id: str,
    *,
    completed_agent_id: str,
    reason: str,
) -> dict[str, Any]:
    """Abort continuity when one bound Agent returns final before terminal."""
    if not _is_nonempty_text(reason):
        raise ValueError("premature Agent completion requires a reason")
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    continuity = claim.get("continuity")
    if not isinstance(continuity, dict) or continuity.get("phase") not in {
        "PAIR_ACTIVE",
        "ROUND_TRIP_COMPLETE",
    }:
        raise ValueError("Agent continuity pair is not active")
    roles = {
        continuity.get("operator_agent_id"): "operator",
        continuity.get("builder_agent_id"): "builder",
    }
    completed_role = roles.get(completed_agent_id)
    if completed_role is None:
        raise ValueError("premature completion changed sibling identity")
    peer_role = "builder" if completed_role == "operator" else "operator"
    continuity["phase"] = "ABORTED"
    continuity["terminal_state"] = "ABORTED"
    continuity[f"{completed_role}_status"] = "PREMATURELY_COMPLETED"
    continuity[f"{peer_role}_status"] = "CONTINUITY_FAILED"
    continuity["failure"] = {
        "agent_id": completed_agent_id,
        "reason": reason,
    }
    claim["status"] = "EXECUTION_ABORTED"
    claim["execution_result"] = {
        "status": "ABORTED",
        "correction_count": continuity.get("correction_count", 0),
        "completed_rounds": list(continuity.get("completed_rounds", [])),
    }
    _replace_registry(registry_path, registry)
    return registry


def finish_agent_harness(registry_path: Path) -> dict[str, Any]:
    """Finalize Replica Agent state after every claim reaches a terminal state."""
    registry = _read_registry(registry_path)
    if registry["scheduling"].get("active_claim_id") is not None:
        raise ValueError("cannot finish Agent harness with an active claim")
    statuses = [claim.get("status") for claim in registry["claims"]]
    protocol_terminal_statuses = {"READY_FOR_PROTOCOL", "CREATION_FAILED"}
    execution_terminal_statuses = {
        "IMPLEMENTATION_READY",
        "RESULT_SUCCESS",
        "RESULT_FAILED",
        "EXECUTION_FAILED",
        "EXECUTION_ABORTED",
        "CREATION_FAILED",
    }
    if not statuses:
        raise ValueError("cannot finish incomplete Agent harness")
    for claim in registry["claims"]:
        if claim.get("status") in {"RESULT_SUCCESS", "RESULT_FAILED"}:
            _validate_final_result(registry_path.parent.resolve(), claim)
        elif claim.get("status") == "IMPLEMENTATION_READY":
            _validate_implementation_result(registry_path.parent.resolve(), claim)
    if any(
        isinstance(status, str)
        and (
            status.startswith("EXECUTION_")
            or status.startswith("RESULT_")
            or status == "IMPLEMENTATION_READY"
        )
        for status in statuses
    ):
        if "EXECUTION_SUCCESS" in statuses:
            raise ValueError(
                "cannot finish Agent execution before candidate finalization"
            )
        if any(status not in execution_terminal_statuses for status in statuses):
            raise ValueError("cannot finish incomplete Agent execution")
        if all(status == "RESULT_SUCCESS" for status in statuses):
            status = "EXECUTION_SUCCESS"
        elif all(
            status in {"RESULT_SUCCESS", "IMPLEMENTATION_READY"}
            for status in statuses
        ):
            status = "IMPLEMENTATION_READY"
        else:
            status = "EXECUTION_COMPLETED_WITH_FAILURES"
    else:
        if any(status not in protocol_terminal_statuses for status in statuses):
            raise ValueError("cannot finish incomplete Agent harness")
        status = (
            "READY_FOR_PROTOCOL"
            if all(status == "READY_FOR_PROTOCOL" for status in statuses)
            else "COMPLETED_WITH_CREATION_FAILURES"
        )
    registry["status"] = status
    registry["replica_agent"]["status"] = status
    _replace_registry(registry_path, registry)
    return registry
