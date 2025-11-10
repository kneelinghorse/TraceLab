"""Document management commands."""

import sys
import time
from pathlib import Path

import click

from cli.utils.api import APIClient
from cli.utils.errors import CLIError, ValidationError, format_error_human, format_error_json


@click.group()
def documents():
    """Manage documents."""
    pass


@documents.command()
@click.argument("project_id")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--process", is_flag=True, help="Process document after upload")
@click.option("--wait", is_flag=True, help="Wait for processing to complete (requires --process)")
@click.pass_obj
def upload(ctx, project_id, file_path, process, wait):
    """Upload a document."""
    try:
        file_path = Path(file_path)
        if not file_path.is_file():
            raise ValidationError(f"Not a file: {file_path}")

        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        # Upload document
        with ctx.output.progress_spinner(f"Uploading {file_path.name}..."):
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                params = {"project_id": project_id}
                document = client.post(f"/api/v1/documents/upload?project_id={project_id}", files=files)

        document_id = document["id"]

        # Process if requested
        if process:
            with ctx.output.progress_spinner(f"Processing document..."):
                result = client.post(f"/api/v1/documents/{document_id}/process")

            # Wait for completion if requested
            if wait:
                with ctx.output.progress_spinner("Waiting for processing..."):
                    while True:
                        doc = client.get(f"/api/v1/documents/{document_id}")
                        if doc.get("processed"):
                            break
                        time.sleep(2)

        if ctx.json_mode:
            ctx.output.print_data(document)
        else:
            ctx.output.success(f"Document uploaded: {document['name']} ({document_id})")
            if process:
                status = "completed" if wait else "processing"
                ctx.output.info(f"Processing status: {status}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@documents.command()
@click.argument("project_id")
@click.option("--status", type=click.Choice(["pending", "processing", "processed", "failed"]), help="Filter by status")
@click.pass_obj
def list(ctx, project_id, status):
    """List documents in a project."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        params = {"project_id": project_id}

        documents = client.get("/api/v1/documents", params=params)

        # Filter by status if specified
        if status:
            documents = [d for d in documents if d.get("validation_status") == status]

        if ctx.json_mode:
            ctx.output.print_data(documents)
        else:
            if not documents:
                ctx.output.info("No documents found")
            else:
                ctx.output.success(f"Found {len(documents)} document(s):")
                for doc in documents:
                    proc_status = "✓" if doc.get("processed") else "○"
                    ctx.output.info(f"  {proc_status} {doc['name']} ({doc['id']})")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@documents.command()
@click.argument("document_id")
@click.pass_obj
def get(ctx, document_id):
    """Get document by ID."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        document = client.get(f"/api/v1/documents/{document_id}")

        ctx.output.print_data(document)

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@documents.command()
@click.argument("document_id")
@click.option("--wait", is_flag=True, help="Wait for processing to complete")
@click.pass_obj
def process(ctx, document_id, wait):
    """Process a document."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        with ctx.output.progress_spinner(f"Processing document..."):
            result = client.post(f"/api/v1/documents/{document_id}/process")

        if wait:
            with ctx.output.progress_spinner("Waiting for completion..."):
                while True:
                    doc = client.get(f"/api/v1/documents/{document_id}")
                    if doc.get("processed"):
                        break
                    time.sleep(2)

        if ctx.json_mode:
            ctx.output.print_data(result)
        else:
            status = "completed" if wait else "processing"
            ctx.output.success(f"Document processing {status}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@documents.command()
@click.argument("document_id")
@click.pass_obj
def status(ctx, document_id):
    """Check document processing status."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        document = client.get(f"/api/v1/documents/{document_id}")

        status_info = {
            "document_id": document_id,
            "processed": document.get("processed", False),
            "chunked": document.get("chunked", False),
            "embedded": document.get("embedded", False),
            "validation_status": document.get("validation_status", "unknown")
        }

        if ctx.json_mode:
            ctx.output.print_data(status_info)
        else:
            ctx.output.info(f"Document: {document.get('name', document_id)}")
            ctx.output.info(f"  Processed: {'✓' if status_info['processed'] else '○'}")
            ctx.output.info(f"  Chunked: {'✓' if status_info['chunked'] else '○'}")
            ctx.output.info(f"  Embedded: {'✓' if status_info['embedded'] else '○'}")
            ctx.output.info(f"  Status: {status_info['validation_status']}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@documents.command()
@click.argument("document_id")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def delete(ctx, document_id, confirm):
    """Delete a document."""
    try:
        if not confirm and not ctx.json_mode:
            click.confirm(f"Are you sure you want to delete document {document_id}?", abort=True)

        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        client.delete(f"/api/v1/documents/{document_id}")

        if ctx.json_mode:
            ctx.output.success("Document deleted", data={"document_id": document_id})
        else:
            ctx.output.success(f"Document deleted: {document_id}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)

