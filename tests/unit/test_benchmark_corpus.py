from scripts.rag_baseline_benchmark import SOURCE_DOCS, build_corpus, build_queries


def test_benchmark_corpus_size(tmp_path) -> None:
    manifest = build_corpus(tmp_path, sources=SOURCE_DOCS, overwrite=True)
    assert manifest["document_count"] >= 50
    assert len(manifest["documents"]) >= 50

    queries = build_queries(sources=SOURCE_DOCS)["queries"]
    assert len(queries) >= 50


def test_benchmark_queries_reference_manifest(tmp_path) -> None:
    manifest = build_corpus(tmp_path, sources=SOURCE_DOCS, overwrite=True)
    doc_ids = {doc["doc_id"] for doc in manifest["documents"]}

    missing = []
    for query in build_queries(sources=SOURCE_DOCS)["queries"]:
        for entry in query.get("relevance", []):
            doc_id = entry.get("doc_id")
            if doc_id and doc_id not in doc_ids:
                missing.append(doc_id)

    assert not missing
