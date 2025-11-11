"""Project management commands."""

import sys

import click

from cli.utils.api import APIClient
from cli.utils.errors import CLIError, format_error_human, format_error_json


@click.group()
def projects():
    """Manage projects."""
    pass


@projects.command()
@click.option("--page", default=1, show_default=True, type=int, help="Page number")
@click.option("--page-size", default=20, show_default=True, type=int, help="Results per page")
@click.option("--search", help="Filter by project name")
@click.pass_obj
def list(ctx, page, page_size, search):
    """List projects with pagination."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search

        response = client.get("/api/v1/projects", params=params)

        if ctx.json_mode:
            ctx.output.print_data(response)
            return

        projects = response.get("data", [])
        meta = response.get("pagination", {})
        total = meta.get("total", len(projects))

        if not projects:
            ctx.output.info("No projects found for the requested page")
            return

        ctx.output.success(
            f"Page {meta.get('page', page)} of {meta.get('pages', '?')} (total {total})"
        )
        for proj in projects:
            ctx.output.info(f"  - {proj['name']} ({proj['id']})")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@projects.command()
@click.argument("project_id")
@click.pass_obj
def get(ctx, project_id):
    """Get project by ID."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        project = client.get(f"/api/v1/projects/{project_id}")

        ctx.output.print_data(project)

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@projects.command()
@click.option("--name", required=True, help="Project name")
@click.option("--description", help="Project description")
@click.option("--research-type", type=click.Choice(["strategic", "tactical", "generative", "evaluative"]), help="Research type")
@click.pass_obj
def create(ctx, name, description, research_type):
    """Create a new project."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        data = {"name": name}
        if description:
            data["description"] = description
        if research_type:
            data["research_type"] = research_type

        with ctx.output.progress_spinner(f"Creating project '{name}'..."):
            project = client.post("/api/v1/projects", data=data)

        if ctx.json_mode:
            ctx.output.print_data(project)
        else:
            ctx.output.success(f"Project created: {project['name']} ({project['id']})")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@projects.command()
@click.argument("project_id")
@click.option("--name", help="New project name")
@click.option("--description", help="New project description")
@click.pass_obj
def update(ctx, project_id, name, description):
    """Update an existing project."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description

        if not data:
            ctx.output.error("No updates provided")
            sys.exit(2)

        project = client.put(f"/api/v1/projects/{project_id}", data=data)

        if ctx.json_mode:
            ctx.output.print_data(project)
        else:
            ctx.output.success(f"Project updated: {project['id']}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@projects.command()
@click.argument("project_id")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def delete(ctx, project_id, confirm):
    """Delete a project."""
    try:
        if not confirm and not ctx.json_mode:
            click.confirm(f"Are you sure you want to delete project {project_id}?", abort=True)

        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        client.delete(f"/api/v1/projects/{project_id}")

        if ctx.json_mode:
            ctx.output.success("Project deleted", data={"project_id": project_id})
        else:
            ctx.output.success(f"Project deleted: {project_id}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)
