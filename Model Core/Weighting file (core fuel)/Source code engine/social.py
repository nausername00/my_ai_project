"""Local social-partner catalog and collaboration entry points."""

from typing import Any

from collaboration import (
    is_local_engine,
    list_collaborator_roles,
    resolve_collaborators,
    run_collaboration,
)
from inference import InferenceEngine


def list_local_partners(engine: InferenceEngine) -> list[dict[str, Any]]:
    model_name = engine.model_name
    if model_name == "placeholder":
        status = "requires_model"
    elif is_local_engine(engine):
        status = "configured"
    else:
        status = "external_model_blocked"
    return [
        {
            "id": role["key"],
            "name": role["name"],
            "focus": role["focus"],
            "instruction": role["instruction"],
            "kind": "local_role",
            "source": "local",
            "model": model_name,
            "status": status,
            "capabilities": ["review"],
            "external": False,
        }
        for role in list_collaborator_roles()
    ]


def get_social_status(engine: InferenceEngine) -> dict[str, Any]:
    model_name = engine.model_name
    return {
        "scope": "local",
        "transport": "in_process",
        "model_configured": model_name != "placeholder" and is_local_engine(engine),
        "model_status": (
            "requires_model"
            if model_name == "placeholder"
            else "configured"
            if is_local_engine(engine)
            else "external_model_blocked"
        ),
        "model": model_name,
        "partner_count": len(list_collaborator_roles()),
        "external_providers_enabled": False,
    }


def collaborate_with_partners(
    engine: InferenceEngine,
    system_prompt: str,
    task: str,
    partner_ids: Any = None,
    role_configs: Any = None,
) -> dict[str, Any]:
    if partner_ids is not None and role_configs is not None:
        raise ValueError("provide partner_ids or roles, not both")

    roles = list_collaborator_roles()
    role_ids = [role["key"] for role in roles]
    if role_configs is not None:
        resolved_roles = resolve_collaborators(role_configs)
        selected_ids = [role.key for role in resolved_roles]
        effective_role_configs = [
            {
                "key": role.key,
                "enabled": True,
                "instruction": role.instruction,
            }
            for role in resolved_roles
        ]
    else:
        if partner_ids is None:
            selected_ids = role_ids
        else:
            if (
                not isinstance(partner_ids, list)
                or not partner_ids
                or len(partner_ids) > len(role_ids)
                or any(not isinstance(partner_id, str) for partner_id in partner_ids)
            ):
                raise ValueError("partner_ids must be a non-empty array of known partner ids")
            if len(set(partner_ids)) != len(partner_ids):
                raise ValueError("partner_ids must be unique")
            unknown_ids = set(partner_ids) - set(role_ids)
            if unknown_ids:
                raise ValueError("partner_ids contains an unknown local partner")
            selected_ids = partner_ids
        effective_role_configs = [
            {"key": partner_id, "enabled": True, "instruction": ""}
            for partner_id in selected_ids
        ]

    result = run_collaboration(
        engine,
        system_prompt,
        task,
        effective_role_configs,
    )
    return {
        **result,
        "scope": "local",
        "partner_ids": selected_ids,
        "external_providers_used": [],
    }
