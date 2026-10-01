"""Vendored from DeepSearch 79ef84842fb84259bafe59924b21fe2f5ad05d7d.
See cmos/contracts/deepsearch-compiler-vendor.md for local adaptations.

Versioned provenance for the mission-contract compiler."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel

CONTRACT_SCHEMA_VERSION = "1.2"
CONTRACT_COMPILER_REVISION = 3

CONFIGURED_ENRICHMENT_MODE: Literal["configured"] = "configured"
NO_ENRICHMENT_MODE: Literal["none"] = "none"
CompilerEnrichmentMode = Literal["configured", "none"]

CANONICAL_CONTRACT_ORIGIN = "canonical"
CANONICAL_CONTRACT_COMPILED_AT = "1970-01-01T00:00:00+00:00"

_REPO_ROOT = Path(__file__).resolve().parent
_SEMANTIC_STATE_INPUTS = (
    "coverage_thresholds",
    "deliverable_format",
    "depth_config",
    "max_loops",
    "min_loops",
    "mission_context",
    "mission_id",
    "mission_objectives",
    "project_id",
    "research_depth",
    "validation_thresholds",
)
_SEMANTIC_MISSION_CONTEXT_INPUTS = (
    "authored_scope",
    "authority_domains",
    "authority_seed_domains",
    "background",
    "constraints",
    "coverage_thresholds",
    "deliverables",
    "excluded_domains",
    "excluded_entities",
    "expected_output_schema",
    "focus",
    "objective",
    "primary_domains",
    "reference_titles",
    "references",
    "required_entities",
    "success_criteria",
    "title",
    "validation_thresholds",
)
_STRUCTURAL_SOURCE_FILES = (
    "deepsearch/mission/compiler_provenance.py",
    "deepsearch/mission/contract.py",
    "deepsearch/mission/scope.py",
    "deepsearch/mission/title_utils.py",
    "deepsearch/agent/deliverable_schemas.py",
    "deepsearch/domain_policy.py",
)
_CONFIGURED_ENRICHMENT_SOURCE_FILES = (
    "deepsearch/mission/entity_extractor_llm.py",
    "deepsearch/config.py",
    "deepsearch/llm/structured_extractor.py",
    "deepsearch/agent/llm_client.py",
)

VENDORED_SOURCE_REVISION = '79ef84842fb84259bafe59924b21fe2f5ad05d7d'


def canonical_json(payload: Mapping[str, Any] | BaseModel) -> str:
    """Serialize a compiler artifact using the cross-service canonical form."""

    value = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def resolve_configured_enrichment_identity() -> tuple[str | None, str | None]:
    """Return the configured extraction backend/model without invoking a model."""

    raise ValueError("TraceLab supports only enrichment_mode=none")


def build_contract_compiler_manifest(
    *,
    enrichment_mode: CompilerEnrichmentMode,
    enrichment_backend: str | None = None,
    enrichment_model: str | None = None,
) -> dict[str, Any]:
    """Build a hash-verifiable manifest for one compiler invocation mode."""

    if enrichment_mode != NO_ENRICHMENT_MODE:
        raise ValueError(f"Unsupported compiler enrichment mode: {enrichment_mode}")
    if enrichment_mode == NO_ENRICHMENT_MODE:
        enrichment_backend = None
        enrichment_model = None
    elif enrichment_backend is None or enrichment_model is None:
        configured_backend, configured_model = resolve_configured_enrichment_identity()
        if enrichment_backend is None:
            enrichment_backend = configured_backend
        if enrichment_model is None:
            enrichment_model = configured_model

    source_paths = list(_STRUCTURAL_SOURCE_FILES)
    if enrichment_mode == CONFIGURED_ENRICHMENT_MODE:
        source_paths.extend(_CONFIGURED_ENRICHMENT_SOURCE_FILES)

    revision, revision_source = _resolve_source_revision()
    manifest: dict[str, Any] = {
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "compiler_revision": CONTRACT_COMPILER_REVISION,
        "semantic_inputs": {
            "state": list(_SEMANTIC_STATE_INPUTS),
            "mission_context": list(_SEMANTIC_MISSION_CONTEXT_INPUTS),
        },
        "required_source_files": [
            {
                "path": "app/services/contract_compiler/" + Path(relative_path).name,
                "upstream_path": relative_path,
                "sha256": hashlib.sha256(
                    (_REPO_ROOT / Path(relative_path).name).read_bytes()
                ).hexdigest(),
            }
            for relative_path in source_paths
        ],
        "enrichment": {
            "mode": enrichment_mode,
            "backend": enrichment_backend,
            "model": enrichment_model,
        },
        "source_revision": revision,
        "source_revision_source": revision_source,
        # A git revision names only the base commit when the working tree is
        # dirty. Per-file hashes remain the exact semantic source identity;
        # this flag prevents consumers from mistaking HEAD for that identity.
        "source_dirty": _resolve_source_dirty(),
        "canonical_metadata": {
            "origin": (
                CANONICAL_CONTRACT_ORIGIN
                if enrichment_mode == NO_ENRICHMENT_MODE
                else None
            ),
            "compiled_at": (
                CANONICAL_CONTRACT_COMPILED_AT
                if enrichment_mode == NO_ENRICHMENT_MODE
                else None
            ),
        },
        "canonical_json": {
            "encoding": "utf-8",
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": False,
            "allow_nan": False,
        },
    }
    manifest["compiler_manifest_sha256"] = hashlib.sha256(
        canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    return manifest


def _resolve_source_revision() -> tuple[str | None, str | None]:
    return VENDORED_SOURCE_REVISION, "vendored_pin"


def _resolve_source_dirty() -> bool:
    # Verify bytes, not the host checkout or environment's build identity.
    manifest = json.loads((_REPO_ROOT / "vendor-manifest.json").read_text())
    return any(
        hashlib.sha256((_REPO_ROOT / entry["file"]).read_bytes()).hexdigest()
        != entry["vendored_sha256"]
        for entry in manifest["files"]
    )


__all__ = [
    "CANONICAL_CONTRACT_COMPILED_AT",
    "CANONICAL_CONTRACT_ORIGIN",
    "CONFIGURED_ENRICHMENT_MODE",
    "CONTRACT_COMPILER_REVISION",
    "CONTRACT_SCHEMA_VERSION",
    "CompilerEnrichmentMode",
    "NO_ENRICHMENT_MODE",
    "build_contract_compiler_manifest",
    "canonical_json",
    "resolve_configured_enrichment_identity",
]
