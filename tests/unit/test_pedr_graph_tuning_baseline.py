from datetime import date

from app.services.pedr.pragmatic import QueryIntent, get_pragmatic_service
from scripts.pedr_graph_tuning_baseline import (
    QuerySpec,
    dedupe_specs,
    filters_to_search_params,
    load_queries_from_file,
    select_diverse_queries,
)


def test_dedupe_specs_keeps_project_variants():
    specs = [
        QuerySpec(query="Find reports", filters={"project_id": "proj-a"}),
        QuerySpec(query="find   reports", filters={"project_id": "proj-b"}),
        QuerySpec(query="Find reports", filters={"project_id": "proj-a"}),
    ]

    deduped = dedupe_specs(specs)

    assert len(deduped) == 2
    assert deduped[0].filters["project_id"] == "proj-a"
    assert deduped[1].filters["project_id"] == "proj-b"


def test_select_diverse_queries_round_robin():
    specs = [
        QuerySpec(query="find documents about testing", filters={}),
        QuerySpec(query="create new project", filters={}),
        QuerySpec(query="update mission status", filters={}),
        QuerySpec(query="delete the report", filters={}),
        QuerySpec(query="run analysis", filters={}),
    ]

    selected = select_diverse_queries(specs, limit=5, seed=1)
    pragmatic = get_pragmatic_service()
    intents = {pragmatic.classify_intent(spec.query).intent for spec in selected}

    assert intents == {
        QueryIntent.SEARCH,
        QueryIntent.CREATE,
        QueryIntent.UPDATE,
        QueryIntent.DELETE,
        QueryIntent.EXECUTE,
    }


def test_filters_to_search_params_parses_dates_and_status():
    filters = {
        "project_id": "proj-1",
        "document_id": "doc-2",
        "date_from": "2025-01-02",
        "date_to": "bad-date",
        "status": ["complete"],
        "allow_pii": False,
        "element_types": ["mission"],
        "document_types": [],
        "source_types": None,
    }

    params = filters_to_search_params(filters)

    assert params["project_id"] == "proj-1"
    assert params["document_id"] == "doc-2"
    assert params["date_from"] == date(2025, 1, 2)
    assert "date_to" not in params
    assert params["status_filters"] == ["complete"]
    assert params["allow_pii"] is False
    assert params["element_types"] == ["mission"]
    assert "document_types" not in params


def test_load_queries_from_file_ignores_comments(tmp_path):
    path = tmp_path / "queries.txt"
    path.write_text("# comment\n query one \n\nquery two\n", encoding="utf-8")

    specs = load_queries_from_file(path)

    assert [spec.query for spec in specs] == ["query one", "query two"]
