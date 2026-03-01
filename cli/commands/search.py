"""Search and RAG query commands."""

import sys

import click

from cli.utils.api import APIClient
from cli.utils.errors import CLIError, format_error_human, format_error_json


@click.group()
def search():
    """Search documents."""
    pass


@search.command()
@click.argument("project_id")
@click.argument("query")
@click.option("--top-k", default=5, help="Number of results to return")
@click.pass_obj
def semantic(ctx, project_id, query, top_k):
    """Perform semantic search."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        with ctx.output.progress_spinner(f"Searching..."):
            results = client.post("/api/v1/search", data={
                "project_id": project_id,
                "query": query,
                "top_k": top_k
            })

        if ctx.json_mode:
            ctx.output.print_data(results)
        else:
            chunks = results.get("results", [])
            if not chunks:
                ctx.output.info("No results found")
            else:
                ctx.output.success(f"Found {len(chunks)} result(s):")
                for i, chunk in enumerate(chunks, 1):
                    score = chunk.get("score", 0)
                    content = chunk.get("content", "")[:200]
                    ctx.output.info(f"\n{i}. Score: {score:.3f}")
                    ctx.output.info(f"   {content}...")
                    ctx.output.info(f"   Chunk ID: {chunk.get('id')}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@click.group()
def rag():
    """RAG query commands."""
    pass


@rag.command()
@click.argument("project_id")
@click.argument("query")
@click.option("--model", default="gpt-5.1", help="LLM model to use")
@click.option("--top-k", default=5, help="Number of context chunks")
@click.pass_obj
def query(ctx, project_id, query, model, top_k):
    """Perform RAG query with LLM synthesis."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        with ctx.output.progress_spinner(f"Querying with {model}..."):
            results = client.post("/api/v1/rag/query", data={
                "project_id": project_id,
                "query": query,
                "model": model,
                "top_k": top_k
            })

        if ctx.json_mode:
            ctx.output.print_data(results)
        else:
            answer = results.get("answer", "No answer generated")
            citations = results.get("citations", [])

            ctx.output.success("Answer:")
            ctx.output.info(f"\n{answer}\n")

            if citations:
                ctx.output.info("\nCitations:")
                for i, citation in enumerate(citations, 1):
                    doc_name = citation.get("document_name", "Unknown")
                    chunk_id = citation.get("chunk_id")
                    ctx.output.info(f"  [{i}] {doc_name} (Chunk: {chunk_id})")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)
