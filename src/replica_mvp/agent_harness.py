from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn

from .second_pass import parse_second_pass


HARNESS_SCHEMA = "replica-agent-harness/v1"
SOL_MODEL = "gpt-5.6-sol"
TERRA_MODEL = "gpt-5.6-terra"
REGISTRY_NAME = "agent-harness.json"


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


def prepare_agent_harness(
    second_pass: Any,
    run_dir: Path,
    *,
    replica_agent_id: str,
    parent_agent_id: str,
) -> dict[str, Any]:
    """Prepare deterministic state for real Codex Agent orchestration."""
    if not _is_nonempty_text(replica_agent_id) or not _is_nonempty_text(
        parent_agent_id
    ):
        raise ValueError("invalid Replica Agent identity")
    canonical = parse_second_pass(second_pass)
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
        _write_new_json(
            run_dir / claim_payload_path,
            canonical_claim["payload"],
        )
        claims.append(
            {
                "claim_id": claim_id,
                "claim_payload_owner": "replica_agent",
                "claim_payload_path": claim_payload_path,
                "status": "PENDING",
                "namespace": claim_namespace,
                "operator": {
                    "agent_id": None,
                    "allowed_peer_agent_id": None,
                    "artifact_namespace": f"{claim_namespace}/operator",
                    "artifact_owner": "operator",
                    "claim_id": claim_id,
                    "parent_agent_id": replica_agent_id,
                    "requested_model": SOL_MODEL,
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
                    "requested_model": TERRA_MODEL,
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
        "replica_agent": {
            "agent_id": replica_agent_id,
            "parent_agent_id": parent_agent_id,
            "requested_model": SOL_MODEL,
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
    correction_count: int | None = None,
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
    if correction_count is None:
        if (
            terminal_state != "ABORTED"
            and continuity.get("completed_rounds") != [0, 1, 2, 3]
        ):
            raise ValueError(
                "Agent continuity terminal requires four completed rounds"
            )
    else:
        if (
            type(correction_count) is not int
            or correction_count < 0
            or correction_count > 3
        ):
            raise ValueError("execution correction_count must be between 0 and 3")
        if terminal_state == "ABORTED":
            raise ValueError("ABORTED continuity cannot claim an execution count")
        expected_rounds = list(range(correction_count + 1))
        if continuity.get("completed_rounds") != expected_rounds:
            raise ValueError("execution terminal does not match completed rounds")
        if terminal_state == "FAILED" and correction_count != 3:
            raise ValueError("execution failure requires correction 3")
        continuity["correction_count"] = correction_count
        claim["status"] = f"EXECUTION_{terminal_state}"
        claim["execution_result"] = {
            "status": terminal_state,
            "correction_count": correction_count,
            "completed_rounds": expected_rounds,
        }
    continuity["phase"] = f"TERMINAL_{terminal_state}"
    continuity["terminal_state"] = terminal_state
    continuity["operator_status"] = "COMPLETED"
    continuity["builder_status"] = "COMPLETED"
    _replace_registry(registry_path, registry)
    return registry


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
        "EXECUTION_SUCCESS",
        "EXECUTION_FAILED",
        "EXECUTION_ABORTED",
        "CREATION_FAILED",
    }
    if not statuses:
        raise ValueError("cannot finish incomplete Agent harness")
    if any(
        isinstance(status, str) and status.startswith("EXECUTION_")
        for status in statuses
    ):
        if any(status not in execution_terminal_statuses for status in statuses):
            raise ValueError("cannot finish incomplete Agent execution")
        status = (
            "EXECUTION_SUCCESS"
            if all(status == "EXECUTION_SUCCESS" for status in statuses)
            else "EXECUTION_COMPLETED_WITH_FAILURES"
        )
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
