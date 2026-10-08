from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

from .agent_execution import _write_state, check_agent_execution_budget, create_agent_execution_state, load_agent_execution_state_file
from .bundle_runtime import validate_web_runtime
from .codex_operator import finalize_codex_operator, prepare_codex_operator
from .second_pass import MODEL_RUNTIMES, parse_second_pass
from .resources import budget_stop, unknown_resources, utc_now
from .session_usage import sessions_usage
from .web_demo import freeze_demo_plan


HARNESS_SCHEMA = "replica-agent-harness/v1"
ASTRA_MODEL = "gpt-6-astra"
ASTRA_REASONING_EFFORT = "medium"
TERRA_MODEL = "gpt-5.6-terra"
TERRA_REASONING_EFFORT = "high"
REGISTRY_NAME = "agent-harness.json"
FINAL_RESULT_SCHEMA = "replica-agent-final-result/v1"
IMPLEMENTATION_RESULT_SCHEMA = "replica-agent-implementation-result/v1"
CANDIDATE_NAME = "operator.json"
BUNDLE_MANIFEST_NAME = "implementation/manifest.json"
IMPLEMENTATION_BUNDLE_SCHEMA = "replica-implementation-bundle/v1"
BUILDER_CONTEXT_SCHEMA = "replica-builder-context/v1"
MAX_BUNDLE_FILES = 256
MAX_BUNDLE_BYTES = 200_000_000
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


_SEALED_RESEARCH_FIELDS = {
    "tests", "evaluation", "expected_behavior", "reference_facts",
    "expected_output", "original_outputs",
}


def _public_research(value: Any) -> Any:
    """Remove sealed evaluation material that no implementing Agent may read."""
    if isinstance(value, dict):
        return {
            key: _public_research(item) for key, item in value.items()
            if key not in _SEALED_RESEARCH_FIELDS
        }
    if isinstance(value, list):
        return [_public_research(item) for item in value]
    return deepcopy(value)


def _builder_context(
    claim_id: str,
    payload: dict[str, Any],
    model_runtime: str,
    demo_plan_path: str | None = None,
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
    public_research = _public_research
    public_scenario = public_research(selected)
    interface = {}
    if demo_plan_path is not None:
        interface = {"interface": {
            "kind": "web_app",
            "demo_plan_path": demo_plan_path,
            "manifest_runtime": {"transport": "web_app", "port_argument": "--<name>", "ready_path": "/<path>"},
            "note": ("Build a web app a person uses in a browser. The frozen demo plan is public; an AI tester "
                     "runs it through the same screens for the final evaluation."),
        }}
    return {
        **interface,
        "schema_version": BUILDER_CONTEXT_SCHEMA,
        "claim_id": claim_id,
        "model_runtime": deepcopy(payload["model_runtime"]),
        "company": deepcopy(payload["company"]),
        "first_pass": deepcopy(payload.get("first_pass")),
        "workflow": deepcopy(second_pass.get("workflow")),
        "findings": public_research(second_pass.get("findings")),
        "selected_scenario": public_scenario,
        "available_scenarios": public_research(scenarios),
        "scenario_selection": deepcopy(payload.get("scenario_selection")),
        "handoff": public_research(second_pass.get("handoff")),
        "execution_policy": deepcopy(payload.get("execution_policy")),
        "runtime_contract": {
            key: deepcopy(value) for key, value in selected.get("evaluation", {}).items()
            if key in {"runtime", "timeout_seconds", "budget", "output_artifacts", "public_examples"}
        },
        "public_assets": [deepcopy(asset) for asset in selected.get("evaluation", {}).get("assets", [])
                          if asset.get("visibility") == "public"],
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
    replica_agent_model: str = ASTRA_MODEL,
    operator_model: str = ASTRA_MODEL,
    builder_model: str = TERRA_MODEL,
    model_runtime: str = "codex",
    fragment_root: Path | None = None,
    research_source: dict[str, str] | None = None,
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
    canonical = parse_second_pass(second_pass, model_runtime=model_runtime, fragment_root=fragment_root)
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
        payload = canonical_claim["payload"]
        web_demo, research_gaps = freeze_web_claim(payload, claim_id, fragment_root, run_dir)
        sealed = {}
        if payload.get("schema_version") == "replica-agent-claim/v2":
            # Sealed tests live only in the evaluator vault; the Operator reads the public claim.
            sealed_path = run_dir / EVALUATOR_VAULT_ROOT / claim_id / "claim-sealed.json"
            sealed_path.parent.mkdir(parents=True)
            _write_new_json(sealed_path, payload)
            sealed = {
                "sealed_claim_path": _relative_path(run_dir, sealed_path),
                "sealed_claim_sha256": _sha256(sealed_path),
            }
            payload = _public_research(payload)
        _write_new_json(
            run_dir / claim_payload_path,
            payload,
        )
        _write_new_json(
            run_dir / builder_context_path,
            _builder_context(
                claim_id,
                canonical_claim["payload"],
                model_runtime,
                web_demo["plan_path"] if web_demo else None,
            ),
        )
        claims.append(
            {
                "claim_id": claim_id,
                "claim_payload_owner": "replica_agent",
                "claim_payload_path": claim_payload_path,
                **sealed,
                "builder_context_owner": "replica_agent",
                "builder_context_path": builder_context_path,
                **({"web_demo": web_demo} if web_demo else {}),
                **({"research_gaps": research_gaps} if research_gaps else {}),
                "status": "RESEARCH_INCOMPLETE" if research_gaps else "PENDING",
                "namespace": claim_namespace,
                "operator": {
                    "agent_id": None,
                    "allowed_peer_agent_id": None,
                    "artifact_namespace": f"{claim_namespace}/operator",
                    "artifact_owner": "operator",
                    "claim_id": claim_id,
                    "parent_agent_id": replica_agent_id,
                    "requested_model": operator_model,
                    "requested_reasoning_effort": ASTRA_REASONING_EFFORT if operator_model == ASTRA_MODEL else None,
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
                    "requested_reasoning_effort": TERRA_REASONING_EFFORT if builder_model == TERRA_MODEL else None,
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
            "requested_reasoning_effort": ASTRA_REASONING_EFFORT if replica_agent_model == ASTRA_MODEL else None,
            "role": "replica_agent",
            "status": "RUNNING",
        },
        "scheduling": {
            "policy": "parallel_claim_pairs",
            "max_concurrent_pairs": len(claims),
            "peak_active_pairs": 0,
            "active_claim_id": None,
            "linked_pair_count": 0,
            "creation_failed_count": 0,
        },
        "filesystem": {
            "registry_owner": "replica_agent",
            "shared_mutation": "forbidden",
            "public_results_root": PUBLIC_RESULTS_ROOT,
            "evaluator_vault_root": EVALUATOR_VAULT_ROOT,
        },
        "claims": claims,
        "require_final_bundle_evaluation": True,
    }
    if "company_claims" in canonical:
        registry["company"] = canonical["company"]
        registry["company_claims"] = canonical["company_claims"]
        registry["research_source"] = research_source
        if canonical.get("research_agent_sessions"):
            registry["research_agent_sessions"] = canonical["research_agent_sessions"]
        if not claims:
            # Research that found nothing executable ends here as a complete company result.
            _write_new_json(run_dir / REGISTRY_NAME, registry)
            return finish_agent_harness(run_dir / REGISTRY_NAME)
    _write_new_json(run_dir / REGISTRY_NAME, registry)
    from .bundle_evaluation import prepare_bundle_evaluation
    for canonical_claim in canonical["claims"]:
        # Web-app claims are evaluated by their public demo plan, not a sealed JSON suite.
        if (canonical_claim["payload"].get("schema_version") == "replica-agent-claim/v2"
                and not is_web_claim(canonical_claim["payload"])):
            registry = prepare_bundle_evaluation(run_dir / REGISTRY_NAME, canonical_claim["claim_id"])
    return registry


def prepare_agent_harness_from_path(
    source: Path,
    run_dir: Path,
    *,
    replica_agent_id: str,
    parent_agent_id: str,
    replica_agent_model: str = ASTRA_MODEL,
    operator_model: str = ASTRA_MODEL,
    builder_model: str = TERRA_MODEL,
    model_runtime: str = "codex",
) -> dict[str, Any]:
    """Read immutable Second JSON and prepare a real-Agent harness registry."""
    try:
        source_bytes = source.read_bytes()
        second_pass = json.loads(
            source_bytes.decode("utf-8-sig"),
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
        fragment_root=source.parent,
        research_source={
            "path": str(source.resolve()),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
        },
    )


def _active_execution_claims(registry: dict[str, Any]) -> list[str]:
    return [claim["claim_id"] for claim in registry["claims"]
            if claim.get("continuity", {}).get("phase") in {"PAIR_ACTIVE", "ROUND_TRIP_COMPLETE"}
            or claim.get("status") in {"EXECUTION_SUCCESS", "IMPLEMENTATION_READY", "EVALUATION_INTERRUPTED"}]


def start_agent_claim(registry_path: Path, claim_id: str) -> dict[str, Any]:
    """Serialize pair registration without waiting for other claim executions."""
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
    if claim.get("status") == "RESEARCH_INCOMPLETE":
        raise ValueError(
            "claim research is incomplete; supplement it with agent-bundle-prepare before activation: "
            + "; ".join(claim.get("research_gaps", []))
        )
    if claim is not next_pending:
        raise ValueError("claim registration must follow research order")
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
    requested_reasoning_effort: str | None = None,
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
    if ("requested_reasoning_effort" in agent
            and requested_reasoning_effort != agent["requested_reasoning_effort"]):
        raise ValueError(f"{role} Agent reasoning effort request does not match policy")
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
        scheduling["creation_failed_count"] = (
            scheduling.get("creation_failed_count", 0) + 1
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
        scheduling["linked_pair_count"] = (
            scheduling.get("linked_pair_count", 0) + 1
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
    # Also upgrade scheduling metadata when resuming an existing harness.
    registry["scheduling"].update(
        policy="parallel_claim_pairs", max_concurrent_pairs=len(registry["claims"])
    )
    continuity.update(
        {
            "phase": "PAIR_ACTIVE",
            "operator_agent_id": operator_agent_id,
            "builder_agent_id": builder_agent_id,
            "operator_status": "ACTIVE_FOR_CLAIM",
            "builder_status": "ACTIVE_FOR_CLAIM",
            "started_at": utc_now(),
        }
    )
    registry["scheduling"]["peak_active_pairs"] = max(
        registry["scheduling"].get("peak_active_pairs", 0), len(_active_execution_claims(registry))
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
        recovery = claim.get("preflight_recovery")
        if recovery:
            archive = registry_path.parent / recovery["archive_path"]
            if _sha256(archive) != recovery["sha256"]:
                raise ValueError("preflight recovery evidence changed")
            previous = json.loads(archive.read_text())["execution_state"]
            prior_resources = previous.get("prior_resources", []) + [a.get("resources", unknown_resources()) for a in previous["attempts"]]
            if state.get("started_at") != previous["started_at"] or state.get("prior_resources", [])[:len(prior_resources)] != prior_resources:
                raise ValueError("preflight recovery cannot reset development time or resources")
        submissions = claim.get("bundle_submissions", [])
        packaging = claim.get("packaging_retries", [])
        if packaging:
            snapshot = packaging[-1]["development_archive"]
            archive = registry_path.parent / snapshot["path"]
            for name, checksum in snapshot["artifacts"].items():
                if _sha256(archive / name) != checksum:
                    raise ValueError("packaging recovery evidence changed")
            previous = json.loads((archive / "execution-state.json").read_text())
            prior_resources = previous.get("prior_resources", []) + [a.get("resources", unknown_resources()) for a in previous["attempts"]]
            if state.get("started_at") != previous["started_at"] or state.get("prior_resources", [])[:len(prior_resources)] != prior_resources:
                raise ValueError("packaging retry cannot reset development time or resources")
        if submissions and submissions[-1].get("development_archive"):
            archive = registry_path.parent / submissions[-1]["development_archive"]["path"]
            previous = json.loads((archive / "execution-state.json").read_text())
            prior_resources = previous.get("prior_resources", []) + [a.get("resources", unknown_resources()) for a in previous["attempts"]]
            if state.get("started_at") != previous.get("started_at") or state.get("prior_resources") != prior_resources:
                raise ValueError("a sealed retry cannot reset development time or resource history")
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
    continuity["finished_at"] = utc_now()
    continuity["terminal_state"] = terminal_state
    continuity["operator_status"] = "COMPLETED"
    continuity["builder_status"] = "COMPLETED"
    _replace_registry(registry_path, registry)
    return registry


def resume_agent_continuity(registry_path: Path, claim_id: str) -> dict[str, Any]:
    """Resume one interrupted direct delivery without resetting development state."""
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    continuity = claim["continuity"]
    if (claim["status"] != "EXECUTION_ABORTED" or continuity["phase"] != "ABORTED"
            or continuity.get("recovered_aborts")):
        raise ValueError("continuity recovery permits one recorded abort per claim")
    if continuity.get("failure", {}).get("agent_id") not in {claim[r]["agent_id"] for r in ("operator", "builder")}:
        raise ValueError("continuity recovery requires an original peer interruption")
    root = registry_path.parent
    state_path = root / claim["operator"]["artifact_namespace"] / "execution-state.json"
    state, state_hash = load_agent_execution_state_file(
        state_path, json.loads((root / claim["claim_payload_path"]).read_text()))
    round_number = state["next_correction_number"]
    completed = continuity["completed_rounds"]
    # Delivery may have been recorded before the Operator advances its execution decision.
    valid_round = any(completed == list(range(end)) and continuity["next_round"] == end
                      for end in (round_number, round_number + 1))
    if (state["operator_agent_id"] != claim["operator"]["agent_id"]
            or state["builder_agent_id"] != claim["builder"]["agent_id"]
            or state["pair_nonce"] != claim["smoke"]["nonce"]
            or not check_agent_execution_budget(state_path)["allowed"]
            or not valid_round):
        raise ValueError("continuity recovery cannot change identity, round, terminal or exhausted budget")
    previous = deepcopy(continuity)
    continuity.update(phase="PAIR_ACTIVE", terminal_state=None, failure=None,
                      operator_status="ACTIVE_FOR_CLAIM", builder_status="ACTIVE_FOR_CLAIM",
                      recovered_aborts=[{"continuity": previous, "execution_result": claim.get("execution_result"),
                                         "execution_state_sha256": state_hash,
                                         "resumed_at": utc_now()}])
    continuity.pop("finished_at", None)
    claim["status"] = "READY_FOR_PROTOCOL"
    claim.pop("execution_result", None)
    registry["status"] = registry["replica_agent"]["status"] = "RUNNING"
    registry["scheduling"]["peak_active_pairs"] = max(
        registry["scheduling"].get("peak_active_pairs", 0), len(_active_execution_claims(registry)))
    _replace_registry(registry_path, registry)
    return registry


def retry_agent_preflight(registry_path: Path, claim_id: str) -> dict[str, Any]:
    """Recover once from a control failure before any implementation action."""
    registry = _read_registry(registry_path)
    claim = _claim_record(registry, claim_id)
    if claim.get("status") != "EXECUTION_FAILED" or claim.get("preflight_recovery"):
        raise ValueError("preflight recovery requires an unrecovered execution failure")
    root = registry_path.parent
    payload = json.loads((root / claim["claim_payload_path"]).read_text())
    state_path = root / claim["operator"]["artifact_namespace"] / "execution-state.json"
    previous, state_hash = load_agent_execution_state_file(state_path, payload)
    result = claim["execution_result"]
    if state_hash != result["execution_state_sha256"]:
        raise ValueError("preflight terminal state binding changed")
    attempts = previous["attempts"]
    actions = [m for a in attempts for m in a.get("resources", {}).get("measurements", [])
               if m["metric"] == "implementation_actions_started"]
    if (previous["status"] != "FAILED" or len(attempts) != 1
            or previous.get("stop_reason", {}).get("category") != "environment_error"
            or attempts[0]["execution_status"] != "blocked" or attempts[0]["test_status"] != "not_run"
            or not actions or any(m["status"] != "measured" or m["value"] != 0 for m in actions)
            or (root / result["candidate_path"]).exists()):
        raise ValueError("recovery requires measured zero actions and no candidate before an environment stop")
    resources = previous.get("prior_resources", []) + [a.get("resources", unknown_resources()) for a in attempts]
    if "budget" not in previous or budget_stop(previous["budget"], previous["started_at"], resources):
        raise ValueError("the frozen development budget is exhausted or unverifiable")
    archive = root / EVALUATOR_VAULT_ROOT / claim_id / "preflight-recovery.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("x", encoding="utf-8") as handle:
        json.dump({"claim_binding": claim, "execution_state": previous}, handle, indent=2)
    state = create_agent_execution_state(claim=payload, claim_id=claim_id,
                                        operator_agent_id=previous["operator_agent_id"],
                                        builder_agent_id=previous["builder_agent_id"], pair_nonce=previous["pair_nonce"])
    state["started_at"] = previous["started_at"]
    state["prior_resources"] = resources
    _write_state(state_path, state, new=False)
    claim["preflight_recovery"] = {"archive_path": archive.relative_to(root).as_posix(),
                                  "sha256": _sha256(archive), "recorded_at": utc_now()}
    claim.pop("execution_result")
    claim["status"] = "READY_FOR_PROTOCOL"
    claim["continuity"].update(phase="READY", completed_rounds=[], next_round=0, correction_count=0,
                               terminal_state=None, failure=None, operator_status="NOT_STARTED",
                               builder_status="NOT_STARTED")
    claim["continuity"].pop("finished_at", None)
    registry["status"] = registry["replica_agent"]["status"] = "RUNNING"
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


def freeze_web_claim(payload: dict[str, Any], claim_id: str, fragment_root: Path | None,
                     run_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Fix a web claim's demo plan before any Agent builds; a bad plan is a research gap."""
    if not is_web_claim(payload):
        return None, []
    selected = _selected_scenario(payload)
    try:
        plan_path = freeze_demo_plan(selected["demo_plan"], claim_id, fragment_root,
                                     run_dir / "claims" / claim_id / "demo")
        scope = _demo_scope(payload, selected, json.loads(plan_path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        return None, [f"demo plan: {error}"]
    return {"plan_path": _relative_path(run_dir, plan_path), "plan_sha256": _sha256(plan_path),
            "frozen_at": utc_now(), "scope": scope}, []


def _demo_scope(payload: dict[str, Any], selected: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Which built workflow steps the demo cases pass through; the rest is reported as unverified."""
    workflow = (payload["second_pass"].get("workflow") or {}).get("steps") or \
        ((payload.get("first_pass") or {}).get("workflow") or {}).get("steps") or []
    texts = [step.get("step") if isinstance(step, dict) else None for step in workflow]
    covered = {index for case in plan["cases"] for index in case["covers_steps"]}
    if any(index > len(texts) for index in covered):
        raise ValueError(f"covers_steps must name steps 1..{len(texts)} of the confirmed workflow")
    steps = [{"step_index": entry["step_index"], "step": texts[entry["step_index"] - 1],
              "disposition": entry["disposition"]}
             for entry in selected.get("step_coverage", []) if entry.get("claim_id", payload["claim_id"]) == payload["claim_id"]]
    return {"steps": steps,
            "uncovered_steps": [step for step in steps
                                if step["disposition"] != "excluded" and step["step_index"] not in covered],
            # Every excluded step or excluded part of a step in the selected scenario, merged claims included,
            # caps the verdict at partial.
            "excluded_steps": [
                {"claim_id": entry.get("claim_id", payload["claim_id"]), "step_index": entry["step_index"],
                 **({"part": part["part"]} if part else {})}
                for entry in selected.get("step_coverage", [])
                for part in ([None] if entry.get("disposition") == "excluded" else entry.get("excluded_parts", []))]}


def is_web_claim(payload: dict[str, Any]) -> bool:
    """A claim whose selected scenario carries a demo plan is built and evaluated as a web app."""
    selected = _selected_scenario(payload)
    return selected is not None and "demo_plan" in selected


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
    if not isinstance(manifest, dict):
        raise ValueError("invalid Terra implementation bundle contract")
    if is_web_claim(claim_payload):
        # A web-app Replica declares how it starts; its demo plan, not JSON calls, evaluates it.
        fields = fields | {"runtime"}
        try:
            validate_web_runtime(manifest.get("runtime"))
        except ValueError as error:
            raise ValueError(f"web-app Replica manifest needs a web_app runtime: {error}") from None
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
        or manifest.get("entrypoint") not in manifest.get("command", [])
        or not isinstance(dependencies, list)
        or not all(
            isinstance(dependency, dict)
            and set(dependency) == {"name", "version", "source", "license"}
            and all(_is_nonempty_text(dependency.get(field)) for field in dependency)
            and dependency["source"].startswith(("https://", "http://"))
            for dependency in dependencies
        )
        or not isinstance(environment_variables, list)
        or not all(
            isinstance(name, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
            for name in environment_variables
        )
        or len(set(environment_variables)) != len(environment_variables)
        or not isinstance(files, list)
        or not files
        or len(files) > MAX_BUNDLE_FILES
    ):
        raise ValueError("invalid Terra implementation bundle contract")

    file_paths = [record.get("path") for record in files if isinstance(record, dict)]
    if (
        len(file_paths) != len(files)
        or not all(_is_nonempty_text(path) for path in file_paths)
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
            relative = path.relative_to(bundle_root)
            # Generated Python caches are never copied unless explicitly declared.
            if relative.as_posix() not in file_paths and "__pycache__" in relative.parts and path.suffix == ".pyc":
                continue
            present.add(relative.as_posix())
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
        if any(attempt["candidate_sha256"] == candidate_sha256 for attempt in claim.get("bundle_submissions", [])):
            raise ValueError("the same candidate cannot be resubmitted to sealed tests")
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
    if isinstance(final_result, dict) and final_result.get("schema_version") == "replica-agent-web-demo-result/v1":
        from .web_evaluation import validate_web_result
        validate_web_result(run_dir, claim)
        return
    if isinstance(final_result, dict) and final_result.get("schema_version") == "replica-agent-bundle-result/v1":
        from .bundle_evaluation import validate_bundle_result
        validate_bundle_result(run_dir, claim)
        return
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
    if claim.get("execution_mode") == "single":
        from .single_agent import validate_single_implementation
        validate_single_implementation(run_dir, claim)
        return
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
    continuity["finished_at"] = utc_now()
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
    if any(claim.get("continuity", {}).get("phase") in {"PAIR_ACTIVE", "ROUND_TRIP_COMPLETE"}
           for claim in registry["claims"]):
        raise ValueError("cannot finish Agent harness with active execution pairs")
    statuses = [claim.get("status") for claim in registry["claims"]]
    protocol_terminal_statuses = {"READY_FOR_PROTOCOL", "CREATION_FAILED", "RESEARCH_INCOMPLETE"}
    execution_terminal_statuses = {
        "RESEARCH_INCOMPLETE",
        "IMPLEMENTATION_READY",
        "RESULT_SUCCESS",
        "RESULT_FAILED",
        # An interrupted final evaluation ends the claim when it is not retried, e.g. after the last submission.
        "EVALUATION_INTERRUPTED",
        "EXECUTION_FAILED",
        "EXECUTION_ABORTED",
        "CREATION_FAILED",
    }
    if not statuses and "company_claims" not in registry:
        raise ValueError("cannot finish incomplete Agent harness")
    for claim in registry["claims"]:
        if claim.get("status") in {"RESULT_SUCCESS", "RESULT_FAILED"}:
            _validate_final_result(registry_path.parent.resolve(), claim)
        elif claim.get("status") == "IMPLEMENTATION_READY":
            _validate_implementation_result(registry_path.parent.resolve(), claim)
            if registry.get("require_final_bundle_evaluation"):
                raise ValueError("cannot finish Agent execution before final bundle evaluation")
    if any(
        isinstance(status, str)
        and (
            status.startswith("EXECUTION_")
            or status.startswith("RESULT_")
            or status in {"IMPLEMENTATION_READY", "EVALUATION_INTERRUPTED"}
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
    elif not statuses:
        status = "COMPLETED_WITHOUT_EXECUTION"
    else:
        if any(status not in protocol_terminal_statuses for status in statuses):
            raise ValueError("cannot finish incomplete Agent harness")
        status = (
            "READY_FOR_PROTOCOL"
            if all(status == "READY_FOR_PROTOCOL" for status in statuses)
            else "COMPLETED_WITH_RESEARCH_GAPS"
            if "RESEARCH_INCOMPLETE" in statuses
            else "COMPLETED_WITH_CREATION_FAILURES"
        )
    # Counted from final claim states, not from pair registration events.
    registry["claim_status_counts"] = {
        name: statuses.count(name) for name in sorted(set(statuses))
    }
    registry["status"] = status
    registry["orchestrator" if registry.get("execution_mode") == "single" else "replica_agent"]["status"] = status
    if "company_claims" in registry:
        root = registry_path.parent.resolve()
        results_path = root / PUBLIC_RESULTS_ROOT / "company-claims.json"
        company_results = _company_results(root, registry)
        results_path.parent.mkdir(exist_ok=True)
        results_path.unlink(missing_ok=True)
        _write_new_json(results_path, company_results)
        architecture_path = root / PUBLIC_RESULTS_ROOT / "architecture.md"
        architecture_path.unlink(missing_ok=True)
        architecture_path.write_text(render_architecture(company_results), encoding="utf-8")
        registry["company_result"] = {
            "path": _relative_path(root, results_path),
            "sha256": _sha256(results_path),
            "architecture_path": _relative_path(root, architecture_path),
        }
    _replace_registry(registry_path, registry)
    return registry


# Failures that say the experiment did not run to a verdict, not how good the Replica was.
_BLOCKED_FAILURES = {
    "research_gap", "environment_error", "access_missing", "data_missing",
    "budget_exhausted", "budget_unverifiable", "implementer_unavailable",
}


def _pre_evaluation_outcome(root: Path, claim: dict[str, Any]) -> dict[str, Any]:
    """Explain a control/development stop without publishing peer messages or sealed cases."""
    status = claim.get("status")
    category = None
    stop = "final_evaluation_not_run"
    reason = "The claim has not completed final bundle evaluation."
    outcome = "experiment_incomplete"
    if status == "RESEARCH_INCOMPLETE":
        category, stop = "research_gap", "research_incomplete"
        reason = "; ".join(claim.get("research_gaps", [])) or "Evaluation research is incomplete."
        outcome = "experiment_blocked"
    elif status == "CREATION_FAILED":
        category = stop = "agent_creation_failed"
        reason = (claim.get("failure") or {}).get("reason") or "The Agent pair could not be created."
        outcome = "experiment_blocked"
    elif status == "EXECUTION_ABORTED":
        category = stop = "agent_protocol_interrupted"
        reason = (claim.get("continuity", {}).get("failure") or {}).get("reason") or "The Agent protocol was interrupted."
        outcome = "experiment_blocked"
    elif status == "EVALUATION_INTERRUPTED":
        category = stop = "evaluation_interrupted"
        attempt = (claim.get("bundle_submissions") or [{}])[-1]
        reason = ("Final evaluation was interrupted and not retried"
                  + (f": {attempt['error']}" if attempt.get("error") else "."))
        outcome = "experiment_blocked"
    elif status == "EXECUTION_FAILED" and claim.get("failure") and not claim.get("execution_result"):
        # A single implementer that ended without a bound implementation.
        category = stop = claim["failure"]["category"]
        reason = claim["failure"]["reason"]
        if category in _BLOCKED_FAILURES:
            outcome = "experiment_blocked"
    elif status == "EXECUTION_FAILED":
        execution = claim.get("execution_result") or {}
        state_stop = None
        if execution.get("execution_state_sha256"):
            payload = json.loads((root / claim["claim_payload_path"]).read_text(encoding="utf-8"))
            state, checksum = load_agent_execution_state_file(
                root / claim["operator"]["artifact_namespace"] / "execution-state.json", payload,
            )
            if checksum != execution["execution_state_sha256"]:
                raise ValueError("failed development state changed before company result")
            state_stop = state.get("stop_reason")
        if state_stop:
            category = stop = state_stop["category"]
            reason = state_stop["reason"]
            if category in _BLOCKED_FAILURES:
                outcome = "experiment_blocked"
        else:
            category = stop = "development_checks_failed"
            reason = (
                f"Development checks did not pass after {execution.get('correction_count', 0)} corrections; "
                "final bundle evaluation was not run."
            )
    result = {"outcome": outcome, "failure_category": category, "stop_reason": stop, "failure_reason": reason}
    if status in {"RESEARCH_INCOMPLETE", "CREATION_FAILED"}:
        result["not_executed_reason"] = reason
    return result


_PLAN_KEYS = ("disposition", "component", "route", "reason", "excluded_parts", "alternatives", "needs")


def _claim_architecture(root: Path, claim: dict[str, Any], demo: dict[str, Any] | None) -> dict[str, Any] | None:
    """The researched workflow step by step: what research planned for it, and what the demo observed.

    The plan comes from the frozen scenario's step_coverage. Observations are case-level: a step lists
    the demo cases planned to pass through it and how those cases ended. No case result is turned into
    a per-step pass or fail, because the demo does not record which step an expectation checks.
    """
    payload = json.loads((root / claim["claim_payload_path"]).read_text(encoding="utf-8"))
    selected = _selected_scenario(payload)
    if selected is None:
        return None
    own = (payload["second_pass"].get("workflow") or {}).get("steps") or \
        ((payload.get("first_pass") or {}).get("workflow") or {}).get("steps") or []
    texts = {(payload["claim_id"], i): s.get("step") for i, s in enumerate(own, 1) if isinstance(s, dict)}
    for absorbed in payload.get("absorbed_claims", []):
        steps = ((absorbed.get("first_pass") or {}).get("workflow") or {}).get("steps") or []
        texts |= {(absorbed["claim_id"], i): s.get("step") for i, s in enumerate(steps, 1) if isinstance(s, dict)}
    planned: dict[int, list[str]] = {}
    if claim.get("web_demo"):
        plan = json.loads((root / claim["web_demo"]["plan_path"]).read_text(encoding="utf-8"))
        for case in plan["cases"]:
            for index in case["covers_steps"]:
                planned.setdefault(index, []).append(case["id"])
    cases = {case["case_id"]: case for case in (demo or {}).get("cases", [])}

    def case_result(case_id: str) -> dict[str, Any]:
        case = cases.get(case_id)
        if case is None:
            return {"case_id": case_id, "execution_status": "not_run"}
        statuses = [item["status"] for item in case["expectations"]]
        return {"case_id": case_id, "execution_status": case["execution_status"],
                **{name: statuses.count(name) for name in ("passed", "failed", "not_evaluated")}}
    steps = []
    for entry in selected.get("step_coverage", []):
        owner = entry.get("claim_id", payload["claim_id"])
        index = entry["step_index"]
        case_ids = planned.get(index, []) if owner == payload["claim_id"] else []
        steps.append({
            "claim_id": owner, "step_index": index, "step": texts.get((owner, index)),
            "plan": {key: deepcopy(entry[key]) for key in _PLAN_KEYS if key in entry},
            "observation": {
                "cases": [case_result(case_id) for case_id in case_ids] if demo is not None else [],
                "evidence": ("case_level" if case_ids and demo is not None else
                             "none: no demo case is planned through this step" if demo is not None else
                             "none: no web demo result"),
            },
        })
    final = claim.get("final_result") or {}
    return {
        "scenario_id": selected["id"],
        "steps": steps,
        "observation": {
            "implementation_submitted": bool(claim.get("implementation_result") or final),
            "code_review": final.get("code_review"),
            "reproduction_status": final.get("reproduction_status"),
        },
        "note": ("plan is what pass-2 research froze before implementation; observation is what the final "
                 "evaluation recorded. A planned route is never counted as a measured success."),
    }


_DISPOSITION_KO = {"implemented": "직접 구현", "external_dependency": "외부 서비스 사용", "excluded": "제외",
                   "unconfirmed": "미확인"}
_ORIGIN_KO = {"company_stated": "기업 공개", "inferred": "추론"}


def render_architecture(company: dict[str, Any]) -> str:
    """A readable plan-versus-observation table per executed claim."""
    def cell(text: Any) -> str:
        return str(text).replace("|", "\\|").replace("\n", " ") if text else "-"
    lines = ["# 워크플로 설계도와 실측", "",
             "단계마다 **계획**(구현 전 2차 조사가 고정한 처리 방식)과 **관측**(최종 평가 기록)을 나눠 적는다. "
             "계획상 경로는 실측 성공으로 세지 않는다. 관측은 사례 단위이며, 사례 결과를 단계별 통과·실패로 바꾸지 않는다.", ""]
    for claim in company["claims"]:
        architecture = claim.get("architecture")
        if architecture is None:
            continue
        observed = architecture["observation"]
        lines += [f"## `{claim['claim_id']}` — 시나리오 `{architecture['scenario_id']}`", "",
                  f"- 구현 제출: {'예' if observed['implementation_submitted'] else '아니오'} / "
                  f"코드 검사: {observed['code_review'] or '-'} / 재현 판정: {observed['reproduction_status'] or '-'}", "",
                  "| 단계 | 계획 | 구성요소(출처) | 우리 경로 | 빠진 것과 하려면 필요한 것 | 관측(계획된 사례) |",
                  "|---|---|---|---|---|---|"]
        for step in architecture["steps"]:
            plan = step["plan"]
            component = plan.get("component") or {}
            left_out = []
            if plan.get("disposition") == "excluded":
                left_out.append(f"단계 전체: {plan.get('reason')} → 필요: {plan.get('needs')}")
            for part in plan.get("excluded_parts", []):
                left_out.append(f"{part['part']}: {part['reason']} → 필요: {part['needs']}")
            cases = step["observation"]["cases"]
            observed_text = ("; ".join(f"{c['case_id']} {c['execution_status']}"
                                      + (f" (충족 {c['passed']}, 불충족 {c['failed']}, 미평가 {c['not_evaluated']})"
                                         if "passed" in c else "") for c in cases)
                             or step["observation"]["evidence"])
            lines.append("| " + " | ".join(cell(x) for x in (
                f"{step['claim_id']} {step['step_index']}. {step['step'] or ''}",
                _DISPOSITION_KO.get(plan.get("disposition"), plan.get("disposition")),
                f"{component.get('description')} ({_ORIGIN_KO.get(component.get('origin'), '미기록')})" if component else "미기록",
                plan.get("route") or ("-" if plan.get("disposition") == "excluded" else "미기록"),
                "<br>".join(left_out),
                observed_text)) + " |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _recorded_agent_ids(registry: dict[str, Any]) -> frozenset[str]:
    """Agents whose usage is reported under their own role, so a parent session must not count them again."""
    ids = {claim[role].get("agent_id") for claim in registry["claims"]
           for role in ("operator", "builder", "implementer") if isinstance(claim.get(role), dict)}
    ids |= {session.get("agent_id") for session in registry.get("research_agent_sessions") or []
            if isinstance(session, dict)}
    return frozenset(i for i in ids if isinstance(i, str) and i)


def _company_results(root: Path, registry: dict[str, Any]) -> dict[str, Any]:
    """Join every researched claim to its execution outcome so no result loses its denominator."""
    executed = {claim["claim_id"]: claim for claim in registry["claims"]}
    runtime = (registry.get("model_runtime") or {}).get("provider")
    entries = []
    for researched in registry["company_claims"]:
        entry = deepcopy(researched)
        claim = executed.get(researched["claim_id"])
        if claim is None:
            entry["outcome"] = "not_executed"
            entries.append(entry)
            continue
        final = claim.get("final_result") or {}
        result = {}
        web = final.get("schema_version") == "replica-agent-web-demo-result/v1"
        if web:
            from .web_evaluation import validate_web_result
            demo = validate_web_result(root, claim)
            selected_id = json.loads((root / claim["claim_payload_path"]).read_text(encoding="utf-8"))["selected_scenario_id"]
            result = {"scenario_id": selected_id, "failure_category": None,
                      "stop_reason": "web_demo_" + final["reproduction_status"]}
            entry["web_demo"] = {
                "result_path": f"{final['public_run_dir']}/demo-result.json",
                "report_path": f"{final['public_run_dir']}/report.md",
                "plan_path": claim["web_demo"]["plan_path"],
                "outcome": demo["outcome"],
                "cases": {case["case_id"]: case["execution_status"] for case in demo["cases"]},
                "code_review": {key: demo["code_review"].get(key) for key in ("status", "reason", "findings")},
                "uncovered_steps": demo["scope"].get("uncovered_steps"),
                "costs": {name: {key: phase[key] for key in (
                    "calls", "completed", "failed", "timeout", "incomplete", "call_seconds", "usage", "models",
                    "cli_list_estimate_usd", "estimate_complete")} for name, phase in demo["costs"]["phases"].items()},
                "wall_seconds": demo["wall_seconds"],
            }
        elif final.get("public_run_dir"):
            result = json.loads((root / final["public_run_dir"] / "replica-result.json").read_text(encoding="utf-8"))
        architecture = _claim_architecture(root, claim, demo if web else None)
        if architecture is not None:
            entry["architecture"] = architecture
        if claim.get("development_log"):
            entry["development_log"] = claim["development_log"]
        entry["development_usage"] = sessions_usage(
            [{"role": role, "agent_id": claim[role].get("agent_id")}
             for role in ("operator", "builder", "implementer") if claim.get(role, {}).get("agent_id")],
            runtime)
        entry.update({
            "harness_status": claim.get("status"),
            "scenario_id": result.get("scenario_id"),
            "reproduction_status": final.get("reproduction_status"),
            "failure_category": result.get("failure_category"),
            "stop_reason": result.get("stop_reason"),
            "result_path": (f"{final['public_run_dir']}/{'demo-result.json' if web else 'replica-result.json'}"
                            if final.get("public_run_dir") else None),
            "result_sha256": final.get("result_sha256"),
            "outcome": (
                "experiment_blocked" if final.get("reproduction_status") == "execution_blocked"
                else final.get("reproduction_status")
            ),
        })
        if claim.get("status") not in {"RESULT_SUCCESS", "RESULT_FAILED"}:
            entry.update(_pre_evaluation_outcome(root, claim))
        entries.append(entry)
    outcomes = [entry["outcome"] for entry in entries]
    return {
        "schema_version": "replica-company-claim-results/v1",
        "company": deepcopy(registry.get("company")),
        "research_source": deepcopy(registry.get("research_source")),
        "harness_status": registry["status"],
        "claim_total": len(entries),
        "selected_for_execution": sum(entry["selected_for_execution"] for entry in entries),
        "outcome_counts": {name: outcomes.count(name) for name in sorted(set(outcomes))},
        "research_usage": (sessions_usage(registry["research_agent_sessions"], runtime)
                           if registry.get("research_agent_sessions") else
                           {"status": "not_recorded", "basis": "research.json recorded no agent_sessions."}),
        "orchestration_usage": sessions_usage(
            [{"role": "replica_agent", "agent_id": (registry.get("replica_agent") or registry.get("orchestrator") or {}).get("agent_id")}],
            runtime, _recorded_agent_ids(registry)),
        "cost_note": (
            "Usage comes from per-call receipts (web demo) and the runtimes' session logs (research, development, "
            "orchestration); a session whose log was not found is unknown, not zero. Usage keys are summed per key. "
            "Human time is not a cost item of the automated run."
        ),
        "interpretation": (
            "Each outcome describes this experiment on one researched workflow. A not_executed, "
            "experiment_incomplete, or experiment_blocked claim is not evidence of the company's "
            "technical barrier, and no single claim's result is a verdict on the whole company. "
            "A not_evaluated web demo ran but could not show its expected results; it is not a failure."
        ),
        "claims": entries,
    }
