"""Prevent the research presentation contract from silently losing API fields."""

import importlib
import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import BaseModel

from app.schemas.evidence_ledger import LedgerDisposition
from app.schemas.mission import MissionStatus

CONTRACT = json.loads((Path(__file__).resolve().parents[2] / "cmos/contracts/oods-object-model.json").read_text())

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("name", CONTRACT["objects"])
def test_every_api_model_field_requires_an_explicit_presentation_mapping(name):
    """An API addition/removal/type change must trigger a reviewed mapping update."""
    entry = CONTRACT["objects"][name]
    module = importlib.import_module(entry["module"])
    models = {
        name: model
        for name, model in vars(module).items()
        if isinstance(model, type) and issubclass(model, BaseModel) and model.__module__ == module.__name__
    }
    assert set(models) == set(entry["schemas"])
    for model_name, model in models.items():
        mapped = entry["schemas"][model_name]
        assert set(model.model_fields) == set(mapped), model_name
        for field, info in model.model_fields.items():
            assert mapped[field]["annotation"] == str(info.annotation), (model_name, field)
            assert mapped[field]["mapping"].strip(), (model_name, field)


@pytest.mark.parametrize("model_path", CONTRACT["nested_schemas"])
def test_document_child_fields_are_not_lost_in_flat_object_mapping(model_path):
    module, _, name = model_path.rpartition(".")
    model = getattr(importlib.import_module(module), name)
    mapped = CONTRACT["nested_schemas"][model_path]
    assert {name: str(info.annotation) for name, info in model.model_fields.items()} == {
        name: info["annotation"] for name, info in mapped.items()
    }


def test_mission_and_evidence_vocabularies_match_the_server_without_billing_states():
    objects = CONTRACT["objects"]
    mission = objects["Mission"]
    states = next(trait["parameters"]["states"] for trait in mission["traits"] if trait["name"] == "lifecycle/Stateful")
    assert set(states) == set(get_args(MissionStatus))
    assert mission["fields"]["status"]["validation"]["enum"] == states
    evidence = objects["Evidence"]
    assert evidence["fields"]["disposition"]["validation"]["enum"] == list(get_args(LedgerDisposition))
    assert evidence["fields"]["primary_category_id"]["validation"]["enum"] == list(get_args(LedgerDisposition))
    assert all(trait["name"] != "lifecycle/Stateful" for trait in evidence["traits"])
    assert evidence["fields"]["source_sighting_count"]["validation"]["minimum"] == 1


def test_absent_ownership_is_not_made_required_and_chunks_stay_embedded():
    objects = CONTRACT["objects"]
    for name in ["Project", "Document", "Collection", "Mission", "Report", "Evidence"]:
        assert objects[name]["fields"]["owner_id"]["required"] is False
    assert objects["Chunk"]["contexts"] == ["inline"]
