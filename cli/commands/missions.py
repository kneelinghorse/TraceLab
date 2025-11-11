"""Mission management commands."""

import sys
from pathlib import Path

import click

from cli.utils.api import APIClient
from cli.utils.errors import CLIError, ValidationError, format_error_human, format_error_json


def _filename_from_disposition(disposition: str | None) -> str | None:
    if not disposition:
        return None
    parts = [segment.strip() for segment in disposition.split(";")]
    for part in parts:
        if part.lower().startswith("filename="):
            _, _, value = part.partition("=")
            return value.strip().strip('"\'')
    return None


@click.group()
def missions():
    """Manage research missions."""
    pass


@missions.command()
@click.argument("project_id")
@click.option("--status", type=click.Choice(["draft", "in_progress", "review", "complete"]), help="Filter by status")
@click.pass_obj
def list(ctx, project_id, status):
    """List missions in a project."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        params = {"project_id": project_id}

        missions = client.get("/api/v1/missions/", params=params)

        # Filter by status if specified
        if status:
            missions = [m for m in missions if m.get("mission_data", {}).get("status") == status]

        if ctx.json_mode:
            ctx.output.print_data(missions)
        else:
            if not missions:
                ctx.output.info("No missions found")
            else:
                ctx.output.success(f"Found {len(missions)} mission(s):")
                for mission in missions:
                    mission_data = mission.get("mission_data", {})
                    title = mission_data.get("title", "Untitled")
                    status = mission_data.get("status", "unknown")
                    progress = mission.get("completion_percentage", 0)
                    ctx.output.info(f"  [{status}] {title} ({progress}% complete) - {mission['id']}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command()
@click.argument("mission_id")
@click.pass_obj
def get(ctx, mission_id):
    """Get mission by ID."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        mission = client.get(f"/api/v1/missions/{mission_id}")

        ctx.output.print_data(mission)

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command()
@click.argument("project_id")
@click.option("--title", required=True, help="Mission title")
@click.option("--yaml", "yaml_file", type=click.Path(exists=True), help="Import from YAML file")
@click.pass_obj
def create(ctx, project_id, title, yaml_file):
    """Create a new mission."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        if yaml_file:
            # Import from YAML
            yaml_content = Path(yaml_file).read_text()
            data = {
                "project_id": project_id,
                "yaml_text": yaml_content,
                "promote_to_complete": False
            }
            with ctx.output.progress_spinner(f"Importing mission from {yaml_file}..."):
                result = client.post("/api/v1/missions/import", data=data)
            mission = result.get("mission", {})
        else:
            # Create basic mission
            mission_data = {
                "mission_id": f"M-{project_id[:8]}",
                "title": title,
                "status": "draft"
            }
            data = {
                "project_id": project_id,
                "mission_data": mission_data
            }
            with ctx.output.progress_spinner(f"Creating mission '{title}'..."):
                mission = client.post("/api/v1/missions/", data=data)

        if ctx.json_mode:
            ctx.output.print_data(mission)
        else:
            mission_id = mission.get("id")
            ctx.output.success(f"Mission created: {mission_id}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command(name="import")
@click.argument("project_id")
@click.argument("yaml_file", type=click.Path(exists=True))
@click.option("--promote", is_flag=True, help="Promote to complete state")
@click.pass_obj
def import_cmd(ctx, project_id, yaml_file, promote):
    """Import mission from YAML file."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        yaml_content = Path(yaml_file).read_text()
        data = {
            "project_id": project_id,
            "yaml_text": yaml_content,
            "promote_to_complete": promote
        }

        with ctx.output.progress_spinner(f"Importing mission from {yaml_file}..."):
            result = client.post("/api/v1/missions/import", data=data)

        mission = result.get("mission", {})

        if ctx.json_mode:
            ctx.output.print_data(mission)
        else:
            mission_id = mission.get("id")
            status = "complete" if promote else "draft"
            ctx.output.success(f"Mission imported: {mission_id} (status: {status})")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command()
@click.argument("mission_id")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "pdf", "docx", "yaml"]),
    default="md",
    help="Export format",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.pass_obj
def export(ctx, mission_id, fmt, output):
    """Export mission report."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        with ctx.output.progress_spinner(f"Exporting mission as {fmt}..."):
            if fmt == "yaml":
                payload = client.get(
                    f"/api/v1/missions/{mission_id}/export",
                    params={"format": fmt},
                )
            else:
                response = client.get_binary(
                    f"/api/v1/missions/{mission_id}/export",
                    params={"format": fmt},
                )

        if fmt == "yaml":
            yaml_text = payload.get("yaml_text", "")
            if output:
                destination = Path(output)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(yaml_text)
                if ctx.json_mode:
                    ctx.output.success("Export complete", data={"file": str(destination), "format": fmt})
                else:
                    ctx.output.success(f"YAML exported to: {destination}")
            else:
                if ctx.json_mode:
                    ctx.output.print_data({"format": fmt, "content": yaml_text})
                else:
                    print(yaml_text)
            return

        suggested_name = _filename_from_disposition(response.headers.get("content-disposition"))
        default_name = suggested_name or f"{mission_id}.{fmt}"

        if fmt == "md" and not output:
            markdown = response.content.decode("utf-8")
            if ctx.json_mode:
                ctx.output.print_data({"format": fmt, "content": markdown})
            else:
                print(markdown)
            return

        destination = Path(output or default_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)

        if ctx.json_mode:
            ctx.output.success("Export complete", data={"file": str(destination), "format": fmt})
        else:
            ctx.output.success(f"Report exported to: {destination}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command()
@click.argument("mission_id")
@click.argument("chunk_id")
@click.option("--note", help="Note about this evidence")
@click.pass_obj
def add_evidence(ctx, mission_id, chunk_id, note):
    """Add evidence chunk to mission."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        # Get current mission
        mission = client.get(f"/api/v1/missions/{mission_id}")
        mission_data = mission.get("mission_data", {})

        # Add evidence
        evidence = mission_data.get("evidence", [])
        new_evidence = {
            "chunk_id": chunk_id,
            "note": note or ""
        }
        evidence.append(new_evidence)
        mission_data["evidence"] = evidence

        # Update mission
        updated = client.put(f"/api/v1/missions/{mission_id}", data={"mission_data": mission_data})

        if ctx.json_mode:
            ctx.output.print_data(updated)
        else:
            ctx.output.success(f"Evidence added to mission: {chunk_id}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command()
@click.argument("mission_id")
@click.pass_obj
def validate(ctx, mission_id):
    """Run quality gates on mission."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        with ctx.output.progress_spinner("Running quality gates..."):
            result = client.get(f"/api/v1/missions/{mission_id}/quality")

        if ctx.json_mode:
            ctx.output.print_data(result)
        else:
            gates = result.get("gates", [])
            ctx.output.success(f"Quality gates: {len(gates)} checks")
            for gate in gates:
                name = gate.get("name", "unknown")
                status = gate.get("status", "unknown")
                icon = "✓" if status == "pass" else "✗"
                ctx.output.info(f"  {icon} {name}: {status}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@missions.command()
@click.argument("mission_id")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def delete(ctx, mission_id, confirm):
    """Delete a mission."""
    try:
        if not confirm and not ctx.json_mode:
            click.confirm(f"Are you sure you want to delete mission {mission_id}?", abort=True)

        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        client.delete(f"/api/v1/missions/{mission_id}")

        if ctx.json_mode:
            ctx.output.success("Mission deleted", data={"mission_id": mission_id})
        else:
            ctx.output.success(f"Mission deleted: {mission_id}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)
